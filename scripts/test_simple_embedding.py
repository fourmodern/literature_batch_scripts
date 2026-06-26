#!/usr/bin/env python
"""
Simple test with sentence-transformers instead of BGE-M3
"""

import os
import sys
import json
import time
from pathlib import Path
from sentence_transformers import SentenceTransformer
from pinecone import Pinecone, ServerlessSpec

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'scripts'))

def main():
    print("🚀 Testing with sentence-transformers...")

    # Initialize simple model (768 dimensions)
    print("Loading model: all-MiniLM-L6-v2...")
    model = SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')

    # Test encoding
    test_text = "This is a test sentence for embedding."
    start = time.time()
    embedding = model.encode(test_text)
    elapsed = time.time() - start

    print(f"✅ Embedding generated in {elapsed:.2f}s")
    print(f"   Dimension: {len(embedding)}")

    # Initialize Pinecone
    api_key = os.getenv("PINECONE_API_KEY")
    if not api_key:
        raise ValueError("PINECONE_API_KEY not found")

    pc = Pinecone(api_key=api_key)

    # Create test index
    index_name = "test-simple-embeddings"

    existing_indexes = [idx.name for idx in pc.list_indexes()]
    if index_name in existing_indexes:
        pc.delete_index(index_name)
        time.sleep(5)

    print(f"Creating index: {index_name}")
    pc.create_index(
        name=index_name,
        dimension=384,  # all-MiniLM-L6-v2 dimension
        metric="cosine",
        spec=ServerlessSpec(
            cloud="aws",
            region="us-east-1"
        )
    )

    time.sleep(10)
    index = pc.Index(index_name)

    # Test upsert
    vectors = [
        {
            "id": "test_1",
            "values": embedding.tolist(),
            "metadata": {"text": test_text}
        }
    ]

    index.upsert(vectors=vectors)
    print("✅ Successfully upserted to Pinecone")

    # Quick test with actual paper
    from text_extractor import extract_text_and_images

    # Load first paper
    with open("papers_batch.json", 'r') as f:
        papers = json.load(f)

    if papers:
        pdf_path = papers[0]['pdf_path']
        print(f"\n📄 Testing with actual paper: {Path(pdf_path).name}")

        text, _, _, _ = extract_text_and_images(pdf_path, None, max_pages=5)

        if text:
            # Take first 1000 chars
            sample = text[:1000]

            start = time.time()
            paper_embedding = model.encode(sample)
            elapsed = time.time() - start

            print(f"✅ Paper embedding generated in {elapsed:.2f}s")

            # Upsert to Pinecone
            vectors = [
                {
                    "id": "paper_test",
                    "values": paper_embedding.tolist(),
                    "metadata": {"text": sample[:500]}  # Truncate for metadata
                }
            ]

            index.upsert(vectors=vectors)
            print("✅ Paper sample upserted to Pinecone")

            # Check stats
            stats = index.describe_index_stats()
            print(f"📊 Index now has {stats['total_vector_count']} vectors")

    print("\n✨ Test complete! Sentence-transformers works much faster than BGE-M3")
    print("   Consider using this for quick prototyping")

if __name__ == "__main__":
    main()