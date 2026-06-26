## Common Debugging Scenarios

**Issue: PDFs not extracting text**
```bash
# Diagnose extraction quality
python scripts/test_pdf_extraction.py

# Check specific collection
python scripts/test_pdf_extraction.py "CollectionName"

# Common causes:
# - Scanned PDFs (image-based, no text layer) → Consider OCR
# - Encrypted PDFs → Check if they open in PDF viewer
# - Corrupted files → Re-download from publisher
```

**Issue: API rate limits**
```bash
# Reduce worker count
python scripts/run_literature_batch.py --workers 2

# Use caching (enabled by default)
# Cache location: ~/.openai_cache/ (24h TTL)

# Check your API tier at platform.openai.com
# Tier 1: ~500 RPM, Tier 2: ~5000 RPM
```

**Issue: Papers not syncing from Zotero**
```bash
# Check Zotero sync status
python scripts/check_zotero_sync.py

# Force sync in Zotero desktop
# Settings → Sync → Sync Now (Cmd/Ctrl+S)

# Check storage quota at zotero.org/settings/storage
```

**Issue: Parallel processing hanging**
```bash
# Check for deadlocks in logs
tail -f logs/summary.log

# Kill hung processes
ps aux | grep python | grep run_literature_batch
kill -9 <PID>

# Resume from checkpoint
python scripts/run_literature_batch.py --resume
```

**Issue: Obsidian files out of sync with Zotero**
```bash
# Check sync status
python scripts/sync_checker.py --output sync_report.json

# Preview what would change
python scripts/sync_executor.py --dry-run

# Execute sync (creates backup first)
python scripts/sync_executor.py

# Process new papers
python scripts/process_missing_papers.py --from-json sync_report.json
```

**Issue: RAG database not finding relevant papers**
```bash
# Check index status
python scripts/check_pinecone_status.py  # For Pinecone
# OR check ChromaDB directory: ./chroma_db/

# Rebuild index
python scripts/build_all_fast.py

# Test search quality
python scripts/test_rag_search.py
python scripts/rag_evaluator.py  # Run benchmark tests
```

**Issue: Environment variables not loading**
```bash
# Check .env location (must be in project root)
ls -la .env

# Verify variables are set
python -c "from dotenv import load_dotenv; import os; load_dotenv(); print(os.getenv('ZOTERO_USER_ID'))"

# Common issue: .env in wrong directory
# Should be: literature_batch_scripts/.env
# Not: literature_batch_scripts/scripts/.env
```
