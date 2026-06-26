#!/usr/bin/env python
"""
Safe Pinecone Migration
ID 기반 접근으로 ChromaDB 오류 회피
"""

import os
import sys
import json
import time
from pathlib import Path
from typing import List, Dict
from tqdm import tqdm
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'scripts'))

from dotenv import load_dotenv
load_dotenv()

import chromadb
import pinecone
from pinecone import Pinecone, ServerlessSpec


def init_pinecone():
    """Initialize Pinecone connection"""
    api_key = os.getenv("PINECONE_API_KEY")
    if not api_key:
        raise ValueError("PINECONE_API_KEY not found in .env")

    pc = Pinecone(api_key=api_key)
    return pc


def migrate_text_safe():
    """Safe text migration using ID-based retrieval"""
    print("\n📝 Safe Text Database Migration...")

    # Load from ChromaDB
    client = chromadb.PersistentClient('./text_rag_bge_m3')
    collection = client.get_collection('text_papers_bge_m3')

    # Get IDs first
    all_ids = collection.get(limit=1)
    print("Testing collection access...")

    # Get collection count
    count = collection.count()
    print(f"Found {count} text chunks in ChromaDB")

    if count == 0:
        print("No data to migrate")
        return

    # Initialize Pinecone
    pc = init_pinecone()

    # Create or get index
    index_name = "text-papers-bge-m3"

    existing_indexes = [idx.name for idx in pc.list_indexes()]

    if index_name not in existing_indexes:
        print(f"Creating Pinecone index: {index_name}")
        pc.create_index(
            name=index_name,
            dimension=1024,  # BGE-M3 dimension
            metric="cosine",
            spec=ServerlessSpec(
                cloud="aws",
                region="us-east-1"
            )
        )
        time.sleep(10)

    index = pc.Index(index_name)

    # Batch process with smaller chunks
    batch_size = 50
    offset = 0
    total_uploaded = 0

    print(f"Starting migration in batches of {batch_size}...")

    with tqdm(total=count) as pbar:
        while offset < count:
            try:
                # Get batch data directly with all fields
                batch_data = collection.get(
                    limit=batch_size,
                    offset=offset,
                    include=['embeddings', 'documents', 'metadatas']
                )

                if not batch_data['ids']:
                    break

                # Prepare vectors
                vectors = []
                for i in range(len(batch_data['ids'])):
                    metadata = batch_data['metadatas'][i] or {}

                    # Clean metadata - remove None values
                    clean_metadata = {k: v for k, v in metadata.items() if v is not None}

                    # Add document text if exists
                    if batch_data['documents'][i]:
                        clean_metadata['text'] = batch_data['documents'][i][:1000]  # Limit text size

                    # Ensure embedding exists (handle numpy arrays)
                    embedding = batch_data['embeddings'][i]
                    if embedding is not None and len(embedding) > 0:
                        # Convert to list if it's a numpy array
                        if hasattr(embedding, 'tolist'):
                            embedding = embedding.tolist()
                        vectors.append({
                            "id": batch_data['ids'][i],
                            "values": embedding,
                            "metadata": clean_metadata
                        })

                # Upload to Pinecone
                if vectors:
                    index.upsert(vectors=vectors)
                    total_uploaded += len(vectors)

                pbar.update(len(batch_data['ids']))
                offset += batch_size

            except Exception as e:
                print(f"\nError at offset {offset}: {e}")
                # Skip this batch and continue
                offset += batch_size
                pbar.update(batch_size)
                continue

    # Get final stats
    stats = index.describe_index_stats()
    print(f"✅ Text DB migrated: {total_uploaded}/{count} chunks")
    print(f"   Pinecone vectors: {stats['total_vector_count']}")

    return index_name


def migrate_image_safe():
    """Safe image migration using ID-based retrieval"""
    print("\n📷 Safe Image Database Migration...")

    # Load from ChromaDB
    client = chromadb.PersistentClient('./image_rag_clip')
    collection = client.get_collection('image_papers_clip')

    # Get collection count
    count = collection.count()
    print(f"Found {count} image embeddings in ChromaDB")

    if count == 0:
        print("No data to migrate")
        return

    # Initialize Pinecone
    pc = init_pinecone()

    # Create or get index
    index_name = "image-papers-clip"

    existing_indexes = [idx.name for idx in pc.list_indexes()]

    if index_name not in existing_indexes:
        print(f"Creating Pinecone index: {index_name}")
        pc.create_index(
            name=index_name,
            dimension=512,  # CLIP dimension
            metric="cosine",
            spec=ServerlessSpec(
                cloud="aws",
                region="us-east-1"
            )
        )
        time.sleep(10)

    index = pc.Index(index_name)

    # Batch process
    batch_size = 50
    offset = 0
    total_uploaded = 0

    print(f"Starting migration in batches of {batch_size}...")

    with tqdm(total=count) as pbar:
        while offset < count:
            try:
                # Get batch data directly with all fields
                batch_data = collection.get(
                    limit=batch_size,
                    offset=offset,
                    include=['embeddings', 'documents', 'metadatas']
                )

                if not batch_data['ids']:
                    break

                # Prepare vectors
                vectors = []
                for i in range(len(batch_data['ids'])):
                    metadata = batch_data['metadatas'][i] or {}

                    # Clean metadata
                    clean_metadata = {k: v for k, v in metadata.items() if v is not None}

                    # Add caption if exists
                    if batch_data['documents'][i]:
                        clean_metadata['caption'] = batch_data['documents'][i][:500]

                    # Ensure embedding exists (handle numpy arrays)
                    embedding = batch_data['embeddings'][i]
                    if embedding is not None and len(embedding) > 0:
                        # Convert to list if it's a numpy array
                        if hasattr(embedding, 'tolist'):
                            embedding = embedding.tolist()
                        vectors.append({
                            "id": batch_data['ids'][i],
                            "values": embedding,
                            "metadata": clean_metadata
                        })

                # Upload to Pinecone
                if vectors:
                    index.upsert(vectors=vectors)
                    total_uploaded += len(vectors)

                pbar.update(len(batch_data['ids']))
                offset += batch_size

            except Exception as e:
                print(f"\nError at offset {offset}: {e}")
                # Skip this batch
                offset += batch_size
                pbar.update(batch_size)
                continue

    # Get final stats
    stats = index.describe_index_stats()
    print(f"✅ Image DB migrated: {total_uploaded}/{count} embeddings")
    print(f"   Pinecone vectors: {stats['total_vector_count']}")

    return index_name


def test_pinecone_search():
    """Test Pinecone search functionality"""
    print("\n🧪 Testing Pinecone Search...")

    pc = init_pinecone()

    # Test text search
    try:
        text_index = pc.Index("text-papers-bge-m3")
        stats = text_index.describe_index_stats()
        print(f"\n📝 Text Index Stats:")
        print(f"   Total vectors: {stats['total_vector_count']}")

        # Sample query
        query_vector = np.random.random(1024).tolist()
        results = text_index.query(
            vector=query_vector,
            top_k=3,
            include_metadata=True
        )

        print(f"   Sample search: {len(results['matches'])} results found")
        if results['matches']:
            print(f"   Top result score: {results['matches'][0]['score']:.3f}")

    except Exception as e:
        print(f"Text search error: {e}")

    # Test image search
    try:
        image_index = pc.Index("image-papers-clip")
        stats = image_index.describe_index_stats()
        print(f"\n📷 Image Index Stats:")
        print(f"   Total vectors: {stats['total_vector_count']}")

        # Sample query
        query_vector = np.random.random(512).tolist()
        results = image_index.query(
            vector=query_vector,
            top_k=3,
            include_metadata=True
        )

        print(f"   Sample search: {len(results['matches'])} results found")
        if results['matches']:
            print(f"   Top result score: {results['matches'][0]['score']:.3f}")

    except Exception as e:
        print(f"Image search error: {e}")


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Safe ChromaDB to Pinecone migration")
    parser.add_argument("--text-only", action="store_true", help="Migrate only text DB")
    parser.add_argument("--image-only", action="store_true", help="Migrate only image DB")
    parser.add_argument("--test", action="store_true", help="Test Pinecone search")

    args = parser.parse_args()

    print(f"""
{'='*70}
🔄 Safe Pinecone Migration Tool
{'='*70}
    """)

    if args.test:
        test_pinecone_search()
        return

    # Check API key
    if not os.getenv("PINECONE_API_KEY"):
        print("❌ PINECONE_API_KEY not found in .env file")
        return

    print("✅ Pinecone API key found")

    # Migration
    if args.text_only:
        migrate_text_safe()
    elif args.image_only:
        migrate_image_safe()
    else:
        # Migrate both
        text_index = migrate_text_safe()
        image_index = migrate_image_safe()

    # Test
    test_pinecone_search()

    print(f"""
{'='*70}
✨ Migration Complete!
{'='*70}
📝 Text vectors: text-papers-bge-m3
📷 Image vectors: image-papers-clip

Use these indexes in your search scripts by setting:
  db_type="pinecone"
{'='*70}
    """)


if __name__ == "__main__":
    main()