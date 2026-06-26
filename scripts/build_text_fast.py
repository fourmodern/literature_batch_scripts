#!/usr/bin/env python
"""
Fast Text Database Builder with BGE-M3
텍스트 데이터베이스만 먼저 빠르게 구축
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
        client = chromadb.PersistentClient('./text_rag_bge_m3')
        collection = client.get_collection('text_papers_bge_m3')
        metadatas = collection.get()['metadatas']
        return set([m['paper_id'] for m in metadatas if m])
    except:
        return set()


def process_paper_wrapper(args):
    """Wrapper for processing single paper"""
    paper, text_rag = args
    paper_id = paper.get('paper_id')

    try:
        result = text_rag.process_paper(
            paper_id,
            paper['pdf_path'],
            paper.get('metadata', {})
        )

        return {
            'paper_id': paper_id,
            'status': 'success' if result.get('status') != 'error' else 'error',
            'chunks': result.get('chunks', 0)
        }
    except Exception as e:
        logging.error(f"Error processing {paper_id}: {e}")
        return {
            'paper_id': paper_id,
            'status': 'error',
            'chunks': 0
        }


def build_text_database_fast():
    """Build text database with maximum speed"""

    # Load papers
    all_papers = load_papers()
    processed = get_processed_papers()

    # Filter unprocessed
    papers_to_process = [p for p in all_papers if p['paper_id'] not in processed]

    print(f"\n{'='*70}")
    print(f"⚡ FAST TEXT DATABASE BUILDER (BGE-M3)")
    print(f"{'='*70}")
    print(f"📊 Status:")
    print(f"  • Total papers: {len(all_papers)}")
    print(f"  • Already processed: {len(processed)}")
    print(f"  • To process: {len(papers_to_process)}")
    print(f"{'='*70}\n")

    if not papers_to_process:
        print("✅ All papers already processed!")
        return

    # Initialize single RAG instance
    from scripts.text_rag_bge_m3 import TextRAGBGEM3
    text_rag = TextRAGBGEM3(db_type="chroma", use_semantic_chunking=False)  # Disable semantic for speed

    # Statistics
    stats = {
        'success': 0,
        'error': 0,
        'total_chunks': 0
    }

    start_time = time.time()

    # Process with ThreadPoolExecutor (better for I/O operations)
    workers = 10  # Increase workers for text processing

    # Prepare arguments
    args_list = [(paper, text_rag) for paper in papers_to_process]

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(process_paper_wrapper, args) for args in args_list]

        with tqdm(total=len(futures), desc="Processing papers") as pbar:
            for future in as_completed(futures):
                try:
                    result = future.result(timeout=60)  # 1 minute timeout

                    if result['status'] == 'success':
                        stats['success'] += 1
                        stats['total_chunks'] += result['chunks']
                    else:
                        stats['error'] += 1

                except Exception as e:
                    stats['error'] += 1
                    logging.error(f"Future error: {e}")

                pbar.update(1)
                pbar.set_postfix({
                    'Success': stats['success'],
                    'Errors': stats['error'],
                    'Chunks': stats['total_chunks'],
                    'Speed': f"{stats['success']/(time.time()-start_time)*60:.1f}/min"
                })

    elapsed = time.time() - start_time

    # Final report
    print(f"\n{'='*70}")
    print(f"✨ TEXT DATABASE COMPLETE")
    print(f"{'='*70}")
    print(f"📊 Results:")
    print(f"  • Success: {stats['success']} papers")
    print(f"  • Errors: {stats['error']} papers")
    print(f"  • Total chunks: {stats['total_chunks']}")
    print(f"⏱️ Time: {elapsed/60:.1f} minutes")
    print(f"⚡ Speed: {stats['success']/(elapsed/60):.1f} papers/minute")
    print(f"{'='*70}\n")

    return stats


def main():
    print("\n🚀 Starting Fast Text Database Builder...")
    print("⏱️ Target: Build text database for all papers quickly")

    build_text_database_fast()

    print("\n✅ Text database complete!")
    print("💡 Next: Build image database with: python build_image_fast.py")
    print("💡 Test with: python scripts/text_rag_bge_m3.py --search 'your query'")


if __name__ == "__main__":
    main()