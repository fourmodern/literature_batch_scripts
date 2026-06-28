"""
Retroactively rewrite the `tags:` block in existing Obsidian literature notes
so they use the new exploded-collection-hierarchy format.

What it does for every .md file under the vault output dir:
  1. Read YAML frontmatter (between the first pair of `---`).
  2. Read the `collections:` field (Zotero collection paths).
  3. Compute the new tag list via markdown_writer.collections_to_tags().
  4. Remove the OLD single-slug collection tag (e.g.
     "000.papers-600.geninus-615.foundation_model-6151.hist_st") if present.
  5. Keep everything else: literature, ai-summary, keyword tags, and any
     manually-added tags.
  6. Rewrite ONLY the `tags:` block; leave the rest of the file untouched.

Idempotent: running it twice produces the same output as running it once.

Usage:
    python scripts/retag_existing_notes.py --dry-run        # preview
    python scripts/retag_existing_notes.py                  # apply
    python scripts/retag_existing_notes.py --limit 5        # apply on 5 files
    python scripts/retag_existing_notes.py --path /some/dir # custom root
"""

import argparse
import os
import re
import sys
from pathlib import Path
from typing import List, Optional, Tuple

from dotenv import load_dotenv

load_dotenv()

# Allow `from markdown_writer import ...` whether run from repo root or scripts/
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from markdown_writer import collections_to_tags  # noqa: E402
from vault_io import iter_markdown, split_frontmatter  # noqa: E402

# Matches the tags: block: header line + the indented list items below it.
TAGS_BLOCK_RE = re.compile(
    r'(^tags:[ \t]*\n)((?:[ \t]+-[^\n]*\n)+)',
    re.MULTILINE,
)
# Matches the collections: block similarly.
COLLECTIONS_BLOCK_RE = re.compile(
    r'(^collections:[ \t]*\n)((?:[ \t]+-[^\n]*\n)+)',
    re.MULTILINE,
)
# Parse a list-item line like:   - "value"     or     - value
LIST_ITEM_RE = re.compile(r'^[ \t]+-\s*(?:"((?:[^"\\]|\\.)*)"|\'((?:[^\'\\]|\\.)*)\'|(.*?))[ \t]*$')


def parse_list_block(block_body: str) -> List[str]:
    """Parse the body of a YAML list (the indented `  - ...` lines)."""
    values = []
    for line in block_body.splitlines():
        m = LIST_ITEM_RE.match(line)
        if not m:
            continue
        # First non-None group wins (quoted or bare)
        val = m.group(1) if m.group(1) is not None else (m.group(2) if m.group(2) is not None else m.group(3))
        if val is None:
            continue
        val = val.strip()
        if val:
            values.append(val)
    return values


def old_collection_slug(collection_path: str) -> str:
    """Reproduce the OLD slug the previous template emitted, so we can drop it.

    Old template did:
        collection | replace('/', '-') | replace(' ', '-')
                   | replace('--', '-') | lower | trim('-')
    """
    s = collection_path.replace('/', '-').replace(' ', '-')
    # Note: original Jinja2 .replace('--', '-') is a single literal replace, not
    # a regex — so a triple-hyphen would collapse to '--' then stay. We mimic
    # that exactly for a faithful match.
    s = s.replace('--', '-')
    s = s.lower().strip('-')
    return s


def build_new_tag_list(existing_tags: List[str], collections: List[str]) -> Tuple[List[str], List[str]]:
    """Return (new_tags, removed_tags) preserving order:
        1. literature, ai-summary (if present)
        2. new exploded collection tags
        3. keyword/other tags (preserved order, but with old slugs removed)
    """
    old_slugs_to_drop = {old_collection_slug(c) for c in collections}
    new_collection_tags = collections_to_tags(collections)

    # System tags first if they were present
    system_order = ['literature', 'ai-summary']
    final = []
    seen = set()

    for t in system_order:
        if t in existing_tags and t not in seen:
            final.append(t)
            seen.add(t)

    # Then new collection tags
    for t in new_collection_tags:
        if t not in seen:
            final.append(t)
            seen.add(t)

    removed = []
    # Then everything else from existing tags (keywords, manual), minus old slugs and system tags
    for t in existing_tags:
        if t in system_order:
            continue
        if t in old_slugs_to_drop:
            removed.append(t)
            continue
        if t in seen:
            continue
        final.append(t)
        seen.add(t)

    return final, removed


def render_tags_block(tags: List[str], indent: str = '  ') -> str:
    """Render a YAML list block. Always double-quote values for safety."""
    lines = []
    for t in tags:
        escaped = t.replace('\\', '\\\\').replace('"', '\\"')
        lines.append(f'{indent}- "{escaped}"')
    return '\n'.join(lines) + '\n'


def process_file(path: Path, dry_run: bool = False, verbose: bool = False) -> Optional[dict]:
    try:
        text = path.read_text(encoding='utf-8')
    except (UnicodeDecodeError, OSError) as e:
        return {'path': path, 'error': f'read failed: {e}'}

    split = split_frontmatter(text)
    if split is None:
        return None  # No frontmatter; skip silently

    frontmatter, body = split

    tags_match = TAGS_BLOCK_RE.search(frontmatter)
    collections_match = COLLECTIONS_BLOCK_RE.search(frontmatter)
    if not tags_match or not collections_match:
        return None  # Unexpected shape; skip

    existing_tags = parse_list_block(tags_match.group(2))
    collections = parse_list_block(collections_match.group(2))

    if not collections:
        return None

    new_tags, removed = build_new_tag_list(existing_tags, collections)

    if new_tags == existing_tags:
        return {'path': path, 'skipped': True}  # Already up to date

    # Detect indentation from the original tags block (first item line)
    first_item = tags_match.group(2).splitlines()[0]
    indent_match = re.match(r'^([ \t]+)-', first_item)
    indent = indent_match.group(1) if indent_match else '  '

    new_tags_block = render_tags_block(new_tags, indent=indent)
    new_frontmatter = (
        frontmatter[:tags_match.start(2)]
        + new_tags_block
        + frontmatter[tags_match.end(2):]
    )
    new_text = new_frontmatter + body

    if verbose or dry_run:
        # Show a brief diff summary
        added = [t for t in new_tags if t not in existing_tags]
        print(f'\n📝 {path.name}')
        if added:
            print(f'   + {added}')
        if removed:
            print(f'   - {removed}')

    if not dry_run:
        # Write atomically: write to .tmp then rename
        tmp = path.with_suffix(path.suffix + '.retag-tmp')
        tmp.write_text(new_text, encoding='utf-8')
        tmp.replace(path)

    return {
        'path': path,
        'added': [t for t in new_tags if t not in existing_tags],
        'removed': removed,
        'changed': True,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    default_root = os.getenv(
        'OUTPUT_DIR',
        str(Path.home() / 'ObsidianVault' / 'LiteratureNotes'),
    )
    parser.add_argument('--path', default=default_root, help='Vault root to scan (default: $OUTPUT_DIR)')
    parser.add_argument('--dry-run', action='store_true', help='Show what would change, do not write')
    parser.add_argument('--limit', type=int, default=None, help='Process only N files')
    parser.add_argument('--verbose', '-v', action='store_true', help='Print every changed file')
    args = parser.parse_args()

    root = Path(args.path)
    if not root.exists():
        print(f'❌ Path does not exist: {root}', file=sys.stderr)
        sys.exit(2)

    print(f'📂 Scanning: {root}')
    md_files = sorted(iter_markdown(root))
    print(f'   Found {len(md_files)} markdown files (archived/system dirs excluded)')
    if args.limit:
        md_files = md_files[: args.limit]
        print(f'   Limit applied: processing first {len(md_files)} files')

    changed = 0
    skipped = 0
    errors = 0
    no_frontmatter = 0

    for path in md_files:
        result = process_file(path, dry_run=args.dry_run, verbose=args.verbose)
        if result is None:
            no_frontmatter += 1
            continue
        if 'error' in result:
            errors += 1
            print(f'⚠️  {path}: {result["error"]}', file=sys.stderr)
            continue
        if result.get('skipped'):
            skipped += 1
            continue
        if result.get('changed'):
            changed += 1

    action = 'would change' if args.dry_run else 'changed'
    print('\n' + '=' * 60)
    print(f'   ✅ {action}:        {changed}')
    print(f'   ⏭️  already up to date: {skipped}')
    print(f'   ➖ no frontmatter / unparseable: {no_frontmatter}')
    print(f'   ❌ errors:        {errors}')
    print('=' * 60)
    if args.dry_run:
        print('\n(dry-run) Re-run without --dry-run to apply changes.')


if __name__ == '__main__':
    main()
