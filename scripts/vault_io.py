"""
Shared helpers for reading the Obsidian literature vault.

This module centralises file-system logic that was previously copy-pasted
(with subtle inconsistencies) across many scripts:

  - SKIP_DIR_NAMES: which directories to never descend into. Several scripts
    each defined their own slightly different set; this is the single source
    of truth.
  - iter_markdown(): walk a vault subtree for ``*.md`` files, resilient to the
    intermittent iCloud Drive ``EDEADLK`` ("Resource deadlock avoided") error.
    Plain ``Path.rglob`` aborts the entire scan when a single ``os.scandir``
    raises; ``os.walk(onerror=...)`` lets us skip the bad directory instead.
  - parse_frontmatter(): extract YAML frontmatter from a note as a dict.
  - key_from_filename(): pull the trailing 8-char Zotero key out of a filename.
  - sanitize_name(): filesystem-safe folder/file name.

Pure stdlib + PyYAML, no project-local imports, so it is safe to import from
any context (``import vault_io`` when ``scripts/`` is on sys.path, or
``from scripts import vault_io`` when the repo root is).
"""

import os
import re
import sys
from pathlib import Path
from typing import Dict, Iterator, Optional, Tuple, Union

import yaml

# Directories that never contain real literature notes. Union of every variant
# that previously lived in individual scripts:
#   - _archived / .obsidian / .obsidian-mobile / .trash : system & backups
#   - .smart-env / .smtcmp_* (matched separately) : plugin caches
#   - pdfs / img : attachment/asset folders (hold no .md, safe to prune)
SKIP_DIR_NAMES = frozenset({
    '_archived',
    '.obsidian',
    '.obsidian-mobile',
    '.trash',
    '.smart-env',
    '.git',
    'pdfs',
    'img',
})

# Zotero attachment keys are 8 uppercase alphanumerics. Notes are named
# ``<Title>_<KEY>.md``; accept the key with or without the ``.md`` suffix so the
# same helper works on both a bare stem and a full filename.
KEY_RE = re.compile(r'_([A-Z0-9]{8})(?:\.md)?$')

# YAML frontmatter delimited by leading/trailing ``---`` lines.
FRONTMATTER_RE = re.compile(r'\A---\n(.*?)\n---\n', re.DOTALL)


def _default_onerror(err: OSError) -> None:
    print(
        f'   ⚠️ skipping unreadable dir: {getattr(err, "filename", err)} '
        f'({err.strerror or err})',
        file=sys.stderr,
    )


def is_under_skipped_dir(path: Union[str, Path], root: Union[str, Path]) -> bool:
    """True if *path* lives under any SKIP_DIR_NAMES directory relative to root."""
    try:
        rel_parts = Path(path).relative_to(root).parts
    except ValueError:
        return True
    return any(part in SKIP_DIR_NAMES for part in rel_parts)


def iter_markdown(
    root: Union[str, Path],
    skip_dirs: frozenset = SKIP_DIR_NAMES,
    onerror=_default_onerror,
) -> Iterator[Path]:
    """Yield every ``*.md`` file under *root*, resilient to iCloud I/O errors.

    Uses ``os.walk(onerror=...)`` instead of ``Path.rglob`` so that a single
    unreadable directory (e.g. iCloud Drive returning ``EDEADLK`` while
    materialising files) is logged and skipped rather than aborting the whole
    scan. ``skip_dirs`` are pruned in-place to avoid descending into them.
    """
    root = Path(root)
    for dirpath, dirnames, filenames in os.walk(root, onerror=onerror):
        dirnames[:] = [d for d in dirnames if d not in skip_dirs]
        for name in filenames:
            if name.endswith('.md'):
                yield Path(dirpath) / name


def frontmatter_block(text: str) -> Optional[str]:
    """Return the raw YAML frontmatter string (without ``---`` fences), or None."""
    m = FRONTMATTER_RE.match(text)
    return m.group(1) if m else None


def split_frontmatter(text: str) -> Optional[Tuple[str, str]]:
    """Split a note into (frontmatter_with_fences, body), or None if absent.

    The first element includes the surrounding ``---`` fences and the trailing
    newline (i.e. the regex group(0)); the second is everything after it. Useful
    for callers that rewrite a block inside the frontmatter and re-join the body.
    """
    m = FRONTMATTER_RE.match(text)
    if not m:
        return None
    return m.group(0), text[m.end():]


def parse_frontmatter(text: str) -> Optional[Dict]:
    """Parse a note's YAML frontmatter into a dict, or None if absent/invalid."""
    block = frontmatter_block(text)
    if block is None:
        return None
    try:
        data = yaml.safe_load(block)
    except yaml.YAMLError:
        return None
    return data if isinstance(data, dict) else None


def key_from_filename(name: Union[str, Path]) -> Optional[str]:
    """Extract the trailing 8-char Zotero key from a filename or stem."""
    stem = Path(name).name
    m = KEY_RE.search(stem)
    return m.group(1) if m else None


def sanitize_name(name: str) -> str:
    """Sanitise a string for use as a filesystem folder/file name."""
    name = name.replace('/', '-').replace('\\', '-').replace(':', '-')
    for ch in ('*', '?', '"', '<', '>', '|'):
        name = name.replace(ch, '')
    return name.strip()
