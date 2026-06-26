## Critical Data Flow

**Batch Processing Flow (run_literature_batch.py)**
```
1. Validate environment variables → Exit if missing
2. Fetch Zotero items via API (pyzotero) → Build collection hierarchy
3. Filter items (--collection, --limit flags)
4. Check done.txt → Skip already processed items
5. Load checkpoint.json → Resume from interruption if exists
6. ThreadPoolExecutor spawns workers (default 5)
7. For each paper in parallel:
   a. Get PDF path from Zotero attachment metadata
   b. Download PDF if missing (pdf_downloader)
   c. Extract text + images (text_extractor)
   d. Generate summaries (gpt_summarizer or gemini_summarizer)
   e. Render markdown from template (markdown_writer)
   f. Write to OUTPUT_DIR/collection_path/Author_Year_Title.md
   g. Mark as done in done.txt (thread-safe)
   h. Save checkpoint every 10 papers
8. On completion or Ctrl+C → Save final checkpoint
```

**Sync System Flow**
```
1. sync_checker.py:
   - Read Zotero SQLite database (~/Zotero/zotero.sqlite)
   - Scan Obsidian OUTPUT_DIR for existing .md files
   - Compare item keys and collection paths
   - Output sync_report.json: {added: [...], deleted: [...], moved: [...]}

2. sync_executor.py:
   - Read sync_report.json (or run sync_checker inline)
   - Create backup tarball of OUTPUT_DIR
   - For moved items: mv file to new collection folder
   - For deleted items: mv file to _archived/{timestamp}/
   - Clean up empty directories

3. process_missing_papers.py:
   - Read sync_report.json["added"] list
   - Process using same pipeline as run_literature_batch.py
```

**RAG Building Flow**
```
1. Collect all PDFs from Zotero storage
2. Extract text using text_extractor
3. Split into chunks (section-aware or fixed-size with overlap)
4. Generate embeddings (sentence-transformers or OpenAI)
5. Store in vector DB:
   - ChromaDB: Local, persistent, ~100ms search for 10k papers
   - Pinecone: Cloud, scalable, ~50ms search regardless of size
6. Query: Text → Embedding → Similarity Search → Retrieve top K chunks
7. Answer: Retrieved chunks + GPT synthesis
```

## Thread Safety and Concurrency

**Thread-Safe Operations**
- `done.txt` writes: Protected by `done_lock` (threading.Lock)
- Progress bar updates: Protected by `progress_lock`
- Checkpoint saves: Protected by file-level locking
- File writes: Each worker writes to unique files (no conflicts)

**Not Thread-Safe (Sequential)**
- Checkpoint loading (happens before workers spawn)
- Environment validation (startup only)
- Collection hierarchy building (single API call)

**Worker Pool Configuration**
- Default: 5 workers (balances speed + API rate limits)
- Recommended: 5-10 workers for GPT processing
- Maximum: Limited by OpenAI API rate limits (tier-dependent)
- Each worker: 1 paper at a time, blocking on API calls

## Error Handling Patterns

- Missing PDFs: Use abstract for summarization instead (fallback)
- API rate limits: Exponential backoff (20s → 40s → 80s), then log + continue
- Invalid collection names: Show available collections, exit
- Missing environment variables: Validate before starting, exit with clear error
- PDF download failures: Detailed logging with common causes, continue processing
- Scanned PDFs (no text): Extract fails → use abstract or skip
- Thread exceptions: Log error, mark item as failed, continue with next item
- Checkpoint save errors: Log warning, continue (next checkpoint will retry)
