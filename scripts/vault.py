"""
Object-oriented facade over the Obsidian literature vault.

``vault_io`` provides the low-level, dependency-free helpers (iter_markdown,
frontmatter parsing, key extraction, name sanitisation). This module wraps them
in two small domain objects:

  - ``Note``  : a single markdown note (lazy file read; parsed frontmatter/body,
                Zotero key, collections, save()).
  - ``Vault`` : the output directory as a whole (iterate notes, index by Zotero
                key, resolve/sanitise paths).

These are convenience objects; the underlying functions in ``vault_io`` remain
the canonical implementation and stay available for existing callers.
"""

import os
import sys
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Union

# Make sibling modules importable whether this file is imported flat
# (``import vault``) or as part of the package (``from scripts import vault``).
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app_config import Settings  # noqa: E402
import vault_io  # noqa: E402


class Note:
    """A single literature note on disk.

    The file is read lazily on first access and cached; pass ``text`` to use an
    in-memory copy without touching disk.
    """

    def __init__(self, path: Union[str, Path], text: Optional[str] = None):
        self.path = Path(path)
        self._text = text

    @classmethod
    def from_file(cls, path: Union[str, Path]) -> 'Note':
        return cls(path)

    @property
    def text(self) -> str:
        if self._text is None:
            self._text = self.path.read_text(encoding='utf-8', errors='replace')
        return self._text

    def reload(self) -> 'Note':
        """Drop the cached text so the next access re-reads from disk."""
        self._text = None
        return self

    @property
    def key(self) -> Optional[str]:
        """Trailing 8-char Zotero key parsed from the filename, if any."""
        return vault_io.key_from_filename(self.path.name)

    @property
    def frontmatter(self) -> Optional[Dict]:
        """Parsed YAML frontmatter as a dict, or None if absent/invalid."""
        return vault_io.parse_frontmatter(self.text)

    @property
    def body(self) -> str:
        """Note body with the frontmatter block stripped (whole text if none)."""
        split = vault_io.split_frontmatter(self.text)
        return split[1] if split else self.text

    @property
    def collections(self) -> List[str]:
        """The ``collections:`` frontmatter value as a list (empty if none)."""
        fm = self.frontmatter or {}
        value = fm.get('collections')
        if value is None:
            return []
        return value if isinstance(value, list) else [value]

    def save(self, text: Optional[str] = None) -> None:
        """Write ``text`` (or the current cached text) back to disk."""
        if text is not None:
            self._text = text
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(self.text, encoding='utf-8')

    def __repr__(self) -> str:
        return f'Note({self.path.name!r}, key={self.key!r})'


class Vault:
    """The Obsidian output directory containing literature notes."""

    def __init__(self, root: Union[str, Path]):
        self.root = Path(root)

    @classmethod
    def from_settings(cls, settings: Optional[Settings] = None) -> 'Vault':
        settings = settings or Settings.from_env()
        return cls(settings.resolve_output_dir())

    @classmethod
    def from_env(cls) -> 'Vault':
        return cls.from_settings()

    def iter_notes(self) -> Iterator[Note]:
        """Yield a Note for every markdown file (iCloud-EDEADLK-safe)."""
        for path in vault_io.iter_markdown(self.root):
            yield Note(path)

    def notes_by_key(self) -> Dict[str, List[Note]]:
        """Index notes by Zotero key (multiple notes per key are possible)."""
        index: Dict[str, List[Note]] = {}
        for note in self.iter_notes():
            key = note.key
            if key:
                index.setdefault(key, []).append(note)
        return index

    def resolve_path(self, *parts: str) -> Path:
        """Join sanitised path parts under the vault root."""
        return self.root.joinpath(*(self.sanitize(p) for p in parts))

    @staticmethod
    def sanitize(name: str) -> str:
        return vault_io.sanitize_name(name)

    def __repr__(self) -> str:
        return f'Vault({str(self.root)!r})'
