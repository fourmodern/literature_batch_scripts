#!/usr/bin/env python
"""
Simple test for RAG system with fresh database
"""

import sys
import os
sys.path.insert(0, 'scripts')

from improved_rag_builder import ImprovedRAGBuilder

print("\n" + "="*50)
print("🚀 Testing RAG System with New Database")
print("="*50)

# Initialize RAG with smaller chunks for faster processing
print("\n1. Initializing RAG builder...")
rag = ImprovedRAGBuilder(
    db_type="chroma",
    chunk_size=500,  # Smaller chunks for testing
    overlap=100
)

# Process a single PDF
pdf_path = os.path.expanduser("~/Zotero/storage/23PS627K/fphar-10-00698.pdf")

if os.path.exists(pdf_path):
    print(f"\n2. Processing PDF: {os.path.basename(pdf_path)}")
    
    result = rag.process_paper(
        pdf_path=pdf_path,
        paper_id="test_001",
        metadata={
            "title": "Test Paper",
            "authors": ["Test Author"],
            "year": "2024"
        }
    )
    
    print(f"\n3. Processing complete!")
    print(f"   - Text chunks: {result.get('text_chunks', 0)}")
    print(f"   - Caption chunks: {result.get('caption_chunks', 0)}")
    print(f"   - Image chunks: {result.get('image_chunks', 0)}")
    print(f"   - Total chunks: {result.get('total_chunks', 0)}")
    
    # Test search
    print("\n4. Testing search...")
    results = rag.search("pharmacology", k=3)
    print(f"   Found {len(results)} results")
    
    if results:
        print("\n5. Sample result:")
        print(f"   Score: {results[0]['score']:.3f}")
        print(f"   Text: {results[0]['text'][:100]}...")
else:
    print(f"\n❌ PDF not found: {pdf_path}")

print("\n" + "="*50)
print("✅ Test Complete!")
print("="*50)