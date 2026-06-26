#!/usr/bin/env python
"""
Build Complete Multimodal RAG - Fast Version
3-4시간 내 완료 목표
"""

import os
import sys
import json
import time
from pathlib import Path
from typing import List, Dict
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor, as_completed
from multiprocessing import cpu_count
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


def get_processed_papers(db_type='image'):
    """Get list of already processed papers"""
    try:
        if db_type == 'image':
            import chromadb
            client = chromadb.PersistentClient('./image_rag_clip')
            collection = client.get_collection('image_papers_clip')
            metadatas = collection.get()['metadatas']
            return set([m['paper_id'] for m in metadatas if m])
        else:  # text
            import chromadb
            client = chromadb.PersistentClient('./text_rag_bge_m3')
            collection = client.get_collection('text_papers_bge_m3')
            metadatas = collection.get()['metadatas']
            return set([m['paper_id'] for m in metadatas if m])
    except:
        return set()


def process_image_batch(papers_batch):
    """Process a batch of papers for image database"""
    from scripts.image_rag_clip import ImageRAGCLIP

    # Create instance for this batch
    image_rag = ImageRAGCLIP(db_type="chroma", max_images_per_paper=8)  # Reduced for speed

    results = []
    for paper in papers_batch:
        paper_id = paper.get('paper_id')
        try:
            result = image_rag.process_paper(
                paper_id,
                paper['pdf_path'],
                paper.get('metadata', {})
            )
            results.append({
                'paper_id': paper_id,
                'status': 'success' if result.get('status') != 'error' else 'error',
                'images': result.get('images', 0)
            })
        except Exception as e:
            results.append({
                'paper_id': paper_id,
                'status': 'error',
                'images': 0
            })
    return results


def process_text_batch(papers_batch):
    """Process a batch of papers for text database"""
    from scripts.text_rag_bge_m3 import TextRAGBGEM3

    # Create instance for this batch
    text_rag = TextRAGBGEM3(db_type="chroma", use_semantic_chunking=True)

    results = []
    for paper in papers_batch:
        paper_id = paper.get('paper_id')
        try:
            result = text_rag.process_paper(
                paper_id,
                paper['pdf_path'],
                paper.get('metadata', {})
            )
            results.append({
                'paper_id': paper_id,
                'status': 'success' if result.get('status') != 'error' else 'error',
                'chunks': result.get('chunks', 0)
            })
        except Exception as e:
            results.append({
                'paper_id': paper_id,
                'status': 'error',
                'chunks': 0
            })
    return results


def build_databases_parallel():
    """Build both databases in parallel"""

    # Load all papers
    all_papers = load_papers()
    logging.info(f"Total papers available: {len(all_papers)}")

    # Get already processed papers
    processed_images = get_processed_papers('image')
    processed_texts = get_processed_papers('text')

    logging.info(f"Already processed - Images: {len(processed_images)}, Text: {len(processed_texts)}")

    # Filter out already processed papers
    papers_for_images = [p for p in all_papers if p['paper_id'] not in processed_images]
    papers_for_texts = [p for p in all_papers if p['paper_id'] not in processed_texts]

    logging.info(f"To process - Images: {len(papers_for_images)}, Text: {len(papers_for_texts)}")

    # Optimal worker configuration
    n_cpu = cpu_count()
    image_workers = min(4, n_cpu // 2)  # Image processing is I/O heavy
    text_workers = min(2, n_cpu // 4)   # Text processing is CPU heavy
    batch_size = 5  # Papers per batch

    print(f"\n{'='*70}")
    print(f"⚡ FAST MULTIMODAL RAG BUILDER")
    print(f"{'='*70}")
    print(f"📊 Status:")
    print(f"  • Total papers: {len(all_papers)}")
    print(f"  • Image DB to process: {len(papers_for_images)} papers")
    print(f"  • Text DB to process: {len(papers_for_texts)} papers")
    print(f"⚙️ Configuration:")
    print(f"  • CPU cores: {n_cpu}")
    print(f"  • Image workers: {image_workers}")
    print(f"  • Text workers: {text_workers}")
    print(f"  • Batch size: {batch_size} papers/batch")
    print(f"{'='*70}\n")

    start_time = time.time()

    # Process images and text in parallel
    import concurrent.futures

    # Statistics
    stats = {
        'images': {'success': 0, 'error': 0, 'total_images': 0},
        'text': {'success': 0, 'error': 0, 'total_chunks': 0}
    }

    # Create batches
    image_batches = [papers_for_images[i:i+batch_size]
                     for i in range(0, len(papers_for_images), batch_size)]
    text_batches = [papers_for_texts[i:i+batch_size]
                    for i in range(0, len(papers_for_texts), batch_size)]

    with ProcessPoolExecutor(max_workers=image_workers+text_workers) as executor:
        futures = []

        # Submit image processing tasks
        for batch in image_batches:
            future = executor.submit(process_image_batch, batch)
            futures.append(('image', future))

        # Submit text processing tasks
        for batch in text_batches:
            future = executor.submit(process_text_batch, batch)
            futures.append(('text', future))

        # Process results with progress bar
        total_tasks = len(futures)
        with tqdm(total=total_tasks, desc="Processing batches") as pbar:
            for db_type, future in futures:
                try:
                    results = future.result(timeout=300)  # 5 min timeout per batch

                    if db_type == 'image':
                        for r in results:
                            if r['status'] == 'success':
                                stats['images']['success'] += 1
                                stats['images']['total_images'] += r['images']
                            else:
                                stats['images']['error'] += 1
                    else:  # text
                        for r in results:
                            if r['status'] == 'success':
                                stats['text']['success'] += 1
                                stats['text']['total_chunks'] += r['chunks']
                            else:
                                stats['text']['error'] += 1

                except Exception as e:
                    logging.error(f"Batch processing error: {e}")

                pbar.update(1)
                pbar.set_postfix({
                    'IMG_OK': stats['images']['success'],
                    'IMG_ERR': stats['images']['error'],
                    'TXT_OK': stats['text']['success'],
                    'TXT_ERR': stats['text']['error']
                })

    elapsed = time.time() - start_time

    # Final report
    print(f"\n{'='*70}")
    print(f"✨ PROCESSING COMPLETE")
    print(f"{'='*70}")
    print(f"📊 Image Database:")
    print(f"  • Success: {stats['images']['success']} papers")
    print(f"  • Errors: {stats['images']['error']} papers")
    print(f"  • Total images: {stats['images']['total_images']}")
    print(f"📊 Text Database:")
    print(f"  • Success: {stats['text']['success']} papers")
    print(f"  • Errors: {stats['text']['error']} papers")
    print(f"  • Total chunks: {stats['text']['total_chunks']}")
    print(f"⏱️ Time: {elapsed/60:.1f} minutes ({elapsed/3600:.1f} hours)")
    print(f"⚡ Speed: {(stats['images']['success'] + stats['text']['success'])/(elapsed/60):.1f} papers/minute")
    print(f"{'='*70}\n")

    return stats


def build_relations():
    """Build relationships between text and images"""
    print("\n🔗 Building relationships...")

    try:
        from scripts.relation_manager import RelationManager
        rm = RelationManager()

        # Get all papers
        papers = load_papers()

        with tqdm(papers, desc="Building relations") as pbar:
            for paper in pbar:
                paper_id = paper.get('paper_id')
                metadata = paper.get('metadata', {})

                try:
                    rm.add_paper(
                        paper_id,
                        title=metadata.get('title', ''),
                        authors=metadata.get('authors', ''),
                        year=metadata.get('year', 0),
                        doi=metadata.get('doi', ''),
                        abstract=metadata.get('abstract', '')
                    )
                    rm.build_relationships_for_paper(paper_id)
                except:
                    pass

        stats = rm.get_statistics()
        print(f"✅ Relations built: {stats}")
        rm.close()

    except Exception as e:
        print(f"❌ Failed to build relations: {e}")


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Fast multimodal RAG builder")
    parser.add_argument("--skip-images", action="store_true", help="Skip image processing")
    parser.add_argument("--skip-text", action="store_true", help="Skip text processing")
    parser.add_argument("--skip-relations", action="store_true", help="Skip relation building")

    args = parser.parse_args()

    print("\n🚀 Starting Fast Multimodal RAG Builder...")
    print("⏱️ Target: Complete within 3-4 hours")

    # Build databases
    if not args.skip_images or not args.skip_text:
        build_databases_parallel()

    # Build relations
    if not args.skip_relations:
        build_relations()

    print("\n✅ All tasks complete!")
    print("💡 Test with: python scripts/hybrid_searcher.py --query 'your query'")


if __name__ == "__main__":
    # Set multiprocessing start method
    import multiprocessing as mp
    mp.set_start_method('spawn', force=True)
    main()