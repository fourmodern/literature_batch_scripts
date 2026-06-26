#!/usr/bin/env python3
"""
Re-embed texts from improved_vector_db with BGE-M3
"""

import os
import time
import chromadb
from FlagEmbedding import BGEM3FlagModel
from pinecone import Pinecone, ServerlessSpec
from tqdm import tqdm
from dotenv import load_dotenv

load_dotenv()

def reembed_texts():
    """Re-embed existing texts with BGE-M3"""

    print("="*70)
    print("🔄 Re-embedding texts with BGE-M3")
    print("="*70)

    # Load ChromaDB
    print("\n📂 Loading ChromaDB...")
    client = chromadb.PersistentClient(path="improved_vector_db")
    collection = client.list_collections()[0]
    print(f"Collection: {collection.name}")

    # Get all data with documents (texts)
    print("Fetching all texts from ChromaDB...")
    all_data = collection.get(include=['documents', 'metadatas'])
    total_texts = len(all_data['ids'])
    print(f"Found {total_texts} texts to re-embed")

    # Initialize BGE-M3
    print("\n🚀 Loading BGE-M3 model...")
    start = time.time()
    model = BGEM3FlagModel('BAAI/bge-m3', use_fp16=True)
    print(f"✅ Model loaded in {time.time() - start:.1f}s")

    # Initialize Pinecone
    print("\n🔑 Initializing Pinecone...")
    pc = Pinecone(api_key=os.getenv('PINECONE_API_KEY'))

    index_name = "text-papers-bge-m3-v2"

    # Delete if exists
    if index_name in [idx.name for idx in pc.list_indexes()]:
        print(f"Deleting existing {index_name}...")
        pc.delete_index(index_name)

    # Create new index
    print(f"Creating index {index_name}...")
    pc.create_index(
        name=index_name,
        dimension=1024,
        metric='cosine',
        spec=ServerlessSpec(cloud='aws', region='us-east-1')
    )

    index = pc.Index(index_name)

    # Process in batches
    batch_size = 32  # BGE-M3 batch size
    upload_batch = []
    upload_size = 100

    print(f"\n📊 Processing {total_texts} texts...")

    for i in tqdm(range(0, total_texts, batch_size), desc="Embedding"):
        batch_end = min(i + batch_size, total_texts)

        # Get batch texts
        batch_texts = []
        batch_ids = []
        batch_metadata = []

        for j in range(i, batch_end):
            text = all_data['documents'][j]
            if not text:
                continue

            batch_texts.append(text[:8192])  # BGE-M3 max length
            batch_ids.append(all_data['ids'][j])

            # Prepare metadata
            metadata = all_data['metadatas'][j] if all_data['metadatas'] else {}
            metadata['text'] = text[:1000]  # Truncate for metadata
            batch_metadata.append(metadata)

        if not batch_texts:
            continue

        # Generate embeddings
        embeddings = model.encode(
            batch_texts,
            batch_size=len(batch_texts),
            max_length=8192,
            return_dense=True,
            return_sparse=False,
            return_colbert_vecs=False
        )

        # Handle dict return
        if isinstance(embeddings, dict):
            embeddings = embeddings['dense_vecs']

        # Prepare for upload
        for id_, embedding, metadata in zip(batch_ids, embeddings, batch_metadata):
            upload_batch.append({
                'id': id_,
                'values': embedding.tolist() if hasattr(embedding, 'tolist') else embedding,
                'metadata': metadata
            })

        # Upload when batch is full
        if len(upload_batch) >= upload_size:
            index.upsert(vectors=upload_batch)
            upload_batch = []

    # Upload remaining
    if upload_batch:
        index.upsert(vectors=upload_batch)

    # Final stats
    print("\n✅ Complete!")
    stats = index.describe_index_stats()
    print(f"Total vectors in Pinecone: {stats['total_vector_count']}")
    print(f"Index: {index_name}")

if __name__ == "__main__":
    reembed_texts()