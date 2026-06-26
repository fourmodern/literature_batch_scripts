#!/usr/bin/env python
"""
Test script for multimodal RAG system
"""

import sys
import os
sys.path.insert(0, 'scripts')

from text_rag_bge_m3 import TextRAGBGEM3
from image_rag_clip import ImageRAGCLIP
from relation_manager import RelationManager
from hybrid_searcher import HybridSearcher

def test_text_rag():
    """Test text RAG with one paper"""
    print("\n" + "="*60)
    print("Testing Text RAG (BGE-M3)")
    print("="*60)

    try:
        # Initialize
        text_rag = TextRAGBGEM3(db_type="chroma", use_semantic_chunking=True)

        # Process one paper
        paper_id = "TEST001"
        pdf_path = "/Users/fourmodern/Zotero/storage/23PS627K/fphar-10-00698.pdf"

        result = text_rag.process_paper(
            paper_id,
            pdf_path,
            {"title": "Test Paper", "year": 2019}
        )

        print(f"✅ Processed: {result}")

        # Test search
        results = text_rag.search("LNP delivery", k=3)
        print(f"\n🔍 Search results: {len(results)} found")
        for i, r in enumerate(results, 1):
            print(f"{i}. Score: {r['score']:.3f}")
            print(f"   Text: {r['text'][:100]}...")

        return True

    except Exception as e:
        print(f"❌ Text RAG test failed: {e}")
        return False


def test_image_rag():
    """Test image RAG with one paper"""
    print("\n" + "="*60)
    print("Testing Image RAG (CLIP)")
    print("="*60)

    try:
        # Initialize
        image_rag = ImageRAGCLIP(db_type="chroma")

        # Process one paper
        paper_id = "TEST002"
        pdf_path = "/Users/fourmodern/Zotero/storage/23PS627K/fphar-10-00698.pdf"

        result = image_rag.process_paper(
            paper_id,
            pdf_path,
            {"title": "Test Paper", "year": 2019}
        )

        print(f"✅ Processed: {result}")

        # Test search
        results = image_rag.search_by_text("nanoparticle structure", k=3)
        print(f"\n🔍 Search results: {len(results)} found")
        for i, r in enumerate(results, 1):
            print(f"{i}. Score: {r['score']:.3f}")
            print(f"   Image: {r['metadata'].get('filename', 'unknown')}")

        return True

    except Exception as e:
        print(f"❌ Image RAG test failed: {e}")
        return False


def test_relations():
    """Test relation manager"""
    print("\n" + "="*60)
    print("Testing Relation Manager")
    print("="*60)

    try:
        rm = RelationManager()

        # Add test paper
        rm.add_paper(
            "TEST001",
            title="Test Paper for Relations",
            authors="John Doe",
            year=2024
        )

        # Add test chunk
        rm.add_text_chunk(
            "TEST001#T001",
            "TEST001",
            {"text": "This refers to Figure 1 and Table 2.", "page_start": 1}
        )

        # Add test image
        rm.add_image(
            "TEST001#I001",
            "TEST001",
            {"filename": "figure1.png", "page": 1}
        )

        # Build relations
        rm.build_relationships_for_paper("TEST001")

        # Get stats
        stats = rm.get_statistics()
        print(f"✅ Relations created: {stats}")

        rm.close()
        return True

    except Exception as e:
        print(f"❌ Relations test failed: {e}")
        return False


def test_hybrid_search():
    """Test hybrid search"""
    print("\n" + "="*60)
    print("Testing Hybrid Search")
    print("="*60)

    try:
        searcher = HybridSearcher()

        # Test search
        results = searcher.search_comprehensive(
            "lipid nanoparticles",
            mode="hybrid",
            k=5
        )

        print(f"✅ Hybrid search returned {len(results)} results")

        # Analyze query
        analysis = searcher.analyze_query_intent("show me Figure 3 about LNP structure")
        print(f"\n📊 Query analysis: {analysis}")

        searcher.close()
        return True

    except Exception as e:
        print(f"❌ Hybrid search test failed: {e}")
        return False


def main():
    """Run all tests"""
    print("\n🚀 Testing Multimodal RAG System")

    results = {
        "Text RAG": test_text_rag(),
        "Image RAG": test_image_rag(),
        "Relations": test_relations(),
        "Hybrid Search": test_hybrid_search()
    }

    print("\n" + "="*60)
    print("📊 Test Results Summary")
    print("="*60)

    for test, passed in results.items():
        status = "✅ PASSED" if passed else "❌ FAILED"
        print(f"{test}: {status}")

    all_passed = all(results.values())
    print("\n" + "="*60)
    if all_passed:
        print("🎉 All tests passed!")
    else:
        print("⚠️ Some tests failed. Check the output above.")
    print("="*60)


if __name__ == "__main__":
    main()