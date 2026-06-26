#!/usr/bin/env python
"""
Simple single-process BGE-M3 builder - no parallelism
"""

import os
import sys
import json
import time
from pathlib import Path
from typing import Dict, List
from tqdm import tqdm

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'scripts'))

from dotenv import load_dotenv
load_dotenv()

from pinecone import Pinecone, ServerlessSpec
from FlagEmbedding import BGEM3FlagModel
from text_extractor import extract_text_and_images
from enhanced_text_chunker import EnhancedTextChunker

def main():
    print("="*70)
    print("🔧 Simple BGE-M3 Builder (Single Process)")
    print("="*70)

    # Load papers
    with open("papers_batch.json", 'r') as f:
        papers = json.load(f)

    print(f"📚 Loaded {len(papers)} papers")

    # Initialize model
    print("🔧 Loading BGE-M3 model...")
    start = time.time()
    model = BGEM3FlagModel('BAAI/bge-m3', use_fp16=True)
    print(f"✅ Model loaded in {time.time() - start:.1f}s")

    # Initialize Pinecone
    api_key = os.getenv("PINECONE_API_KEY")
    if not api_key:
        raise ValueError("PINECONE_API_KEY not found")

    pc = Pinecone(api_key=api_key)

    # Create or get index
    index_name = "simple-bge-m3"

    existing_indexes = [idx.name for idx in pc.list_indexes()]
    if index_name not in existing_indexes:
        print(f"🔧 Creating index: {index_name}")
        pc.create_index(
            name=index_name,
            dimension=1024,
            metric="cosine",
            spec=ServerlessSpec(
                cloud="aws",
                region="us-east-1"
            )
        )
        time.sleep(10)

    index = pc.Index(index_name)
    print(f"✅ Using index: {index_name}")

    # Initialize chunker
    chunker = EnhancedTextChunker()

    # Process papers
    total_chunks = 0
    batch = []
    batch_size = 50

    for i, paper in enumerate(tqdm(papers[:10], desc="Processing papers")):  # Process first 10 papers
        paper_id = paper.get('paper_id', Path(paper['pdf_path']).stem)
        pdf_path = paper['pdf_path']

        try:
            # Extract text
            text, _, _, _ = extract_text_and_images(pdf_path, None, max_pages=10)

            if not text or len(text) < 100:
                continue

            # Create chunks
            chunks = chunker.chunk_text(text, {})  # EnhancedTextChunker needs metadata

            # Generate embeddings and prepare vectors
            for j, chunk in enumerate(chunks[:20]):  # Max 20 chunks per paper
                # Generate embedding
                chunk_text = chunk['content'] if isinstance(chunk, dict) else chunk
                result = model.encode(chunk_text, batch_size=1, max_length=8192)

                if isinstance(result, dict):
                    embedding = result['dense_vecs']
                else:
                    embedding = result

                # Prepare vector
                vector = {
                    "id": f"{paper_id}_chunk_{j}",
                    "values": embedding.tolist() if hasattr(embedding, 'tolist') else list(embedding),
                    "metadata": {
                        "paper_id": paper_id,
                        "chunk_index": j,
                        "text": chunk_text[:1000]  # Store first 1000 chars
                    }
                }

                batch.append(vector)
                total_chunks += 1

                # Upload batch
                if len(batch) >= batch_size:
                    index.upsert(vectors=batch)
                    print(f"✅ Uploaded {len(batch)} vectors (Total: {total_chunks})")
                    batch = []

        except Exception as e:
            print(f"❌ Error processing {paper_id}: {e}")
            continue

    # Upload final batch
    if batch:
        index.upsert(vectors=batch)
        print(f"✅ Uploaded final {len(batch)} vectors")

    # Final stats
    stats = index.describe_index_stats()
    print(f"""
{"="*70}
✨ Complete!
{"="*70}
📊 Index: {index_name}
📈 Total vectors: {stats['total_vector_count']}
📝 Papers processed: 10
{"="*70}
""")

if __name__ == "__main__":
    main()