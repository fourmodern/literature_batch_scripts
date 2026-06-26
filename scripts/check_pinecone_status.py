#!/usr/bin/env python3
"""Check Pinecone index status"""

import os
from pinecone import Pinecone
from dotenv import load_dotenv

load_dotenv()

pc = Pinecone(api_key=os.getenv('PINECONE_API_KEY'))

# List all indexes
print("="*70)
print("📊 Pinecone Index Status")
print("="*70)

for idx in pc.list_indexes():
    print(f"\n📌 Index: {idx.name}")
    index = pc.Index(idx.name)
    stats = index.describe_index_stats()
    print(f"  - Total vectors: {stats['total_vector_count']}")
    print(f"  - Dimension: {idx.dimension}")
    print(f"  - Metric: {idx.metric}")