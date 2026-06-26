#!/usr/bin/env python
"""
Build Text Database with BGE-M3
BGE-M3를 사용한 텍스트 데이터베이스 구축
"""

import os
import sys
import json
from pathlib import Path
from typing import List, Dict
from tqdm import tqdm

# Add script directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'scripts'))

from dotenv import load_dotenv
load_dotenv()

from scripts.text_rag_bge_m3 import TextRAGBGEM3


def load_papers(limit: int = None):
    """Load papers from batch file"""
    batch_files = ['papers_batch.json', 'batch_50_papers.json']

    for batch_file in batch_files:
        if os.path.exists(batch_file):
            print(f"📂 Loading {batch_file}...")
            with open(batch_file, 'r') as f:
                data = json.load(f)

            papers = []
            for item in data:
                if isinstance(item, dict) and 'pdf_path' in item:
                    papers.append({
                        'pdf_path': item['pdf_path'],
                        'paper_id': item.get('paper_id', Path(item['pdf_path']).stem),
                        'metadata': item.get('metadata', {})
                    })

            if papers:
                if limit:
                    papers = papers[:limit]
                print(f"✅ Loaded {len(papers)} papers")
                return papers

    raise ValueError("No papers found!")


def build_text_database(papers: List[Dict]):
    """Build text database for all papers"""
    print(f"\n{'='*60}")
    print(f"📚 Building Text Database with BGE-M3")
    print(f"{'='*60}")
    print(f"Total papers: {len(papers)}")

    # Initialize RAG system
    text_rag = TextRAGBGEM3(
        db_type="chroma",
        use_semantic_chunking=True
    )

    # Statistics
    stats = {
        'total': len(papers),
        'success': 0,
        'errors': 0,
        'chunks': 0
    }

    # Process each paper
    with tqdm(papers, desc="Processing papers") as pbar:
        for paper in pbar:
            paper_id = paper.get('paper_id', Path(paper['pdf_path']).stem)
            pdf_path = paper['pdf_path']
            metadata = paper.get('metadata', {})

            try:
                # Process paper
                result = text_rag.process_paper(paper_id, pdf_path, metadata)

                if result.get('status') != 'error':
                    stats['success'] += 1
                    stats['chunks'] += result.get('chunks', 0)
                else:
                    stats['errors'] += 1

            except Exception as e:
                stats['errors'] += 1
                print(f"\n❌ Error processing {paper_id}: {e}")

            pbar.set_postfix({
                'Success': stats['success'],
                'Errors': stats['errors'],
                'Chunks': stats['chunks']
            })

    # Print final statistics
    print(f"\n📊 Text Database Build Complete:")
    print(f"  ✅ Success: {stats['success']}/{stats['total']}")
    print(f"  ❌ Errors: {stats['errors']}")
    print(f"  📝 Total chunks: {stats['chunks']}")

    return stats


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Build text database with BGE-M3")
    parser.add_argument("--limit", type=int, default=None, help="Limit papers")

    args = parser.parse_args()

    # Load papers
    papers = load_papers(args.limit)

    # Build database
    build_text_database(papers)

    print(f"\n✅ Text database created at: ./text_rag_bge_m3/")
    print(f"💡 Test search with: python scripts/text_rag_bge_m3.py --search 'your query'")


if __name__ == "__main__":
    main()