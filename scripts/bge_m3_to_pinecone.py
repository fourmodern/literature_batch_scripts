#!/usr/bin/env python3
"""
BGE-M3 Text Embeddings to Pinecone
Process papers and create BGE-M3 embeddings for text chunks
"""

import os
import sys
import time
from pathlib import Path
from typing import List, Dict
import numpy as np
from tqdm import tqdm
from FlagEmbedding import BGEM3FlagModel
from pinecone import Pinecone, ServerlessSpec
from dotenv import load_dotenv

# Add scripts to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'scripts'))

from enhanced_text_chunker import EnhancedTextChunker
from text_extractor import extract_text_from_pdf

load_dotenv()

def process_papers_to_pinecone():
    """Process papers and upload BGE-M3 embeddings to Pinecone"""

    print("="*70)
    print("📝 BGE-M3 Text Embeddings to Pinecone")
    print("="*70)

    # Initialize BGE-M3
    print("\n🚀 Loading BGE-M3 model...")
    start_time = time.time()
    model = BGEM3FlagModel('BAAI/bge-m3', use_fp16=True)
    print(f"✅ Model loaded in {time.time() - start_time:.1f}s")

    # Initialize Pinecone
    print("\n🔑 Initializing Pinecone...")
    pc = Pinecone(api_key=os.getenv('PINECONE_API_KEY'))

    index_name = "text-papers-bge-m3"

    # Check if index exists
    existing_indexes = [idx.name for idx in pc.list_indexes()]
    if index_name in existing_indexes:
        print(f"Deleting existing index {index_name}...")
        pc.delete_index(index_name)

    # Create index
    print(f"Creating index {index_name} with 1024 dimensions...")
    pc.create_index(
        name=index_name,
        dimension=1024,  # BGE-M3 dimension
        metric='cosine',
        spec=ServerlessSpec(
            cloud='aws',
            region='us-east-1'
        )
    )

    index = pc.Index(index_name)

    # Initialize chunker
    chunker = EnhancedTextChunker()

    # Find PDF files
    pdf_dir = Path(os.getenv('PDF_DIR', './pdfs'))
    if not pdf_dir.exists():
        # Try Zotero directory
        pdf_dir = Path.home() / 'Zotero' / 'storage'

    print(f"\n📂 Searching for PDFs in {pdf_dir}...")
    pdf_files = list(pdf_dir.glob('**/*.pdf'))[:100]  # Process first 100 papers
    print(f"Found {len(pdf_files)} PDFs to process")

    # Track processed papers
    processed_count = 0
    total_chunks = 0
    batch_vectors = []
    batch_size = 100

    print("\n📄 Processing papers...")
    for pdf_path in tqdm(pdf_files, desc="Processing PDFs"):
        try:
            # Extract text
            text = extract_text_from_pdf(str(pdf_path))
            if not text or len(text) < 500:
                continue

            # Create chunks
            chunks = chunker.chunk_text(text)
            if not chunks:
                continue

            # Generate embeddings for chunks
            chunk_texts = [chunk['content'] for chunk in chunks]

            # Batch encode with BGE-M3
            embeddings = model.encode(
                chunk_texts,
                batch_size=32,
                max_length=8192,
                return_dense=True,
                return_sparse=False,
                return_colbert_vecs=False
            )

            # Handle dict return
            if isinstance(embeddings, dict):
                embeddings = embeddings['dense_vecs']

            # Prepare vectors for Pinecone
            for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
                vector_id = f"{pdf_path.stem}_{i}"

                metadata = {
                    'text': chunk['content'][:1000],  # Truncate for metadata limits
                    'file': pdf_path.name,
                    'chunk_index': i,
                    'section': chunk.get('section', 'Unknown'),
                    'page': chunk.get('page', 0)
                }

                batch_vectors.append({
                    'id': vector_id,
                    'values': embedding.tolist() if hasattr(embedding, 'tolist') else embedding,
                    'metadata': metadata
                })

                # Upload batch if full
                if len(batch_vectors) >= batch_size:
                    index.upsert(vectors=batch_vectors)
                    total_chunks += len(batch_vectors)
                    batch_vectors = []

            processed_count += 1

            # Progress update
            if processed_count % 10 == 0:
                print(f"\n✅ Processed {processed_count} papers, {total_chunks} chunks")

        except Exception as e:
            print(f"\n⚠️ Error processing {pdf_path.name}: {e}")
            continue

    # Upload remaining vectors
    if batch_vectors:
        index.upsert(vectors=batch_vectors)
        total_chunks += len(batch_vectors)

    # Final stats
    print(f"\n{'='*70}")
    print(f"✨ Processing Complete!")
    print(f"{'='*70}")
    print(f"📊 Statistics:")
    print(f"  - Papers processed: {processed_count}")
    print(f"  - Total chunks: {total_chunks}")
    print(f"  - Index name: {index_name}")

    stats = index.describe_index_stats()
    print(f"  - Vectors in Pinecone: {stats['total_vector_count']}")
    print(f"\n📍 View at: https://app.pinecone.io/")

if __name__ == "__main__":
    process_papers_to_pinecone()