"""
Walk the Obsidian vault and build a DOI → file index.

For every .md file whose frontmatter contains a non-empty `doi:` field, record:
  {
    "<normalized DOI>": {
      "path": "<absolute path>",
      "rel": "<path relative to vault root>",
      "stem": "<filename stem without extension>",
      "key": "<Zotero key parsed from filename trailing _XXXXXXXX, if any>"
    }
  }

The normalization strips URL prefixes and lowercases the DOI so that
'https://doi.org/10.1038/X', '10.1038/X', and 'doi:10.1038/X' all map to
'10.1038/x'.

Output: cache/doi_index.json (atomic write).
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Dict, Optional

from dotenv import load_dotenv

from vault_io import iter_markdown, frontmatter_block, key_from_filename

load_dotenv()

DOI_LINE_RE = re.compile(r'^doi:\s*"?([^"\n]*)"?\s*$', re.MULTILINE)


def normalize_doi(doi: str) -> Optional[str]:
    """Lowercase and strip URL/prefix. Return None if it doesn't look like a DOI."""
    if not doi:
        return None
    s = doi.strip().lower()
    # Strip common prefixes
    for prefix in ('https://doi.org/', 'http://doi.org/', 'doi.org/', 'doi:'):
        if s.startswith(prefix):
            s = s[len(prefix):]
            break
    s = s.strip()
    # Basic shape check: must contain '10.' prefix and a slash
    if not s.startswith('10.') or '/' not in s:
        return None
    return s


def extract_doi(text: str) -> Optional[str]:
    fm = frontmatter_block(text)
    if fm is None:
        return None
    doi_match = DOI_LINE_RE.search(fm)
    if not doi_match:
        return None
    return normalize_doi(doi_match.group(1))


def build_index(root: Path) -> Dict[str, dict]:
    index: Dict[str, dict] = {}
    duplicates = 0
    no_doi = 0
    skipped = 0  # directories pruned by iter_markdown are not counted here
    for md in iter_markdown(root):
        try:
            text = md.read_text(encoding='utf-8')
        except (UnicodeDecodeError, OSError):
            continue
        doi = extract_doi(text)
        if not doi:
            no_doi += 1
            continue
        stem = md.stem
        rec = {
            'path': str(md),
            'rel': str(md.relative_to(root)),
            'stem': stem,
            'key': key_from_filename(stem),
        }
        if doi in index:
            duplicates += 1
            # Keep the path with a Zotero key suffix in preference (more authoritative)
            if rec['key'] and not index[doi].get('key'):
                index[doi] = rec
        else:
            index[doi] = rec
    return index, {'no_doi': no_doi, 'duplicates': duplicates, 'skipped': skipped}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    default_root = os.getenv(
        'OUTPUT_DIR',
        str(Path.home() / 'ObsidianVault' / 'LiteratureNotes'),
    )
    parser.add_argument('--path', default=default_root, help='Vault root to scan')
    parser.add_argument(
        '--output',
        default=str(Path(__file__).resolve().parent.parent / 'cache' / 'doi_index.json'),
        help='Output JSON path',
    )
    args = parser.parse_args()

    root = Path(args.path)
    if not root.exists():
        print(f'❌ Path does not exist: {root}', file=sys.stderr)
        sys.exit(2)

    print(f'📂 Scanning: {root}')
    index, stats = build_index(root)
    print(f'   ✅ DOIs indexed:      {len(index)}')
    print(f'   ⏭️  files w/o DOI:     {stats["no_doi"]}')
    print(f'   ⚠️  duplicate DOIs:    {stats["duplicates"]}')
    print(f'   🗄️  skipped (archived/system): {stats["skipped"]}')

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(out.suffix + '.tmp')
    tmp.write_text(json.dumps(index, indent=2, ensure_ascii=False), encoding='utf-8')
    tmp.replace(out)
    print(f'💾 Wrote: {out}')


if __name__ == '__main__':
    main()
