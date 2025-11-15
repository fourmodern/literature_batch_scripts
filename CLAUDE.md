# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Purpose

A comprehensive literature processing system that extracts metadata and PDFs from Zotero, generates AI summaries using GPT or Gemini, and creates Obsidian-compatible markdown notes with automatic synchronization.

Optimized for Korean-language academic paper summarization but adaptable for other languages. Supports both text-only (GPT) and multimodal (Gemini) processing for papers with important figures and images.

**Optional RAG System**: Advanced users can build searchable vector databases from academic papers for semantic search and question-answering (see scripts/rag/ directory).

## Commands

### Initial Setup
```bash
# Install core dependencies
pip install -r requirements.txt

# Install RAG system dependencies (optional, see scripts/rag/)
pip install -r requirements_rag.txt

# Copy and configure environment
cp .env.example .env
# Edit .env with your API keys and paths
```

### Environment Configuration
Key environment variables in `.env`:
- `ZOTERO_USER_ID`: Your Zotero user ID (required)
- `ZOTERO_API_KEY`: Your Zotero API key (required)
- `OUTPUT_DIR`: Output directory for markdown files (default: ./ObsidianVault/LiteratureNotes/)
- `PDF_DIR`: Zotero storage directory (auto-detected if not set)
- `SUMMARIZER`: Choose `gpt` (text-only) or `gemini` (multimodal)
- `OPENAI_API_KEY`: Required for GPT summarization and RAG answer generation
- `GEMINI_API_KEY`: Required for Gemini summarization
- `MODEL`: GPT model selection (`gpt-4o-mini` or `gpt-4o`)
- `GEMINI_MODEL`: Gemini model selection (`gemini-1.5-pro` or `gemini-1.5-flash`)
- `PINECONE_API_KEY`: Optional, for cloud-based vector search
- `PINECONE_ENVIRONMENT`: Pinecone environment (e.g., `gcp-starter`)

### Testing Setup
```bash
# Verify environment variables are set correctly
python scripts/run_literature_batch.py --list-collections

# Test with a single paper to ensure everything works
python scripts/run_literature_batch.py --limit 1
```

### Running the Pipeline
```bash
# Process all papers
python scripts/run_literature_batch.py

# Process with specific options
python scripts/run_literature_batch.py --limit 10 --collection "Machine Learning"
python scripts/run_literature_batch.py --dry-run --overwrite

# List available collections
python scripts/run_literature_batch.py --list-collections

# Skip GPT summarization (metadata only)
python scripts/run_literature_batch.py --skip-gpt --limit 50

# Fast processing with parallel workers (default: 5)
python scripts/run_literature_batch.py --workers 10

# Skip PDF downloads for faster processing
python scripts/run_literature_batch.py --no-pdf-download

# Maximum speed: parallel processing + skip downloads
python scripts/run_literature_batch.py --workers 10 --no-pdf-download

# Diagnose PDF sync issues
python scripts/check_zotero_sync.py

# Check Zotero-Obsidian sync status
python scripts/sync_checker.py                           # Compare all items
python scripts/sync_checker.py --collection "AIDD"       # Compare specific collection
python scripts/sync_checker.py --output sync_report.json # Save report as JSON

# Execute sync (move/archive files based on comparison)
python scripts/sync_executor.py --dry-run                      # Preview changes without executing
python scripts/sync_executor.py                                # Execute sync (with backup)
python scripts/sync_executor.py --no-backup                    # Execute without backup (not recommended)
python scripts/sync_executor.py --collection "AIDD"            # Sync specific collection only
python scripts/sync_executor.py --from-json sync_report.json   # Use existing comparison JSON

# Automatic synchronization (macOS launchd)
python scripts/zotero_auto_sync.py                             # Run manual sync
bash scripts/setup_plist.sh                                    # Configure auto-sync (30min interval)
```

### Processing Single PDF Files
```bash
# Process a single PDF file (external PDF, extracts metadata from content)
python scripts/process_single_pdf.py /path/to/paper.pdf

# Process with custom output directory
python scripts/process_single_pdf.py /path/to/paper.pdf --output-dir ./MyNotes/

# Process without GPT summarization (metadata only)
python scripts/process_single_pdf.py /path/to/paper.pdf --skip-gpt

# Process a Zotero storage PDF with full metadata from Zotero API
python scripts/process_zotero_pdf.py ~/Zotero/storage/ABCD1234/paper.pdf

# Process Zotero PDF with custom output directory
python scripts/process_zotero_pdf.py ~/Zotero/storage/ABCD1234/paper.pdf --output-dir ./MyNotes/

# Process Zotero PDF without GPT summarization
python scripts/process_zotero_pdf.py ~/Zotero/storage/ABCD1234/paper.pdf --skip-gpt
```

### RAG System Commands (Optional)
RAG scripts are located in `scripts/rag/` directory. See `requirements_rag.txt` for dependencies.

### Command Line Arguments
- `--limit N`: Process only N papers
- `--collection "Name"`: Process only papers from a specific Zotero collection
- `--list-collections`: Show all available collections with paper counts and exit
- `--skip-gpt`: Skip GPT summarization (only extract metadata and save to markdown)
- `--dry-run`: Preview what would be processed without creating files
- `--overwrite`: Reprocess papers even if already done
- `--resume`: Continue from last checkpoint after interruption
- `--copy-pdfs`: Copy PDFs to Obsidian vault (default: use file:// links to Zotero storage)
- `--workers N`: Number of parallel workers for processing (default: 5, recommended: 5-10)
- `--no-pdf-download`: Skip automatic PDF downloads (use local files only)

## Architecture

### Literature Processing Pipeline
1. **Zotero API** → Fetch paper metadata and collection hierarchy via pyzotero
2. **PDF Location** → Auto-detect Zotero storage directory (~/Zotero/storage/)
3. **PDF Download** → Automatically download missing PDFs from Zotero server
4. **Text Extraction** → Extract full text from PDFs using PyMuPDF (fallback to pdfplumber)
5. **AI Summarization** → Generate short (5 lines) and detailed (1 page) summaries via GPT/Gemini
6. **Markdown Generation** → Create structured notes using Jinja2 templates
7. **Folder Organization** → Mirror Zotero collection structure in output directory
8. **Auto-Sync** → Keep Obsidian vault synchronized with Zotero library (macOS launchd)

### Key Design Decisions

**Zotero Integration**
- Uses pyzotero API to fetch metadata directly (no export files needed)
- Automatically detects Zotero data directory across platforms
- Preserves collection hierarchy as folder structure
- Handles standard Zotero storage pattern: `storage/[8-char-key]/filename.pdf`
- **Pagination support**: Fetches all items (not limited to 100) with automatic batching
- **Item type support**: Journal articles, arXiv preprints, conference papers

**Processing Strategy**
- Tracks processed papers in `logs/done.txt` to avoid duplicates
- Falls back to abstract if PDF extraction fails
- Continues processing even if individual papers fail
- Logs all operations to `logs/summary.log`
- Saves checkpoint every 10 papers to `logs/checkpoint.json`
- Handles interruptions gracefully (Ctrl+C) with automatic checkpoint saving
- Supports resuming from checkpoint with `--resume` flag
- **Parallel processing**: Process multiple papers simultaneously (5 workers by default)
- **Performance optimization**: Silent PDF operations, optional download skipping

**AI Summarization**
- Supports two AI providers:
  - **GPT (OpenAI)**: Text-only processing with GPT-4o-mini by default (128k token context)
  - **Gemini (Google)**: Multimodal processing with text + images, using Gemini 1.5 Pro by default
- Generates three types of content: short summary, detailed summary, and analysis sections (contributions, limitations, ideas)
- Truncates very long texts to ~30k characters (GPT) or ~800k characters (Gemini) to stay within token limits
- Uses temperature 0.3 for consistent, factual summaries
- **Rate limit handling**:
  - Automatic exponential backoff: 20s → 40s → 80s on rate limits
  - Smart retry logic for different error types (timeout, connection, server errors)
  - Response caching (24h) to avoid duplicate API calls
  - Configurable worker count based on API tier (2-10 workers)
- Can be skipped entirely with `--skip-gpt` for faster processing
- **Anti-hallucination measures**: 
  - Strict prompts to only use content from the PDF
  - Instructions to mark missing information as "논문에 명시되지 않음"
  - Focus on extracting actual quotes and data from papers
- **Multimodal features (Gemini only)**:
  - Extracts and analyzes figures, charts, and diagrams
  - Selects most important image as "featured image"
  - Includes image context in summaries

**Output Structure**
- Creates folders matching Zotero collection paths
- Sanitizes folder/file names for filesystem compatibility
- Includes full bibliographic metadata in frontmatter
- Supports Obsidian-specific features (tags, links, callouts)

**Auto-Sync System**
- Monitors Zotero library for changes (added/deleted/moved papers)
- Archives deleted papers instead of deleting them (`_archived/` folder)
- Moves papers to new collection folders when collections change
- Runs automatically every 30 minutes via macOS launchd
- Safe processing order: deleted/moved BEFORE added (prevents conflicts)

### Module Responsibilities

**Core Processing** (scripts/)
- `run_literature_batch.py`: Main orchestrator, CLI handling, progress tracking, parallel processing coordination
- `process_single_pdf.py`: Process individual PDF files without Zotero, extract metadata from PDF content
- `process_zotero_pdf.py`: Process single Zotero storage PDF with full metadata from API
- `process_missing_papers.py`: Process papers from sync_checker.py JSON report

**Sync & Auto-Sync** (scripts/)
- `zotero_auto_sync.py`: Automatic synchronization orchestrator (runs via launchd)
- `sync_checker.py`: Compare Zotero database with Obsidian folder to find differences (added/deleted/moved items)
- `sync_executor.py`: Execute sync operations - move files to new collections, archive deleted items
- `setup_plist.sh`: Configure macOS launchd for automatic synchronization

**Data Extraction** (scripts/)
- `zotero_fetch.py`: Zotero API interaction, collection hierarchy building, pagination handling, multi-item-type support
- `text_extractor.py`: PDF text extraction with PyMuPDF fallback to pdfplumber, image extraction for multimodal processing
- `zotero_path_finder.py`: Cross-platform Zotero directory detection
- `pdf_downloader.py`: Downloads missing PDFs from Zotero server with retry logic

**AI Summarization** (scripts/)
- `gpt_summarizer.py`: OpenAI API calls with rate limit handling, prompt management, Korean language summaries, caching support
- `gemini_summarizer.py`: Google Gemini API calls with multimodal support (text + images)

**Utilities** (scripts/)
- `markdown_writer.py`: Template rendering, file writing, Obsidian-compatible formatting
- `utils.py`: Logging, progress tracking, checkpoint management
- `create_batch_file.py`: Generate JSON batch files for bulk PDF processing
- `check_zotero_sync.py`: Diagnostic tool for verifying Zotero file sync status

**RAG System** (scripts/rag/ - optional)
- Various scripts for building and querying vector databases
- See `requirements_rag.txt` for dependencies

### Error Handling Patterns

- Missing PDFs: Use abstract for summarization instead
- API rate limits: Log error and continue with next paper
- Invalid collection names: Show available collections
- Missing environment variables: Validate before starting
- PDF download failures: Detailed logging with common causes

### Troubleshooting PDF Extraction

**Common PDF Extraction Issues:**
- **Scanned PDFs**: Image-based PDFs with no text layer
- **Encrypted PDFs**: Password-protected files
- **Corrupted PDFs**: Damaged or incomplete files
- **Non-standard encoding**: Some PDFs use unusual text encoding

**Solutions:**
- For scanned PDFs: Consider OCR tools (not included)
- Check if PDFs open correctly in a PDF viewer
- Try downloading fresh copies from publishers
- Use `--skip-gpt` to identify which PDFs extract successfully

### Zotero-Obsidian Sync Workflow

The sync system keeps your Obsidian vault in sync with your Zotero library.

**Two-Step Process:**

1. **Check Sync Status** (`sync_checker.py`):
   ```bash
   python scripts/sync_checker.py --output sync_report.json
   ```
   - Compares Zotero SQLite database with Obsidian folder
   - Identifies: Added (Zotero only), Deleted (Obsidian only), Moved (collection changed)
   - Outputs comparison to JSON file

2. **Execute Sync** (`sync_executor.py`):
   ```bash
   # ALWAYS preview first
   python scripts/sync_executor.py --dry-run

   # Then execute
   python scripts/sync_executor.py
   ```
   - **Moved items**: Relocates files to new collection folders
   - **Deleted items**: Archives files to `_archived/{date}/` (doesn't delete)
   - **Added items**: Shows list (process with `run_literature_batch.py`)
   - **Automatic backup**: Creates `.tar.gz` backup before changes

**Initial Bulk Sync:**
```bash
# 1. Check what needs syncing
python scripts/sync_checker.py

# 2. Preview changes (recommended)
python scripts/sync_executor.py --dry-run

# 3. Execute sync with backup
python scripts/sync_executor.py

# 4. Process new papers
python scripts/run_literature_batch.py --collection "CollectionName"
```

**Safety Features:**
- **Dry-run mode**: Preview all changes before executing
- **Automatic backup**: Full vault backup before sync (can disable with `--no-backup`)
- **Archive instead of delete**: Deleted items moved to `_archived/` folder
- **Empty folder cleanup**: Automatically removes empty directories

**Automatic Sync (Recommended):**
```bash
# Set up auto-sync (runs every 30 minutes)
bash scripts/setup_plist.sh

# Manual sync anytime
python scripts/zotero_auto_sync.py
```

**Manual Workflow:**
```bash
# 1. Check for changes
python scripts/sync_checker.py

# 2. Preview and execute sync
python scripts/sync_executor.py --dry-run
python scripts/sync_executor.py

# 3. Process new papers from Zotero
python scripts/run_literature_batch.py --limit 10
```

### Troubleshooting PDF Downloads

If PDFs aren't downloading from Zotero servers:

1. **Check Zotero Sync Settings**
   - In Zotero: Edit → Preferences → Sync → Settings
   - Enable "Sync attachment files in My Library"
   - Choose "Sync attachment files in group libraries using Zotero storage"

2. **Run Diagnostic Script**
   ```bash
   python scripts/check_zotero_sync.py
   ```
   This will show:
   - Which PDFs are available on Zotero servers
   - Which are only local
   - Sync status and potential issues

3. **Common Causes**
   - File sync disabled in Zotero preferences
   - Zotero storage quota exceeded (check at zotero.org/settings/storage)
   - PDFs added but not synced yet (manually sync in Zotero)
   - Using WebDAV instead of Zotero storage
   - Network/firewall blocking Zotero API

4. **Manual Sync**
   - In Zotero: Click sync button or press Cmd/Ctrl+S
   - Wait for sync to complete before running the pipeline

## Development Notes

### Adding New Features
When extending functionality:
1. Follow existing module separation (fetch → extract → summarize → write)
2. Update progress tracking if adding new processing steps
3. Maintain backwards compatibility with existing `done.txt` format

### Template Modifications
The Jinja2 template at `templates/literature_note.md` can be customized. Available variables include all Zotero metadata fields plus:
- `short_summary`, `long_summary`
- `contribution`, `limitations`, `ideas`
- `collections` (list of collection paths)
- `pdf_path` (absolute path to PDF)
- `featured_image` (dict with filename, page, dimensions, selection_reason - Gemini only)
- `extracted_images` (list of extracted images with metadata - Gemini only)
- `image_captions` (list of detected captions - Gemini only)
- `annotations` (Zotero highlights and comments)
- `authors`, `year`, `doi`, `journal`
- `bibliography` (formatted citation)

### Zotero Storage Paths
The system expects PDFs in standard Zotero storage:
```
~/Zotero/storage/ABCD1234/Paper.pdf
```
For custom locations, set `PDF_DIR` in `.env`.

### Key Files and Logs
- `logs/done.txt`: List of processed paper keys (one per line)
- `logs/summary.log`: Detailed processing log with timestamps
- `logs/checkpoint.json`: Resume checkpoint containing progress state
- `logs/auto_sync/`: Auto-sync logs and change reports
- `ObsidianVault/LiteratureNotes/`: Default output directory for markdown files
- `_archived/`: Deleted papers are moved here instead of being deleted
- `sync_report.json`: Sync status comparison report (optional output from sync_checker.py)
- `config/com.fourmodern.zotero-sync.plist`: macOS launchd configuration

### Performance Considerations
- Default 5 parallel workers balances speed and API rate limits
- Each worker processes one paper at a time
- PDF extraction is CPU-intensive; GPT API calls are I/O-bound
- With 10 workers, can process ~100 papers in 10-15 minutes (with GPT)
- Without GPT (`--skip-gpt`), can process ~500 papers in 5-10 minutes

### RAG System (Optional)

Advanced users can build searchable vector databases from their academic papers. RAG scripts are located in `scripts/rag/` directory.

**Installation:**
```bash
pip install -r requirements_rag.txt
```

**Features:**
- Text-based and multimodal (text + image) search
- Local (ChromaDB) or cloud (Pinecone) storage
- Semantic chunking and embedding generation
- See scripts in `scripts/rag/` for details