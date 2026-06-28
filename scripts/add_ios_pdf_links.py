"""
Add a vault-relative PDF link (so iOS Obsidian can open the PDF) next to the
existing macOS-only file:// link in each note. Idempotent.

Existing line in notes:
    > 📄 [Open PDF locally](file:///Users/<u>/Zotero/storage/<KEY>/<filename>.pdf)

What this script adds (one line below):
    > 📱 [[pdfs/<KEY>/<filename>.pdf|Open PDF (iOS)]]

The Zotero-key folder layout (`pdfs/<KEY>/<filename>.pdf`) must already exist
inside the vault (e.g. copied by rsync from ~/Zotero/storage/).

Usage:
    python scripts/add_ios_pdf_links.py --vault /path/to/llm-wiki/sources [--dry-run]
"""

import argparse
import re
import sys
from pathlib import Path
from urllib.parse import unquote

from dotenv import load_dotenv

from vault_io import iter_markdown

load_dotenv()

# Match the file:// PDF link line. Captures KEY and filename.
FILE_LINK_RE = re.compile(
    r'^(?P<indent>>\s*)📄\s*\[Open PDF locally\]\(file://[^)]*?/Zotero/storage/(?P<key>[A-Z0-9]{8})/(?P<filename>[^)]+\.pdf)\)\s*$',
    re.MULTILINE,
)
# Idempotency marker — if this is already present immediately after the
# 📄 line, skip insertion.
IOS_MARKER = '📱'


def process_file(path: Path, dry_run: bool = False) -> str:
    """Returns 'changed' | 'skipped' | 'no-pdf-link' | 'already-has-ios'."""
    try:
        text = path.read_text(encoding='utf-8')
    except (UnicodeDecodeError, OSError):
        return 'skipped'

    matches = list(FILE_LINK_RE.finditer(text))
    if not matches:
        return 'no-pdf-link'

    # Build replacement: keep the file:// line, append an iOS line below
    new_text = text
    offset = 0
    inserted = 0
    skipped_existing = 0
    for m in matches:
        original_line = m.group(0)
        key = m.group('key')
        filename_url = m.group('filename')
        filename = unquote(filename_url)
        indent = m.group('indent')

        # Check what comes right after this line in the CURRENT text (using
        # adjusted offset for prior insertions)
        end_in_new = m.end() + offset
        # Peek at next 200 chars after the line — if it already contains
        # 📱 and the same key, skip
        peek = new_text[end_in_new: end_in_new + 200]
        if IOS_MARKER in peek.splitlines()[0] if peek.splitlines() else False:
            # Already has iOS line immediately after
            skipped_existing += 1
            continue
        # More robust: check that the very next non-empty line includes the
        # marker AND the key
        next_lines = peek.splitlines()[:3]
        already = False
        for nl in next_lines:
            if IOS_MARKER in nl and key in nl:
                already = True
                break
        if already:
            skipped_existing += 1
            continue

        # Insert iOS line right after the file:// line
        ios_line = f'\n{indent}{IOS_MARKER} [[pdfs/{key}/{filename}|Open PDF (iOS)]]'
        new_text = new_text[: end_in_new] + ios_line + new_text[end_in_new:]
        offset += len(ios_line)
        inserted += 1

    if inserted == 0:
        return 'already-has-ios' if skipped_existing else 'no-pdf-link'

    if not dry_run:
        tmp = path.with_suffix(path.suffix + '.ios-tmp')
        tmp.write_text(new_text, encoding='utf-8')
        tmp.replace(path)

    return 'changed'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        '--vault',
        default=str(Path.home() / 'Library/Mobile Documents/iCloud~md~obsidian/Documents/llm-wiki/llm-wiki/sources'),
        help='Root path of the vault subtree to update',
    )
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--limit', type=int, default=None)
    parser.add_argument('--verbose', '-v', action='store_true')
    args = parser.parse_args()

    root = Path(args.vault)
    if not root.exists():
        print(f'❌ Path does not exist: {root}', file=sys.stderr)
        sys.exit(2)

    print(f'📂 Scanning: {root}')

    md_files = sorted(iter_markdown(root))
    if args.limit:
        md_files = md_files[: args.limit]
    print(f'   Found {len(md_files)} markdown files')

    counts = {'changed': 0, 'skipped': 0, 'no-pdf-link': 0, 'already-has-ios': 0}
    for md in md_files:
        result = process_file(md, dry_run=args.dry_run)
        counts[result] = counts.get(result, 0) + 1
        if args.verbose and result == 'changed':
            print(f'   ✏️  {md.name}')

    action = 'would change' if args.dry_run else 'changed'
    print('\n' + '=' * 60)
    print(f'   ✅ {action}:               {counts["changed"]}')
    print(f'   ⏭️  already has iOS link:  {counts["already-has-ios"]}')
    print(f'   ➖ no file:// PDF link:    {counts["no-pdf-link"]}')
    print(f'   ❌ unreadable / skipped:   {counts["skipped"]}')
    print('=' * 60)


if __name__ == '__main__':
    main()
