#!/usr/bin/env python
"""
Direct simple processing - no parallelism, just sequential
"""

import os
import sys
import json
import time
from pathlib import Path
from tqdm import tqdm

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'scripts'))

from dotenv import load_dotenv
load_dotenv()

from pinecone import Pinecone
from FlagEmbedding import BGEM3FlagModel
from text_extractor import extract_text_and_images
from enhanced_text_chunker import EnhancedTextChunker

def main():
    print("="*70)
    print("🔧 Direct Simple BGE-M3 Processing")
    print("="*70)

    # Initialize
    print("Loading BGE-M3 model...")
    model = BGEM3FlagModel('BAAI/bge-m3', use_fp16=True)
    print("✅ Model loaded")

    chunker = EnhancedTextChunker()

    # Pinecone
    pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
    index = pc.Index("papers-multimodal-v2")  # Use existing index

    # Load papers
    with open("papers_batch.json", 'r') as f:
        papers = json.load(f)

    print(f"📚 Processing {len(papers)} papers")

    total_vectors = 0

    # Process only first 3 papers for testing
    for paper in tqdm(papers[:3], desc="Processing"):
        paper_id = paper.get('paper_id', Path(paper['pdf_path']).stem)
        pdf_path = paper['pdf_path']

        try:
            # Extract text
            print(f"\n📄 Processing {paper_id}")
            text, _, _, _ = extract_text_and_images(pdf_path, None, max_pages=5)

            if not text or len(text) < 100:
                print(f"  ❌ No text extracted")
                continue

            print(f"  ✅ Extracted {len(text)} chars")

            # Chunk
            chunks = chunker.chunk_text(text, {})
            print(f"  📝 Created {len(chunks)} chunks")

            # Process first 5 chunks only
            batch_texts = []
            for chunk in chunks[:5]:
                batch_texts.append(chunk['content'])

            if batch_texts:
                # Batch encode
                print(f"  🔄 Generating embeddings for {len(batch_texts)} chunks...")
                start = time.time()
                result = model.encode(
                    batch_texts,
                    batch_size=len(batch_texts),
                    max_length=8192
                )
                elapsed = time.time() - start
                print(f"  ✅ Generated in {elapsed:.1f}s")

                # Get embeddings
                if isinstance(result, dict):
                    embeddings = result['dense_vecs']
                else:
                    embeddings = result

                # Prepare vectors
                vectors = []
                for i, (chunk, embedding) in enumerate(zip(chunks[:5], embeddings)):
                    vector = {
                        "id": f"{paper_id}_chunk_{i}",
                        "values": embedding.tolist() if hasattr(embedding, 'tolist') else list(embedding),
                        "metadata": {
                            "paper_id": paper_id,
                            "chunk_index": i,
                            "text": chunk['content'][:500]
                        }
                    }
                    vectors.append(vector)

                # Upload
                if vectors:
                    index.upsert(vectors=vectors)
                    total_vectors += len(vectors)
                    print(f"  ✅ Uploaded {len(vectors)} vectors (Total: {total_vectors})")

        except Exception as e:
            print(f"  ❌ Error: {e}")
            continue

    # Final stats
    stats = index.describe_index_stats()
    print(f"""
{"="*70}
✨ Complete!
📊 Total vectors in index: {stats['total_vector_count']}
📝 Papers processed: 3
{"="*70}
""")

if __name__ == "__main__":
    main()