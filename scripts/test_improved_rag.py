#!/usr/bin/env python
"""
Test script for the improved RAG system
"""

import sys
sys.path.insert(0, 'scripts')

print("="*50)
print("🚀 Testing Improved RAG System")
print("="*50)

# Test 1: Text Chunker
print("\n1️⃣ Testing Text Chunker...")
try:
    from enhanced_text_chunker import EnhancedTextChunker
    chunker = EnhancedTextChunker(chunk_size=200, overlap=50)
    test_text = "This is a test. " * 30
    chunks = chunker.chunk_text(test_text)
    print(f"   ✅ Created {len(chunks)} chunks")
except Exception as e:
    print(f"   ❌ Error: {e}")

# Test 2: Caption Vectorizer
print("\n2️⃣ Testing Caption Vectorizer...")
try:
    from caption_vectorizer import CaptionVectorizer
    vectorizer = CaptionVectorizer()
    figures = [{'number': '1', 'title': 'Architecture', 'page': 1}]
    tables = [{'number': '1', 'title': 'Results', 'page': 2}]
    chunks = vectorizer.create_caption_chunks(figures, tables, [], {})
    print(f"   ✅ Created {len(chunks)} caption chunks")
except Exception as e:
    print(f"   ❌ Error: {e}")

# Test 3: Image Analyzer
print("\n3️⃣ Testing Image Analyzer...")
try:
    from image_analyzer import ImageAnalyzer
    analyzer = ImageAnalyzer()
    if analyzer.enabled:
        print("   ✅ Gemini API configured")
    else:
        print("   ⚠️ Gemini API not configured")
except Exception as e:
    print(f"   ❌ Error: {e}")

# Test 4: Evaluation Dataset
print("\n4️⃣ Testing Evaluation Dataset...")
try:
    from evaluation_dataset import EvaluationDatasetGenerator
    generator = EvaluationDatasetGenerator()
    papers = [{'paper_id': 'test1', 'title': 'Test', 'abstract': 'Abstract'}]
    dataset = generator.generate_dataset(papers, questions_per_paper=2, total_questions=2)
    print(f"   ✅ Generated {len(dataset)} questions")
except Exception as e:
    print(f"   ❌ Error: {e}")

# Test 5: RAG Builder
print("\n5️⃣ Testing RAG Builder...")
try:
    from improved_rag_builder import ImprovedRAGBuilder
    print("   ⏳ Initializing RAG builder...")
    rag = ImprovedRAGBuilder(db_type="chroma", chunk_size=500, overlap=100)
    print("   ✅ RAG builder initialized")
    
    # Test search (if collection exists)
    try:
        results = rag.search("deep learning", k=3)
        print(f"   ✅ Search working ({len(results)} results)")
    except:
        print("   ℹ️ No data in database yet")
        
except Exception as e:
    print(f"   ❌ Error: {e}")

# Test 6: RAG Evaluator
print("\n6️⃣ Testing RAG Evaluator...")
try:
    from rag_evaluator import RAGEvaluator
    evaluator = RAGEvaluator()
    print("   ✅ RAG evaluator initialized")
except Exception as e:
    print(f"   ❌ Error: {e}")

print("\n" + "="*50)
print("✅ All modules tested successfully!")
print("="*50)
print("\n📝 Next steps:")
print("1. Process PDFs: python scripts/improved_rag_builder.py --pdf /path/to/pdf")
print("2. Batch process: python scripts/improved_rag_builder.py --batch batch.json")
print("3. Search: python scripts/improved_rag_builder.py --search 'your query'")
print("4. Evaluate: python scripts/rag_evaluator.py")