#!/usr/bin/env python
"""
Fast Parallel RAG Builder with multiprocessing
"""

import json
import multiprocessing as mp
from pathlib import Path
import time
from datetime import datetime
import sys
import os

# Add scripts directory to path
sys.path.insert(0, 'scripts')

def process_paper_batch(args):
    """Process a batch of papers (worker function)"""
    worker_id, papers, db_type, start_idx = args

    # Import here to avoid pickling issues
    from improved_rag_builder import ImprovedRAGBuilder

    print(f"[Worker {worker_id}] Starting {len(papers)} papers for {db_type} (indices {start_idx}-{start_idx+len(papers)-1})")

    try:
        builder = ImprovedRAGBuilder(
            db_type=db_type,
            collection_name=f"rag_papers_{datetime.now().strftime('%Y%m%d')}"
        )

        success_count = 0
        for i, paper in enumerate(papers):
            paper_num = start_idx + i + 1
            try:
                print(f"[Worker {worker_id}] Processing [{paper_num}/714] {paper['key']}")
                builder.process_paper(paper)
                success_count += 1
            except Exception as e:
                print(f"[Worker {worker_id}] Error processing {paper['key']}: {e}")

        print(f"[Worker {worker_id}] Completed: {success_count}/{len(papers)} papers processed")
        return success_count

    except Exception as e:
        print(f"[Worker {worker_id}] Fatal error: {e}")
        return 0

def main():
    print("=" * 60)
    print("🚀 Fast Parallel RAG Database Builder")
    print("=" * 60)

    # Load papers
    with open("papers_batch.json", 'r', encoding='utf-8') as f:
        all_papers = json.load(f)

    print(f"📚 Total papers: {len(all_papers)}")

    # Use CPU count for workers (but cap at 8 to avoid overload)
    num_workers = min(mp.cpu_count(), 8)
    print(f"🔧 Using {num_workers} parallel workers")

    # Split papers into batches
    batch_size = len(all_papers) // num_workers + (1 if len(all_papers) % num_workers else 0)
    batches = []

    for i in range(0, len(all_papers), batch_size):
        batch = all_papers[i:i + batch_size]
        if batch:
            batches.append((len(batches), batch, "chroma", i))  # worker_id, papers, db_type, start_idx

    print(f"📦 Split into {len(batches)} batches (~{batch_size} papers each)")

    # Process in parallel
    start_time = time.time()

    print("\n🏃 Starting parallel processing for ChromaDB...")
    print("=" * 60)

    with mp.Pool(num_workers) as pool:
        results = pool.map(process_paper_batch, batches)

    total_processed = sum(results)
    elapsed = time.time() - start_time

    print("\n" + "=" * 60)
    print(f"✅ ChromaDB Complete: {total_processed}/{len(all_papers)} papers")
    print(f"⏱️ Time: {elapsed/60:.1f} minutes")
    print(f"📊 Rate: {total_processed/(elapsed/60):.1f} papers/minute")

    # Now process Pinecone (can reuse same batches)
    print("\n🏃 Starting parallel processing for Pinecone...")
    print("=" * 60)

    # Update batches for Pinecone
    pinecone_batches = [(b[0], b[1], "pinecone", b[3]) for b in batches]

    start_time = time.time()

    with mp.Pool(num_workers) as pool:
        results = pool.map(process_paper_batch, pinecone_batches)

    total_processed = sum(results)
    elapsed = time.time() - start_time

    print("\n" + "=" * 60)
    print(f"✅ Pinecone Complete: {total_processed}/{len(all_papers)} papers")
    print(f"⏱️ Time: {elapsed/60:.1f} minutes")
    print(f"📊 Rate: {total_processed/(elapsed/60):.1f} papers/minute")
    print("=" * 60)

if __name__ == "__main__":
    # Required for multiprocessing on macOS
    mp.set_start_method('spawn', force=True)
    main()