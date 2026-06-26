#!/usr/bin/env python
"""
Fast Multimodal Builder - Optimized for speed
이미지 DB만 먼저 빌드 (CLIP은 이미 로드됨)
"""

import os
import sys
import json
import time
from pathlib import Path
from typing import List, Dict
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm

# Add script directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'scripts'))

from dotenv import load_dotenv
load_dotenv()


def process_single_paper(args):
    """Process a single paper for image database"""
    paper_id, pdf_path, metadata, rag_instance = args

    try:
        # Process paper
        result = rag_instance.process_paper(paper_id, pdf_path, metadata)

        return {
            'paper_id': paper_id,
            'status': 'success' if result.get('status') != 'error' else 'error',
            'images': result.get('images', 0),
            'errors': result.get('errors', [])
        }
    except Exception as e:
        return {
            'paper_id': paper_id,
            'status': 'error',
            'images': 0,
            'errors': [str(e)]
        }


def build_image_db_fast(papers: List[Dict], workers: int = 8):
    """
    Build image database using thread pool (faster for I/O operations)
    """
    print(f"\n{'='*60}")
    print(f"🚀 Fast Image Database Builder (CLIP)")
    print(f"{'='*60}")
    print(f"📊 Total papers: {len(papers)}")
    print(f"👷 Workers: {workers}")

    # Import and create single instance
    from scripts.image_rag_clip import ImageRAGCLIP

    # Create single RAG instance
    image_rag = ImageRAGCLIP(
        db_type="chroma",
        max_images_per_paper=10  # Reduced for speed
    )

    # Prepare arguments
    args_list = []
    for paper in papers:
        paper_id = paper.get('paper_id', Path(paper['pdf_path']).stem)
        pdf_path = paper['pdf_path']
        metadata = paper.get('metadata', {})
        args_list.append((paper_id, pdf_path, metadata, image_rag))

    # Statistics
    stats = {
        'total': len(papers),
        'processed': 0,
        'success': 0,
        'errors': 0,
        'images': 0
    }

    # Process with ThreadPoolExecutor (better for I/O-bound tasks)
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(process_single_paper, args) for args in args_list]

        with tqdm(total=len(futures), desc="Processing images") as pbar:
            for future in as_completed(futures):
                try:
                    result = future.result(timeout=60)  # 1 minute timeout
                    stats['processed'] += 1

                    if result['status'] == 'success':
                        stats['success'] += 1
                        stats['images'] += result.get('images', 0)
                    else:
                        stats['errors'] += 1

                except Exception as e:
                    stats['errors'] += 1

                pbar.update(1)
                pbar.set_postfix({
                    'Success': stats['success'],
                    'Errors': stats['errors'],
                    'Images': stats['images']
                })

    # Print final statistics
    print(f"\n📊 Image Processing Complete:")
    print(f"  ✅ Success: {stats['success']}/{stats['total']}")
    print(f"  ❌ Errors: {stats['errors']}")
    print(f"  🖼️ Total images: {stats['images']}")

    return stats


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


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Fast multimodal builder")
    parser.add_argument("--workers", type=int, default=8, help="Number of workers")
    parser.add_argument("--limit", type=int, default=None, help="Limit papers")

    args = parser.parse_args()

    # Load papers
    papers = load_papers(args.limit)

    # Start time
    start_time = time.time()

    print(f"\n{'='*60}")
    print(f"⚡ Fast Multimodal RAG Builder")
    print(f"{'='*60}")
    print(f"📚 Papers to process: {len(papers)}")
    print(f"⚡ Thread workers: {args.workers}")

    # Build image database
    results = build_image_db_fast(papers, args.workers)

    # Final statistics
    elapsed = time.time() - start_time

    print(f"\n{'='*60}")
    print(f"✨ Build Complete!")
    print(f"{'='*60}")
    print(f"⏱️ Total time: {elapsed/60:.1f} minutes")
    print(f"⚡ Speed: {len(papers)/(elapsed/60):.1f} papers/minute")

    print(f"\n💡 Next steps:")
    print(f"1. Build text database: python scripts/text_rag_bge_m3.py --build-db")
    print(f"2. Build relations: python scripts/relation_manager.py --build-all")
    print(f"3. Test search: python scripts/hybrid_searcher.py --query 'your query'")


if __name__ == "__main__":
    main()