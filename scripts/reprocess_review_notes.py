"""
Re-process Obsidian notes that were summarized with the legacy review template.

Workflow per note:
  1. Find notes whose body contains '## 1. 리뷰 개요' (legacy review structure).
  2. Parse existing frontmatter for metadata (title, authors, doi, etc.).
  3. Extract pdf_path from the body (look for 'Open PDF locally' line).
  4. Re-extract text from the PDF (text-only — images already on disk).
  5. Re-classify with folder_hint = collection path. Misclassified prediction /
     method papers move from 'review' → 'computational' / 'experimental'.
  6. Generate fresh short/long/contribution/limitations/ideas summaries using
     the new improved review prompt (or the appropriate type-specific prompt).
  7. Re-render the markdown with preserved:
        - related: block (cross-links built by inject_references)
        - <!-- references-in-vault:begin/end --> body section
        - featured_image relative path (if present)
        - tags / collections / keywords from existing frontmatter
  8. Atomic write back to the same path.

Parallel: ThreadPoolExecutor with N workers (default 5). Each worker does its
own OpenAI API calls — the existing rate-limit handling in gpt_summarizer
applies.

Usage:
    python scripts/reprocess_review_notes.py --dry-run --limit 3
    python scripts/reprocess_review_notes.py --workers 5
    python scripts/reprocess_review_notes.py --workers 5 --limit 50
"""

import argparse
import json
import os
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from dotenv import load_dotenv
from tqdm import tqdm

load_dotenv()

# Make scripts dir importable
SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from text_extractor import extract_text_from_pdf, extract_text_and_images
from gpt_summarizer import (
    classify_paper_type_llm,
    get_prompts_for_paper_type,
    summarize_text_with_retry,
    summarize_text_with_images_retry,
    generate_sections,
    SummarizationFailed,
)
from markdown_writer import render_note
from vault_io import iter_markdown

# --- Markers / parsers --------------------------------------------------------

LEGACY_REVIEW_MARKERS = [
    '## 1. 리뷰 개요',  # old review template heading (exact)
    '- 리뷰 주제와 목적',  # old review template bullet (with dash prefix)
    # Older review-variant (pre-legacy): uses '## 1. 논문 개요' + '## 2. 주요 분류 체계'
    '## 2. 주요 분류 체계',
    '## 1. 논문 개요',
    # AI self-acknowledgment phrase (when review template was forced on a non-review)
    '리뷰/서베이가 아니라',
]

FRONTMATTER_RE = re.compile(r'\A---\n(.*?)\n---\n', re.DOTALL)
PDF_LINK_RE = re.compile(
    # `.*?\.pdf` instead of `[^)]+` so filenames with embedded parens
    # (e.g. "Antibody-Drug Conjugates (ADCs).pdf") match the whole path.
    r'\[Open PDF locally\]\(file://(.*?\.pdf)\)'
)
FEATURED_IMG_RE = re.compile(
    r'## 🎯 핵심 그림\s*\n\s*!\[\[([^\]]+)\]\]\s*\n\s*> \*\*([^*]+)\*\* - 페이지 (\d+) \((\d+)×(\d+)px\)',
    re.MULTILINE,
)
RELATED_BLOCK_RE = re.compile(
    r'^related:\s*(\[\])?\s*(\n(?:[ \t]+-[^\n]*\n)*)?',
    re.MULTILINE,
)
REF_SECTION_BEGIN = '<!-- references-in-vault:begin -->'
REF_SECTION_END = '<!-- references-in-vault:end -->'
REF_SECTION_RE = re.compile(
    re.escape(REF_SECTION_BEGIN) + r'.*?' + re.escape(REF_SECTION_END) + r'\n?',
    re.DOTALL,
)
IOS_PDF_LINE_RE = re.compile(r'^> 📱 \[\[pdfs/[^\]]+\]\]\s*$', re.MULTILINE)
KEY_FROM_STEM_RE = re.compile(r'_([A-Z0-9]{8})$')
TAG_LINE_RE = re.compile(r'^(\s*-\s+"?)([^"\n]+)("?)\s*$')


def is_legacy_review(text: str) -> bool:
    for marker in LEGACY_REVIEW_MARKERS:
        if marker in text:
            return True
    return False


def parse_simple_yaml(fm_text: str) -> Dict:
    """Very loose YAML parser sufficient for our frontmatter shape.

    Handles: scalar key, multi-line list (- item) blocks, quoted strings.
    Does NOT support nested mappings (we don't have any in this template).
    """
    out: Dict = {}
    current_key: Optional[str] = None
    current_list: Optional[List] = None

    for raw_line in fm_text.splitlines():
        line = raw_line.rstrip('\n')
        if not line.strip():
            continue
        # List item under the current key
        m_item = re.match(r'^(\s+)-\s+(.*)$', line)
        if m_item and current_list is not None:
            val = m_item.group(2).strip()
            # Strip surrounding quotes
            if (val.startswith('"') and val.endswith('"')) or \
               (val.startswith("'") and val.endswith("'")):
                val = val[1:-1]
            current_list.append(val)
            continue

        # New top-level key
        m_kv = re.match(r'^([A-Za-z_][\w-]*)\s*:\s*(.*)$', line)
        if not m_kv:
            continue
        key, val = m_kv.group(1), m_kv.group(2).strip()
        if val == '' or val is None:
            # Could be a list header or null
            current_key = key
            current_list = []
            out[key] = current_list
            continue
        if val == '[]':
            out[key] = []
            current_key = key
            current_list = None
            continue
        # Scalar value (quoted)
        if (val.startswith('"') and val.endswith('"')) or \
           (val.startswith("'") and val.endswith("'")):
            val = val[1:-1]
        out[key] = val
        current_key = key
        current_list = None

    # Strip empty trailing lists
    for k in list(out.keys()):
        if isinstance(out[k], list) and not out[k]:
            # Preserve null/empty intent
            pass

    return out


def extract_pdf_path(body: str) -> Optional[str]:
    m = PDF_LINK_RE.search(body)
    if not m:
        return None
    return m.group(1)


def extract_featured_image(body: str) -> Optional[Dict]:
    m = FEATURED_IMG_RE.search(body)
    if not m:
        return None
    return {
        'relative_path': m.group(1),
        'selection_reason': m.group(2).strip(),
        'page': int(m.group(3)),
        'width': int(m.group(4)),
        'height': int(m.group(5)),
        'filename': Path(m.group(1)).name,
    }


def extract_related_lines(frontmatter: str) -> str:
    """Return the entire related: block as it appears in the frontmatter."""
    m = RELATED_BLOCK_RE.search(frontmatter)
    if not m:
        return 'related: []\n'
    return m.group(0)


def extract_ref_section(body: str) -> Optional[str]:
    m = REF_SECTION_RE.search(body)
    if not m:
        return None
    return m.group(0)


def collection_path_from_file(path: Path, vault_root: Path) -> str:
    try:
        rel = path.relative_to(vault_root)
    except ValueError:
        return ''
    parts = rel.parts[:-1]  # drop the filename
    return '/'.join(parts)


def normalize_paper_dict(fm: Dict, body: str, vault_root: Path, file_path: Path) -> Dict:
    """Build the dict consumed by render_note() from frontmatter + body."""
    paper = dict(fm)  # shallow copy

    # Ensure types are correct
    if 'tags' in paper and isinstance(paper['tags'], list):
        # tags are user-managed via collection_to_tags filter; we'll re-derive
        pass
    if 'keywords' in paper and not isinstance(paper.get('keywords'), list):
        # keywords need to be a list for the template
        kws = paper.get('keywords')
        if isinstance(kws, str) and kws.strip():
            paper['keywords'] = [kw.strip() for kw in kws.split(',') if kw.strip()]
        else:
            paper['keywords'] = []

    if 'collections' in paper and not isinstance(paper['collections'], list):
        paper['collections'] = [paper['collections']]

    if 'authors' in paper and not isinstance(paper['authors'], list):
        paper['authors'] = [paper['authors']]

    # title / journal etc are scalars

    # PDF path (preserve absolute file:// link)
    pdf_path = extract_pdf_path(body)
    if pdf_path:
        paper['pdf_path'] = f"file://{pdf_path}"

    # Featured image
    feat = extract_featured_image(body)
    if feat:
        paper['featured_image'] = feat
    else:
        paper['featured_image'] = None

    # Abstract: try to find existing `> [!Abstract]` block
    abstract_match = re.search(
        r'^> \[!Abstract\]\s*\n((?:>[^\n]*\n)+)', body, re.MULTILINE,
    )
    if abstract_match:
        abs_lines = abstract_match.group(1).splitlines()
        abstract = '\n'.join(re.sub(r'^>\s?', '', line) for line in abs_lines).strip()
        paper['abstract'] = abstract
    else:
        paper.setdefault('abstract', '')

    # date: keep original, do not bump (template uses `date | default('now')`)
    if 'date' not in paper or not paper.get('date'):
        paper['date'] = datetime.now().strftime('%Y-%m-%d')

    # Key
    stem = file_path.stem
    key_match = KEY_FROM_STEM_RE.search(stem)
    if key_match:
        paper['key'] = key_match.group(1)

    # Empty defaults for fields the template references
    paper.setdefault('figure_captions', [])
    paper.setdefault('table_captions', [])
    paper.setdefault('annotations', [])
    paper.setdefault('extracted_images', [])
    paper.setdefault('image_captions', [])
    paper.setdefault('publisher', '')
    paper.setdefault('volume', '')
    paper.setdefault('issue', '')
    paper.setdefault('pages', '')
    paper.setdefault('itemType', 'journalArticle')
    paper.setdefault('bibliography', '')

    # zotero_link / zotero_app_link: rebuild from user_id + key
    user_id = os.getenv('ZOTERO_USER_ID', '')
    if user_id and paper.get('key'):
        paper['zotero_link'] = f"https://www.zotero.org/users/{user_id}/items/{paper['key']}"
        paper['zotero_app_link'] = f"zotero://select/items/0_{paper['key']}"
    else:
        # Try to recover from existing body
        zw = re.search(r'\[Open in Zotero Web Library\]\((https://www\.zotero\.org/[^)]+)\)', body)
        za = re.search(r'\[Open in Zotero Desktop\]\((zotero://[^)]+)\)', body)
        if zw:
            paper['zotero_link'] = zw.group(1)
        if za:
            paper['zotero_app_link'] = za.group(1)

    paper.setdefault('citekey', paper.get('key', ''))
    return paper


# --- Re-write logic -----------------------------------------------------------

def reinject_related_and_ref_section(new_text: str, old_related_block: str,
                                     old_ref_section: Optional[str]) -> str:
    """Replace render_note's default related:/ref section with preserved ones."""
    # Replace related: block in new_text frontmatter
    fm_match = FRONTMATTER_RE.match(new_text)
    if not fm_match:
        return new_text
    fm = fm_match.group(0)
    body = new_text[fm_match.end():]

    new_related_block = old_related_block if old_related_block.endswith('\n') else old_related_block + '\n'
    rel_match = RELATED_BLOCK_RE.search(fm)
    if rel_match:
        fm_new = fm[:rel_match.start()] + new_related_block + fm[rel_match.end():]
    else:
        # Insert before closing '---'
        fm_new = fm.rstrip('\n').rstrip('-').rstrip('\n')
        fm_new = fm_new + '\n' + new_related_block + '---\n'

    # Append reference section to body (after stripping any existing one)
    body_clean = REF_SECTION_RE.sub('', body)
    if old_ref_section:
        if not body_clean.endswith('\n'):
            body_clean += '\n'
        body_clean = body_clean.rstrip() + '\n\n' + old_ref_section
        if not body_clean.endswith('\n'):
            body_clean += '\n'

    return fm_new + body_clean


# --- Per-note pipeline --------------------------------------------------------

class NoteProcessor:
    def __init__(self, vault_root: Path, dry_run: bool = False,
                 force_review: bool = False, verbose: bool = False,
                 multimodal: bool = False):
        self.vault_root = vault_root
        self.dry_run = dry_run
        self.force_review = force_review
        self.verbose = verbose
        self.multimodal = multimodal
        self.stats_lock = threading.Lock()
        self.stats = {
            'processed': 0,
            'reclassified': {'review': 0, 'computational': 0, 'experimental': 0},
            'errors': 0,
            'skipped_no_pdf': 0,
            'skipped_short_text': 0,
        }

    def _bump(self, key: str, sub: Optional[str] = None):
        with self.stats_lock:
            if sub is None:
                self.stats[key] = self.stats.get(key, 0) + 1
            else:
                self.stats[key][sub] = self.stats[key].get(sub, 0) + 1

    def process_one(self, path: Path) -> Tuple[Path, bool, Optional[str]]:
        try:
            raw = path.read_text(encoding='utf-8')
        except Exception as e:
            return path, False, f'read error: {e}'

        fm_match = FRONTMATTER_RE.match(raw)
        if not fm_match:
            return path, False, 'no frontmatter'
        fm_text = fm_match.group(1)
        body = raw[fm_match.end():]

        # Preserve old artifacts
        old_related_block = extract_related_lines(fm_match.group(0))
        old_ref_section = extract_ref_section(body)

        fm = parse_simple_yaml(fm_text)
        title = fm.get('title') or path.stem

        # PDF path
        pdf_path_str = extract_pdf_path(body)
        if not pdf_path_str or not os.path.exists(pdf_path_str):
            self._bump('skipped_no_pdf')
            return path, False, f'pdf missing: {pdf_path_str}'

        # Re-extract text from PDF (and images if multimodal)
        images: List[Dict] = []
        try:
            if self.multimodal:
                # Extract to a tmp dir so we don't churn the iCloud img/ folder;
                # the markdown's existing featured_image link is preserved separately.
                import tempfile
                tmp_dir = tempfile.mkdtemp(prefix='reproc_img_')
                text, images, _captions, _featured = extract_text_and_images(
                    pdf_path_str, output_dir=tmp_dir,
                )
            else:
                text = extract_text_from_pdf(pdf_path_str)
        except Exception as e:
            return path, False, f'pdf extract error: {e}'

        if not text or len(text.strip()) < 500:
            self._bump('skipped_short_text')
            return path, False, f'extracted text too short ({len(text or "")} chars)'

        # Truncate to ~30k chars (matches existing pipeline)
        if len(text) > 30000:
            text = text[:30000]

        # Folder hint
        folder_hint = collection_path_from_file(path, self.vault_root)

        # Classify
        if self.force_review:
            paper_type = 'review'
        else:
            try:
                paper_type = classify_paper_type_llm(
                    text, title, use_cache=True, folder_hint=folder_hint
                )
            except Exception:
                paper_type = 'review'  # default to review since legacy was review

        self._bump('reclassified', paper_type)
        if self.verbose:
            print(f'  📄 {path.name[:60]}... → {paper_type}')

        # Generate summaries
        short_prompt, long_prompt = get_prompts_for_paper_type(paper_type, title)
        model = os.getenv('MODEL', 'gpt-5.2-pro')
        short_tokens = 1200
        long_tokens = 9000 if paper_type == 'review' else 6000

        try:
            if self.multimodal and images:
                # Multimodal: send up to 3 images alongside text
                short = summarize_text_with_images_retry(
                    text, images, short_prompt, model=model,
                    max_tokens=short_tokens, use_optimizer=True,
                )
                long = summarize_text_with_images_retry(
                    text, images, long_prompt, model=model,
                    max_tokens=long_tokens, use_optimizer=True,
                )
            else:
                short = summarize_text_with_retry(
                    text, short_prompt, model=model,
                    max_tokens=short_tokens, use_optimizer=True,
                )
                long = summarize_text_with_retry(
                    text, long_prompt, model=model,
                    max_tokens=long_tokens, use_optimizer=True,
                )
            contribution, limitations, ideas, keywords_raw = generate_sections(
                text, title, use_optimizer=True,
            )
        except SummarizationFailed as e:
            return path, False, f'summarization failed: {e}'
        except Exception as e:
            return path, False, f'summarization error: {e}'

        # Parse keywords
        if isinstance(keywords_raw, str):
            if ',' in keywords_raw:
                kws = [kw.strip() for kw in keywords_raw.strip().split(',') if kw.strip()]
            elif '\n' in keywords_raw:
                kws = [kw.strip() for kw in keywords_raw.strip().split('\n') if kw.strip()]
            else:
                kws = [keywords_raw.strip()] if keywords_raw.strip() else []
        else:
            kws = keywords_raw if isinstance(keywords_raw, list) else []

        # Build context for render_note
        paper = normalize_paper_dict(fm, body, self.vault_root, path)
        paper['short_summary'] = short
        paper['long_summary'] = long
        paper['contribution'] = contribution
        paper['limitations'] = limitations
        paper['ideas'] = ideas
        if kws:
            paper['keywords'] = kws

        try:
            rendered = render_note('literature_note.md', paper)
        except Exception as e:
            return path, False, f'render error: {e}'

        # Restore preserved fields
        final = reinject_related_and_ref_section(rendered, old_related_block, old_ref_section)

        # Re-add iOS PDF link line under the macOS PDF link (matches add_ios_pdf_links output)
        # (Cheaper to just run add_ios_pdf_links.py once at the end of the batch.)

        if self.dry_run:
            self._bump('processed')
            return path, True, 'dry-run (no write)'

        # Atomic write
        tmp = path.with_suffix(path.suffix + '.tmp')
        try:
            tmp.write_text(final, encoding='utf-8')
            tmp.replace(path)
        except Exception as e:
            return path, False, f'write error: {e}'

        self._bump('processed')
        return path, True, paper_type


# --- Discovery ----------------------------------------------------------------

def find_legacy_review_notes(vault_root: Path) -> List[Path]:
    out: List[Path] = []
    for md in iter_markdown(vault_root):
        try:
            head = md.read_text(encoding='utf-8', errors='replace')
        except Exception:
            continue
        if is_legacy_review(head):
            out.append(md)
    return out


# --- CLI ---------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    default_root = os.getenv(
        'OUTPUT_DIR',
        str(Path.home() / 'ObsidianVault' / 'LiteratureNotes'),
    )
    parser.add_argument('--path', default=default_root, help='Vault root')
    parser.add_argument('--workers', type=int, default=5, help='Parallel workers (default 5)')
    parser.add_argument('--limit', type=int, help='Process at most N notes')
    parser.add_argument('--dry-run', action='store_true', help='Do not write files')
    parser.add_argument('--force-review', action='store_true',
                        help='Skip reclassification and force review template')
    parser.add_argument('--multimodal', action='store_true',
                        help='Extract images and send them to vision-capable GPT-5.x')
    parser.add_argument('--verbose', action='store_true')
    parser.add_argument('--file', help='Process only this single note (absolute path)')
    parser.add_argument('--list-file',
                        help='File listing paths to process (one per line; overrides discovery)')
    args = parser.parse_args()

    vault_root = Path(args.path)
    if not vault_root.exists():
        print(f'❌ Vault not found: {vault_root}', file=sys.stderr)
        sys.exit(2)

    # Discover notes
    if args.file:
        notes = [Path(args.file)]
    elif args.list_file:
        with open(args.list_file, 'r', encoding='utf-8') as f:
            notes = [Path(line.strip()) for line in f if line.strip() and not line.startswith('#')]
    else:
        print(f'🔍 Scanning {vault_root} for legacy review-template notes...')
        notes = find_legacy_review_notes(vault_root)
        print(f'   Found: {len(notes)}')

    if args.limit:
        notes = notes[:args.limit]
        print(f'   Limiting to first {len(notes)}')

    if not notes:
        print('Nothing to do.')
        return

    processor = NoteProcessor(
        vault_root=vault_root,
        dry_run=args.dry_run,
        force_review=args.force_review,
        verbose=args.verbose,
        multimodal=args.multimodal,
    )

    errors: List[Tuple[str, str]] = []
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=args.workers) as pool, \
         tqdm(total=len(notes), desc='Re-processing', unit='note') as pbar:
        futures = {pool.submit(processor.process_one, n): n for n in notes}
        for fut in as_completed(futures):
            path, ok, msg = fut.result()
            if not ok:
                errors.append((str(path), msg or 'unknown'))
                processor._bump('errors')
            pbar.set_postfix_str(f'errors={len(errors)}')
            pbar.update(1)

    elapsed = time.time() - t0
    print()
    print('=' * 60)
    print(f'Done in {elapsed:.1f}s ({elapsed/60:.1f} min)')
    print(json.dumps(processor.stats, indent=2, ensure_ascii=False))
    if errors:
        print(f'\n❌ Errors ({len(errors)}):')
        for p, m in errors[:30]:
            print(f'  - {Path(p).name}: {m}')
        log_path = Path('logs') / f'reprocess_review_errors_{datetime.now():%Y%m%d_%H%M%S}.log'
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text(
            '\n'.join(f'{p}\t{m}' for p, m in errors), encoding='utf-8',
        )
        print(f'   Full list: {log_path}')


if __name__ == '__main__':
    main()
