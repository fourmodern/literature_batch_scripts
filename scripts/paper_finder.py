#!/usr/bin/env python
"""
Paper Finder - 논문 검색 및 메타데이터 반환
질문에서 관련 논문을 찾아 제목, 저자, 연도 등을 반환
"""

import os
import sys
from typing import List, Dict, Optional
import json
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))

from dotenv import load_dotenv
load_dotenv()

import chromadb
from FlagEmbedding import BGEM3FlagModel
try:
    import openai
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False


class PaperFinder:
    def __init__(self, db_type: str = "chroma"):
        """Initialize Paper Finder"""
        self.db_type = db_type

        # Initialize BGE-M3 model
        print("🔄 Loading BGE-M3 model...")
        self.model = BGEM3FlagModel('BAAI/bge-m3', use_fp16=True)

        # Initialize database
        if db_type == "chroma":
            self.text_client = chromadb.PersistentClient('./text_rag_bge_m3')
            self.text_collection = self.text_client.get_collection('text_papers_bge_m3')

            self.image_client = chromadb.PersistentClient('./image_rag_clip')
            self.image_collection = self.image_client.get_collection('image_papers_clip')

        # OpenAI for query understanding
        if OPENAI_AVAILABLE:
            openai.api_key = os.getenv("OPENAI_API_KEY")

    def extract_search_intent(self, query: str) -> Dict:
        """Extract search intent from natural language query"""

        prompt = f"""
        사용자의 질문에서 논문 검색 의도를 파악하세요:

        질문: {query}

        다음 정보를 JSON 형식으로 추출하세요:
        - search_keywords: 핵심 검색 키워드 (리스트)
        - topic: 주요 주제
        - author_hints: 저자 관련 힌트 (있다면)
        - year_range: 연도 범위 (있다면)
        - specific_terms: 특정 기술/약물/방법론

        예시:
        {{"search_keywords": ["LNP", "mRNA delivery"], "topic": "lipid nanoparticle", "specific_terms": ["ALC-0315"]}}
        """

        if not OPENAI_AVAILABLE:
            # Fallback to simple keyword extraction
            return {"search_keywords": query.split(), "topic": query}

        try:
            response = openai.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "You are a scientific literature search assistant."},
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"},
                temperature=0
            )

            return json.loads(response.choices[0].message.content)
        except:
            # Fallback to simple keyword extraction
            return {"search_keywords": query.split(), "topic": query}

    def find_papers(self, query: str, top_k: int = 10) -> List[Dict]:
        """Find relevant papers based on query"""

        # Extract search intent
        intent = self.extract_search_intent(query)
        print(f"\n🔍 Search intent: {intent}")

        # Create enhanced query
        enhanced_query = " ".join(intent.get('search_keywords', [query]))

        # Generate embedding
        embedding = self.model.encode(
            enhanced_query,
            batch_size=1,
            max_length=8192
        )['dense_vecs'].tolist()[0]

        # Search in text database
        results = self.text_collection.query(
            query_embeddings=[embedding],
            n_results=top_k * 3,  # Get more results for deduplication
            include=['metadatas', 'documents', 'distances']
        )

        # Extract unique papers
        papers_dict = {}

        for i, metadata in enumerate(results['metadatas'][0]):
            if metadata:
                paper_id = metadata.get('paper_id', '')

                if paper_id and paper_id not in papers_dict:
                    papers_dict[paper_id] = {
                        'paper_id': paper_id,
                        'title': metadata.get('title', 'Unknown Title'),
                        'authors': metadata.get('authors', 'Unknown Authors'),
                        'year': metadata.get('year', 'N/A'),
                        'journal': metadata.get('journal', 'N/A'),
                        'doi': metadata.get('doi', ''),
                        'abstract': metadata.get('abstract', '')[:500],  # First 500 chars
                        'relevance_score': 1.0 - results['distances'][0][i],
                        'matched_content': results['documents'][0][i][:200] if results['documents'][0][i] else '',
                        'chunk_type': metadata.get('chunk_type', 'text')
                    }

        # Sort by relevance and return top k
        papers = sorted(papers_dict.values(), key=lambda x: x['relevance_score'], reverse=True)

        return papers[:top_k]

    def search_by_author(self, author_name: str, top_k: int = 10) -> List[Dict]:
        """Search papers by author name"""

        # Search for author in metadata
        results = self.text_collection.get(
            where={"authors": {"$contains": author_name}},
            limit=1000,
            include=['metadatas']
        )

        papers_dict = {}
        for metadata in results['metadatas']:
            if metadata:
                paper_id = metadata.get('paper_id', '')
                if paper_id and paper_id not in papers_dict:
                    papers_dict[paper_id] = {
                        'paper_id': paper_id,
                        'title': metadata.get('title', 'Unknown Title'),
                        'authors': metadata.get('authors', 'Unknown Authors'),
                        'year': metadata.get('year', 'N/A'),
                        'journal': metadata.get('journal', 'N/A'),
                        'doi': metadata.get('doi', '')
                    }

        papers = sorted(papers_dict.values(), key=lambda x: x.get('year', '0'), reverse=True)
        return papers[:top_k]

    def search_by_keyword(self, keyword: str, top_k: int = 10) -> List[Dict]:
        """Search papers by specific keyword"""

        # Generate embedding for keyword
        embedding = self.model.encode(
            keyword,
            batch_size=1,
            max_length=8192
        )['dense_vecs'].tolist()[0]

        # Search
        results = self.text_collection.query(
            query_embeddings=[embedding],
            n_results=top_k * 2,
            include=['metadatas', 'distances']
        )

        papers_dict = {}
        for i, metadata in enumerate(results['metadatas'][0]):
            if metadata:
                paper_id = metadata.get('paper_id', '')
                if paper_id and paper_id not in papers_dict:
                    papers_dict[paper_id] = {
                        'paper_id': paper_id,
                        'title': metadata.get('title', 'Unknown Title'),
                        'authors': metadata.get('authors', 'Unknown Authors'),
                        'year': metadata.get('year', 'N/A'),
                        'relevance_score': 1.0 - results['distances'][0][i]
                    }

        papers = sorted(papers_dict.values(), key=lambda x: x['relevance_score'], reverse=True)
        return papers[:top_k]

    def get_paper_details(self, paper_id: str) -> Dict:
        """Get detailed information about a specific paper"""

        # Get all chunks for this paper
        results = self.text_collection.get(
            where={"paper_id": paper_id},
            include=['metadatas', 'documents']
        )

        if not results['metadatas']:
            return None

        # Get first metadata (should be consistent across chunks)
        metadata = results['metadatas'][0]

        # Collect all text chunks
        chunks = []
        for i, doc in enumerate(results['documents']):
            chunk_meta = results['metadatas'][i]
            chunks.append({
                'type': chunk_meta.get('chunk_type', 'text'),
                'content': doc
            })

        # Check for images
        image_results = self.image_collection.get(
            where={"paper_id": paper_id},
            include=['metadatas']
        )

        images = []
        for img_meta in image_results['metadatas']:
            if img_meta:
                images.append({
                    'path': img_meta.get('image_path', ''),
                    'caption': img_meta.get('caption', ''),
                    'page': img_meta.get('page', 0)
                })

        return {
            'paper_id': paper_id,
            'title': metadata.get('title', 'Unknown Title'),
            'authors': metadata.get('authors', 'Unknown Authors'),
            'year': metadata.get('year', 'N/A'),
            'journal': metadata.get('journal', 'N/A'),
            'doi': metadata.get('doi', ''),
            'abstract': metadata.get('abstract', ''),
            'num_chunks': len(chunks),
            'num_images': len(images),
            'chunks': chunks[:5],  # First 5 chunks
            'images': images[:3]   # First 3 images
        }

    def format_results(self, papers: List[Dict], query: str) -> str:
        """Format search results for display"""

        if not papers:
            return "🔍 No papers found matching your query."

        output = f"📚 Found {len(papers)} papers for: '{query}'\n"
        output += "=" * 70 + "\n\n"

        for i, paper in enumerate(papers, 1):
            output += f"{i}. 📄 {paper['title']}\n"
            output += f"   👥 {paper['authors']}\n"
            output += f"   📅 Year: {paper.get('year', 'N/A')}"

            if paper.get('journal'):
                output += f" | 📖 {paper['journal']}"

            if paper.get('doi'):
                output += f"\n   🔗 DOI: {paper['doi']}"

            if paper.get('relevance_score'):
                output += f"\n   📊 Relevance: {paper['relevance_score']:.2%}"

            if paper.get('matched_content'):
                output += f"\n   💡 Snippet: ...{paper['matched_content']}..."

            output += "\n" + "-" * 70 + "\n"

        return output


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Find papers in the database")
    parser.add_argument("query", help="Search query")
    parser.add_argument("--top-k", type=int, default=5, help="Number of results")
    parser.add_argument("--author", action="store_true", help="Search by author")
    parser.add_argument("--keyword", action="store_true", help="Search by keyword")
    parser.add_argument("--details", help="Get details for specific paper ID")

    args = parser.parse_args()

    # Initialize finder
    finder = PaperFinder()

    if args.details:
        # Get paper details
        details = finder.get_paper_details(args.details)
        if details:
            print(f"\n📄 Paper Details: {details['title']}")
            print(f"Authors: {details['authors']}")
            print(f"Year: {details['year']}")
            print(f"Chunks: {details['num_chunks']}, Images: {details['num_images']}")
        else:
            print("Paper not found")

    elif args.author:
        # Search by author
        papers = finder.search_by_author(args.query, args.top_k)
        print(f"\n📚 Papers by '{args.query}':")
        for paper in papers:
            print(f"- {paper['year']}: {paper['title']}")

    elif args.keyword:
        # Search by keyword
        papers = finder.search_by_keyword(args.query, args.top_k)
        print(finder.format_results(papers, args.query))

    else:
        # Natural language search
        papers = finder.find_papers(args.query, args.top_k)
        print(finder.format_results(papers, args.query))


if __name__ == "__main__":
    main()