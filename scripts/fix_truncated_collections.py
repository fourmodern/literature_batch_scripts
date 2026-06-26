"""
One-off repair: fix notes whose frontmatter `collections:` (and derived tags)
lost the top-level prefix due to the Zotero API collection-pagination bug
(zot.collections() returning only 100 of >100 collections, dropping top-level
parents like '000.Papers').

Truth source = the note's actual folder location relative to the vault root,
which is already correct. We rewrite the frontmatter `collections:` value to
match the folder, and swap the collection-derived hierarchy tags.

Idempotent: a note whose collections already equals its folder path is skipped.
"""
import os
import re
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS_DIR))
from markdown_writer import collections_to_tags  # noqa: E402

VAULT = Path(os.path.expanduser(os.getenv('OUTPUT_DIR')))
SKIP = {'_archived', '.obsidian', '.trash', 'img'}
COLL_BLOCK_RE = re.compile(r'(^collections:\s*\n)((?:[ \t]*-[^\n]*\n)+)', re.M)


def correct_collection_for(path: Path) -> str:
    rel = path.relative_to(VAULT)
    parts = rel.parts[:-1]  # drop filename
    return '/'.join(parts)


def current_collections(block: str):
    return [v.strip().strip('"') for v in re.findall(r'-\s*"?([^"\n]+)"?', block)]


def fix_note(path: Path, dry_run: bool = False) -> bool:
    correct = correct_collection_for(path)
    if not correct or correct == 'Uncategorized':
        return False
    text = path.read_text(encoding='utf-8')
    m = COLL_BLOCK_RE.search(text)
    if not m:
        return False
    cur_vals = current_collections(m.group(2))
    if cur_vals == [correct]:
        return False  # already correct

    old_tags = set(collections_to_tags(cur_vals))
    new_tags = collections_to_tags([correct])

    # Rebuild collections block (single correct path)
    new_block = m.group(1) + f'  - "{correct}"\n'
    text2 = text[:m.start()] + new_block + text[m.end():]

    # Swap collection-derived tags inside the tags: block
    tm = re.search(r'(^tags:\s*\n)((?:[ \t]*-[^\n]*\n)+)', text2, re.M)
    if tm:
        tag_lines = tm.group(2).split('\n')
        kept = []
        for ln in tag_lines:
            if not ln.strip():
                continue
            val = re.sub(r'^\s*-\s*', '', ln).strip().strip('"')
            if val in old_tags and val not in new_tags:
                continue  # drop stale collection tag
            kept.append(ln)
        # Insert new collection tags right after `- ai-summary` (or at top)
        out_lines = []
        inserted = False
        for ln in kept:
            out_lines.append(ln)
            if ln.strip() == '- ai-summary' and not inserted:
                for nt in new_tags:
                    out_lines.append(f'  - "{nt}"')
                inserted = True
        if not inserted:  # no ai-summary anchor; prepend
            ins = [f'  - "{nt}"' for nt in new_tags]
            out_lines = ins + out_lines
        # de-dup while preserving order
        seen = set(); dedup = []
        for ln in out_lines:
            key = re.sub(r'^\s*-\s*', '', ln).strip().strip('"')
            if key in seen:
                continue
            seen.add(key); dedup.append(ln)
        new_tag_block = tm.group(1) + '\n'.join(dedup) + '\n'
        text2 = text2[:tm.start()] + new_tag_block + text2[tm.end():]

    if dry_run:
        print(f'WOULD FIX: {path.relative_to(VAULT)}  {cur_vals} -> {correct}')
        return True
    tmp = path.with_suffix(path.suffix + '.fixtmp')
    tmp.write_text(text2, encoding='utf-8')
    tmp.replace(path)
    print(f'FIXED: {path.relative_to(VAULT)}  {cur_vals} -> {correct}')
    return True


def main():
    dry = '--dry-run' in sys.argv
    fixed = 0
    for p in VAULT.rglob('*.md'):
        if any(part in SKIP for part in p.parts):
            continue
        text = p.read_text(encoding='utf-8', errors='replace')
        m = COLL_BLOCK_RE.search(text)
        if not m:
            continue
        vals = current_collections(m.group(2))
        # truncated heuristic: a value that is a numeric-prefixed mid-level path
        # not starting with the true top-level folder
        correct = correct_collection_for(p)
        if vals == [correct] or correct == 'Uncategorized' or not correct:
            continue
        # Only fix when current value is a suffix of the correct path (truncation),
        # to avoid touching legitimately multi-collection notes.
        if len(vals) == 1 and correct.endswith(vals[0]) and vals[0] != correct:
            if fix_note(p, dry_run=dry):
                fixed += 1
    print(f'\n{"Would fix" if dry else "Fixed"}: {fixed} notes')


if __name__ == '__main__':
    main()
