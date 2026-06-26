#!/usr/bin/env python
"""
Safe Parallel RAG Builder
생산자-소비자 패턴으로 안전한 병렬 처리
- 다중 프로세스: PDF 처리 + 임베딩 생성
- 단일 프로세스: 데이터베이스 쓰기 (SQLite 충돌 방지)
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

import chromadb
from FlagEmbedding import BGEM3FlagModel
import torch
from sentence_transformers import SentenceTransformer
import clip
from PIL import Image

# Data structures
@dataclass
class ProcessedChunk:
    chunk_id: str
    paper_id: str
    content: str
    embedding: List[float]
    metadata: Dict
    chunk_type: str = "text"

@dataclass
class ProcessedImage:
    image_id: str
    paper_id: str
    image_path: str
    caption: str
    embedding: List[float]
    metadata: Dict

class SafeRAGBuilder:
    def __init__(self, num_workers: int = 4, batch_size: int = 50):
        self.num_workers = num_workers
        self.batch_size = batch_size

        # Queues for producer-consumer pattern
        self.text_queue = mp.Queue(maxsize=1000)
        self.image_queue = mp.Queue(maxsize=1000)
        self.result_queue = mp.Queue(maxsize=1000)

        # Progress tracking
        self.text_processed = mp.Value('i', 0)
        self.image_processed = mp.Value('i', 0)
        self.total_papers = mp.Value('i', 0)

        # Stop flags
        self.stop_event = mp.Event()

        # Initialize models in main process (they'll be reloaded in workers)
        print("🔄 Initializing models...")

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
                    chunks = chunker.chunk_text(text, paper_id, metadata)

                    # Process each chunk
                    for chunk in chunks:
                        if self.stop_event.is_set():
                            break

                        # Generate embedding
                        embedding = model.encode(
                            chunk['content'],
                            batch_size=1,
                            max_length=8192
                        )['dense_vecs']

                        if len(embedding.shape) == 1:
                            embedding = embedding.tolist()
                        else:
                            embedding = embedding[0].tolist()

                        # Create processed chunk
                        processed = ProcessedChunk(
                            chunk_id=chunk['chunk_id'],
                            paper_id=paper_id,
                            content=chunk['content'],
                            embedding=embedding,
                            metadata=chunk['metadata'],
                            chunk_type="text"
                        )

                        # Send to result queue
                        self.result_queue.put(('text', processed))

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

    def image_worker(self, worker_id: int):
        """Worker process for image processing"""
        try:
            # Initialize CLIP model in worker
            device = "cuda" if torch.cuda.is_available() else "cpu"
            model, preprocess = clip.load("ViT-B/32", device=device)

            from text_extractor import extract_text_and_images

            print(f"🖼️ Image worker {worker_id} started")

            while not self.stop_event.is_set():
                try:
                    # Get paper from queue
                    paper = self.image_queue.get(timeout=5)
                    if paper is None:  # Poison pill
                        break

                    paper_id = paper['paper_id']
                    pdf_path = paper['pdf_path']
                    metadata = paper.get('metadata', {})

                    # Extract images
                    output_dir = f"./temp_images/{paper_id}"
                    os.makedirs(output_dir, exist_ok=True)

                    _, images, captions, _ = extract_text_and_images(pdf_path, output_dir, max_pages=None)

                    # Process each image
                    for i, (img_path, caption) in enumerate(zip(images, captions)):
                        if self.stop_event.is_set():
                            break

                        try:
                            # Load and preprocess image
                            image = Image.open(img_path).convert('RGB')
                            image_input = preprocess(image).unsqueeze(0).to(device)

                            # Generate embedding
                            with torch.no_grad():
                                embedding = model.encode_image(image_input)
                                embedding = embedding.cpu().numpy()[0].tolist()

                            # Create processed image
                            processed = ProcessedImage(
                                image_id=f"{paper_id}_img_{i}",
                                paper_id=paper_id,
                                image_path=img_path,
                                caption=caption,
                                embedding=embedding,
                                metadata={**metadata, 'page': i, 'image_type': 'extracted'}
                            )

                            # Send to result queue
                            self.result_queue.put(('image', processed))

                        except Exception as e:
                            print(f"Image processing error: {e}")
                            continue

                    with self.image_processed.get_lock():
                        self.image_processed.value += 1

                except Empty:
                    continue
                except Exception as e:
                    print(f"Image worker {worker_id} error: {e}")
                    continue

        except KeyboardInterrupt:
            pass
        finally:
            print(f"🖼️ Image worker {worker_id} finished")

    def database_writer(self):
        """Single thread for database writing to avoid SQLite conflicts"""
        try:
            # Initialize ChromaDB connections
            text_client = chromadb.PersistentClient('./text_rag_bge_m3_safe')
            try:
                text_collection = text_client.get_collection('text_papers_bge_m3')
            except:
                text_collection = text_client.create_collection(
                    'text_papers_bge_m3',
                    metadata={"hnsw:space": "cosine"}
                )

            image_client = chromadb.PersistentClient('./image_rag_clip_safe')
            try:
                image_collection = image_client.get_collection('image_papers_clip')
            except:
                image_collection = image_client.create_collection(
                    'image_papers_clip',
                    metadata={"hnsw:space": "cosine"}
                )

            print("💾 Database writer started")

            text_batch = []
            image_batch = []

            while not self.stop_event.is_set():
                try:
                    # Get processed item from queue
                    item_type, item = self.result_queue.get(timeout=5)

                    if item_type == 'text':
                        text_batch.append(item)
                        if len(text_batch) >= self.batch_size:
                            self._write_text_batch(text_collection, text_batch)
                            text_batch = []

                    elif item_type == 'image':
                        image_batch.append(item)
                        if len(image_batch) >= self.batch_size:
                            self._write_image_batch(image_collection, image_batch)
                            image_batch = []

                except Empty:
                    # Write remaining items
                    if text_batch:
                        self._write_text_batch(text_collection, text_batch)
                        text_batch = []
                    if image_batch:
                        self._write_image_batch(image_collection, image_batch)
                        image_batch = []
                    continue
                except Exception as e:
                    print(f"Database writer error: {e}")
                    continue

            # Final write
            if text_batch:
                self._write_text_batch(text_collection, text_batch)
            if image_batch:
                self._write_image_batch(image_collection, image_batch)

        except KeyboardInterrupt:
            pass
        finally:
            print("💾 Database writer finished")

    def _write_text_batch(self, collection, batch: List[ProcessedChunk]):
        """Write text batch to ChromaDB"""
        try:
            ids = [item.chunk_id for item in batch]
            embeddings = [item.embedding for item in batch]
            documents = [item.content for item in batch]
            metadatas = [item.metadata for item in batch]

            collection.add(
                ids=ids,
                embeddings=embeddings,
                documents=documents,
                metadatas=metadatas
            )

        except Exception as e:
            print(f"Error writing text batch: {e}")

    def _write_image_batch(self, collection, batch: List[ProcessedImage]):
        """Write image batch to ChromaDB"""
        try:
            ids = [item.image_id for item in batch]
            embeddings = [item.embedding for item in batch]
            documents = [item.caption for item in batch]
            metadatas = [item.metadata for item in batch]

            collection.add(
                ids=ids,
                embeddings=embeddings,
                documents=documents,
                metadatas=metadatas
            )

        except Exception as e:
            print(f"Error writing image batch: {e}")

    def progress_monitor(self):
        """Monitor and display progress"""
        while not self.stop_event.is_set():
            try:
                text_count = self.text_processed.value
                image_count = self.image_processed.value
                total = self.total_papers.value

                print(f"\r📊 Progress: Text {text_count}/{total} | Image {image_count}/{total} | Queue: {self.result_queue.qsize()}", end="")

                time.sleep(5)

            except KeyboardInterrupt:
                break

    def build_databases(self, papers: List[Dict]):
        """Main orchestration method"""
        try:
            print(f"\n🚀 Starting safe parallel RAG building with {self.num_workers} workers")

            # Start database writer thread
            writer_thread = Thread(target=self.database_writer)
            writer_thread.start()

            # Start progress monitor thread
            monitor_thread = Thread(target=self.progress_monitor)
            monitor_thread.start()

            # Start worker processes
            text_workers = []
            image_workers = []

            # Text workers
            for i in range(self.num_workers):
                p = mp.Process(target=self.text_worker, args=(i,))
                p.start()
                text_workers.append(p)

            # Image workers
            for i in range(self.num_workers):
                p = mp.Process(target=self.image_worker, args=(i,))
                p.start()
                image_workers.append(p)

            # Feed papers to queues
            for paper in papers:
                self.text_queue.put(paper)
                self.image_queue.put(paper)

            # Send poison pills
            for _ in range(self.num_workers):
                self.text_queue.put(None)
                self.image_queue.put(None)

            # Wait for workers to finish
            for p in text_workers:
                p.join()
            for p in image_workers:
                p.join()

            # Signal stop
            self.stop_event.set()

            # Wait for writer and monitor
            writer_thread.join()
            monitor_thread.join()

            print(f"\n✅ Safe parallel RAG building completed!")

        except KeyboardInterrupt:
            print("\n🛑 Interrupted by user")
            self.stop_event.set()

            # Terminate workers
            for p in text_workers:
                p.terminate()
            for p in image_workers:
                p.terminate()

            writer_thread.join(timeout=5)
            monitor_thread.join(timeout=5)

def signal_handler(signum, frame):
    """Handle Ctrl+C gracefully"""
    print("\n🛑 Stopping safely...")


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Safe parallel RAG builder")
    parser.add_argument("--workers", type=int, default=4, help="Number of worker processes")
    parser.add_argument("--batch-size", type=int, default=50, help="Database batch size")
    parser.add_argument("--papers", default="papers_batch.json", help="Papers batch file")

    args = parser.parse_args()

    # Set up signal handler
    signal.signal(signal.SIGINT, signal_handler)

    print(f"""
{'='*70}
🔧 Safe Parallel RAG Builder
{'='*70}
Workers: {args.workers}
Batch size: {args.batch_size}
Architecture: Producer-Consumer Pattern
- Multiple processes: PDF processing + embedding generation
- Single thread: Database writing (SQLite conflict prevention)
{'='*70}
    """)

    # Initialize builder
    builder = SafeRAGBuilder(
        num_workers=args.workers,
        batch_size=args.batch_size
    )

    # Load papers
    papers = builder.load_papers(args.papers)

    # Build databases
    builder.build_databases(papers)

    print(f"""
{'='*70}
✨ Safe RAG Building Complete!
{'='*70}
📝 Text DB: ./text_rag_bge_m3_safe/
📷 Image DB: ./image_rag_clip_safe/

Next steps:
1. Verify database integrity
2. Migrate to Pinecone if needed
3. Test search functionality
{'='*70}
    """)

if __name__ == "__main__":
    mp.set_start_method('spawn', force=True)  # For CUDA compatibility
    main()