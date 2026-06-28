"""
Mirror newly-processed Zotero literature notes (and their PDFs) into the
llm-wiki Obsidian vault on iCloud, then refresh cross-references for the
mirrored vault.

Pipeline (each step idempotent, safe to re-run):
  1. rsync .md from 81.zotero/ -> llm-wiki/sources/  (skip _archived, --update)
  2. rsync PDFs from ~/Zotero/storage/ -> llm-wiki/sources/pdfs/  (PDFs only)
  3. add_ios_pdf_links.py on llm-wiki/sources/  (inserts iOS-clickable link)
  4. build_doi_index.py + fetch_openalex_refs.py + inject_references.py
     against the llm-wiki vault so newly mirrored notes pick up cross-links.

The OpenAlex fetcher uses its on-disk cache; only DOIs that haven't been seen
before make HTTP calls, so each incremental sync is cheap.

Invoke standalone OR from zotero_auto_sync.py after each batch.
"""

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / 'scripts'

DEFAULT_SRC_VAULT = Path(os.getenv(
    'OUTPUT_DIR',
    str(Path.home() / 'ObsidianVault' / 'LiteratureNotes'),
))
DEFAULT_DEST_VAULT = Path(os.getenv(
    'LLM_WIKI_SOURCES',
    str(Path.home() / 'Library/Mobile Documents/iCloud~md~obsidian/Documents/llm-wiki/llm-wiki/sources'),
))
DEFAULT_PDF_SRC = Path(os.getenv(
    'PDF_DIR',
    str(Path.home() / 'Zotero/storage'),
))


def run(label: str, cmd: list, check: bool = False) -> int:
    """Run a subprocess, stream output, return exit code."""
    print(f'\n▶ {label}')
    print(f'   {" ".join(str(c) for c in cmd)}')
    try:
        r = subprocess.run(cmd, check=check)
        return r.returncode
    except FileNotFoundError as e:
        print(f'   ❌ command not found: {e}', file=sys.stderr)
        return 127
    except subprocess.CalledProcessError as e:
        print(f'   ❌ exit {e.returncode}', file=sys.stderr)
        return e.returncode


# rsync exit codes that signal a *transient* I/O problem rather than a real
# misconfiguration. On this vault the source lives on iCloud Drive, whose file
# provider intermittently returns EDEADLK ("Resource deadlock avoided") while it
# is actively materialising files. rsync surfaces that as a partial-transfer
# error (23) or a hard I/O error (10/11/12/20/30/35). These almost always clear
# on a short retry once iCloud settles, so we retry instead of aborting the
# whole mirror (which previously left llm-wiki stuck for days).
RSYNC_TRANSIENT_CODES = {10, 11, 12, 20, 23, 24, 30, 35}


def run_rsync_with_retries(label: str, cmd: list, attempts: int = 4, delay: int = 15) -> int:
    """Run an rsync command, retrying on transient iCloud I/O errors.

    Returns 0 if any attempt succeeds, otherwise the last non-zero exit code.
    """
    rc = 0
    for attempt in range(1, attempts + 1):
        suffix = '' if attempt == 1 else f' (retry {attempt - 1}/{attempts - 1})'
        rc = run(f'{label}{suffix}', cmd)
        if rc == 0:
            return 0
        if rc not in RSYNC_TRANSIENT_CODES or attempt == attempts:
            return rc
        print(f'   ⏳ transient rsync error {rc}; waiting {delay}s before retry '
              f'(iCloud likely still syncing)', file=sys.stderr)
        time.sleep(delay)
    return rc


def rsync_markdown(src: Path, dest: Path) -> int:
    """Mirror markdown + img with --delete so Zotero moves / archives in the
    source show up as moves / removals in the destination. Critical exclusions:
      - pdfs/   : managed by rsync_pdfs(); --delete must NOT touch it
      - img/    : already synced as part of source; protect from deletion since
                  we keep it under the same key-folder layout as the source
      - _archived: never sync, but also never delete (it isn't present in dest)
      - dotfiles: Obsidian config, plugin caches, etc. live only in dest
    """
    dest.mkdir(parents=True, exist_ok=True)
    cmd = [
        'rsync', '-a', '--delete',
        '--exclude', '_archived',
        '--exclude', '.DS_Store',
        '--exclude', '.obsidian',
        '--exclude', '.obsidian-mobile',
        '--exclude', '.trash',
        '--exclude', '.smart-env',
        '--exclude', '.smtcmp_*',
        '--exclude', 'pdfs',
        f'{src}/',
        f'{dest}/',
    ]
    return run_rsync_with_retries('Mirror markdown + img (with delete)', cmd)


def rsync_pdfs(src: Path, dest: Path) -> int:
    dest.mkdir(parents=True, exist_ok=True)
    cmd = [
        'rsync', '-a', '--update',
        '--include', '*/',
        '--include', '*.pdf',
        '--exclude', '*',
        f'{src}/',
        f'{dest}/',
    ]
    return run_rsync_with_retries('Mirror PDFs', cmd)


def add_ios_links(vault: Path) -> int:
    cmd = [sys.executable, str(SCRIPTS / 'add_ios_pdf_links.py'), '--vault', str(vault)]
    return run('Add iOS PDF links (idempotent)', cmd)


def refresh_references(vault: Path) -> int:
    """Refresh cross-references against the llm-wiki vault.

    Each helper writes its outputs under cache/, which is repo-relative.
    We point build_doi_index at the LLM-WIKI vault so the DOI index and
    therefore the wiki-link injection both operate on the mirrored copy.
    """
    cache_doi = ROOT / 'cache' / 'doi_index.llm_wiki.json'
    cache_ref = ROOT / 'cache' / 'reference_map.json'

    rc1 = run(
        'Build DOI index (llm-wiki)',
        [
            sys.executable,
            str(SCRIPTS / 'build_doi_index.py'),
            '--path', str(vault),
            '--output', str(cache_doi),
        ],
    )
    if rc1 != 0:
        return rc1

    # OpenAlex fetcher relies on cache/doi_index.json by default; pass our path.
    rc2 = run(
        'Fetch OpenAlex references (cached)',
        [
            sys.executable,
            str(SCRIPTS / 'fetch_openalex_refs.py'),
            '--doi-index', str(cache_doi),
        ],
    )
    if rc2 != 0:
        return rc2

    rc3 = run(
        'Inject wiki-links',
        [
            sys.executable,
            str(SCRIPTS / 'inject_references.py'),
            '--doi-index', str(cache_doi),
            '--ref-map', str(cache_ref),
        ],
    )
    return rc3


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--src', default=str(DEFAULT_SRC_VAULT), help='Source vault path (81.zotero)')
    parser.add_argument('--dest', default=str(DEFAULT_DEST_VAULT), help='Destination llm-wiki sources/')
    parser.add_argument('--pdf-src', default=str(DEFAULT_PDF_SRC), help='Zotero storage root for PDFs')
    parser.add_argument('--skip-pdfs', action='store_true', help='Skip PDF rsync (fast mirror)')
    parser.add_argument('--skip-refs', action='store_true', help='Skip OpenAlex reference refresh')
    args = parser.parse_args()

    src = Path(args.src)
    dest = Path(args.dest)
    pdf_src = Path(args.pdf_src)

    if not src.exists():
        print(f'❌ Source vault not found: {src}', file=sys.stderr)
        sys.exit(2)
    if not pdf_src.exists() and not args.skip_pdfs:
        print(f'⚠️  PDF source not found, skipping PDFs: {pdf_src}', file=sys.stderr)
        args.skip_pdfs = True

    print(f'📤 Source:      {src}')
    print(f'📥 Destination: {dest}')

    # 1. markdown + img
    rc = rsync_markdown(src, dest)
    if rc != 0:
        print('❌ Markdown mirror failed; aborting downstream steps', file=sys.stderr)
        sys.exit(rc)

    # 2. PDFs
    if not args.skip_pdfs:
        rc = rsync_pdfs(pdf_src, dest / 'pdfs')
        if rc != 0:
            print('⚠️  PDF mirror failed; continuing (notes still usable)', file=sys.stderr)

    # 3. iOS PDF links
    rc = add_ios_links(dest)
    if rc != 0:
        print('⚠️  iOS link injection had errors; continuing', file=sys.stderr)

    # 4. References
    if not args.skip_refs:
        rc = refresh_references(dest)
        if rc != 0:
            print('⚠️  Reference refresh had errors; mirror itself succeeded', file=sys.stderr)
            # Don't fail the whole mirror on ref errors
            sys.exit(0)

    print('\n✅ Mirror to llm-wiki complete.')


if __name__ == '__main__':
    main()
