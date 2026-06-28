"""
Archive stale duplicate notes left behind when papers were re-filed into deeper
Zotero subcollections (and re-processed with longer filenames) but the old
shallow-collection copy was never removed.

Decision per Zotero key with >1 note in the vault:
  - correct_path = the item's DEEPEST Zotero collection (mirrors markdown_writer).
  - keepers = copies physically located in correct_path.
      * exactly 1 keeper  -> keep it, archive all others.
      * >1 keeper (same folder, different filename) -> keep the LONGEST filename
        (most complete title = newest processing), archive the rest.
      * 0 keepers (no copy in the correct folder) -> AMBIGUOUS: keep the copy in
        the deepest existing folder, archive shallower ones. (Logged distinctly.)
  - Items whose key is not in Zotero at all are skipped (reported elsewhere).

Archived files move to _archived/{timestamp}/<original-rel-path> (reversible).
A .tar.gz backup of every affected file is written first.

Usage:
    python scripts/dedup_stale_notes.py --dry-run
    python scripts/dedup_stale_notes.py            # executes (with backup)
"""
import os
import sys
import tarfile
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from vault_io import iter_markdown, key_from_filename
from zotero_client import ZoteroDatabase

VAULT = Path(os.path.expanduser(os.getenv('OUTPUT_DIR')))


def zotero_deepest_paths():
    """Map each Zotero item key to its deepest (most-nested) collection path."""
    db = ZoteroDatabase(os.path.expanduser('~/Zotero'))
    try:
        return {k: max(v, key=lambda x: x.count('/'))
                for k, v in db.item_collections().items()}
    finally:
        db.close()


def collect_notes():
    bykey = defaultdict(list)
    for p in iter_markdown(VAULT):
        key = key_from_filename(p.name)
        if key:
            bykey[key].append(p)
    return bykey


def folder_of(p: Path) -> str:
    return '/'.join(p.relative_to(VAULT).parts[:-1])


def main():
    dry = '--dry-run' in sys.argv
    deepest = zotero_deepest_paths()
    bykey = collect_notes()
    dups = {k: v for k, v in bykey.items() if len(v) > 1}

    to_archive = []   # (path, reason)
    ambiguous = []
    for key, paths in dups.items():
        correct = deepest.get(key)
        if not correct:
            # key not in Zotero -> leave duplicates alone (separate concern)
            continue
        keepers = [p for p in paths if folder_of(p) == correct]
        if len(keepers) >= 1:
            # keep longest filename among keepers; archive everything else
            keep = max(keepers, key=lambda p: len(p.name))
            for p in paths:
                if p != keep:
                    to_archive.append((p, f'dup; keep {keep.relative_to(VAULT)}'))
        else:
            # no copy in correct folder: keep deepest-folder copy, archive shallower
            keep = max(paths, key=lambda p: folder_of(p).count('/'))
            for p in paths:
                if p != keep:
                    to_archive.append((p, f'no-correct-folder; keep deepest {keep.relative_to(VAULT)}'))
            ambiguous.append((key, correct, [str(p.relative_to(VAULT)) for p in paths]))

    print(f'Duplicate keys: {len(dups)}')
    print(f'Files to archive: {len(to_archive)}')
    print(f'Ambiguous (no copy in correct folder): {len(ambiguous)}')
    print()
    for p, reason in to_archive[:40]:
        print(f'  ARCHIVE: {p.relative_to(VAULT)}')
        print(f'           ({reason})')
    if len(to_archive) > 40:
        print(f'  ... and {len(to_archive)-40} more')

    if ambiguous:
        print('\n=== AMBIGUOUS cases (review) ===')
        for key, correct, ps in ambiguous[:20]:
            print(f'  {key}  correct={correct}')
            for x in ps:
                print(f'     {x}')

    if dry:
        print('\n[dry-run] No files moved.')
        return

    if not to_archive:
        print('Nothing to archive.')
        return

    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    archive_root = VAULT / '_archived' / f'dedup_{ts}'
    backup_path = Path(__file__).resolve().parent.parent / 'logs' / f'dedup_backup_{ts}.tar.gz'
    backup_path.parent.mkdir(parents=True, exist_ok=True)

    # 1) Backup every file we're about to move
    with tarfile.open(backup_path, 'w:gz') as tar:
        for p, _ in to_archive:
            tar.add(p, arcname=str(p.relative_to(VAULT)))
    print(f'\n💾 Backup: {backup_path}')

    # 2) Move to _archived preserving relative path
    moved = 0
    for p, _ in to_archive:
        rel = p.relative_to(VAULT)
        dest = archive_root / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        p.rename(dest)
        moved += 1
    print(f'📦 Archived {moved} stale duplicate notes -> {archive_root}')


if __name__ == '__main__':
    main()
