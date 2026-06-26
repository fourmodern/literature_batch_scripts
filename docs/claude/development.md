## Development Notes

### Coding Conventions

**Import Organization**
```python
# Standard library imports first
import os
import sys
from pathlib import Path

# Third-party imports
from pyzotero import zotero
from dotenv import load_dotenv

# Local imports last
from text_extractor import extract_text_from_pdf
from gpt_summarizer import generate_short_long
```

**Environment Variable Loading**
- Always load .env at module top: `load_dotenv()` before imports that need env vars
- Use `os.getenv("VAR", "default")` with defaults for optional vars
- Validate required vars in `validate_environment()` function at startup

**File Path Handling**
- Use `os.path.join()` for cross-platform compatibility (not f-strings with /)
- Sanitize collection/file names with `sanitize_folder_name()` before filesystem operations
- Handle Zotero storage pattern: `storage/{8-char-key}/filename.pdf`
- Support both absolute paths and file:// URLs for PDF links

**Error Handling**
- Use try/except for API calls with specific exception types
- Log errors with context (paper title, key, collection)
- Continue processing on single-item failures (don't crash entire batch)
- Return meaningful error messages to user

**Parallel Processing**
- Use `concurrent.futures.ThreadPoolExecutor` (not multiprocessing - API calls are I/O bound)
- Protect shared resources with `threading.Lock`
- Each worker processes one item completely before next
- Pass immutable arguments to workers (no shared mutable state)

**Logging**
- Use structured logging with timestamps: `[YYYY-MM-DD HH:MM:SS]`
- Log to both console and `logs/summary.log`
- Include paper identifiers in all log messages (key or title)
- Use tqdm for progress bars (don't print in loops)

### Adding New Features

When extending functionality:
1. Follow existing module separation (fetch → extract → summarize → write)
2. Update progress tracking if adding new processing steps
3. Maintain backwards compatibility with existing `done.txt` format (one key per line)
4. Add new dependencies to appropriate requirements file:
   - Core features → `requirements.txt`
   - RAG features → `requirements_rag.txt`
   - Optional features → `requirements_optional.txt`
5. Update environment variable validation if adding new API keys
6. Add command-line arguments to argparse in `run_literature_batch.py`
7. Update CLAUDE.md (and `docs/claude/*.md` subdocs) with new commands and architecture changes

### Template Modifications

The Jinja2 template at `templates/literature_note.md` can be customized for output formatting. Available variables include all Zotero metadata fields plus:
- `short_summary`, `long_summary` (AI-generated Korean summaries)
- `contribution`, `limitations`, `ideas` (AI-generated analysis sections)
- `collections` (list of collection paths, e.g., ["AI/Machine Learning", "Papers"])
- `pdf_path` (absolute path or file:// URL to PDF)
- `featured_image` (dict with filename, page, dimensions, selection_reason - Gemini only)
- `extracted_images` (list of extracted images with metadata - Gemini only)
- `image_captions` (list of detected captions - Gemini only)
- `figure_captions`, `table_captions` (extracted from PDF)
- `annotations` (Zotero highlights and comments)
- `authors` (list of author names)
- `year`, `doi`, `journal`, `volume`, `issue`, `pages`
- `bibliography` (formatted citation string)
- `zotero_link` (web library URL)
- `zotero_app_link` (zotero://select/... URL)
- `ai_tool_links` (formatted links to AI analysis tools)

### Zotero Storage Paths
The system expects PDFs in standard Zotero storage:
```
~/Zotero/storage/ABCD1234/Paper.pdf
```
For custom locations, set `PDF_DIR` in `.env`.

### Key Files and Logs
- `logs/done.txt`: List of processed paper keys (one per line, used to skip already-processed items)
- `logs/summary.log`: Detailed processing log with timestamps (tail -f to monitor live)
- `logs/checkpoint.json`: Resume checkpoint containing progress state ({"processed": [...], "current_index": N})
- `ObsidianVault/LiteratureNotes/`: Default output directory for markdown files
- `sync_report.json`: Sync status comparison report (optional output from sync_checker.py)
- `templates/literature_note.md`: Jinja2 template for markdown output
- `.env`: Environment configuration (API keys, paths)

### Directory Structure
```
literature_batch_scripts/
├── scripts/                 # All Python scripts
│   ├── run_literature_batch.py   # Main entry point
│   ├── zotero_fetch.py           # Zotero API client
│   ├── text_extractor.py         # PDF processing
│   ├── gpt_summarizer.py         # GPT API wrapper
│   ├── gemini_summarizer.py      # Gemini API wrapper
│   ├── markdown_writer.py        # Template rendering
│   ├── sync_checker.py           # Sync detection
│   ├── sync_executor.py          # Sync execution
│   ├── process_missing_papers.py # Process from sync report
│   └── [50+ other scripts]
├── templates/               # Jinja2 templates
│   └── literature_note.md
├── docs/                    # Detailed documentation
│   └── claude/              # Split CLAUDE.md sections
├── logs/                    # Runtime logs (created on first run)
│   ├── done.txt
│   ├── summary.log
│   └── checkpoint.json
├── ObsidianVault/           # Output directory (configurable)
│   └── LiteratureNotes/
│       ├── Collection1/
│       │   └── Author_2024_PaperTitle.md
│       └── Collection2/
├── requirements.txt         # Core dependencies
├── requirements_rag.txt     # RAG system dependencies
├── requirements_optional.txt # Optional features
├── .env.example             # Example environment config
├── .env                     # Your config (not in git)
├── CLAUDE.md                # Index for Claude Code (imports docs/claude/*.md)
└── README.md                # User documentation
```

### Performance Considerations
- Default 5 parallel workers balances speed and API rate limits
- Each worker processes one paper at a time
- PDF extraction is CPU-intensive; GPT API calls are I/O-bound
- With 10 workers, can process ~100 papers in 10-15 minutes (with GPT)
- Without GPT (`--skip-gpt`), can process ~500 papers in 5-10 minutes
