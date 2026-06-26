#!/usr/bin/env python
"""
Test Pinecone multimodal search
"""

import os
import sys
from typing import List, Dict
import json
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'scripts'))

from dotenv import load_dotenv
load_dotenv()

from pinecone import Pinecone
from FlagEmbedding import BGEM3FlagModel
import numpy as np


def test_text_search(query: str = "LNP mRNA delivery"):
    """Test text search in Pinecone"""
    print(f"\n📝 Testing Text Search: '{query}'")
    print("=" * 70)

    # Initialize
    pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))

    try:
        # Get index
        index = pc.Index("text-papers-bge-m3")
        stats = index.describe_index_stats()
        print(f"Index has {stats['total_vector_count']} vectors")

        # Generate query embedding
        print("Generating query embedding...")
        model = BGEM3FlagModel('BAAI/bge-m3', use_fp16=True)
        embeddings = model.encode(
            query,
            batch_size=1,
            max_length=8192
        )
        # BGE-M3 returns dense_vecs - handle both 1D and 2D cases
        dense_vecs = embeddings['dense_vecs']
        if len(dense_vecs.shape) == 1:
            query_embedding = dense_vecs.tolist()
        else:
            query_embedding = dense_vecs[0].tolist()

        print(f"Query embedding dimension: {len(query_embedding)}")

        # Search
        print("Searching...")
        results = index.query(
            vector=query_embedding,
            top_k=5,
            include_metadata=True
        )

        print(f"\nFound {len(results['matches'])} results:")
        for i, match in enumerate(results['matches'], 1):
            print(f"\n{i}. Score: {match['score']:.3f}")
            if 'metadata' in match:
                metadata = match['metadata']
                print(f"   Title: {metadata.get('title', 'Unknown')}")
                print(f"   Authors: {metadata.get('authors', 'Unknown')}")
                print(f"   Year: {metadata.get('year', 'N/A')}")
                if 'text' in metadata:
                    print(f"   Text: {metadata['text'][:200]}...")

    except Exception as e:
        print(f"Error: {e}")


def test_image_search():
    """Test image search in Pinecone with random vector"""
    print(f"\n📷 Testing Image Search")
    print("=" * 70)

    # Initialize
    pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))

    try:
        # Get index
        index = pc.Index("image-papers-clip")
        stats = index.describe_index_stats()
        print(f"Index has {stats['total_vector_count']} vectors")

        if stats['total_vector_count'] == 0:
            print("No vectors in image index yet")
            return

        # Use random vector for testing
        print("Using random query vector...")
        query_embedding = np.random.random(512).tolist()

        # Search
        print("Searching...")
        results = index.query(
            vector=query_embedding,
            top_k=5,
            include_metadata=True
        )

        print(f"\nFound {len(results['matches'])} results:")
        for i, match in enumerate(results['matches'], 1):
            print(f"\n{i}. Score: {match['score']:.3f}")
            if 'metadata' in match:
                metadata = match['metadata']
                print(f"   Paper ID: {metadata.get('paper_id', 'Unknown')}")
                print(f"   Image: {metadata.get('image_path', 'Unknown')}")
                if 'caption' in metadata:
                    print(f"   Caption: {metadata['caption'][:200]}...")

    except Exception as e:
        print(f"Error: {e}")


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Test Pinecone search")
    parser.add_argument("--query", default="LNP mRNA delivery", help="Search query")
    parser.add_argument("--image", action="store_true", help="Test image search")

    args = parser.parse_args()

    print(f"""
{'='*70}
🧪 Pinecone Multimodal Search Test
{'='*70}
    """)

    if args.image:
        test_image_search()
    else:
        test_text_search(args.query)

    print(f"""
{'='*70}
✅ Test Complete
{'='*70}
    """)


if __name__ == "__main__":
    main()