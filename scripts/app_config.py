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
