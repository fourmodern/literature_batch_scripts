#!/usr/bin/env python3
"""
Fast parallel BGE-M3 embedding with direct Pinecone upload
Using threading for I/O-bound operations
"""

import os
import time
import chromadb
from FlagEmbedding import BGEM3FlagModel
from pinecone import Pinecone, ServerlessSpec
from tqdm import tqdm
from dotenv import load_dotenv
import threading
from queue import Queue
import numpy as np

load_dotenv()

def upload_worker(queue, index):
    """Worker thread for uploading to Pinecone"""
    while True:
        batch = queue.get()
        if batch is None:
            break
        try:
            index.upsert(vectors=batch)
        except Exception as e:
            print(f"Upload error: {e}")
        queue.task_done()

def main():
    print("="*70)
    print("🚀 Fast Parallel BGE-M3 Embedding")
    print("="*70)

    # Load ChromaDB
    print("\n📂 Loading ChromaDB...")
    client = chromadb.PersistentClient(path="improved_vector_db")
    collection = client.list_collections()[0]

    # Get count
    total = collection.count()
    print(f"Total texts: {total}")

    # Load BGE-M3
    print("\n🤖 Loading BGE-M3...")
    start = time.time()
    model = BGEM3FlagModel('BAAI/bge-m3', use_fp16=True)
    print(f"✅ Loaded in {time.time()-start:.1f}s")

    # Initialize Pinecone
    print("\n📌 Initializing Pinecone...")
    pc = Pinecone(api_key=os.getenv('PINECONE_API_KEY'))

    # Delete empty indexes first
    empty_indexes = ["papers-multimodal-v2", "text-papers-bge-m3", "simple-bge-m3"]
    for idx in empty_indexes:
        if idx in [i.name for i in pc.list_indexes()]:
            print(f"Deleting empty index: {idx}")
            pc.delete_index(idx)

    index_name = "text-papers-bge-m3-v2"

    # Use existing index or create new
    if index_name not in [idx.name for idx in pc.list_indexes()]:
        pc.create_index(
            name=index_name,
            dimension=1024,
            metric='cosine',
            spec=ServerlessSpec(cloud='aws', region='us-east-1')
        )

    index = pc.Index(index_name)

    # Setup upload queue and workers
    upload_queue = Queue(maxsize=10)
    upload_threads = []

    for _ in range(3):  # 3 upload threads
        t = threading.Thread(target=upload_worker, args=(upload_queue, index))
        t.start()
        upload_threads.append(t)

    # Process in larger batches
    batch_size = 256  # Larger batch for efficiency
    chunk_size = 100  # Upload chunk size

    print(f"\n⚡ Processing {total} texts...")

    processed = 0
    upload_batch = []

    with tqdm(total=total) as pbar:
        offset = 0

        while offset < total:
            # Get large batch from ChromaDB
            limit = min(batch_size, total - offset)
            data = collection.get(
                limit=limit,
                offset=offset,
                include=['documents', 'metadatas']
            )

            if not data['ids']:
                break

            # Prepare texts
            texts = []
            valid_indices = []

            for i, doc in enumerate(data['documents']):
                if doc and len(doc) > 10:
                    texts.append(doc[:8192])
                    valid_indices.append(i)

            if texts:
                # Batch encode all at once
                embeddings = model.encode(
                    texts,
                    batch_size=len(texts),
                    max_length=8192,
                    return_dense=True,
                    return_sparse=False,
                    return_colbert_vecs=False
                )

                # Handle dict return
                if isinstance(embeddings, dict):
                    embeddings = embeddings['dense_vecs']

                # Prepare upload data
                for idx, emb_idx in enumerate(valid_indices):
                    vec_id = data['ids'][emb_idx]
                    metadata = data['metadatas'][emb_idx] if data['metadatas'] else {}
                    metadata['text'] = data['documents'][emb_idx][:1000]

                    upload_batch.append({
                        'id': vec_id,
                        'values': embeddings[idx].tolist() if hasattr(embeddings[idx], 'tolist') else embeddings[idx],
                        'metadata': metadata
                    })

                    # Queue for upload when chunk is ready
                    if len(upload_batch) >= chunk_size:
                        upload_queue.put(upload_batch[:chunk_size])
                        upload_batch = upload_batch[chunk_size:]

            processed += len(data['ids'])
            pbar.update(len(data['ids']))
            offset += limit

    # Upload remaining
    if upload_batch:
        upload_queue.put(upload_batch)

    # Wait for uploads to complete
    upload_queue.join()

    # Stop workers
    for _ in upload_threads:
        upload_queue.put(None)
    for t in upload_threads:
        t.join()

    # Final stats
    print("\n✅ Complete!")
    stats = index.describe_index_stats()
    print(f"Vectors in Pinecone: {stats['total_vector_count']}")
    print(f"Index: {index_name}")

if __name__ == "__main__":
    main()