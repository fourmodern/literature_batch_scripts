## Troubleshooting PDF Extraction

If most PDFs are failing to extract text:

1. **Run Detailed Diagnostics**
   ```bash
   python scripts/test_pdf_extraction.py
   ```
   This shows:
   - File sizes and page counts
   - Extraction quality metrics
   - Whether PDFs are scanned (image-based)
   - First few lines of extracted text

2. **Common PDF Extraction Issues**
   - **Scanned PDFs**: Image-based PDFs with no text layer
   - **Encrypted PDFs**: Password-protected files
   - **Corrupted PDFs**: Damaged or incomplete files
   - **Non-standard encoding**: Some PDFs use unusual text encoding
   - **Too strict validation**: Now lowered to 100 chars minimum

3. **Solutions**
   - For scanned PDFs: Consider OCR tools (not included)
   - Check if PDFs open correctly in a PDF viewer
   - Try downloading fresh copies from publishers
   - Use `--skip-gpt` to identify which PDFs extract successfully

## Zotero-Obsidian Sync Workflow

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

**Typical Workflow:**
```bash
# Option 1: Manual workflow
# 1. Check for changes
python scripts/sync_checker.py --output sync_report.json

# 2. Execute sync if needed
python scripts/sync_executor.py --dry-run  # Preview first
python scripts/sync_executor.py            # Execute

# 3. Process missing papers from sync report
python scripts/process_missing_papers.py --from-json sync_report.json

# Option 2: Automated workflow
python scripts/zotero_auto_sync.py  # Handles sync check and processing automatically
```

## Troubleshooting PDF Downloads

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
