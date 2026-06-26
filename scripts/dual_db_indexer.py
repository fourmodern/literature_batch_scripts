#!/usr/bin/env python3
"""
Dual DB Indexer for New Papers
새 논문을 두 Pinecone 인덱스에 동시에 임베딩:
- text-papers-bge-m3-v2: 텍스트 청크 (BGE-M3, 1024d)
- improved-vector-db: 그림/캡션 (CLIP, 512d)
"""

import os
import sys
import json
import argparse
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime
import numpy as np
from tqdm import tqdm

# Add scripts to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / '.env')

# Import custom modules
from text_extractor import extract_text_and_images
from enhanced_text_chunker import EnhancedTextChunker

# Pinecone
from pinecone import Pinecone

# Track processed papers
PROGRESS_FILE = Path(__file__).parent.parent / 'logs' / 'dual_indexed_papers.json'


class DualDBIndexer:
    """
    Dual database indexer for papers:
    - BGE-M3 for text → text-papers-bge-m3-v2
    - CLIP for images/captions → improved-vector-db
    """

    def __init__(self, skip_text: bool = False, skip_image: bool = False):
        """
        Initialize dual indexer.

        Args:
            skip_text: Skip text indexing (BGE-M3)
            skip_image: Skip image indexing (CLIP)
        """
        self.skip_text = skip_text
        self.skip_image = skip_image

        # Initialize Pinecone
        print("🔑 Initializing Pinecone...")
        self.pc = Pinecone(api_key=os.getenv('PINECONE_API_KEY'))

        # Text index (BGE-M3)
        self.text_index_name = "text-papers-bge-m3-v2"
        self.text_index = self.pc.Index(self.text_index_name)
        print(f"✅ Connected to text index: {self.text_index_name}")

        # Image index (CLIP)
        self.image_index_name = "improved-vector-db"
        self.image_index = self.pc.Index(self.image_index_name)
        print(f"✅ Connected to image index: {self.image_index_name}")

        # Initialize models (lazy loading)
        self.bge_model = None
        self.clip_model = None

        # Chunker
        self.chunker = EnhancedTextChunker(chunk_size=1000, overlap=200)

        # Track processed papers
        self.processed_papers = self._load_processed()

    def _load_bge_model(self):
        """Lazy load BGE-M3 model."""
        if self.bge_model is None and not self.skip_text:
            print("🚀 Loading BGE-M3 model...")
            from FlagEmbedding import BGEM3FlagModel
            self.bge_model = BGEM3FlagModel('BAAI/bge-m3', use_fp16=True)
            print("✅ BGE-M3 loaded")
        return self.bge_model

    def _load_clip_model(self):
        """Lazy load CLIP model."""
        if self.clip_model is None and not self.skip_image:
            print("🚀 Loading CLIP model...")
            from sentence_transformers import SentenceTransformer
            self.clip_model = SentenceTransformer('clip-ViT-B-32-multilingual-v1')
            print("✅ CLIP loaded")
        return self.clip_model

    def _load_processed(self) -> set:
        """Load list of already processed papers."""
        if PROGRESS_FILE.exists():
            with open(PROGRESS_FILE, 'r') as f:
                return set(json.load(f))
        return set()

    def _save_processed(self):
        """Save list of processed papers."""
        PROGRESS_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(PROGRESS_FILE, 'w') as f:
            json.dump(list(self.processed_papers), f, indent=2)

    def _generate_bge_embeddings(self, texts: List[str]) -> np.ndarray:
        """Generate BGE-M3 embeddings for texts."""
        model = self._load_bge_model()
        embeddings = model.encode(
            texts,
            batch_size=32,
            max_length=8192,
            return_dense=True,
            return_sparse=False,
            return_colbert_vecs=False
        )
        if isinstance(embeddings, dict):
            embeddings = embeddings['dense_vecs']
        return embeddings

    def _generate_clip_embeddings(self, texts: List[str]) -> np.ndarray:
        """Generate CLIP embeddings for texts/captions."""
        model = self._load_clip_model()
        embeddings = model.encode(
            texts,
            batch_size=32,
            show_progress_bar=False,
            convert_to_numpy=True
        )
        return embeddings

    def _generate_clip_image_embeddings(self, image_paths: List[str]) -> np.ndarray:
        """Generate CLIP embeddings for images."""
        model = self._load_clip_model()
        valid_paths = [p for p in image_paths if os.path.exists(p)]
        if not valid_paths:
            return np.array([])

        embeddings = model.encode(
            valid_paths,
            batch_size=8,
            show_progress_bar=False,
            convert_to_numpy=True
        )
        return embeddings

    def index_paper(self, pdf_path: str, paper_id: str, metadata: Dict = None) -> Dict:
        """
        Index a single paper to both databases.

        Args:
            pdf_path: Path to PDF file
            paper_id: Zotero key or unique identifier
            metadata: Paper metadata (title, authors, etc.)

        Returns:
            Statistics dict
        """
        if paper_id in self.processed_papers:
            print(f"⏭️  Already indexed: {paper_id}")
            return {"status": "skipped", "paper_id": paper_id}

        metadata = metadata or {}
        title = metadata.get('title', Path(pdf_path).stem)
        print(f"\n📄 Indexing: {title[:60]}...")
        print(f"   Key: {paper_id}")

        stats = {
            "paper_id": paper_id,
            "text_chunks": 0,
            "caption_chunks": 0,
            "image_chunks": 0,
            "status": "success"
        }

        try:
            # 1. Extract content from PDF
            print("   📖 Extracting content...")
            text, images, captions, featured_image = extract_text_and_images(
                pdf_path,
                output_dir=f"./extracted_images/{paper_id}",
                max_pages=30
            )

            if not text or len(text) < 200:
                print(f"   ⚠️  Insufficient text extracted")
                stats["status"] = "insufficient_text"
                return stats

            # 2. Index TEXT to BGE-M3 index
            if not self.skip_text:
                print("   📝 Indexing text chunks (BGE-M3)...")
                text_chunks = self.chunker.chunk_text(text, metadata)

                if text_chunks:
                    chunk_texts = [c['text'] for c in text_chunks]
                    embeddings = self._generate_bge_embeddings(chunk_texts)

                    # Prepare vectors
                    vectors = []
                    for i, (chunk, emb) in enumerate(zip(text_chunks, embeddings)):
                        vec_id = f"{paper_id}_text_{i}"
                        vectors.append({
                            'id': vec_id,
                            'values': emb.tolist() if hasattr(emb, 'tolist') else list(emb),
                            'metadata': {
                                'paper_id': paper_id,
                                'title': title[:200],
                                'chunk_type': 'text',
                                'chunk_index': i,
                                'section': chunk.get('section', 'full_text'),
                                'page': chunk.get('page', 0),
                                'char_count': len(chunk['text']),
                                'text': chunk['text'][:1000]  # Pinecone metadata limit
                            }
                        })

                    # Upload in batches
                    batch_size = 100
                    for i in range(0, len(vectors), batch_size):
                        batch = vectors[i:i+batch_size]
                        self.text_index.upsert(vectors=batch)

                    stats["text_chunks"] = len(vectors)
                    print(f"   ✅ Text: {len(vectors)} chunks indexed")

            # 3. Index IMAGES/CAPTIONS to CLIP index
            if not self.skip_image:
                print("   🖼️  Indexing images/captions (CLIP)...")

                clip_vectors = []

                # 3a. Caption embeddings
                if captions:
                    caption_texts = [c.get('text', c.get('caption', '')) for c in captions if c]
                    caption_texts = [t for t in caption_texts if t and len(t) > 10]

                    if caption_texts:
                        caption_embs = self._generate_clip_embeddings(caption_texts)

                        for i, (caption, emb) in enumerate(zip(caption_texts, caption_embs)):
                            vec_id = f"{paper_id}_caption_{i}"
                            clip_vectors.append({
                                'id': vec_id,
                                'values': emb.tolist() if hasattr(emb, 'tolist') else list(emb),
                                'metadata': {
                                    'paper_id': paper_id,
                                    'filename': title[:100],
                                    'chunk_type': 'caption',
                                    'chunk_index': i,
                                    'page': captions[i].get('page', 0) if i < len(captions) else 0,
                                    'char_count': len(caption),
                                    'text': caption[:500]
                                }
                            })

                        stats["caption_chunks"] = len(clip_vectors)

                # 3b. Image embeddings (if extracted)
                if images:
                    image_paths = [img.get('path', '') for img in images[:10] if img.get('path')]
                    valid_paths = [p for p in image_paths if os.path.exists(p)]

                    if valid_paths:
                        image_embs = self._generate_clip_image_embeddings(valid_paths)

                        for i, (path, emb) in enumerate(zip(valid_paths, image_embs)):
                            vec_id = f"{paper_id}_image_{i}"
                            clip_vectors.append({
                                'id': vec_id,
                                'values': emb.tolist() if hasattr(emb, 'tolist') else list(emb),
                                'metadata': {
                                    'paper_id': paper_id,
                                    'filename': title[:100],
                                    'chunk_type': 'image',
                                    'chunk_index': i,
                                    'page': images[i].get('page', 0) if i < len(images) else 0,
                                    'char_count': 0,
                                    'image_path': path
                                }
                            })

                        stats["image_chunks"] = len(image_embs)

                # Upload to CLIP index
                if clip_vectors:
                    batch_size = 100
                    for i in range(0, len(clip_vectors), batch_size):
                        batch = clip_vectors[i:i+batch_size]
                        self.image_index.upsert(vectors=batch)

                    print(f"   ✅ Images/Captions: {len(clip_vectors)} chunks indexed")

            # Mark as processed
            self.processed_papers.add(paper_id)
            self._save_processed()

            print(f"   ✅ Complete: text={stats['text_chunks']}, captions={stats['caption_chunks']}, images={stats['image_chunks']}")

        except Exception as e:
            print(f"   ❌ Error: {e}")
            stats["status"] = "error"
            stats["error"] = str(e)
            import traceback
            traceback.print_exc()

        return stats

    def index_from_zotero(self, keys: List[str] = None, limit: int = None) -> Dict:
        """
        Index papers from Zotero storage.

        Args:
            keys: List of Zotero keys to process (None = all)
            limit: Maximum number of papers to process

        Returns:
            Summary statistics
        """
        from zotero_fetch import fetch_zotero_items
        from zotero_path_finder import get_default_pdf_dir

        print("\n" + "="*60)
        print("📚 Dual DB Indexing from Zotero")
        print("="*60)

        # Fetch Zotero items
        print("\n🔍 Fetching Zotero items...")
        items = fetch_zotero_items(
            os.getenv('ZOTERO_USER_ID'),
            os.getenv('ZOTERO_API_KEY')
        )
        print(f"   Found {len(items)} items")

        # Filter by keys if specified
        if keys:
            items = [item for item in items if item['key'] in keys]
            print(f"   Filtered to {len(items)} items by keys")

        # Apply limit
        if limit:
            items = items[:limit]
            print(f"   Limited to {limit} items")

        # Get PDF directory - ensure we're pointing to storage folder
        pdf_base = get_default_pdf_dir()
        # Add /storage if needed
        if not str(pdf_base).endswith('storage'):
            pdf_dir = Path(pdf_base) / 'storage'
        else:
            pdf_dir = Path(pdf_base)
        print(f"   PDF directory: {pdf_dir}")

        # Process each paper
        summary = {
            "total": len(items),
            "success": 0,
            "skipped": 0,
            "errors": 0,
            "text_chunks": 0,
            "image_chunks": 0
        }

        print(f"\n📄 Processing {len(items)} papers...")
        for i, item in enumerate(tqdm(items, desc="Indexing"), 1):
            key = item['key']
            title = item.get('title', key)

            # Find PDF in storage/KEY/ folder
            pdf_path = None
            storage_dir = pdf_dir / key
            if storage_dir.exists():
                pdfs = list(storage_dir.glob('*.pdf'))
                if pdfs:
                    pdf_path = str(pdfs[0])

            if not pdf_path:
                print(f"\n   ⚠️  No PDF for {key}: {title[:40]}...")
                summary["errors"] += 1
                continue

            # Index paper
            metadata = {
                'title': title,
                'authors': item.get('authors', []),
                'year': item.get('year', ''),
                'collection': item.get('collection_path', '')
            }

            result = self.index_paper(pdf_path, key, metadata)

            if result.get("status") == "skipped":
                summary["skipped"] += 1
            elif result.get("status") == "success":
                summary["success"] += 1
                summary["text_chunks"] += result.get("text_chunks", 0)
                summary["image_chunks"] += result.get("image_chunks", 0) + result.get("caption_chunks", 0)
            else:
                summary["errors"] += 1

        # Print summary
        print("\n" + "="*60)
        print("📊 Indexing Summary")
        print("="*60)
        print(f"   Total papers: {summary['total']}")
        print(f"   ✅ Success: {summary['success']}")
        print(f"   ⏭️  Skipped: {summary['skipped']}")
        print(f"   ❌ Errors: {summary['errors']}")
        print(f"   📝 Text chunks: {summary['text_chunks']}")
        print(f"   🖼️  Image chunks: {summary['image_chunks']}")

        return summary

    def get_stats(self) -> Dict:
        """Get current index statistics."""
        text_stats = self.text_index.describe_index_stats()
        image_stats = self.image_index.describe_index_stats()

        return {
            "text_index": {
                "name": self.text_index_name,
                "vectors": text_stats.total_vector_count,
                "dimension": 1024
            },
            "image_index": {
                "name": self.image_index_name,
                "vectors": image_stats.total_vector_count,
                "dimension": 512
            },
            "processed_papers": len(self.processed_papers)
        }


def main():
    parser = argparse.ArgumentParser(description="Dual DB Indexer for Papers")
    parser.add_argument('--pdf', type=str, help='Path to single PDF file')
    parser.add_argument('--key', type=str, help='Zotero key for the paper')
    parser.add_argument('--keys', type=str, help='Comma-separated Zotero keys')
    parser.add_argument('--from-json', type=str, help='JSON file with paper list (sync_report format)')
    parser.add_argument('--limit', type=int, help='Maximum papers to process')
    parser.add_argument('--skip-text', action='store_true', help='Skip text indexing')
    parser.add_argument('--skip-image', action='store_true', help='Skip image indexing')
    parser.add_argument('--stats', action='store_true', help='Show index statistics')

    args = parser.parse_args()

    # Initialize indexer
    indexer = DualDBIndexer(
        skip_text=args.skip_text,
        skip_image=args.skip_image
    )

    if args.stats:
        # Show statistics
        stats = indexer.get_stats()
        print("\n📊 Index Statistics:")
        print(f"   Text index ({stats['text_index']['name']}): {stats['text_index']['vectors']:,} vectors")
        print(f"   Image index ({stats['image_index']['name']}): {stats['image_index']['vectors']:,} vectors")
        print(f"   Processed papers: {stats['processed_papers']}")
        return

    if args.pdf:
        # Index single PDF
        key = args.key or Path(args.pdf).stem
        indexer.index_paper(args.pdf, key)

    elif args.keys:
        # Index specific keys from Zotero
        keys = [k.strip() for k in args.keys.split(',')]
        indexer.index_from_zotero(keys=keys, limit=args.limit)

    elif args.from_json:
        # Index from sync report JSON
        print(f"📂 Loading from: {args.from_json}")
        with open(args.from_json, 'r') as f:
            data = json.load(f)

        added_items = data.get('added', [])
        if not added_items:
            print("✅ No new papers to index")
            return

        keys = [item['key'] for item in added_items]
        print(f"   Found {len(keys)} papers to index")

        indexer.index_from_zotero(keys=keys, limit=args.limit)

    else:
        # Index all from Zotero
        indexer.index_from_zotero(limit=args.limit)


if __name__ == "__main__":
    main()
