#!/usr/bin/env python3
"""
Migrate improved_vector_db ChromaDB to Pinecone
"""

import os
import chromadb
from pinecone import Pinecone, ServerlessSpec
from tqdm import tqdm
from dotenv import load_dotenv

load_dotenv()

def migrate_improved_db():
    """Migrate improved_vector_db to Pinecone"""

    print("=" * 70)
    print("🔄 Migrating improved_vector_db to Pinecone")
    print("=" * 70)

    # Load ChromaDB
    print("\n📂 Loading ChromaDB from improved_vector_db/...")
    client = chromadb.PersistentClient(path="improved_vector_db")

    # List collections
    collections = client.list_collections()
    print(f"Found {len(collections)} collections")

    if not collections:
        print("❌ No collections found in improved_vector_db")
        return

    # Use first collection
    collection = collections[0]
    print(f"Using collection: {collection.name}")

    # Get total count
    total_count = collection.count()
    print(f"Total vectors: {total_count}")

    # Get sample to determine dimension
    sample = collection.get(limit=1, include=['embeddings'])
    if len(sample['embeddings']) == 0:
        print("❌ No embeddings found")
        return

    dimension = len(sample['embeddings'][0])
    print(f"Vector dimension: {dimension}")

    # Initialize Pinecone
    print("\n🔑 Initializing Pinecone...")
    pc = Pinecone(api_key=os.getenv('PINECONE_API_KEY'))

    index_name = "improved-vector-db"

    # Check existing indexes
    existing_indexes = [idx.name for idx in pc.list_indexes()]
    if index_name in existing_indexes:
        print(f"Deleting existing index {index_name}...")
        pc.delete_index(index_name)

    # Create index
    print(f"Creating index {index_name} with {dimension} dimensions...")
    pc.create_index(
        name=index_name,
        dimension=dimension,
        metric='cosine',
        spec=ServerlessSpec(
            cloud='aws',
            region='us-east-1'
        )
    )

    index = pc.Index(index_name)

    # Migrate in batches
    batch_size = 100
    print(f"\n📤 Migrating {total_count} vectors...")

    # Process in chunks due to ChromaDB limitations
    offset = 0
    with tqdm(total=total_count, desc="Uploading") as pbar:
        while offset < total_count:
            # Get batch from ChromaDB
            limit = min(batch_size, total_count - offset)
            batch = collection.get(
                limit=limit,
                offset=offset,
                include=['embeddings', 'metadatas', 'documents']
            )

            if not batch['ids']:
                break

            # Prepare vectors for Pinecone
            vectors = []
            for i in range(len(batch['ids'])):
                metadata = batch['metadatas'][i] if batch['metadatas'] else {}

                # Add text content if available
                if batch['documents'] and batch['documents'][i]:
                    # Truncate text to avoid metadata size limits
                    text = batch['documents'][i]
                    if len(text) > 1000:
                        text = text[:997] + "..."
                    metadata['text'] = text

                vectors.append({
                    'id': batch['ids'][i],
                    'values': batch['embeddings'][i],
                    'metadata': metadata
                })

            # Upload to Pinecone
            try:
                index.upsert(vectors=vectors)
                pbar.update(len(batch['ids']))
            except Exception as e:
                print(f"\n⚠️ Error uploading batch at offset {offset}: {e}")

            offset += len(batch['ids'])

    # Verify
    print("\n✅ Migration complete!")
    stats = index.describe_index_stats()
    print(f"Pinecone index {index_name}: {stats['total_vector_count']} vectors")
    print(f"View at: https://app.pinecone.io/")

if __name__ == "__main__":
    migrate_improved_db()