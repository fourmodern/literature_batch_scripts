#!/usr/bin/env python
"""
Monitor progress of RAG building
"""

import time
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'scripts'))


def get_db_stats():
    """Get current database statistics"""
    stats = {}

    # Image DB
    try:
        import chromadb
        client = chromadb.PersistentClient('./image_rag_clip')
        collection = client.get_collection('image_papers_clip')
        metadatas = collection.get()['metadatas']
        papers = set([m['paper_id'] for m in metadatas if m])
        stats['image_embeddings'] = collection.count()
        stats['image_papers'] = len(papers)
    except:
        stats['image_embeddings'] = 0
        stats['image_papers'] = 0

    # Text DB
    try:
        import chromadb
        client = chromadb.PersistentClient('./text_rag_bge_m3')
        collection = client.get_collection('text_papers_bge_m3')
        metadatas = collection.get()['metadatas']
        papers = set([m['paper_id'] for m in metadatas if m])
        stats['text_embeddings'] = collection.count()
        stats['text_papers'] = len(papers)
    except:
        stats['text_embeddings'] = 0
        stats['text_papers'] = 0

    return stats


def main():
    print("📊 Monitoring RAG Building Progress...")
    print("Press Ctrl+C to stop\n")

    start_stats = get_db_stats()
    start_time = time.time()

    try:
        while True:
            current_stats = get_db_stats()
            elapsed = time.time() - start_time
            elapsed_min = elapsed / 60

            # Calculate progress
            img_new = current_stats['image_papers'] - start_stats['image_papers']
            txt_new = current_stats['text_papers'] - start_stats['text_papers']

            # Calculate rate
            img_rate = img_new / elapsed_min if elapsed_min > 0 else 0
            txt_rate = txt_new / elapsed_min if elapsed_min > 0 else 0

            # Estimate time remaining
            img_remaining = max(0, 714 - current_stats['image_papers'])
            txt_remaining = max(0, 714 - current_stats['text_papers'])

            img_eta = img_remaining / img_rate if img_rate > 0 else 999
            txt_eta = txt_remaining / txt_rate if txt_rate > 0 else 999

            # Clear and print
            os.system('clear' if os.name == 'posix' else 'cls')
            print(f"{'='*60}")
            print(f"📊 RAG Building Progress Monitor")
            print(f"{'='*60}")
            print(f"⏱️ Elapsed: {elapsed_min:.1f} minutes")
            print(f"\n📷 Image Database:")
            print(f"  Papers: {current_stats['image_papers']}/714 ({current_stats['image_papers']/7.14:.1f}%)")
            print(f"  Embeddings: {current_stats['image_embeddings']}")
            print(f"  Rate: {img_rate:.1f} papers/min")
            print(f"  ETA: {img_eta:.0f} min" if img_eta < 999 else "  ETA: calculating...")
            print(f"\n📝 Text Database:")
            print(f"  Papers: {current_stats['text_papers']}/714 ({current_stats['text_papers']/7.14:.1f}%)")
            print(f"  Embeddings: {current_stats['text_embeddings']}")
            print(f"  Rate: {txt_rate:.1f} papers/min")
            print(f"  ETA: {txt_eta:.0f} min" if txt_eta < 999 else "  ETA: calculating...")
            print(f"\n🎯 Overall Progress:")
            total_progress = (current_stats['image_papers'] + current_stats['text_papers']) / (714 * 2) * 100
            print(f"  {total_progress:.1f}% complete")
            print(f"{'='*60}")

            time.sleep(10)  # Update every 10 seconds

    except KeyboardInterrupt:
        print("\n\n✅ Monitoring stopped")


if __name__ == "__main__":
    main()