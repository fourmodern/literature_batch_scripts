#!/usr/bin/env python
"""
Migrate ChromaDB to Pinecone
ChromaDB의 벡터 데이터를 Pinecone으로 이전
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

    # Initialize Pinecone
    pc = Pinecone(api_key=api_key)
    return pc


def migrate_text_db():
    """Migrate text embeddings from ChromaDB to Pinecone"""
    print("\n📝 Migrating Text Database to Pinecone...")

    # Load from ChromaDB
    client = chromadb.PersistentClient('./text_rag_bge_m3')
    collection = client.get_collection('text_papers_bge_m3')

    # Get all data
    results = collection.get(include=['embeddings', 'documents', 'metadatas'])

    if not results['ids']:
        print("No data found in ChromaDB text collection")
        return

    print(f"Found {len(results['ids'])} text chunks to migrate")

    # Initialize Pinecone
    pc = init_pinecone()

    # Create or get index
    index_name = "text-papers-bge-m3"

    # Check if index exists
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
        # Wait for index to be ready
        time.sleep(10)

    index = pc.Index(index_name)

    # Prepare vectors for upsert
    batch_size = 100
    total_batches = (len(results['ids']) + batch_size - 1) // batch_size

    print(f"Uploading in {total_batches} batches...")

    for i in tqdm(range(0, len(results['ids']), batch_size), desc="Uploading to Pinecone"):
        batch_ids = results['ids'][i:i+batch_size]
        batch_embeddings = results['embeddings'][i:i+batch_size]
        batch_metadatas = results['metadatas'][i:i+batch_size]
        batch_documents = results['documents'][i:i+batch_size]

        # Prepare vectors
        vectors = []
        for j in range(len(batch_ids)):
            # Add document text to metadata
            metadata = batch_metadatas[j] or {}
            metadata['text'] = batch_documents[j] if batch_documents[j] else ""

            vectors.append({
                "id": batch_ids[j],
                "values": batch_embeddings[j],
                "metadata": metadata
            })

        # Upsert to Pinecone
        try:
            index.upsert(vectors=vectors)
        except Exception as e:
            print(f"Error uploading batch: {e}")
            continue

    # Get final stats
    stats = index.describe_index_stats()
    print(f"✅ Text DB migrated: {stats['total_vector_count']} vectors in Pinecone")
    return index_name


def migrate_image_db():
    """Migrate image embeddings from ChromaDB to Pinecone"""
    print("\n📷 Migrating Image Database to Pinecone...")

    # Load from ChromaDB
    client = chromadb.PersistentClient('./image_rag_clip')
    collection = client.get_collection('image_papers_clip')

    # Get all data
    results = collection.get(include=['embeddings', 'documents', 'metadatas'])

    if not results['ids']:
        print("No data found in ChromaDB image collection")
        return

    print(f"Found {len(results['ids'])} image embeddings to migrate")

    # Initialize Pinecone
    pc = init_pinecone()

    # Create or get index
    index_name = "image-papers-clip"

    # Check if index exists
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
        # Wait for index to be ready
        time.sleep(10)

    index = pc.Index(index_name)

    # Prepare vectors for upsert
    batch_size = 100
    total_batches = (len(results['ids']) + batch_size - 1) // batch_size

    print(f"Uploading in {total_batches} batches...")

    for i in tqdm(range(0, len(results['ids']), batch_size), desc="Uploading to Pinecone"):
        batch_ids = results['ids'][i:i+batch_size]
        batch_embeddings = results['embeddings'][i:i+batch_size]
        batch_metadatas = results['metadatas'][i:i+batch_size]
        batch_documents = results['documents'][i:i+batch_size]

        # Prepare vectors
        vectors = []
        for j in range(len(batch_ids)):
            # Add caption text to metadata
            metadata = batch_metadatas[j] or {}
            metadata['caption'] = batch_documents[j] if batch_documents[j] else ""

            vectors.append({
                "id": batch_ids[j],
                "values": batch_embeddings[j],
                "metadata": metadata
            })

        # Upsert to Pinecone
        try:
            index.upsert(vectors=vectors)
        except Exception as e:
            print(f"Error uploading batch: {e}")
            continue

    # Get final stats
    stats = index.describe_index_stats()
    print(f"✅ Image DB migrated: {stats['total_vector_count']} vectors in Pinecone")
    return index_name


def verify_migration():
    """Verify the migration was successful"""
    print("\n🔍 Verifying Migration...")

    pc = init_pinecone()

    # Check text index
    try:
        text_index = pc.Index("text-papers-bge-m3")
        text_stats = text_index.describe_index_stats()
        print(f"📝 Text Index: {text_stats['total_vector_count']} vectors")
        print(f"   Namespaces: {list(text_stats['namespaces'].keys())}")
    except:
        print("❌ Text index not found")

    # Check image index
    try:
        image_index = pc.Index("image-papers-clip")
        image_stats = image_index.describe_index_stats()
        print(f"📷 Image Index: {image_stats['total_vector_count']} vectors")
        print(f"   Namespaces: {list(image_stats['namespaces'].keys())}")
    except:
        print("❌ Image index not found")

    # Test query
    print("\n🧪 Testing sample query...")
    try:
        # Generate random query vector
        query_vector = np.random.random(1024).tolist()
        results = text_index.query(
            vector=query_vector,
            top_k=3,
            include_metadata=True
        )
        print(f"✅ Query successful, found {len(results['matches'])} results")
        if results['matches']:
            print(f"   Sample result: {results['matches'][0]['id'][:50]}...")
    except Exception as e:
        print(f"❌ Query failed: {e}")


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Migrate ChromaDB to Pinecone")
    parser.add_argument("--text-only", action="store_true", help="Migrate only text DB")
    parser.add_argument("--image-only", action="store_true", help="Migrate only image DB")
    parser.add_argument("--verify", action="store_true", help="Only verify existing Pinecone indexes")

    args = parser.parse_args()

    print(f"""
{'='*70}
🔄 ChromaDB → Pinecone Migration Tool
{'='*70}
    """)

    if args.verify:
        verify_migration()
        return

    # Check Pinecone API key
    if not os.getenv("PINECONE_API_KEY"):
        print("❌ PINECONE_API_KEY not found in .env file")
        return

    print(f"✅ Pinecone API key found")

    # Migration
    if args.text_only:
        migrate_text_db()
    elif args.image_only:
        migrate_image_db()
    else:
        # Migrate both
        text_index = migrate_text_db()
        image_index = migrate_image_db()

    # Verify
    verify_migration()

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