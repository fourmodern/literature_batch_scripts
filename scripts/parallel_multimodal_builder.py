#!/usr/bin/env python
"""
Parallel Builder for Multimodal RAG System
병렬 처리로 빠르게 텍스트와 이미지 DB 구축
"""

import os
import sys
import json
import time
import argparse
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
from multiprocessing import Manager, Queue, Process
import multiprocessing as mp
from tqdm import tqdm

# Add script directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'scripts'))

# Environment variables
from dotenv import load_dotenv
load_dotenv()


def process_single_paper_text(args):
    """Process a single paper for text database (in separate process)"""
    paper_id, pdf_path, metadata = args

    try:
        # Import here to avoid serialization issues
        from scripts.text_rag_bge_m3 import TextRAGBGEM3

        # Create instance for this process
        text_rag = TextRAGBGEM3(db_type="chroma", use_semantic_chunking=True)

        # Process paper
        result = text_rag.process_paper(paper_id, pdf_path, metadata)

        return {
            'paper_id': paper_id,
            'status': 'success' if result.get('status') != 'error' else 'error',
            'chunks': result.get('chunks', 0),
            'errors': result.get('errors', [])
        }
    except Exception as e:
        return {
            'paper_id': paper_id,
            'status': 'error',
            'chunks': 0,
            'errors': [str(e)]
        }


def process_single_paper_image(args):
    """Process a single paper for image database (in separate process)"""
    paper_id, pdf_path, metadata = args

    try:
        # Import here to avoid serialization issues
        from scripts.image_rag_clip import ImageRAGCLIP

        # Create instance for this process
        image_rag = ImageRAGCLIP(db_type="chroma", max_images_per_paper=15)

        # Process paper
        result = image_rag.process_paper(paper_id, pdf_path, metadata)

        return {
            'paper_id': paper_id,
            'status': 'success' if result.get('status') != 'error' else 'error',
            'images': result.get('images', 0),
            'embeddings': result.get('embeddings', 0),
            'errors': result.get('errors', [])
        }
    except Exception as e:
        return {
            'paper_id': paper_id,
            'status': 'error',
            'images': 0,
            'embeddings': 0,
            'errors': [str(e)]
        }


def process_batch_parallel(papers: List[Dict],
                          mode: str,
                          workers: int = 4,
                          batch_size: int = 10):
    """
    Process papers in parallel batches

    Args:
        papers: List of paper dictionaries
        mode: 'text' or 'image'
        workers: Number of parallel workers
        batch_size: Papers per batch
    """
    print(f"\n{'='*60}")
    print(f"🚀 Parallel Processing: {mode.upper()} Database")
    print(f"{'='*60}")
    print(f"📊 Total papers: {len(papers)}")
    print(f"👷 Workers: {workers}")
    print(f"📦 Batch size: {batch_size}")

    # Prepare arguments
    args_list = []
    for paper in papers:
        paper_id = paper.get('paper_id', Path(paper['pdf_path']).stem)
        pdf_path = paper['pdf_path']
        metadata = paper.get('metadata', {})
        args_list.append((paper_id, pdf_path, metadata))

    # Statistics
    stats = {
        'total': len(papers),
        'processed': 0,
        'success': 0,
        'errors': 0,
        'chunks': 0 if mode == 'text' else 0,
        'images': 0 if mode == 'image' else 0
    }

    # Process function
    process_func = process_single_paper_text if mode == 'text' else process_single_paper_image

    # Process in batches with progress bar
    with ProcessPoolExecutor(max_workers=workers) as executor:
        # Submit all tasks
        futures = []
        for i in range(0, len(args_list), batch_size):
            batch = args_list[i:i+batch_size]
            for args in batch:
                future = executor.submit(process_func, args)
                futures.append(future)

        # Process results with progress bar
        with tqdm(total=len(futures), desc=f"Processing {mode}") as pbar:
            for future in as_completed(futures):
                try:
                    result = future.result(timeout=120)  # 2 minute timeout per paper
                    stats['processed'] += 1

                    if result['status'] == 'success':
                        stats['success'] += 1
                        if mode == 'text':
                            stats['chunks'] += result.get('chunks', 0)
                        else:
                            stats['images'] += result.get('images', 0)
                    else:
                        stats['errors'] += 1

                except Exception as e:
                    stats['errors'] += 1
                    print(f"\n❌ Error: {e}")

                pbar.update(1)
                pbar.set_postfix({
                    'Success': stats['success'],
                    'Errors': stats['errors'],
                    'Chunks' if mode == 'text' else 'Images':
                        stats.get('chunks', 0) if mode == 'text' else stats.get('images', 0)
                })

    # Print final statistics
    print(f"\n📊 {mode.upper()} Processing Complete:")
    print(f"  ✅ Success: {stats['success']}/{stats['total']}")
    print(f"  ❌ Errors: {stats['errors']}")
    if mode == 'text':
        print(f"  📝 Total chunks: {stats['chunks']}")
    else:
        print(f"  🖼️ Total images: {stats['images']}")

    return stats


def build_relations(papers: List[Dict]):
    """Build relationships between text and images"""
    print(f"\n{'='*60}")
    print(f"🔗 Building Cross-Database Relations")
    print(f"{'='*60}")

    try:
        from scripts.relation_manager import RelationManager

        rm = RelationManager()

        with tqdm(papers, desc="Building relations") as pbar:
            for paper in pbar:
                paper_id = paper.get('paper_id', Path(paper['pdf_path']).stem)
                metadata = paper.get('metadata', {})

                try:
                    # Add paper info
                    rm.add_paper(
                        paper_id,
                        title=metadata.get('title', ''),
                        authors=metadata.get('authors', ''),
                        year=metadata.get('year', 0),
                        doi=metadata.get('doi', ''),
                        abstract=metadata.get('abstract', '')
                    )

                    # Build automatic relationships
                    rm.build_relationships_for_paper(paper_id)

                except Exception as e:
                    pass  # Skip errors

        # Get statistics
        stats = rm.get_statistics()
        print(f"\n✅ Relations built:")
        for key, value in stats.items():
            print(f"  {key}: {value}")

        rm.close()

    except Exception as e:
        print(f"❌ Failed to build relations: {e}")


def load_all_papers():
    """Load all papers from the batch file"""
    # First try the full batch
    batch_files = [
        'papers_batch.json',  # Full 714 papers
        'batch_50_papers.json'  # Fallback to 50
    ]

    for batch_file in batch_files:
        if os.path.exists(batch_file):
            print(f"📂 Loading {batch_file}...")
            with open(batch_file, 'r') as f:
                data = json.load(f)

            # Ensure proper format
            papers = []
            for item in data:
                if isinstance(item, dict) and 'pdf_path' in item:
                    papers.append({
                        'pdf_path': item['pdf_path'],
                        'paper_id': item.get('paper_id', Path(item['pdf_path']).stem),
                        'metadata': item.get('metadata', {})
                    })

            if papers:
                print(f"✅ Loaded {len(papers)} papers")
                return papers

    # If no batch file, create from Zotero
    print("Creating batch file from Zotero...")
    os.system("python scripts/create_batch_file.py")

    if os.path.exists('papers_batch.json'):
        with open('papers_batch.json', 'r') as f:
            data = json.load(f)
        return data

    raise ValueError("No papers found!")


def main():
    parser = argparse.ArgumentParser(
        description="Parallel builder for multimodal RAG system"
    )

    parser.add_argument("--mode", nargs='+', default=['text', 'image', 'relations'],
                       choices=['text', 'image', 'relations', 'all'],
                       help="Which components to build")
    parser.add_argument("--workers", type=int, default=4,
                       help="Number of parallel workers")
    parser.add_argument("--batch-size", type=int, default=10,
                       help="Papers per batch")
    parser.add_argument("--limit", type=int, default=None,
                       help="Limit number of papers to process")

    args = parser.parse_args()

    # Handle "all" mode
    if 'all' in args.mode:
        modes = ['text', 'image', 'relations']
    else:
        modes = args.mode

    # Load papers
    papers = load_all_papers()

    # Apply limit if specified
    if args.limit:
        papers = papers[:args.limit]
        print(f"🔧 Limited to {len(papers)} papers")

    # Start time
    start_time = time.time()

    print(f"\n{'='*60}")
    print(f"🚀 Multimodal RAG Parallel Builder")
    print(f"{'='*60}")
    print(f"📚 Papers to process: {len(papers)}")
    print(f"⚡ Parallel workers: {args.workers}")
    print(f"📋 Modes: {', '.join(modes)}")

    # Process each mode
    results = {}

    if 'text' in modes:
        results['text'] = process_batch_parallel(
            papers, 'text', args.workers, args.batch_size
        )

    if 'image' in modes:
        results['image'] = process_batch_parallel(
            papers, 'image', args.workers, args.batch_size
        )

    if 'relations' in modes:
        build_relations(papers)

    # Final statistics
    elapsed = time.time() - start_time

    print(f"\n{'='*60}")
    print(f"✨ Build Complete!")
    print(f"{'='*60}")

    if 'text' in results:
        print(f"📝 Text DB: {results['text']['success']} papers, {results['text']['chunks']} chunks")

    if 'image' in results:
        print(f"🖼️ Image DB: {results['image']['success']} papers, {results['image']['images']} images")

    print(f"⏱️ Total time: {elapsed/60:.1f} minutes")
    print(f"⚡ Processing speed: {len(papers)/(elapsed/60):.1f} papers/minute")

    print(f"\n💡 Tip: Test the system with:")
    print(f"   python scripts/hybrid_searcher.py --query 'your search query'")


if __name__ == "__main__":
    # Set multiprocessing start method
    mp.set_start_method('spawn', force=True)
    main()