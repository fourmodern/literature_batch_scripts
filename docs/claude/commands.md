## Commands

### Initial Setup
```bash
# Install core dependencies
pip install -r requirements.txt

# Install RAG system dependencies (optional)
pip install -r requirements_rag.txt

# Install all optional features (if available)
pip install -r requirements_optional.txt

# Copy and configure environment
cp .env.example .env
# Edit .env with your API keys and paths

# If using conda environment (recommended):
conda activate zot
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

# Test PDF extraction quality
python scripts/test_pdf_extraction.py
python scripts/test_pdf_extraction.py "TYK2"  # Test specific collection

# Check Zotero-Obsidian sync status
python scripts/sync_checker.py                           # Compare all items
python scripts/sync_checker.py --collection "AIDD"       # Compare specific collection
python scripts/sync_checker.py --output sync_report.json # Save report as JSON

# Execute sync (move/archive files based on comparison)
python scripts/sync_executor.py --dry-run                # Preview changes without executing
python scripts/sync_executor.py                          # Execute sync (with backup)
python scripts/sync_executor.py --no-backup              # Execute without backup (not recommended)
python scripts/sync_executor.py --collection "AIDD"      # Sync specific collection only
python scripts/sync_executor.py --from-json sync_report.json  # Use existing comparison JSON

# Process missing papers from sync report
python scripts/process_missing_papers.py --from-json sync_report.json
python scripts/process_missing_papers.py --from-json sync_report.json --limit 10

# Automated Zotero-Obsidian sync (runs periodically)
python scripts/zotero_auto_sync.py  # Check sync status and process new papers automatically
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

### RAG System Commands
```bash
# Build text-only vector database from Zotero papers
python scripts/text_only_rag_builder.py --build-db
python scripts/build_text_fast.py          # Fast parallel text embedding
python scripts/simple_bge_builder.py       # Simple BGE-M3 based builder

# Build multimodal (text + images) vector database
python scripts/vision_language_rag_builder.py
python scripts/build_multimodal_rag.py
python scripts/fast_multimodal_builder.py  # Parallel multimodal processing

# Build all databases at once
python scripts/build_all_fast.py           # Fast parallel build for all modalities

# Search in vector database
python scripts/search_examples.py
python scripts/search_multimodal.py
python scripts/hybrid_searcher.py          # Hybrid text+image search

# All-in-one: Process papers + build RAG
python scripts/run_all_in_one.py --collection "LNP" --limit 100

# Monitor RAG building progress
./scripts/monitor_rag.sh
python scripts/monitor_progress.py

# Monitor all processes
./scripts/monitor_all.sh

# Test RAG search quality
python scripts/test_rag_search.py
python scripts/test_rag_simple.py
python scripts/rag_evaluator.py            # Evaluate RAG performance
```

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
