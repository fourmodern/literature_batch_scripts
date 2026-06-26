## Architecture

### Literature Processing Pipeline
1. **Zotero API** → Fetch paper metadata and collection hierarchy via pyzotero
2. **PDF Location** → Auto-detect Zotero storage directory (~/Zotero/storage/)
3. **PDF Download** → Automatically download missing PDFs from Zotero server
4. **Text Extraction** → Extract full text from PDFs using PyMuPDF (fallback to pdfplumber)
5. **AI Summarization** → Generate short (5 lines) and detailed (1 page) summaries via GPT
6. **Markdown Generation** → Create structured notes using Jinja2 templates
7. **Folder Organization** → Mirror Zotero collection structure in output directory

### RAG System Pipeline
1. **PDF Processing** → Extract text and images from PDFs
2. **Chunking** → Split text into semantic chunks (sections, paragraphs with overlap)
3. **Embedding** → Generate vector embeddings using sentence-transformers or CLIP
4. **Vector Storage** → Store in ChromaDB (local) or Pinecone (cloud)
5. **Query Processing** → Convert user queries to embeddings
6. **Similarity Search** → Find relevant chunks using cosine similarity
7. **Answer Generation** → Use GPT to synthesize answers from retrieved contexts

### Key Design Decisions

**Zotero Integration**
- Uses pyzotero API to fetch metadata directly (no export files needed)
- Automatically detects Zotero data directory across platforms
- Preserves collection hierarchy as folder structure
- Handles standard Zotero storage pattern: `storage/[8-char-key]/filename.pdf`
- **Pagination support**: Fetches all items (not limited to 100) with automatic batching

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

### Module Responsibilities

**Core Processing**
- `run_literature_batch.py`: Main orchestrator, CLI handling, progress tracking, parallel processing coordination
  - ThreadPoolExecutor for parallel processing (default 5 workers)
  - Progress tracking with `tqdm` and thread-safe locks
  - Checkpoint system saves every 10 papers to `logs/checkpoint.json`
  - Graceful shutdown on Ctrl+C with automatic checkpoint save
- `process_single_pdf.py`: Process individual PDF files without Zotero, extract metadata from PDF content
- `process_zotero_pdf.py`: Process single Zotero storage PDF with full metadata from API
- `run_all_in_one.py`: Combined pipeline for processing papers and building RAG database

**Data Extraction**
- `zotero_fetch.py`: Zotero API interaction, collection hierarchy building, pagination handling
  - Uses pyzotero library for Zotero API v3 access
  - Recursive collection hierarchy building (parent-child relationships)
  - Handles pagination automatically (fetches all items, not just first 100)
  - Collection filtering by name with case-insensitive partial matching
- `text_extractor.py`: PDF text extraction with PyMuPDF fallback to pdfplumber, image extraction for multimodal processing
  - Primary: PyMuPDF (fitz) for fast extraction
  - Fallback: pdfplumber for problematic PDFs
  - Image extraction with page number and position metadata
  - Figure/table caption detection
- `zotero_path_finder.py`: Cross-platform Zotero directory detection
  - Auto-detects: ~/Zotero, ~/Documents/Zotero, ~/.zotero/zotero
  - Platform-specific paths (macOS, Windows, Linux)
- `pdf_downloader.py`: Downloads missing PDFs from Zotero server with retry logic
  - Uses Zotero API `/items/<key>/file` endpoint
  - Checks for existing files before downloading
  - Exponential backoff on failures

**AI Summarization**
- `gpt_summarizer.py`: OpenAI API calls with rate limit handling, prompt management, Korean language summaries, caching support
  - Dynamic model selection based on text length (gpt-4o-mini default)
  - Response caching (24h TTL) to avoid duplicate API calls
  - Smart text truncation preserving Abstract/Methods/Results sections
  - Exponential backoff: 20s → 40s → 80s on rate limits
  - Temperature 0.3 for factual consistency
- `gemini_summarizer.py`: Google Gemini API calls with multimodal support (text + images)
  - Processes text + extracted images together
  - Selects "featured image" (most important figure)
  - Image context included in summaries
- `api_cost_optimizer.py`: API cost optimization utilities
  - Smart model selection based on task complexity
  - Response caching to reduce API calls
  - Text truncation strategies

**RAG System**
- `text_only_rag_builder.py`: Builds text-based vector database using ChromaDB/Pinecone with sentence-transformers
  - Section-aware chunking (Abstract, Methods, Results, etc.)
  - Configurable chunk size (default 1000 chars) with overlap (default 200 chars)
  - Supports multiple embedding models (sentence-transformers, OpenAI)
- `vision_language_rag_builder.py`: Multimodal RAG with CLIP embeddings for text and images
- `build_text_fast.py`: Fast parallel text embedding with multiple workers
- `build_multimodal_rag.py`: Multimodal database builder
- `build_all_fast.py`: Parallel builder for all RAG modalities at once
- `search_examples.py`: Text-based semantic search interface
- `search_multimodal.py`: Multimodal search supporting text and image queries
- `hybrid_searcher.py`: Combines text and image similarity search
- `simple_bge_builder.py`: Simple BGE-M3 based RAG builder (recommended for Korean)
- `migrate_to_pinecone.py`: Migrate ChromaDB to Pinecone cloud
- `check_pinecone_status.py`: Verify Pinecone index health and stats

**Sync System**
- `sync_checker.py`: Compare Zotero SQLite database with Obsidian folder to find differences
  - Reads Zotero database directly (~/Zotero/zotero.sqlite)
  - Identifies Added (in Zotero only), Deleted (in Obsidian only), Moved (collection changed)
  - Outputs JSON report for automated processing
- `sync_executor.py`: Execute sync operations based on sync_checker results
  - Moves files to new collection folders (for Moved items)
  - Archives deleted items to `_archived/{date}/` (doesn't delete)
  - Creates `.tar.gz` backup before any changes
  - Cleans up empty directories after moves
- `process_missing_papers.py`: Process papers from sync report JSON
  - Reads sync_report.json from sync_checker
  - Processes only "added" items (new papers in Zotero)
  - Uses same processing pipeline as run_literature_batch.py
- `zotero_auto_sync.py`: Automated sync daemon
  - Runs sync_checker + process_missing_papers in a loop
  - Configurable check interval (default: hourly)

**Utilities**
- `markdown_writer.py`: Template rendering, file writing, Obsidian-compatible formatting
  - Uses Jinja2 templates from `templates/literature_note.md`
  - Handles Obsidian frontmatter (YAML metadata)
  - Generates Zotero links (web + desktop app)
  - Embeds PDF links (file:// or relative paths)
- `markdown_writer_enhanced.py`: Enhanced markdown writer with additional features
- `utils.py`: Logging, progress tracking, checkpoint management
  - Checkpoint format: JSON with processed items list + current index
  - `done.txt` tracking: one Zotero key per line
  - Thread-safe file operations with locks
- `create_batch_file.py`: Generate JSON batch files for bulk PDF processing
- `test_pdf_extraction.py`: Diagnostic tool for debugging PDF extraction issues
  - Shows file sizes, page counts, extraction quality
  - Identifies scanned PDFs (image-based, no text layer)
  - Displays first few lines of extracted text
- `check_zotero_sync.py`: Diagnostic tool for verifying Zotero file sync status
  - Checks which PDFs are synced to Zotero servers
  - Identifies local-only PDFs
- `paper_finder.py`: Search and locate specific papers in the system
- `count_preprints.py`: Count preprints in collections
- `monitor_progress.py`: Monitor processing progress in real-time
  - Tail logs/summary.log for live updates
  - Display progress bars and statistics
