"""
Scan the Obsidian vault for notes whose TITLE strongly suggests a review/survey
but whose body was NOT rendered with the review template — i.e. they were
under-classified as computational/experimental.

Logic:
  1. Walk vault for *.md (skip _archived/, .obsidian/, .trash/).
  2. Parse frontmatter `title:` field.
  3. Match title against strong review patterns:
        'A Survey', 'A Review', 'Survey of', 'Survey on',
        'Systematic Review', 'Systematic Survey',
        'Meta-Analysis', 'Meta Analysis', 'Meta-Review',
        'Literature Review', 'Narrative Review',
        'Scoping Review', 'Umbrella Review',
        'Comprehensive Review', 'Comprehensive Survey',
        'Patent Review',
  4. Check body for review template markers:
        '## 1. 리뷰 개요'                  (legacy)
        '## 1. 리뷰 주제·동기·범위'         (new)
        '리뷰 주제와 목적'                  (legacy bullet)
        '## 1. 리뷰 주제 동기 범위'         (variant)
  5. If title is a strong-review match AND no review marker present → candidate.

Output: a text file with absolute paths, one per line, ready to be fed to
        reprocess_review_notes.py via --list-file.
"""

import argparse
import os
import re
import sys
from pathlib import Path
from typing import List, Optional

from dotenv import load_dotenv

load_dotenv()

FRONTMATTER_RE = re.compile(r'\A---\n(.*?)\n---\n', re.DOTALL)
TITLE_LINE_RE = re.compile(r'^title:\s*"?([^"\n]*)"?\s*$', re.MULTILINE)

# Title patterns that strongly indicate a review/survey.
# Designed to be HIGH-PRECISION: prefer false-negatives over false-positives.
STRONG_REVIEW_TITLE_PATTERNS = [
    re.compile(r'\b(?:a|the)?\s*survey(?:\s+of|\s+on|:|\s+paper)', re.IGNORECASE),
    re.compile(r':\s*a\s+survey\b', re.IGNORECASE),
    re.compile(r':\s*a\s+review\b', re.IGNORECASE),
    re.compile(r'\bsystematic\s+(?:review|survey)\b', re.IGNORECASE),
    re.compile(r'\bmeta[-\s]?analysis\b', re.IGNORECASE),
    re.compile(r'\bmeta[-\s]?review\b', re.IGNORECASE),
    re.compile(r'\bliterature\s+review\b', re.IGNORECASE),
    re.compile(r'\bnarrative\s+review\b', re.IGNORECASE),
    re.compile(r'\bscoping\s+review\b', re.IGNORECASE),
    re.compile(r'\bumbrella\s+review\b', re.IGNORECASE),
    re.compile(r'\bcomprehensive\s+(?:review|survey)\b', re.IGNORECASE),
    re.compile(r'\bpatent\s+review\b', re.IGNORECASE),
]

# Anti-patterns that override the strong match — papers titled "X prediction
# with deep learning A comprehensive review" are sometimes method papers, but
# also sometimes genuine reviews; we still flag for re-classification so the
# LLM can decide.
# (We don't add anti-patterns here — the classifier will make the final call.)

REVIEW_BODY_MARKERS = [
    '## 1. 리뷰 개요',
    '## 1. 리뷰 주제·동기·범위',
    '## 1. 리뷰 주제 동기 범위',
    '- 리뷰 주제와 목적',
]

SKIP_DIR_NAMES = {'_archived', '.obsidian', '.trash', '.smart-env'}


def is_skipped(path: Path, root: Path) -> bool:
    try:
        rel_parts = path.relative_to(root).parts
    except ValueError:
        return True
    return any(part in SKIP_DIR_NAMES for part in rel_parts)


def extract_title(text: str) -> Optional[str]:
    m = FRONTMATTER_RE.match(text)
    if not m:
        return None
    fm = m.group(1)
    t = TITLE_LINE_RE.search(fm)
    if not t:
        return None
    return t.group(1).strip()


def title_is_strong_review(title: str) -> bool:
    if not title:
        return False
    return any(p.search(title) for p in STRONG_REVIEW_TITLE_PATTERNS)


def body_has_review_template(body: str) -> bool:
    return any(marker in body for marker in REVIEW_BODY_MARKERS)


def scan(root: Path) -> List[Path]:
    candidates: List[Path] = []
    for md in root.rglob('*.md'):
        if is_skipped(md, root):
            continue
        try:
            text = md.read_text(encoding='utf-8', errors='replace')
        except Exception:
            continue
        title = extract_title(text)
        if not title or not title_is_strong_review(title):
            continue
        # Strong-review title — check current template
        if body_has_review_template(text):
            continue  # already using review template
        candidates.append(md)
    return candidates


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    default_root = os.getenv(
        'OUTPUT_DIR',
        str(Path.home() / 'Library/Mobile Documents/iCloud~md~obsidian/Documents/fourmodern/80. References/81. zotero'),
    )
    parser.add_argument('--path', default=default_root, help='Vault root')
    parser.add_argument('--output', default='cache/under_classified_reviews.txt',
                        help='Output list path (one absolute path per line)')
    parser.add_argument('--verbose', action='store_true')
    args = parser.parse_args()

    root = Path(args.path)
    if not root.exists():
        print(f'❌ Vault not found: {root}', file=sys.stderr)
        sys.exit(2)

    print(f'📂 Scanning: {root}')
    candidates = scan(root)
    print(f'   Under-classified review candidates: {len(candidates)}')

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        '\n'.join(str(p) for p in candidates) + '\n' if candidates else '',
        encoding='utf-8',
    )
    print(f'💾 Wrote: {out}')

    if args.verbose:
        print('\nFirst 20 candidates:')
        for c in candidates[:20]:
            print(f'  {c.name}')


if __name__ == '__main__':
    main()
