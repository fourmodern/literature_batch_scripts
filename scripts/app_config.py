"""
Centralised configuration and Zotero-client construction.

Previously every script repeated the same boilerplate: ``load_dotenv()``, read
``ZOTERO_USER_ID`` / ``ZOTERO_API_KEY``, build ``zotero.Zotero(...)``, and
resolve ``OUTPUT_DIR`` (each with a slightly different fallback default). This
module is the single source of truth for all of that.

Pure stdlib + python-dotenv + pyzotero, no project-local imports, so it is safe
to import from any context (``import app_config`` when ``scripts/`` is on
sys.path, or ``from scripts import app_config`` when the repo root is).
"""

import os
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Optional, Sequence

from dotenv import load_dotenv

# Load .env once, when this module is first imported.
load_dotenv()

# Generic, non-identifying fallback for the Obsidian output vault. The real
# location always comes from the OUTPUT_DIR environment variable.
DEFAULT_OUTPUT_DIR = str(Path.home() / 'ObsidianVault' / 'LiteratureNotes')


class ConfigError(RuntimeError):
    """Raised when required configuration / environment is missing."""


@dataclass
class Settings:
    """All environment-derived configuration in one place.

    Build one with ``Settings.from_env()``. Individual fields mirror the
    ``.env`` variables; ``output_dir`` is expanded but otherwise values are the
    raw environment strings (None when unset). The module-level helper functions
    below remain as thin shims for existing callers.
    """

    zotero_user_id: Optional[str] = None
    zotero_api_key: Optional[str] = None
    output_dir: Optional[str] = None
    pdf_dir: Optional[str] = None
    openai_api_key: Optional[str] = None
    gemini_api_key: Optional[str] = None
    pinecone_api_key: Optional[str] = None
    summarizer: str = 'gpt'
    model: Optional[str] = None
    gemini_model: Optional[str] = None

    @classmethod
    def from_env(cls) -> 'Settings':
        """Read configuration from the (already-loaded) environment."""
        output_dir = os.getenv('OUTPUT_DIR')
        pdf_dir = os.getenv('PDF_DIR')
        return cls(
            zotero_user_id=os.getenv('ZOTERO_USER_ID'),
            zotero_api_key=os.getenv('ZOTERO_API_KEY'),
            output_dir=os.path.expanduser(output_dir) if output_dir else None,
            pdf_dir=os.path.expanduser(pdf_dir) if pdf_dir else None,
            openai_api_key=os.getenv('OPENAI_API_KEY'),
            gemini_api_key=os.getenv('GEMINI_API_KEY'),
            pinecone_api_key=os.getenv('PINECONE_API_KEY'),
            summarizer=os.getenv('SUMMARIZER', 'gpt'),
            model=os.getenv('MODEL'),
            gemini_model=os.getenv('GEMINI_MODEL'),
        )

    def require(self, *names: str) -> None:
        """Raise ConfigError if any named field is unset/empty.

        Names are field names (e.g. 'zotero_user_id') or their .env aliases
        (e.g. 'ZOTERO_USER_ID'); both forms are accepted.
        """
        valid = {f.name for f in fields(self)}
        missing = []
        for name in names:
            field = name.lower()
            if field not in valid:
                raise ValueError(f"Unknown Settings field: {name}")
            if not getattr(self, field):
                missing.append(name.upper())
        if missing:
            raise ConfigError(
                f"Missing required configuration: {', '.join(missing)}. "
                f"Set them in your .env file."
            )

    def resolve_output_dir(self, required: bool = True) -> Optional[str]:
        """Return output_dir, falling back to DEFAULT_OUTPUT_DIR or raising."""
        if self.output_dir:
            return self.output_dir
        if required:
            raise ConfigError(
                "OUTPUT_DIR is not set. Set it in your .env file to your "
                "Obsidian vault path."
            )
        return DEFAULT_OUTPUT_DIR


def get_env(name: str, default: Optional[str] = None) -> Optional[str]:
    """Thin wrapper around os.getenv for a single import surface."""
    return os.getenv(name, default)


def require_env(*names: str) -> None:
    """Raise ConfigError if any of *names* is unset/empty."""
    missing = [n for n in names if not os.getenv(n)]
    if missing:
        raise ConfigError(
            f"Missing required environment variable(s): {', '.join(missing)}. "
            f"Set them in your .env file."
        )


def validate_env(required: Sequence[str] = ('ZOTERO_USER_ID', 'ZOTERO_API_KEY')) -> None:
    """Alias for require_env taking a sequence (back-compat with callers)."""
    require_env(*required)


def get_zotero_client(library_type: str = 'user'):
    """Construct a pyzotero client from ZOTERO_USER_ID / ZOTERO_API_KEY.

    Raises ConfigError with a clear message if either credential is missing.
    """
    require_env('ZOTERO_USER_ID', 'ZOTERO_API_KEY')
    # Imported lazily so modules that only need config (not the Zotero API)
    # don't pay the pyzotero import cost.
    from pyzotero import zotero
    return zotero.Zotero(
        os.getenv('ZOTERO_USER_ID'),
        library_type,
        os.getenv('ZOTERO_API_KEY'),
    )


def resolve_output_dir(required: bool = True, expand: bool = True) -> Optional[str]:
    """Return the OUTPUT_DIR vault path.

    If unset and ``required`` is True, raise ConfigError; otherwise fall back to
    DEFAULT_OUTPUT_DIR. ``expand`` runs os.path.expanduser on the result.
    """
    value = os.getenv('OUTPUT_DIR')
    if not value:
        if required:
            raise ConfigError(
                "OUTPUT_DIR is not set. Set it in your .env file to your "
                "Obsidian vault path."
            )
        value = DEFAULT_OUTPUT_DIR
    return os.path.expanduser(value) if expand else value


def resolve_pdf_dir(default: str = None) -> Optional[str]:
    """Return the PDF_DIR (Zotero storage) path, expanded, or *default*."""
    value = os.getenv('PDF_DIR', default)
    return os.path.expanduser(value) if value else value
