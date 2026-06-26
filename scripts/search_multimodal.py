#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
멀티모달 RAG 검색 도구
"""

import os
from typing import List, Dict, Any
import chromadb
from sentence_transformers import SentenceTransformer
from PIL import Image
import json

class MultimodalSearcher:
    def __init__(self, use_pinecone: bool = False):
        """멀티모달 검색 초기화"""

        # CLIP 모델 로드
        print("🔄 CLIP 모델 로딩 중...")
        self.model = SentenceTransformer('clip-ViT-B-32')

        # ChromaDB 연결
        self.client = chromadb.PersistentClient(path="./real_multimodal_db")
        self.collection = self.client.get_collection("vision_language_papers")
        print(f"✅ ChromaDB 연결됨: {self.collection.count()}개 벡터")

        # Pinecone (선택적)
        self.pinecone_index = None
        if use_pinecone:
            try:
                from pinecone import Pinecone
                pc = Pinecone(api_key=os.getenv('PINECONE_API_KEY'))
                self.pinecone_index = pc.Index('multimodal-papers')
                print("✅ Pinecone 연결됨")
            except:
                print("⚠️  Pinecone 연결 실패")

    def search_text(self, query: str, top_k: int = 10, search_type: str = "both"):
        """
        텍스트로 검색

        Args:
            query: 검색 쿼리
            top_k: 반환할 결과 수
            search_type: "text", "image", "both" 중 선택
        """
        print(f"\n🔍 검색: '{query}' (타입: {search_type})")

        # 쿼리 임베딩
        query_embedding = self.model.encode(query).tolist()

        # ChromaDB에서 검색
        where_clause = None if search_type == "both" else {"type": search_type}

        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            where=where_clause
        )

        return self._format_results(results)

    def search_image(self, image_path: str, top_k: int = 10):
        """
        이미지로 유사한 이미지/텍스트 검색

        Args:
            image_path: 검색할 이미지 경로
            top_k: 반환할 결과 수
        """
        print(f"\n🖼️  이미지로 검색: {image_path}")

        # 이미지 임베딩
        image = Image.open(image_path)
        image_embedding = self.model.encode(image).tolist()

        # ChromaDB에서 검색
        results = self.collection.query(
            query_embeddings=[image_embedding],
            n_results=top_k
        )

        return self._format_results(results)

    def _format_results(self, results):
        """검색 결과 포맷팅"""
        formatted = []

        for i, doc_id in enumerate(results['ids'][0]):
            metadata = results['metadatas'][0][i]
            distance = results['distances'][0][i]

            # 문서 내용 추출
            if 'documents' in results and results['documents'][0][i]:
                content = results['documents'][0][i][:200] + "..."
            else:
                content = "No content"

            formatted.append({
                'rank': i + 1,
                'id': doc_id,
                'type': metadata.get('type', 'unknown'),
                'paper_id': metadata.get('paper_id', 'unknown'),
                'similarity': 1 - distance,  # 코사인 유사도
                'content_preview': content,
                'metadata': metadata
            })

        return formatted

    def search_by_paper(self, paper_id: str):
        """특정 논문의 모든 청크 가져오기"""
        results = self.collection.get(
            where={"paper_id": paper_id}
        )
        print(f"\n📄 논문 {paper_id}: {len(results['ids'])}개 청크 발견")
        return results


def main():
    """사용 예시"""
    searcher = MultimodalSearcher()

    print("\n" + "="*60)
    print("🚀 멀티모달 RAG 검색 시스템")
    print("="*60)

    while True:
        print("\n옵션:")
        print("1. 텍스트로 검색")
        print("2. 텍스트로 이미지만 검색")
        print("3. 이미지로 검색")
        print("4. 특정 논문 보기")
        print("5. 종료")

        choice = input("\n선택 (1-5): ").strip()

        if choice == "1":
            query = input("검색어 입력: ").strip()
            results = searcher.search_text(query, top_k=5, search_type="both")

            print(f"\n📊 검색 결과 (상위 5개):")
            for r in results:
                print(f"\n{r['rank']}. [{r['type']}] {r['paper_id']}")
                print(f"   유사도: {r['similarity']:.3f}")
                print(f"   미리보기: {r['content_preview']}")

        elif choice == "2":
            query = input("검색어 입력 (이미지 찾기): ").strip()
            results = searcher.search_text(query, top_k=5, search_type="image")

            print(f"\n🖼️  이미지 검색 결과:")
            for r in results:
                print(f"\n{r['rank']}. {r['id']}")
                print(f"   논문: {r['paper_id']}")
                print(f"   유사도: {r['similarity']:.3f}")
                if 'image_path' in r['metadata']:
                    print(f"   경로: {r['metadata']['image_path']}")

        elif choice == "3":
            image_path = input("이미지 경로 입력: ").strip()
            if os.path.exists(image_path):
                results = searcher.search_image(image_path, top_k=5)

                print(f"\n🎯 유사한 콘텐츠:")
                for r in results:
                    print(f"\n{r['rank']}. [{r['type']}] {r['paper_id']}")
                    print(f"   유사도: {r['similarity']:.3f}")
            else:
                print("❌ 이미지 파일을 찾을 수 없습니다.")

        elif choice == "4":
            paper_id = input("논문 ID 입력: ").strip()
            results = searcher.search_by_paper(paper_id)
            if results['ids']:
                text_count = sum(1 for m in results['metadatas'] if m.get('type') == 'text')
                image_count = sum(1 for m in results['metadatas'] if m.get('type') == 'image')
                print(f"   - 텍스트 청크: {text_count}개")
                print(f"   - 이미지: {image_count}개")

        elif choice == "5":
            print("\n👋 종료합니다.")
            break


if __name__ == "__main__":
    main()