"""
Inject Obsidian wiki-links into existing notes based on the OpenAlex reference
map. Updates two things per note (only if there are matched references):

  1. Frontmatter `related:` field — populated with [[stem]] wiki-links so the
     Obsidian graph view picks them up.
  2. Body section "📖 References in this vault" appended (or replaced if it
     already exists) listing each matched reference as a wiki-link.

Inputs:
  cache/doi_index.json    (built by build_doi_index.py)
  cache/reference_map.json (built by fetch_openalex_refs.py)

Idempotent: re-running detects existing "References in this vault" section by
HTML comment markers and replaces it cleanly.
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Dict, List

from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DOI_INDEX = ROOT / 'cache' / 'doi_index.json'
DEFAULT_REF_MAP = ROOT / 'cache' / 'reference_map.json'

SKIP_DIR_NAMES = {'_archived', '.obsidian', '.trash'}

FRONTMATTER_RE = re.compile(r'\A---\n(.*?)\n---\n', re.DOTALL)
RELATED_BLOCK_RE = re.compile(r'^related:\s*(\[\])?\s*(\n(?:[ \t]+-[^\n]*\n)*)?', re.MULTILINE)

SECTION_BEGIN = '<!-- references-in-vault:begin -->'
SECTION_END = '<!-- references-in-vault:end -->'
SECTION_RE = re.compile(
    re.escape(SECTION_BEGIN) + r'.*?' + re.escape(SECTION_END) + r'\n?',
    re.DOTALL,
)


def render_related_block(stems: List[str], indent: str = '  ') -> str:
    """Replace the entire related: block with a YAML list of [[wiki-links]]."""
    if not stems:
        return 'related: []\n'
    lines = ['related:']
    for stem in stems:
        # Escape any double quotes in stem (rare but defensive)
        s = stem.replace('"', '\\"')
        lines.append(f'{indent}- "[[{s}]]"')
    return '\n'.join(lines) + '\n'


def render_section(refs: List[dict]) -> str:
    """refs: list of dicts with 'stem' and 'doi'. Renders an empty-state line
    when refs is empty, so every note carries the section as a stable anchor.
    """
    lines = [SECTION_BEGIN, '## 📖 References in this vault', '']
    if refs:
        for r in refs:
            lines.append(f'- [[{r["stem"]}]]  *(doi: {r["doi"]})*')
    else:
        lines.append('_이 vault 내에 인용된 논문이 없습니다._')
    lines.append('')
    lines.append(SECTION_END)
    return '\n'.join(lines) + '\n'


def update_note(path: Path, related_stems: List[str], section_refs: List[dict], dry_run: bool = False, verbose: bool = False) -> bool:
    """Returns True if file was changed."""
    try:
        text = path.read_text(encoding='utf-8')
    except (UnicodeDecodeError, OSError) as e:
        print(f'   ⚠️  read failed for {path}: {e}', file=sys.stderr)
        return False

    fm_match = FRONTMATTER_RE.match(text)
    if not fm_match:
        return False
    frontmatter = fm_match.group(0)
    body = text[fm_match.end():]

    # Replace related: block in frontmatter
    related_match = RELATED_BLOCK_RE.search(frontmatter)
    new_related_block = render_related_block(related_stems)
    if related_match:
        new_frontmatter = (
            frontmatter[: related_match.start()]
            + new_related_block
            + frontmatter[related_match.end():]
        )
    else:
        # Insert before the closing ---
        new_frontmatter = frontmatter.rstrip('---\n').rstrip() + '\n' + new_related_block + '---\n'

    # Replace or append References-in-vault section. Always render — even
    # when section_refs is empty, the section emits a "no references" anchor
    # so every note carries a stable spot for future cross-links.
    new_section = render_section(section_refs)
    if SECTION_RE.search(body):
        new_body = SECTION_RE.sub(new_section, body, count=1)
    else:
        sep = '\n' if not body.endswith('\n') else ''
        sep2 = '' if body.endswith('\n\n') else '\n'
        new_body = body + sep + sep2 + '\n' + new_section

    new_text = new_frontmatter + new_body

    if new_text == text:
        return False

    if verbose or dry_run:
        print(f'\n📝 {path.name}')
        print(f'   related: {len(related_stems)} links')
        print(f'   section: {len(section_refs)} entries')

    if not dry_run:
        tmp = path.with_suffix(path.suffix + '.ref-tmp')
        tmp.write_text(new_text, encoding='utf-8')
        tmp.replace(path)

    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--doi-index', default=str(DEFAULT_DOI_INDEX))
    parser.add_argument('--ref-map', default=str(DEFAULT_REF_MAP))
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--verbose', '-v', action='store_true')
    parser.add_argument('--limit', type=int, default=None, help='Process only first N source DOIs')
    args = parser.parse_args()

    doi_index_path = Path(args.doi_index)
    ref_map_path = Path(args.ref_map)
    if not doi_index_path.exists():
        print(f'❌ Missing {doi_index_path} — run build_doi_index.py first', file=sys.stderr)
        sys.exit(2)
    if not ref_map_path.exists():
        print(f'❌ Missing {ref_map_path} — run fetch_openalex_refs.py first', file=sys.stderr)
        sys.exit(2)

    doi_index: Dict[str, dict] = json.loads(doi_index_path.read_text(encoding='utf-8'))
    ref_map: Dict[str, List[str]] = json.loads(ref_map_path.read_text(encoding='utf-8'))

    print(f'📚 Vault papers: {len(doi_index)}')
    print(f'🔗 Reference map: {len(ref_map)}')

    # Iterate every vault paper (not just papers in ref_map) so every note
    # gets the section — including new papers OpenAlex hasn't indexed yet
    # and papers whose references don't overlap the vault.
    source_dois = list(doi_index.keys())
    if args.limit:
        source_dois = source_dois[: args.limit]

    changed = 0
    matched_total = 0
    no_match = 0

    archived_skipped = 0
    for src_doi in source_dois:
        src_rec = doi_index[src_doi]
        src_path = Path(src_rec['path'])
        if not src_path.exists():
            continue
        # Skip archived/system paths defensively (even if index was built without filter)
        if any(part in SKIP_DIR_NAMES for part in src_path.parts):
            archived_skipped += 1
            continue
        ref_dois = ref_map.get(src_doi, []) or []
        matches = []
        seen_stems = set()
        for r_doi in ref_dois:
            if r_doi == src_doi:
                continue  # skip self-reference, just in case
            r_rec = doi_index.get(r_doi)
            if not r_rec:
                continue
            stem = r_rec['stem']
            if stem in seen_stems:
                continue
            seen_stems.add(stem)
            matches.append({'stem': stem, 'doi': r_doi})
        if not matches:
            no_match += 1
            # Still inject the empty-state section so every note has a stable
            # anchor — the section renders the "no references" placeholder.
        # Sort references alphabetically by stem so the section is stable
        matches.sort(key=lambda m: m['stem'].lower())
        related_stems = [m['stem'] for m in matches]
        if update_note(src_path, related_stems, matches, dry_run=args.dry_run, verbose=args.verbose):
            changed += 1
            matched_total += len(matches)

    action = 'would update' if args.dry_run else 'updated'
    print('\n' + '=' * 60)
    print(f'   ✅ {action}:            {changed}')
    print(f'   ➖ no matched refs:     {no_match}')
    print(f'   🗄️  archived skipped:   {archived_skipped}')
    print(f'   🔗 total wiki-links:    {matched_total}')
    if changed:
        print(f'   🧮 avg links per note:  {matched_total / changed:.1f}')
    print('=' * 60)


if __name__ == '__main__':
    main()
