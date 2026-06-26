#!/usr/bin/env python
"""
Enhanced Pinecone Migration with Relations
텍스트-이미지 관계를 포함한 Pinecone 마이그레이션
"""

import os
import sys
import json
import time
from pathlib import Path
from typing import List, Dict
from tqdm import tqdm
import sqlite3

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


def load_relations():
    """Load text-image relations from SQLite"""
    relations = {}

    db_path = 'text_image_relations.db'
    if not os.path.exists(db_path):
        print("⚠️ No relations database found")
        return relations

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Load all relations
    cursor.execute("""
        SELECT text_chunk_id, image_id, relation_type, confidence
        FROM image_text_relations
    """)

    for row in cursor.fetchall():
        text_id, image_id, rel_type, confidence = row

        # Store bidirectional relations
        if text_id not in relations:
            relations[text_id] = {'images': []}
        relations[text_id]['images'].append({
            'image_id': image_id,
            'type': rel_type,
            'confidence': confidence
        })

        if image_id not in relations:
            relations[image_id] = {'texts': []}
        relations[image_id]['texts'].append({
            'text_id': text_id,
            'type': rel_type,
            'confidence': confidence
        })

    conn.close()
    print(f"📊 Loaded {len(relations)} relation entries")
    return relations


def migrate_text_with_relations(relations):
    """Migrate text embeddings with image relations in metadata"""
    print("\n📝 Migrating Text Database with Relations...")

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

    # Create index with metadata config
    index_name = "text-papers-multimodal"

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

    # Prepare vectors with enhanced metadata
    batch_size = 100
    print(f"Uploading with relation metadata...")

    for i in tqdm(range(0, len(results['ids']), batch_size), desc="Uploading to Pinecone"):
        batch_ids = results['ids'][i:i+batch_size]
        batch_embeddings = results['embeddings'][i:i+batch_size]
        batch_metadatas = results['metadatas'][i:i+batch_size]
        batch_documents = results['documents'][i:i+batch_size]

        vectors = []
        for j in range(len(batch_ids)):
            chunk_id = batch_ids[j]
            metadata = batch_metadatas[j] or {}

            # Add text content
            metadata['text'] = batch_documents[j] if batch_documents[j] else ""

            # Add image relations if exists
            if chunk_id in relations and 'images' in relations[chunk_id]:
                # Store as JSON string to preserve structure
                metadata['related_images'] = json.dumps(relations[chunk_id]['images'])
                metadata['has_images'] = True
                metadata['num_related_images'] = len(relations[chunk_id]['images'])
            else:
                metadata['has_images'] = False
                metadata['num_related_images'] = 0

            vectors.append({
                "id": chunk_id,
                "values": batch_embeddings[j],
                "metadata": metadata
            })

        # Upsert to Pinecone
        try:
            index.upsert(vectors=vectors)
        except Exception as e:
            print(f"Error uploading batch: {e}")
            continue

    stats = index.describe_index_stats()
    print(f"✅ Text DB migrated: {stats['total_vector_count']} vectors with relations")
    return index_name


def migrate_image_with_relations(relations):
    """Migrate image embeddings with text relations in metadata"""
    print("\n📷 Migrating Image Database with Relations...")

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

    # Create index
    index_name = "image-papers-multimodal"

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

    # Prepare vectors with enhanced metadata
    batch_size = 100
    print(f"Uploading with relation metadata...")

    for i in tqdm(range(0, len(results['ids']), batch_size), desc="Uploading to Pinecone"):
        batch_ids = results['ids'][i:i+batch_size]
        batch_embeddings = results['embeddings'][i:i+batch_size]
        batch_metadatas = results['metadatas'][i:i+batch_size]
        batch_documents = results['documents'][i:i+batch_size]

        vectors = []
        for j in range(len(batch_ids)):
            image_id = batch_ids[j]
            metadata = batch_metadatas[j] or {}

            # Add caption
            metadata['caption'] = batch_documents[j] if batch_documents[j] else ""

            # Add text relations if exists
            if image_id in relations and 'texts' in relations[image_id]:
                # Store as JSON string
                metadata['related_texts'] = json.dumps(relations[image_id]['texts'])
                metadata['has_texts'] = True
                metadata['num_related_texts'] = len(relations[image_id]['texts'])
            else:
                metadata['has_texts'] = False
                metadata['num_related_texts'] = 0

            vectors.append({
                "id": image_id,
                "values": batch_embeddings[j],
                "metadata": metadata
            })

        # Upsert to Pinecone
        try:
            index.upsert(vectors=vectors)
        except Exception as e:
            print(f"Error uploading batch: {e}")
            continue

    stats = index.describe_index_stats()
    print(f"✅ Image DB migrated: {stats['total_vector_count']} vectors with relations")
    return index_name


def test_multimodal_search():
    """Test multimodal search with relations"""
    print("\n🧪 Testing Multimodal Search...")

    pc = init_pinecone()

    # Test text search
    try:
        text_index = pc.Index("text-papers-multimodal")

        # Create dummy query
        import numpy as np
        query_vector = np.random.random(1024).tolist()

        results = text_index.query(
            vector=query_vector,
            top_k=3,
            include_metadata=True,
            filter={"has_images": True}  # Only get texts with images
        )

        print("\n📝 Text search results with images:")
        for match in results['matches']:
            print(f"  - Score: {match['score']:.3f}")
            if 'related_images' in match['metadata']:
                images = json.loads(match['metadata']['related_images'])
                print(f"    Related images: {len(images)}")
                for img in images[:2]:
                    print(f"      • {img['image_id']} ({img['type']})")
    except Exception as e:
        print(f"Text search error: {e}")

    # Test image search
    try:
        image_index = pc.Index("image-papers-multimodal")

        query_vector = np.random.random(512).tolist()

        results = image_index.query(
            vector=query_vector,
            top_k=3,
            include_metadata=True,
            filter={"has_texts": True}
        )

        print("\n📷 Image search results with texts:")
        for match in results['matches']:
            print(f"  - Score: {match['score']:.3f}")
            if 'related_texts' in match['metadata']:
                texts = json.loads(match['metadata']['related_texts'])
                print(f"    Related texts: {len(texts)}")
    except Exception as e:
        print(f"Image search error: {e}")


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Migrate to Pinecone with relations")
    parser.add_argument("--test", action="store_true", help="Test multimodal search")

    args = parser.parse_args()

    print(f"""
{'='*70}
🔄 Enhanced Pinecone Migration (with Relations)
{'='*70}
    """)

    if args.test:
        test_multimodal_search()
        return

    # Check API key
    if not os.getenv("PINECONE_API_KEY"):
        print("❌ PINECONE_API_KEY not found in .env file")
        return

    print("✅ Pinecone API key found")

    # Load relations
    relations = load_relations()

    # Migrate with relations
    text_index = migrate_text_with_relations(relations)
    image_index = migrate_image_with_relations(relations)

    # Test
    test_multimodal_search()

    print(f"""
{'='*70}
✨ Migration Complete with Relations!
{'='*70}
📝 Text index: text-papers-multimodal
📷 Image index: image-papers-multimodal
🔗 Relations preserved in metadata

Key features:
• Text chunks include related_images metadata
• Image embeddings include related_texts metadata
• Bidirectional navigation preserved
• Filter by has_images/has_texts for multimodal content
{'='*70}
    """)


if __name__ == "__main__":
    main()