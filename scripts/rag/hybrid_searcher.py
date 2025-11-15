"""
Hybrid Searcher for Multimodal RAG
텍스트와 이미지 DB를 통합 검색하는 인터페이스
"""

import os
import sys
import json
import numpy as np
from pathlib import Path
from typing import List, Dict, Optional, Tuple, Any, Union
from datetime import datetime
from PIL import Image
import heapq

# Add script directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import custom modules
from text_rag_bge_m3 import TextRAGBGEM3
from image_rag_clip import ImageRAGCLIP
from relation_manager import RelationManager

# Environment variables
from dotenv import load_dotenv
load_dotenv()


class HybridSearcher:
    """
    Unified search interface for multimodal RAG system.
    Combines text and image search with relationship awareness.
    """

    def __init__(self,
                 text_db_type: str = "chroma",
                 image_db_type: str = "chroma",
                 use_relations: bool = True):
        """
        Initialize the hybrid searcher.

        Args:
            text_db_type: Database type for text RAG
            image_db_type: Database type for image RAG
            use_relations: Whether to use relation manager
        """
        print("🚀 Initializing Hybrid Searcher...")

        # Initialize individual RAG systems
        try:
            self.text_rag = TextRAGBGEM3(db_type=text_db_type)
            print("✅ Text RAG (BGE-M3) initialized")
        except Exception as e:
            print(f"⚠️ Text RAG initialization failed: {e}")
            self.text_rag = None

        try:
            self.image_rag = ImageRAGCLIP(db_type=image_db_type)
            print("✅ Image RAG (CLIP) initialized")
        except Exception as e:
            print(f"⚠️ Image RAG initialization failed: {e}")
            self.image_rag = None

        # Initialize relation manager
        if use_relations:
            try:
                self.relations = RelationManager()
                print("✅ Relation Manager initialized")
            except Exception as e:
                print(f"⚠️ Relation Manager initialization failed: {e}")
                self.relations = None
        else:
            self.relations = None

        print("✅ Hybrid Searcher ready")

    def search_comprehensive(self,
                            query: str,
                            mode: str = "hybrid",
                            k: int = 10,
                            text_weight: float = 0.65,
                            image_weight: float = 0.35,
                            filter_paper: Optional[str] = None) -> List[Dict]:
        """
        Comprehensive search across text and image databases.

        Args:
            query: Search query
            mode: Search mode - "text", "image", or "hybrid"
            k: Number of results to return
            text_weight: Weight for text results (hybrid mode)
            image_weight: Weight for image results (hybrid mode)
            filter_paper: Optional paper ID to filter results

        Returns:
            List of search results with enriched information
        """
        results = []

        # Prepare filter
        filter_dict = {'paper_id': filter_paper} if filter_paper else None

        # Text search
        if mode in ["text", "hybrid"] and self.text_rag:
            text_results = self.text_rag.search(query, k=k*2, filter_dict=filter_dict)

            # Enrich text results
            for result in text_results:
                result['modality'] = 'text'
                result['weighted_score'] = result['score'] * text_weight if mode == "hybrid" else result['score']

                # Add related images if relations available
                if self.relations:
                    chunk_id = result['id']
                    related_images = self.relations.get_related_images(chunk_id)
                    result['related_images'] = related_images[:3]  # Top 3 related images

                    # Add paper info
                    paper_id = result['metadata'].get('paper_id')
                    if paper_id:
                        paper_info = self.relations.get_paper_info(paper_id)
                        if paper_info:
                            result['paper_title'] = paper_info.get('title', '')
                            result['paper_year'] = paper_info.get('year', 0)
                            result['paper_authors'] = paper_info.get('authors', '')

                results.extend([result])

        # Image search
        if mode in ["image", "hybrid"] and self.image_rag:
            image_results = self.image_rag.search_by_text(query, k=k*2, filter_dict=filter_dict)

            # Enrich image results
            for result in image_results:
                result['modality'] = 'image'
                result['weighted_score'] = result['score'] * image_weight if mode == "hybrid" else result['score']

                # Add text context if relations available
                if self.relations:
                    image_id = result['id']
                    text_context = self.relations.get_image_context(image_id)
                    result['text_context'] = text_context[:3]  # Top 3 related chunks

                    # Add paper info
                    paper_id = result['metadata'].get('paper_id')
                    if paper_id:
                        paper_info = self.relations.get_paper_info(paper_id)
                        if paper_info:
                            result['paper_title'] = paper_info.get('title', '')
                            result['paper_year'] = paper_info.get('year', 0)
                            result['paper_authors'] = paper_info.get('authors', '')

                results.append(result)

        # Merge and rank results for hybrid mode
        if mode == "hybrid" and len(results) > 0:
            results = self._merge_and_rank_results(results, k)
        else:
            # Simple sorting for single-mode search
            results = sorted(results, key=lambda x: x.get('weighted_score', x.get('score', 0)), reverse=True)[:k]

        return results

    def _merge_and_rank_results(self,
                                results: List[Dict],
                                k: int) -> List[Dict]:
        """
        Merge and re-rank results from different modalities.

        Args:
            results: Combined list of results
            k: Number of results to return

        Returns:
            Merged and ranked results
        """
        # Group results by paper
        paper_groups = {}
        for result in results:
            paper_id = result['metadata'].get('paper_id', 'unknown')
            if paper_id not in paper_groups:
                paper_groups[paper_id] = {
                    'text_results': [],
                    'image_results': [],
                    'max_score': 0,
                    'paper_info': {}
                }

            if result['modality'] == 'text':
                paper_groups[paper_id]['text_results'].append(result)
            else:
                paper_groups[paper_id]['image_results'].append(result)

            # Track maximum score and paper info
            score = result.get('weighted_score', result.get('score', 0))
            if score > paper_groups[paper_id]['max_score']:
                paper_groups[paper_id]['max_score'] = score
                paper_groups[paper_id]['paper_info'] = {
                    'title': result.get('paper_title', ''),
                    'year': result.get('paper_year', 0),
                    'authors': result.get('paper_authors', '')
                }

        # Create merged results
        merged = []
        for paper_id, group in paper_groups.items():
            # Calculate combined score
            text_scores = [r.get('weighted_score', 0) for r in group['text_results']]
            image_scores = [r.get('weighted_score', 0) for r in group['image_results']]

            combined_score = max(text_scores) if text_scores else 0
            combined_score += max(image_scores) if image_scores else 0

            # Create merged result
            merged_result = {
                'paper_id': paper_id,
                'combined_score': combined_score,
                'text_matches': len(group['text_results']),
                'image_matches': len(group['image_results']),
                'best_text': group['text_results'][0] if group['text_results'] else None,
                'best_image': group['image_results'][0] if group['image_results'] else None,
                'paper_info': group['paper_info']
            }
            merged.append(merged_result)

        # Sort by combined score
        merged = sorted(merged, key=lambda x: x['combined_score'], reverse=True)

        # Expand back to individual results
        final_results = []
        for m in merged[:k]:
            # Add best text result
            if m['best_text']:
                m['best_text']['combined_score'] = m['combined_score']
                final_results.append(m['best_text'])

            # Add best image result if no text or high image score
            if m['best_image'] and (not m['best_text'] or m['image_matches'] > m['text_matches']):
                m['best_image']['combined_score'] = m['combined_score']
                final_results.append(m['best_image'])

            if len(final_results) >= k:
                break

        return final_results[:k]

    def find_paper_by_image(self,
                            image_path: str,
                            k: int = 5) -> List[Dict]:
        """
        Find papers containing similar images.

        Args:
            image_path: Path to query image
            k: Number of papers to return

        Returns:
            List of papers with similarity scores
        """
        if not self.image_rag:
            print("⚠️ Image RAG not available")
            return []

        # Search for similar images
        similar_images = self.image_rag.search_by_image(image_path, k=k*3)

        # Group by paper and enrich
        papers = {}
        for img in similar_images:
            paper_id = img['metadata'].get('paper_id')
            if paper_id not in papers:
                papers[paper_id] = {
                    'paper_id': paper_id,
                    'best_match_score': img['score'],
                    'matched_images': [],
                    'paper_info': {}
                }

                # Get paper info from relations
                if self.relations:
                    paper_info = self.relations.get_paper_info(paper_id)
                    if paper_info:
                        papers[paper_id]['paper_info'] = paper_info

            papers[paper_id]['matched_images'].append({
                'image_id': img['id'],
                'score': img['score'],
                'page': img['metadata'].get('page', 0),
                'caption': img.get('caption', '')
            })

        # Convert to list and sort
        paper_list = list(papers.values())
        paper_list = sorted(paper_list, key=lambda x: x['best_match_score'], reverse=True)

        return paper_list[:k]

    def get_paper_summary(self, paper_id: str) -> Dict:
        """
        Get comprehensive summary of a paper.

        Args:
            paper_id: Paper identifier

        Returns:
            Paper summary with text and images
        """
        summary = {
            'paper_id': paper_id,
            'paper_info': {},
            'text_chunks': [],
            'images': [],
            'featured_image': None,
            'statistics': {}
        }

        # Get paper info from relations
        if self.relations:
            paper_info = self.relations.get_paper_info(paper_id)
            if paper_info:
                summary['paper_info'] = paper_info
                summary['featured_image'] = self.relations.get_featured_image(paper_id)

        # Get text chunks
        if self.text_rag:
            filter_dict = {'paper_id': paper_id}
            text_chunks = self.text_rag.search("", k=100, filter_dict=filter_dict)
            summary['text_chunks'] = text_chunks[:10]  # Top 10 chunks
            summary['statistics']['total_text_chunks'] = len(text_chunks)

        # Get images
        if self.image_rag:
            images = self.image_rag.get_paper_images(paper_id)
            summary['images'] = images
            summary['statistics']['total_images'] = len(images)

        return summary

    def cross_modal_search(self,
                          query: Union[str, str],
                          query_type: str = "text",
                          target_type: str = "both",
                          k: int = 10) -> List[Dict]:
        """
        Cross-modal search: text→image or image→text.

        Args:
            query: Query (text or image path)
            query_type: "text" or "image"
            target_type: "text", "image", or "both"
            k: Number of results

        Returns:
            Search results
        """
        results = []

        if query_type == "text":
            # Text query
            if target_type in ["image", "both"] and self.image_rag:
                # Text → Image search using CLIP
                image_results = self.image_rag.search_by_text(query, k=k)
                for r in image_results:
                    r['search_type'] = 'text_to_image'
                results.extend(image_results)

            if target_type in ["text", "both"] and self.text_rag:
                # Regular text search
                text_results = self.text_rag.search(query, k=k)
                for r in text_results:
                    r['search_type'] = 'text_to_text'
                results.extend(text_results)

        elif query_type == "image":
            # Image query
            if target_type in ["image", "both"] and self.image_rag:
                # Image → Image search
                image_results = self.image_rag.search_by_image(query, k=k)
                for r in image_results:
                    r['search_type'] = 'image_to_image'
                results.extend(image_results)

            # Note: Image → Text search would require different approach
            # (e.g., generating text description from image first)

        # Sort by score
        results = sorted(results, key=lambda x: x.get('score', 0), reverse=True)[:k]

        return results

    def analyze_query_intent(self, query: str) -> Dict:
        """
        Analyze query to determine best search strategy.

        Args:
            query: User query

        Returns:
            Analysis with recommendations
        """
        analysis = {
            'query': query,
            'recommended_mode': 'hybrid',
            'likely_targets': [],
            'keywords': []
        }

        # Check for image-related keywords
        image_keywords = ['figure', 'graph', 'chart', 'diagram', 'image', 'plot',
                         '그림', '도표', '차트', '그래프']
        for keyword in image_keywords:
            if keyword.lower() in query.lower():
                analysis['recommended_mode'] = 'image'
                analysis['likely_targets'].append('image')

        # Check for text-heavy keywords
        text_keywords = ['abstract', 'introduction', 'methods', 'results', 'discussion',
                        'conclusion', '초록', '서론', '방법', '결과', '논의', '결론']
        for keyword in text_keywords:
            if keyword.lower() in query.lower():
                analysis['recommended_mode'] = 'text'
                analysis['likely_targets'].append('text')

        # Extract potential keywords
        words = query.split()
        keywords = [w for w in words if len(w) > 3 and not w.lower() in ['the', 'and', 'or', 'in', 'on', 'at']]
        analysis['keywords'] = keywords

        return analysis

    def get_statistics(self) -> Dict:
        """
        Get system statistics.

        Returns:
            Statistics dictionary
        """
        stats = {
            'text_rag': {},
            'image_rag': {},
            'relations': {}
        }

        # Get relation statistics
        if self.relations:
            stats['relations'] = self.relations.get_statistics()

        # Note: Would need to add methods in RAG classes to get their stats

        return stats

    def close(self):
        """Close all connections."""
        if self.relations:
            self.relations.close()


def main():
    """Main function for testing hybrid search."""
    import argparse

    parser = argparse.ArgumentParser(description="Hybrid Multimodal Searcher")
    parser.add_argument("--query", type=str, help="Search query")
    parser.add_argument("--image", type=str, help="Image path for image search")
    parser.add_argument("--mode", type=str, default="hybrid",
                       choices=["text", "image", "hybrid"],
                       help="Search mode")
    parser.add_argument("--k", type=int, default=10, help="Number of results")
    parser.add_argument("--paper", type=str, help="Get summary for specific paper")

    args = parser.parse_args()

    # Initialize searcher
    searcher = HybridSearcher()

    if args.query:
        # Analyze query
        analysis = searcher.analyze_query_intent(args.query)
        print(f"\n📊 Query Analysis:")
        print(f"  Recommended mode: {analysis['recommended_mode']}")
        print(f"  Keywords: {analysis['keywords']}")

        # Perform search
        results = searcher.search_comprehensive(
            args.query,
            mode=args.mode,
            k=args.k
        )

        print(f"\n🔍 Found {len(results)} results:\n")
        for i, result in enumerate(results, 1):
            print(f"{i}. {result.get('modality', 'unknown').upper()} Result")
            print(f"   Score: {result.get('weighted_score', result.get('score', 0)):.3f}")

            if result['modality'] == 'text':
                print(f"   Text: {result['text'][:150]}...")
            else:
                print(f"   Image: {result['metadata'].get('filename', 'unknown')}")
                print(f"   Caption: {result.get('caption', '')[:150]}...")

            if 'paper_title' in result:
                print(f"   Paper: {result['paper_title']} ({result.get('paper_year', 'N/A')})")

            print()

    elif args.image:
        # Search by image
        results = searcher.find_paper_by_image(args.image, k=args.k)

        print(f"\n🖼️ Found {len(results)} papers with similar images:\n")
        for i, paper in enumerate(results, 1):
            print(f"{i}. Paper: {paper['paper_id']}")
            print(f"   Best match score: {paper['best_match_score']:.3f}")
            print(f"   Matched images: {len(paper['matched_images'])}")

            if paper['paper_info']:
                info = paper['paper_info']
                print(f"   Title: {info.get('title', 'N/A')}")
                print(f"   Year: {info.get('year', 'N/A')}")

            print()

    elif args.paper:
        # Get paper summary
        summary = searcher.get_paper_summary(args.paper)

        print(f"\n📄 Paper Summary: {args.paper}\n")
        if summary['paper_info']:
            info = summary['paper_info']
            print(f"Title: {info.get('title', 'N/A')}")
            print(f"Authors: {info.get('authors', 'N/A')}")
            print(f"Year: {info.get('year', 'N/A')}")

        print(f"\nStatistics:")
        for key, value in summary['statistics'].items():
            print(f"  {key}: {value}")

        if summary['featured_image']:
            print(f"\nFeatured Image: {summary['featured_image'].get('filename', 'N/A')}")

    else:
        # Show statistics
        stats = searcher.get_statistics()
        print("\n📈 System Statistics:\n")
        for category, data in stats.items():
            print(f"{category}:")
            for key, value in data.items():
                print(f"  {key}: {value}")

    searcher.close()


if __name__ == "__main__":
    main()