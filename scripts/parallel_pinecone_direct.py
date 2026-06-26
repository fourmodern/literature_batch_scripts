#!/usr/bin/env python
"""
Direct Parallel Pinecone RAG Builder
생산자-소비자 패턴으로 Pinecone에 직접 병렬 처리
- ChromaDB 건드리지 않고 Pinecone에 바로 쓰기
"""

import os
import sys
import json
import time
import multiprocessing as mp
from queue import Queue, Empty
from threading import Thread
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from tqdm import tqdm
import signal

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'scripts'))

from dotenv import load_dotenv
load_dotenv()

from pinecone import Pinecone, ServerlessSpec
from FlagEmbedding import BGEM3FlagModel

@dataclass
class ProcessedChunk:
    chunk_id: str
    paper_id: str
    content: str
    embedding: List[float]
    metadata: Dict
    chunk_type: str = "text"

class SafePineconeRAGBuilder:
    def __init__(self, num_workers: int = 4, batch_size: int = 100):
        self.num_workers = num_workers
        self.batch_size = batch_size

        # Queues for producer-consumer pattern
        self.text_queue = mp.Queue(maxsize=1000)
        self.result_queue = mp.Queue(maxsize=1000)

        # Progress tracking
        self.text_processed = mp.Value('i', 0)
        self.total_papers = mp.Value('i', 0)
        self.total_vectors = mp.Value('i', 0)

        # Stop flags
        self.stop_event = mp.Event()

        # Store index name for workers to initialize their own Pinecone connections
        self.index_name = None

    def init_pinecone(self):
        """Initialize Pinecone connection"""
        api_key = os.getenv("PINECONE_API_KEY")
        if not api_key:
            raise ValueError("PINECONE_API_KEY not found in .env")

        pc = Pinecone(api_key=api_key)

        # Create new index with timestamp
        index_name = "papers-multimodal-v2"

        existing_indexes = [idx.name for idx in pc.list_indexes()]

        if index_name in existing_indexes:
            print(f"⚠️ Index {index_name} already exists, deleting...")
            pc.delete_index(index_name)
            time.sleep(10)

        print(f"🔧 Creating new Pinecone index: {index_name}")
        pc.create_index(
            name=index_name,
            dimension=1024,  # BGE-M3 dimension
            metric="cosine",
            spec=ServerlessSpec(
                cloud="aws",
                region="us-east-1"
            )
        )

        time.sleep(15)  # Wait for index to be ready
        self.index_name = index_name
        print(f"✅ Pinecone index {index_name} ready")
        # Don't store pc object to avoid serialization issues
        return index_name

    def load_papers(self, batch_file: str = "papers_batch.json") -> List[Dict]:
        """Load papers from batch file"""
        papers = []
        with open(batch_file, 'r') as f:
            data = json.load(f)
            for item in data:
                if isinstance(item, dict) and 'pdf_path' in item:
                    papers.append({
                        'pdf_path': item['pdf_path'],
                        'paper_id': item.get('paper_id', Path(item['pdf_path']).stem),
                        'metadata': item.get('metadata', {})
                    })

        self.total_papers.value = len(papers)
        print(f"📚 Loaded {len(papers)} papers")
        return papers

    def text_worker(self, worker_id: int):
        """Worker process for text processing"""
        try:
            # Initialize BGE-M3 model in worker
            model = BGEM3FlagModel('BAAI/bge-m3', use_fp16=True)

            from text_extractor import extract_text_and_images
            from enhanced_text_chunker import EnhancedTextChunker

            chunker = EnhancedTextChunker()

            print(f"🔤 Text worker {worker_id} started")

            while not self.stop_event.is_set():
                try:
                    # Get paper from queue
                    paper = self.text_queue.get(timeout=5)
                    if paper is None:  # Poison pill
                        break

                    paper_id = paper['paper_id']
                    pdf_path = paper['pdf_path']
                    metadata = paper.get('metadata', {})

                    # Extract text
                    text, _, _, _ = extract_text_and_images(pdf_path, None, max_pages=None)

                    if not text or len(text) < 100:
                        continue

                    # Generate chunks
                    chunks = chunker.chunk_text(text, metadata)

                    # Process each chunk
                    for chunk in chunks:
                        if self.stop_event.is_set():
                            break

                        # Generate embedding
                        result = model.encode(
                            chunk['content'],
                            batch_size=1,
                            max_length=8192
                        )

                        # Handle both dict and array returns
                        if isinstance(result, dict):
                            embedding = result['dense_vecs']
                        else:
                            embedding = result

                        if len(embedding.shape) == 1:
                            embedding = embedding.tolist()
                        else:
                            embedding = embedding[0].tolist()

                        # Clean metadata for Pinecone
                        clean_metadata = {k: v for k, v in chunk['metadata'].items()
                                        if v is not None and isinstance(v, (str, int, float, bool))}

                        # Add text content (truncated for metadata size limits)
                        clean_metadata['text'] = chunk['content'][:1000] if chunk['content'] else ""

                        # Create processed chunk
                        processed = ProcessedChunk(
                            chunk_id=chunk['chunk_id'],
                            paper_id=paper_id,
                            content=chunk['content'],
                            embedding=embedding,
                            metadata=clean_metadata,
                            chunk_type="text"
                        )

                        # Send to result queue
                        self.result_queue.put(processed)

                    with self.text_processed.get_lock():
                        self.text_processed.value += 1

                except Empty:
                    continue
                except Exception as e:
                    print(f"Text worker {worker_id} error: {e}")
                    continue

        except KeyboardInterrupt:
            pass
        finally:
            print(f"🔤 Text worker {worker_id} finished")

    def pinecone_writer(self):
        """Single thread for Pinecone writing"""
        try:
            # Initialize Pinecone connection in this thread
            from pinecone import Pinecone
            pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
            index = pc.Index(self.index_name)

            print("💾 Pinecone writer started")

            batch = []

            while not self.stop_event.is_set():
                try:
                    # Get processed item from queue
                    item = self.result_queue.get(timeout=5)

                    # Prepare vector for Pinecone
                    vector = {
                        "id": item.chunk_id,
                        "values": item.embedding,
                        "metadata": item.metadata
                    }

                    batch.append(vector)

                    if len(batch) >= self.batch_size:
                        self._write_pinecone_batch(index, batch)
                        batch = []

                except Empty:
                    # Write remaining items
                    if batch:
                        self._write_pinecone_batch(index, batch)
                        batch = []
                    continue
                except Exception as e:
                    print(f"Pinecone writer error: {e}")
                    continue

            # Final write
            if batch:
                self._write_pinecone_batch(index, batch)

        except KeyboardInterrupt:
            pass
        finally:
            print("💾 Pinecone writer finished")

    def _write_pinecone_batch(self, index, batch: List[Dict]):
        """Write batch to Pinecone"""
        try:
            index.upsert(vectors=batch)

            with self.total_vectors.get_lock():
                self.total_vectors.value += len(batch)

            print(f"✅ Wrote batch of {len(batch)} vectors (Total: {self.total_vectors.value})")

        except Exception as e:
            print(f"Error writing Pinecone batch: {e}")

    def progress_monitor(self):
        """Monitor and display progress"""
        while not self.stop_event.is_set():
            try:
                text_count = self.text_processed.value
                total = self.total_papers.value
                vector_count = self.total_vectors.value

                print(f"\r📊 Progress: {text_count}/{total} papers | Vectors: {vector_count}", end="")

                time.sleep(5)

            except KeyboardInterrupt:
                break

    def build_databases(self, papers: List[Dict]):
        """Main orchestration method"""
        try:
            print(f"\n🚀 Starting direct Pinecone RAG building with {self.num_workers} workers")

            # Initialize Pinecone
            index_name = self.init_pinecone()

            # Start Pinecone writer thread
            writer_thread = Thread(target=self.pinecone_writer)
            writer_thread.start()

            # Start progress monitor thread
            monitor_thread = Thread(target=self.progress_monitor)
            monitor_thread.start()

            # Start worker processes
            text_workers = []

            # Text workers
            for i in range(self.num_workers):
                p = mp.Process(target=self.text_worker, args=(i,))
                p.start()
                text_workers.append(p)

            # Feed papers to queues
            for paper in papers:
                self.text_queue.put(paper)

            # Send poison pills
            for _ in range(self.num_workers):
                self.text_queue.put(None)

            # Wait for workers to finish
            for p in text_workers:
                p.join()

            # Signal stop
            self.stop_event.set()

            # Wait for writer and monitor
            writer_thread.join()
            monitor_thread.join()

            # Final stats
            from pinecone import Pinecone
            pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
            index = pc.Index(index_name)
            stats = index.describe_index_stats()
            print(f"\n✅ Direct Pinecone RAG building completed!")
            print(f"📊 Final stats: {stats['total_vector_count']} vectors in Pinecone")
            print(f"🎯 Index name: {index_name}")

        except KeyboardInterrupt:
            print("\n🛑 Interrupted by user")
            self.stop_event.set()

            # Terminate workers
            for p in text_workers:
                p.terminate()

            writer_thread.join(timeout=5)
            monitor_thread.join(timeout=5)

def signal_handler(signum, frame):
    """Handle Ctrl+C gracefully"""
    print("\n🛑 Stopping safely...")

def main():
    import argparse

    parser = argparse.ArgumentParser(description="Direct parallel Pinecone RAG builder")
    parser.add_argument("--workers", type=int, default=4, help="Number of worker processes")
    parser.add_argument("--batch-size", type=int, default=100, help="Pinecone batch size")
    parser.add_argument("--papers", default="papers_batch.json", help="Papers batch file")

    args = parser.parse_args()

    # Set up signal handler
    signal.signal(signal.SIGINT, signal_handler)

    print(f"""
{'='*70}
🔧 Direct Parallel Pinecone RAG Builder
{'='*70}
Workers: {args.workers}
Batch size: {args.batch_size}
Architecture: Producer-Consumer Pattern → Direct to Pinecone
- Multiple processes: PDF processing + BGE-M3 embedding generation
- Single thread: Pinecone writing (no SQLite conflicts)
- Clean slate: New index created for fresh start
{'='*70}
    """)

    # Check API key
    if not os.getenv("PINECONE_API_KEY"):
        print("❌ PINECONE_API_KEY not found in .env file")
        return

    # Initialize builder
    builder = SafePineconeRAGBuilder(
        num_workers=args.workers,
        batch_size=args.batch_size
    )

    # Load papers
    papers = builder.load_papers(args.papers)

    # Build databases
    builder.build_databases(papers)

    print(f"""
{'='*70}
✨ Direct Pinecone RAG Building Complete!
{'='*70}
🎯 New Pinecone Index: papers-multimodal-v2

Expected results:
- ~70,000 text vectors from 714 papers
- No data loss due to SQLite conflicts
- Ready for immediate search

Next steps:
1. Test search functionality
2. Add image embeddings if needed
3. Compare with previous 16,185 vectors
{'='*70}
    """)

if __name__ == "__main__":
    mp.set_start_method('spawn', force=True)
    main()