#!/usr/bin/env python
"""
Simple RAG Search Test
"""

import sys
import os
sys.path.insert(0, 'scripts')
os.environ['TOKENIZERS_PARALLELISM'] = 'false'

from improved_rag_builder import ImprovedRAGBuilder

print("\n" + "="*50)
print("🔍 RAG Search Test")
print("="*50)

# Test both databases
for db_type in ['chroma', 'pinecone']:
    print(f"\n### Testing {db_type.upper()} ###")
    
    try:
        # Initialize RAG
        rag = ImprovedRAGBuilder(db_type=db_type)
        
        # Test queries
        queries = [
            "lipid nanoparticle",
            "EGFR mutation",
            "deep learning",
            "pharmacology"
        ]
        
        for query in queries:
            results = rag.search(query, k=3)
            print(f"\nQuery: '{query}'")
            print(f"  Found {len(results)} results")
            
            if results and len(results) > 0:
                print(f"  Top result (score: {results[0]['score']:.3f})")
                print(f"  Text: {results[0]['text'][:100]}...")
    
    except Exception as e:
        print(f"  Error: {e}")

print("\n" + "="*50)
print("✅ Test Complete")
print("="*50)
print("\nTo add data to the databases:")
print("  ChromaDB:  python scripts/improved_rag_builder.py --db chroma --pdf /path/to/pdf")
print("  Pinecone:  python scripts/improved_rag_builder.py --db pinecone --pdf /path/to/pdf")