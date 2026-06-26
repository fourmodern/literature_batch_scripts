#!/usr/bin/env python
"""
Parallel RAG Database Builder
714개의 논문을 병렬로 처리하여 ChromaDB와 Pinecone에 저장
"""

import json
import os
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import time
from datetime import datetime

def split_batch(papers, num_workers=10):
    """논문 리스트를 여러 워커로 분할"""
    batch_size = len(papers) // num_workers + (1 if len(papers) % num_workers else 0)
    batches = []

    for i in range(0, len(papers), batch_size):
        batch = papers[i:i + batch_size]
        if batch:
            batches.append(batch)

    return batches

def create_worker_batch(papers, worker_id, output_dir="worker_batches"):
    """워커용 배치 파일 생성"""
    os.makedirs(output_dir, exist_ok=True)
    batch_file = f"{output_dir}/worker_{worker_id}_batch.json"

    with open(batch_file, 'w', encoding='utf-8') as f:
        json.dump(papers, f, ensure_ascii=False, indent=2)

    return batch_file

def process_batch(worker_id, batch_file, db_type="chroma"):
    """단일 배치 처리"""
    log_file = f"logs/worker_{worker_id}_{db_type}.log"
    os.makedirs("logs", exist_ok=True)

    cmd = [
        "/opt/homebrew/anaconda3/envs/zot/bin/python",
        "scripts/improved_rag_builder.py",
        "--batch", batch_file,
        "--db", db_type
    ]

    print(f"🚀 Worker {worker_id} started for {db_type} with {batch_file}")

    with open(log_file, 'w') as log:
        try:
            process = subprocess.run(
                cmd,
                stdout=log,
                stderr=subprocess.STDOUT,
                text=True,
                env={**os.environ, "PYTHONUNBUFFERED": "1"}
            )

            if process.returncode == 0:
                print(f"✅ Worker {worker_id} completed for {db_type}")
                return True
            else:
                print(f"❌ Worker {worker_id} failed for {db_type}")
                return False

        except Exception as e:
            print(f"❌ Worker {worker_id} error: {e}")
            return False

def main():
    print("=" * 60)
    print("🚀 Parallel RAG Database Builder")
    print("=" * 60)

    # Load all papers
    with open("papers_batch.json", 'r', encoding='utf-8') as f:
        all_papers = json.load(f)

    print(f"📚 Total papers: {len(all_papers)}")

    # Number of parallel workers
    NUM_WORKERS = 8  # 8개 워커로 병렬 처리

    # Split papers into batches
    batches = split_batch(all_papers, NUM_WORKERS)
    print(f"📦 Split into {len(batches)} batches (~{len(batches[0])} papers each)")

    # Create worker batch files
    batch_files = []
    for i, batch in enumerate(batches):
        batch_file = create_worker_batch(batch, i)
        batch_files.append((i, batch_file))
        print(f"  - Worker {i}: {len(batch)} papers")

    print("\n" + "=" * 60)
    print("🏃 Starting parallel processing...")
    print("=" * 60)

    start_time = time.time()

    # Process ChromaDB and Pinecone in parallel
    with ThreadPoolExecutor(max_workers=NUM_WORKERS * 2) as executor:
        futures = []

        # Submit ChromaDB tasks
        print("\n📊 ChromaDB Processing:")
        for worker_id, batch_file in batch_files:
            future = executor.submit(process_batch, f"{worker_id}_chroma", batch_file, "chroma")
            futures.append((future, f"Worker {worker_id} ChromaDB"))

        # Submit Pinecone tasks
        print("\n📊 Pinecone Processing:")
        for worker_id, batch_file in batch_files:
            future = executor.submit(process_batch, f"{worker_id}_pinecone", batch_file, "pinecone")
            futures.append((future, f"Worker {worker_id} Pinecone"))

        # Wait for completion
        completed = 0
        total = len(futures)

        print(f"\n⏳ Processing {total} tasks in parallel...")
        for future, name in futures:
            try:
                result = future.result()
                completed += 1
                print(f"[{completed}/{total}] {name}: {'✅ Success' if result else '❌ Failed'}")
            except Exception as e:
                completed += 1
                print(f"[{completed}/{total}] {name}: ❌ Error - {e}")

    elapsed = time.time() - start_time
    print("\n" + "=" * 60)
    print(f"✨ Completed in {elapsed/60:.1f} minutes")
    print(f"📊 Processing rate: {len(all_papers)/(elapsed/60):.1f} papers/minute")
    print("=" * 60)

if __name__ == "__main__":
    main()