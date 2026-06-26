#!/usr/bin/env python
"""
Fast Image Database Builder with CLIP
이미지 추출 최소화하여 빠르게 구축
"""

import os
import sys
import json
import time
from pathlib import Path
from typing import List, Dict
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm
import logging

# Add script directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'scripts'))

from dotenv import load_dotenv
load_dotenv()

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')


def load_papers():
    """Load all papers from batch file"""
    if os.path.exists('papers_batch.json'):
        with open('papers_batch.json', 'r') as f:
            data = json.load(f)

        papers = []
        for item in data:
            if isinstance(item, dict) and 'pdf_path' in item:
                papers.append({
                    'pdf_path': item['pdf_path'],
                    'paper_id': item.get('paper_id', Path(item['pdf_path']).stem),
                    'metadata': item.get('metadata', {})
                })
        return papers
    return []


def get_processed_papers():
    """Get list of already processed papers"""
    try:
        import chromadb
        client = chromadb.PersistentClient('./image_rag_clip')
        collection = client.get_collection('image_papers_clip')
        metadatas = collection.get()['metadatas']
        return set([m['paper_id'] for m in metadatas if m])
    except:
        return set()


def process_paper_wrapper(args):
    """Wrapper for processing single paper"""
    paper, image_rag = args
    paper_id = paper.get('paper_id')

    try:
        result = image_rag.process_paper(
            paper_id,
            paper['pdf_path'],
            paper.get('metadata', {})
        )

        return {
            'paper_id': paper_id,
            'status': 'success' if result.get('status') != 'error' else 'error',
            'images': result.get('images', 0)
        }
    except Exception as e:
        logging.error(f"Error processing {paper_id}: {e}")
        return {
            'paper_id': paper_id,
            'status': 'error',
            'images': 0
        }


def build_image_database_fast():
    """Build image database with maximum speed"""

    # Load papers
    all_papers = load_papers()
    processed = get_processed_papers()

    # Filter unprocessed
    papers_to_process = [p for p in all_papers if p['paper_id'] not in processed]

    print(f"\n{'='*70}")
    print(f"⚡ FAST IMAGE DATABASE BUILDER (CLIP)")
    print(f"{'='*70}")
    print(f"📊 Status:")
    print(f"  • Total papers: {len(all_papers)}")
    print(f"  • Already processed: {len(processed)}")
    print(f"  • To process: {len(papers_to_process)}")
    print(f"{'='*70}\n")

    if not papers_to_process:
        print("✅ All papers already processed!")
        return

    # Initialize single RAG instance with minimal settings
    from scripts.image_rag_clip import ImageRAGCLIP
    image_rag = ImageRAGCLIP(
        db_type="chroma",
        max_images_per_paper=5  # Reduced to 5 for speed
    )

    # Statistics
    stats = {
        'success': 0,
        'error': 0,
        'total_images': 0
    }

    start_time = time.time()

    # Process with ThreadPoolExecutor
    workers = 8  # Optimal for image processing

    # Prepare arguments
    args_list = [(paper, image_rag) for paper in papers_to_process]

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(process_paper_wrapper, args) for args in args_list]

        with tqdm(total=len(futures), desc="Processing papers") as pbar:
            for future in as_completed(futures):
                try:
                    result = future.result(timeout=30)  # 30 second timeout

                    if result['status'] == 'success':
                        stats['success'] += 1
                        stats['total_images'] += result['images']
                    else:
                        stats['error'] += 1

                except Exception as e:
                    stats['error'] += 1
                    logging.error(f"Future error: {e}")

                pbar.update(1)
                pbar.set_postfix({
                    'Success': stats['success'],
                    'Errors': stats['error'],
                    'Images': stats['total_images'],
                    'Speed': f"{stats['success']/(time.time()-start_time)*60:.1f}/min"
                })

    elapsed = time.time() - start_time

    # Final report
    print(f"\n{'='*70}")
    print(f"✨ IMAGE DATABASE COMPLETE")
    print(f"{'='*70}")
    print(f"📊 Results:")
    print(f"  • Success: {stats['success']} papers")
    print(f"  • Errors: {stats['error']} papers")
    print(f"  • Total images: {stats['total_images']}")
    print(f"⏱️ Time: {elapsed/60:.1f} minutes")
    print(f"⚡ Speed: {stats['success']/(elapsed/60):.1f} papers/minute")
    print(f"{'='*70}\n")

    return stats


def main():
    print("\n🚀 Starting Fast Image Database Builder...")
    print("⏱️ Target: Build image database for all papers quickly")

    build_image_database_fast()

    print("\n✅ Image database complete!")
    print("💡 Test with: python scripts/hybrid_searcher.py --query 'your query'")


if __name__ == "__main__":
    main()