"""
Main Builder for Multimodal RAG System
텍스트와 이미지 분리 DB 구축 및 관계 설정
"""

import os
import sys
import json
import argparse
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime
from tqdm import tqdm
import time

# Add script directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import custom modules
from text_rag_bge_m3 import TextRAGBGEM3
from image_rag_clip import ImageRAGCLIP
from relation_manager import RelationManager
from hybrid_searcher import HybridSearcher

# Environment variables
from dotenv import load_dotenv
load_dotenv()


class MultimodalRAGBuilder:
    """
    Main builder for the complete multimodal RAG system.
    Orchestrates text DB, image DB, and relationship building.
    """

    def __init__(self,
                 db_type: str = "chroma",
                 rebuild: bool = False):
        """
        Initialize the builder.

        Args:
            db_type: Database type ("chroma" or "pinecone")
            rebuild: Whether to rebuild from scratch
        """
        self.db_type = db_type
        self.rebuild = rebuild

        print("=" * 60)
        print("🚀 Multimodal RAG System Builder")
        print("=" * 60)

        # Initialize components
        self.text_rag = None
        self.image_rag = None
        self.relations = None

        # Statistics
        self.stats = {
            'papers_processed': 0,
            'text_chunks': 0,
            'images': 0,
            'relations': 0,
            'errors': []
        }

    def build_text_db(self, papers: List[Dict], use_semantic: bool = True):
        """
        Build text database with BGE-M3.

        Args:
            papers: List of paper dictionaries
            use_semantic: Use semantic chunking
        """
        print("\n" + "=" * 60)
        print("📚 Building Text Database (BGE-M3)")
        print("=" * 60)

        try:
            # Initialize text RAG
            self.text_rag = TextRAGBGEM3(
                db_type=self.db_type,
                use_semantic_chunking=use_semantic
            )

            # Process each paper
            for paper in tqdm(papers, desc="Processing text"):
                paper_id = paper.get('paper_id', Path(paper['pdf_path']).stem)
                pdf_path = paper['pdf_path']
                metadata = paper.get('metadata', {})

                try:
                    # Process paper
                    result = self.text_rag.process_paper(paper_id, pdf_path, metadata)

                    if result.get('status') != 'error':
                        self.stats['text_chunks'] += result.get('chunks', 0)

                        # Add to relations if available
                        if self.relations:
                            self._add_text_to_relations(paper_id, result)

                except Exception as e:
                    print(f"  ❌ Error processing {paper_id}: {e}")
                    self.stats['errors'].append(f"Text/{paper_id}: {str(e)}")

            print(f"\n✅ Text DB complete: {self.stats['text_chunks']} chunks")

        except Exception as e:
            print(f"❌ Failed to build text DB: {e}")
            self.stats['errors'].append(f"Text DB: {str(e)}")

    def build_image_db(self, papers: List[Dict], max_images: int = 20):
        """
        Build image database with CLIP.

        Args:
            papers: List of paper dictionaries
            max_images: Maximum images per paper
        """
        print("\n" + "=" * 60)
        print("🖼️ Building Image Database (CLIP)")
        print("=" * 60)

        try:
            # Initialize image RAG
            self.image_rag = ImageRAGCLIP(
                db_type=self.db_type,
                max_images_per_paper=max_images
            )

            # Process each paper
            for paper in tqdm(papers, desc="Processing images"):
                paper_id = paper.get('paper_id', Path(paper['pdf_path']).stem)
                pdf_path = paper['pdf_path']
                metadata = paper.get('metadata', {})

                try:
                    # Process paper
                    result = self.image_rag.process_paper(paper_id, pdf_path, metadata)

                    if result.get('status') != 'error':
                        self.stats['images'] += result.get('images', 0)

                        # Add to relations if available
                        if self.relations:
                            self._add_images_to_relations(paper_id, result)

                except Exception as e:
                    print(f"  ❌ Error processing {paper_id}: {e}")
                    self.stats['errors'].append(f"Image/{paper_id}: {str(e)}")

            print(f"\n✅ Image DB complete: {self.stats['images']} images")

        except Exception as e:
            print(f"❌ Failed to build image DB: {e}")
            self.stats['errors'].append(f"Image DB: {str(e)}")

    def build_relations(self, papers: List[Dict]):
        """
        Build relationships between text and images.

        Args:
            papers: List of paper dictionaries
        """
        print("\n" + "=" * 60)
        print("🔗 Building Cross-Database Relations")
        print("=" * 60)

        try:
            # Initialize relation manager
            self.relations = RelationManager()

            # Process each paper
            for paper in tqdm(papers, desc="Building relations"):
                paper_id = paper.get('paper_id', Path(paper['pdf_path']).stem)
                metadata = paper.get('metadata', {})

                try:
                    # Add paper info
                    self.relations.add_paper(
                        paper_id,
                        title=metadata.get('title', ''),
                        authors=metadata.get('authors', ''),
                        year=metadata.get('year', 0),
                        doi=metadata.get('doi', ''),
                        abstract=metadata.get('abstract', '')
                    )

                    # Build automatic relationships
                    self.relations.build_relationships_for_paper(paper_id)
                    self.stats['relations'] += 1

                except Exception as e:
                    print(f"  ❌ Error processing {paper_id}: {e}")
                    self.stats['errors'].append(f"Relations/{paper_id}: {str(e)}")

            # Get final statistics
            rel_stats = self.relations.get_statistics()
            print(f"\n✅ Relations complete:")
            for key, value in rel_stats.items():
                print(f"   {key}: {value}")

        except Exception as e:
            print(f"❌ Failed to build relations: {e}")
            self.stats['errors'].append(f"Relations: {str(e)}")

    def _add_text_to_relations(self, paper_id: str, result: Dict):
        """Add text processing results to relations."""
        # This would be implemented to add text chunks to relations
        pass

    def _add_images_to_relations(self, paper_id: str, result: Dict):
        """Add image processing results to relations."""
        # This would be implemented to add images to relations
        pass

    def build_all(self,
                 papers: List[Dict],
                 modes: List[str] = ["text", "image", "relations"]):
        """
        Build all components.

        Args:
            papers: List of paper dictionaries
            modes: Which components to build
        """
        start_time = time.time()

        print(f"\n📊 Processing {len(papers)} papers")
        print(f"   Modes: {', '.join(modes)}")

        # Build relations first if requested (needed for enrichment)
        if "relations" in modes:
            self.build_relations(papers)

        # Build text database
        if "text" in modes:
            self.build_text_db(papers)

        # Build image database
        if "image" in modes:
            self.build_image_db(papers)

        # Final statistics
        elapsed = time.time() - start_time
        self.print_statistics(elapsed)

    def print_statistics(self, elapsed_time: float):
        """Print final statistics."""
        print("\n" + "=" * 60)
        print("📈 Build Statistics")
        print("=" * 60)

        print(f"✅ Papers processed: {self.stats['papers_processed']}")
        print(f"📝 Text chunks: {self.stats['text_chunks']}")
        print(f"🖼️ Images: {self.stats['images']}")
        print(f"🔗 Relations: {self.stats['relations']}")

        if self.stats['errors']:
            print(f"\n⚠️ Errors ({len(self.stats['errors'])}):")
            for error in self.stats['errors'][:5]:  # Show first 5 errors
                print(f"   - {error}")

        print(f"\n⏱️ Total time: {elapsed_time:.1f} seconds")
        print("=" * 60)


def load_batch_file(batch_file: str) -> List[Dict]:
    """
    Load batch file with paper information.

    Args:
        batch_file: Path to JSON batch file

    Returns:
        List of paper dictionaries
    """
    with open(batch_file, 'r') as f:
        batch = json.load(f)

    # Ensure each item has required fields
    papers = []
    for item in batch:
        if 'pdf_path' in item:
            paper = {
                'pdf_path': item['pdf_path'],
                'paper_id': item.get('paper_id', Path(item['pdf_path']).stem),
                'metadata': item.get('metadata', {})
            }
            papers.append(paper)

    return papers


def main():
    """Main function."""
    parser = argparse.ArgumentParser(
        description="Build Multimodal RAG System with Text and Image Databases"
    )

    # Input options
    parser.add_argument("--batch", type=str, required=True,
                       help="Batch JSON file with papers")
    parser.add_argument("--mode", type=str, nargs='+',
                       default=["text", "image", "relations"],
                       choices=["text", "image", "relations", "all"],
                       help="Which components to build")

    # Database options
    parser.add_argument("--db", type=str, default="chroma",
                       choices=["chroma", "pinecone"],
                       help="Database type")
    parser.add_argument("--rebuild", action="store_true",
                       help="Rebuild from scratch (clear existing)")

    # Text options
    parser.add_argument("--semantic-chunking", action="store_true", default=True,
                       help="Use semantic chunking for text")

    # Image options
    parser.add_argument("--max-images", type=int, default=20,
                       help="Maximum images per paper")

    # Parse arguments
    args = parser.parse_args()

    # Handle "all" mode
    if "all" in args.mode:
        modes = ["text", "image", "relations"]
    else:
        modes = args.mode

    # Load batch file
    print(f"📂 Loading batch file: {args.batch}")
    papers = load_batch_file(args.batch)
    print(f"✅ Loaded {len(papers)} papers")

    # Initialize builder
    builder = MultimodalRAGBuilder(
        db_type=args.db,
        rebuild=args.rebuild
    )

    # Build components
    builder.build_all(papers, modes)

    print("\n✨ Build complete!")


if __name__ == "__main__":
    main()