"""
Mirror newly-processed Zotero literature notes (and their PDFs) into the
llm-wiki Obsidian vault on iCloud, then refresh cross-references for the
mirrored vault.

Pipeline (each step idempotent, safe to re-run):
  1. mirror .md notes 81.zotero/ -> llm-wiki/sources/  (fast delta copy)
  2. mirror img/ figure folders (only newly-added paper folders)
  3. mirror PDFs ~/Zotero/storage/ -> llm-wiki/sources/pdfs/  (only new keys)
  4. add_ios_pdf_links.py on llm-wiki/sources/  (inserts iOS-clickable link)
  5. build_doi_index.py + fetch_openalex_refs.py + inject_references.py
     against the llm-wiki vault so newly mirrored notes pick up cross-links.

Why not `rsync -a --delete` for step 1?  A full-tree rsync stat()s every one of
~1200 notes plus ~950 img folders across iCloud *before* it transfers anything,
which stalled the mirror for minutes and left the daemon perpetually behind. We
instead do a metadata-only os.walk of both vaults (milliseconds even on iCloud)
and copy only the files that actually differ, so cost scales with new papers,
not with total vault size.

The OpenAlex fetcher uses its on-disk cache; only DOIs that haven't been seen
before make HTTP calls, so each incremental sync is cheap.

Invoke standalone OR from zotero_auto_sync.py after each batch.
"""

import argparse
import os
import shutil
import subprocess
import sys
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


# Directory names that are never part of the note mirror: Zotero's archive,
# the figure/PDF stores (handled by their own steps), and Obsidian's own config
# and plugin caches which live only in the destination vault.
SKIP_DIR_NAMES = frozenset({
    '_archived', 'img', 'pdfs',
    '.obsidian', '.obsidian-mobile', '.trash', '.smart-env', '.git',
})


def _walk_md(root: Path):
    """Return ({relpath: os.stat_result}, walk_ok).

    Metadata-only traversal (no file contents read), so it stays in the
    millisecond range even when the vault lives on iCloud. ``walk_ok`` is False
    if the traversal hit *any* I/O error (e.g. iCloud EDEADLK) — callers must
    then refuse destructive operations, since a partial view of the source must
    never drive deletions in the mirror.
    """
    files = {}
    errors = []
    for dirpath, dirnames, filenames in os.walk(root, onerror=errors.append):
        dirnames[:] = [
            d for d in dirnames
            if d not in SKIP_DIR_NAMES and not d.startswith('.smtcmp_')
        ]
        for name in filenames:
            if not name.endswith('.md'):
                continue
            full = os.path.join(dirpath, name)
            try:
                st = os.stat(full)
            except OSError as exc:
                errors.append(exc)
                continue
            files[os.path.relpath(full, root)] = st
    return files, not errors


def mirror_markdown(src: Path, dest: Path) -> int:
    """Mirror .md notes src -> dest by copying only the delta.

    Replaces a full ``rsync -a --delete`` (which stalled for minutes stat-ing
    every file over iCloud). A note is (re)copied when it is new or when the
    source copy is newer than the destination — the ``--update`` rule, so
    wiki-links injected into the destination later in the pipeline are not
    clobbered on the next run. Notes that disappear from the source (Zotero
    archive / collection move) are removed from the mirror, but only when the
    source walk completed cleanly and did not collapse to a suspiciously small
    set, so a transient iCloud read can never trigger mass deletion.
    """
    dest.mkdir(parents=True, exist_ok=True)
    src_files, src_ok = _walk_md(src)
    dest_files, _ = _walk_md(dest)

    added = updated = deleted = 0
    for rel, st in src_files.items():
        dst_st = dest_files.get(rel)
        is_new = dst_st is None
        if is_new or st.st_mtime > dst_st.st_mtime + 2:
            target = dest / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            try:
                shutil.copy2(src / rel, target)
                if is_new:
                    added += 1
                else:
                    updated += 1
            except OSError as exc:
                print(f'   ⚠️ copy failed {rel}: {exc}', file=sys.stderr)

    stale = dest_files.keys() - src_files.keys()
    if not src_ok:
        print('   ⚠️ source walk hit I/O errors; skipping deletions this run '
              '(copy-only to avoid mirroring a partial view)', file=sys.stderr)
    elif stale and src_files and len(src_files) >= 0.5 * len(dest_files):
        for rel in stale:
            try:
                (dest / rel).unlink()
                deleted += 1
            except OSError as exc:
                print(f'   ⚠️ delete failed {rel}: {exc}', file=sys.stderr)
    elif stale:
        print(f'   ⚠️ {len(stale)} stale notes but source set too small '
              f'({len(src_files)} vs dest {len(dest_files)}); skipping deletions',
              file=sys.stderr)

    print(f'   notes: +{added} added, ~{updated} updated, -{deleted} removed '
          f'(source has {len(src_files)})')
    return 0


def mirror_img(src_img: Path, dest_img: Path) -> int:
    """Copy per-paper figure folders that exist in the source but not the
    mirror. Figures are written once when a paper is processed and never edited,
    so skipping folders already present keeps this to the new-paper delta."""
    if not src_img.exists():
        return 0
    dest_img.mkdir(parents=True, exist_ok=True)
    try:
        src_names = {p.name for p in src_img.iterdir() if p.is_dir()}
        dest_names = {p.name for p in dest_img.iterdir() if p.is_dir()}
    except OSError as exc:
        print(f'   ⚠️ img listing failed: {exc}', file=sys.stderr)
        return 0
    copied = 0
    for name in sorted(src_names - dest_names):
        try:
            shutil.copytree(src_img / name, dest_img / name)
            copied += 1
        except OSError as exc:
            print(f'   ⚠️ img copy failed {name}: {exc}', file=sys.stderr)
    print(f'   img: +{copied} new folders (source has {len(src_names)})')
    return 0


def mirror_pdfs(storage: Path, dest_pdfs: Path) -> int:
    """Copy the .pdf(s) from Zotero storage keys not yet mirrored. PDFs are
    immutable once stored, so existing key folders are skipped."""
    if not storage.exists():
        return 0
    dest_pdfs.mkdir(parents=True, exist_ok=True)
    try:
        dest_keys = {p.name for p in dest_pdfs.iterdir() if p.is_dir()}
        key_dirs = [p for p in storage.iterdir() if p.is_dir()]
    except OSError as exc:
        print(f'   ⚠️ pdf listing failed: {exc}', file=sys.stderr)
        return 0
    copied = 0
    for key_dir in key_dirs:
        if key_dir.name in dest_keys:
            continue
        try:
            pdfs = [f for f in key_dir.iterdir() if f.suffix.lower() == '.pdf']
        except OSError:
            continue
        if not pdfs:
            continue
        out_dir = dest_pdfs / key_dir.name
        out_dir.mkdir(exist_ok=True)
        for pdf in pdfs:
            try:
                shutil.copy2(pdf, out_dir / pdf.name)
                copied += 1
            except OSError as exc:
                print(f'   ⚠️ pdf copy failed {pdf.name}: {exc}', file=sys.stderr)
    print(f'   pdfs: +{copied} new files')
    return 0


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

    # 1. markdown notes (critical, fast delta)
    print('\n▶ Mirror markdown notes (delta)')
    mirror_markdown(src, dest)

    # 2. figure folders (best-effort, new-paper delta)
    print('\n▶ Mirror img figure folders (delta)')
    mirror_img(src / 'img', dest / 'img')

    # 3. PDFs
    if not args.skip_pdfs:
        print('\n▶ Mirror PDFs (delta)')
        mirror_pdfs(pdf_src, dest / 'pdfs')

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
