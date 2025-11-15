"""
Multimodal RAG Builder with CLIP
진정한 멀티모달 검색을 위한 개선된 구현
"""

import os
import json
from pathlib import Path
from typing import List, Dict, Tuple, Optional
import numpy as np
from PIL import Image
import chromadb
from dotenv import load_dotenv
import google.generativeai as genai
import base64

load_dotenv()

class MultimodalRAGBuilder:
    """멀티모달 RAG 시스템 (텍스트 + 이미지 통합 검색)"""

    def __init__(self, use_pinecone: bool = True):
        from sentence_transformers import SentenceTransformer

        # CLIP ViT-B-32 사용 (안정적이고 검증된 모델)
        # Jina CLIP은 custom_st 모듈 필요로 설치 복잡
        self.model = SentenceTransformer('clip-ViT-B-32')
        print("✅ CLIP ViT-B-32 멀티모달 모델 로드")
        print("   - 진짜 멀티모달: 이미지 픽셀을 직접 임베딩")
        print("   - 텍스트와 이미지가 같은 512차원 공간에 매핑")
        print("   - 크로스모달 검색 가능 (텍스트→이미지, 이미지→텍스트)")
        self.embedding_dim = 512

        # ChromaDB 초기화 - 새로운 DB 이름
        self.client = chromadb.PersistentClient(path="./real_multimodal_db")

        # 컬렉션 생성 (CLIP 512차원)
        try:
            self.collection = self.client.create_collection(
                name="vision_language_papers",
                metadata={"hnsw:space": "cosine"}
            )
        except:
            self.collection = self.client.get_collection("vision_language_papers")

        # Pinecone 초기화 (옵션)
        self.use_pinecone = use_pinecone
        self.pinecone_index = None
        if use_pinecone:
            self._init_pinecone()

    def _init_pinecone(self):
        """Pinecone 초기화 (최신 API)"""
        try:
            from pinecone import Pinecone, ServerlessSpec

            api_key = os.getenv('PINECONE_API_KEY')
            if not api_key:
                print("⚠️  PINECONE_API_KEY not found in .env")
                self.use_pinecone = False
                return

            # Pinecone 클라이언트 초기화 (2024-2025 최신)
            pc = Pinecone(api_key=api_key)

            index_name = "multimodal-papers-clip"

            # 인덱스 존재 확인 및 생성 (v5.0.1 compatible)
            existing_indexes = pc.list_indexes()
            index_exists = any(idx.name == index_name for idx in existing_indexes)

            if not index_exists:
                pc.create_index(
                    name=index_name,
                    dimension=self.embedding_dim,  # CLIP 512차원
                    metric='cosine',
                    spec=ServerlessSpec(
                        cloud='aws',
                        region='us-east-1'
                    )
                )
                print(f"✅ Pinecone 인덱스 '{index_name}' 생성됨")

                # 인덱스가 준비될 때까지 대기
                import time
                while not pc.describe_index(index_name).status['ready']:
                    time.sleep(1)
            else:
                print(f"✅ 기존 Pinecone 인덱스 '{index_name}' 사용")

            # 인덱스 연결
            self.pinecone_index = pc.Index(index_name)
            stats = self.pinecone_index.describe_index_stats()
            print(f"   - 인덱스 통계: {stats['total_vector_count']} vectors")

        except Exception as e:
            print(f"⚠️  Pinecone 초기화 실패: {e}")
            self.use_pinecone = False

    def process_paper(self, paper_id: str, pdf_path: str, image_dir: str):
        """논문 하나를 처리 (텍스트 + 이미지)"""

        try:
            from text_extractor import extract_text_and_images

            # 1. 텍스트와 이미지 추출
            text, images, captions, featured_image = extract_text_and_images(pdf_path, image_dir)
        except Exception as e:
            print(f"⚠️  {paper_id}: 추출 실패 - {e}")
            return 0
        
        chunks = []
        embeddings = []
        metadatas = []
        ids = []
        
        # 2. 텍스트 청크 처리
        text_chunks = self._chunk_text(text)
        for i, chunk in enumerate(text_chunks):
            chunk_id = f"{paper_id}_text_{i}"
            
            # CLIP 텍스트 임베딩 생성
            text_embedding = self.model.encode(chunk)
            
            chunks.append(chunk)
            embeddings.append(text_embedding)
            ids.append(chunk_id)
            metadatas.append({
                'type': 'text',
                'paper_id': paper_id,
                'pdf_path': pdf_path,
                'chunk_index': i
            })
        
        # 3. 이미지 처리 (실제 이미지 임베딩)
        for i, img_info in enumerate(images):
            img_path = os.path.join(image_dir, img_info['filename'])
            
            if os.path.exists(img_path):
                # 해당 이미지의 캡션 찾기
                caption = ""
                for cap in captions:
                    if cap.get('page') == img_info.get('page'):
                        caption = cap.get('text', '')
                        break
                
                # CLIP으로 실제 이미지 임베딩 생성
                image = Image.open(img_path)
                image_embedding = self.model.encode(image)
                
                # 캡션도 별도로 임베딩
                if caption:
                    caption_embedding = self.model.encode(caption)
                    # 이미지와 캡션 임베딩을 평균하여 통합
                    combined_embedding = (image_embedding + caption_embedding) / 2
                else:
                    combined_embedding = image_embedding
                
                # 저장
                img_id = f"{paper_id}_img_{i}"
                chunks.append(f"[IMAGE] {img_info['filename']} - {caption[:200]}")
                embeddings.append(combined_embedding)
                ids.append(img_id)
                metadatas.append({
                    'type': 'image',
                    'paper_id': paper_id,
                    'pdf_path': pdf_path,
                    'image_path': img_path,
                    'page': img_info.get('page', 0),
                    'caption': caption,
                    'filename': img_info['filename']
                })
        
        # 4. DB에 저장
        if chunks:
            # ChromaDB에 저장
            self.collection.add(
                embeddings=embeddings,
                documents=chunks,
                metadatas=metadatas,
                ids=ids
            )

            # Pinecone에도 저장
            if self.use_pinecone and self.pinecone_index:
                try:
                    # Pinecone 형식으로 변환
                    vectors = []
                    for i, (id_, emb, meta) in enumerate(zip(ids, embeddings, metadatas)):
                        # metadata에 document 텍스트 추가
                        meta_copy = meta.copy()
                        meta_copy['text'] = chunks[i][:1000]  # Pinecone 메타데이터 제한으로 1000자만

                        vectors.append({
                            'id': id_,
                            'values': emb.tolist() if isinstance(emb, np.ndarray) else emb,
                            'metadata': meta_copy
                        })

                    # 배치로 업서트 (100개씩)
                    for i in range(0, len(vectors), 100):
                        batch = vectors[i:i+100]
                        self.pinecone_index.upsert(vectors=batch)

                except Exception as e:
                    print(f"⚠️  Pinecone 저장 실패: {e}")

            print(f"✅ {paper_id}: {len(text_chunks)}개 텍스트, {len(images)}개 이미지 저장 (ChromaDB + Pinecone)")

        return len(chunks)
    
    def _chunk_text(self, text: str, chunk_size: int = 500) -> List[str]:
        """텍스트를 청크로 분할"""
        words = text.split()
        chunks = []
        for i in range(0, len(words), chunk_size):
            chunk = ' '.join(words[i:i+chunk_size])
            chunks.append(chunk)
        return chunks
    
    def search(self, query: str, search_type: str = "all", k: int = 10):
        """
        통합 검색
        search_type: 'all', 'text', 'image'
        """
        # CLIP 쿼리 임베딩 생성
        if query.endswith(('.png', '.jpg', '.jpeg')):
            # 이미지 파일로 직접 검색
            query_image = Image.open(query)
            query_embedding = self.model.encode(query_image)
        else:
            # 텍스트로 검색
            query_embedding = self.model.encode(query)
        
        # 검색 필터
        where = None
        if search_type == "text":
            where = {"type": "text"}
        elif search_type == "image":
            where = {"type": "image"}
        
        # 검색 실행
        results = self.collection.query(
            query_embeddings=[query_embedding.tolist()],
            n_results=k,
            where=where
        )
        
        # 결과 포맷팅
        formatted_results = []
        for i in range(len(results['ids'][0])):
            result = {
                'id': results['ids'][0][i],
                'content': results['documents'][0][i],
                'metadata': results['metadatas'][0][i],
                'distance': results['distances'][0][i],
                'similarity': 1 - results['distances'][0][i]
            }
            
            # 이미지 결과인 경우 추가 정보
            if result['metadata']['type'] == 'image':
                result['image_path'] = result['metadata'].get('image_path', '')
                result['caption'] = result['metadata'].get('caption', '')
                result['page'] = result['metadata'].get('page', 0)
            
            formatted_results.append(result)
        
        return formatted_results
    
    def search_similar_images(self, image_path: str, k: int = 10):
        """유사한 이미지 검색"""
        # 실제 이미지를 로드하여 임베딩
        image = Image.open(image_path)
        image_embedding = self.model.encode(image)
        
        results = self.collection.query(
            query_embeddings=[image_embedding.tolist()],
            n_results=k,
            where={"type": "image"}
        )
        
        return self._format_results(results)
    
    def _format_results(self, results):
        """결과 포맷팅"""
        formatted = []
        for i in range(len(results['ids'][0])):
            formatted.append({
                'id': results['ids'][0][i],
                'content': results['documents'][0][i],
                'metadata': results['metadatas'][0][i],
                'similarity': 1 - results['distances'][0][i]
            })
        return formatted


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='Multimodal RAG Builder')
    parser.add_argument('--batch', type=str, help='Batch JSON file')
    parser.add_argument('--search', type=str, help='Search query')
    parser.add_argument('--search-image', type=str, help='Search with image file')
    parser.add_argument('--type', type=str, default='all',
                       choices=['all', 'text', 'image'],
                       help='Search type')
    parser.add_argument('--use-pinecone', action='store_true',
                       help='Also save to Pinecone (requires PINECONE_API_KEY)')

    args = parser.parse_args()

    rag = MultimodalRAGBuilder(use_pinecone=args.use_pinecone)
    
    if args.batch:
        # 배치 처리
        with open(args.batch, 'r') as f:
            papers = json.load(f)
        
        total_papers = len(papers)
        print(f"\n📚 총 {total_papers}개 논문 처리 시작...")

        for i, paper in enumerate(papers, 1):
            paper_id = paper.get('paper_id')
            pdf_path = paper.get('pdf_path')
            image_dir = f"./extracted_images/{paper_id}"

            if os.path.exists(pdf_path):
                print(f"\n[{i}/{total_papers}] Processing {paper_id}...")
                try:
                    rag.process_paper(paper_id, pdf_path, image_dir)
                except Exception as e:
                    print(f"⚠️  {paper_id}: 처리 실패 - {e}")
                    continue
            else:
                print(f"[{i}/{total_papers}] PDF not found: {pdf_path}")
    
    elif args.search:
        # 텍스트 검색
        results = rag.search(args.search, search_type=args.type)
        
        print(f"\n🔍 검색 결과: '{args.search}'")
        print("=" * 60)
        
        for i, result in enumerate(results[:5], 1):
            print(f"\n{i}. [{result['metadata']['type'].upper()}]")
            print(f"   논문: {result['metadata']['paper_id']}")
            print(f"   유사도: {result['similarity']:.3f}")
            
            if result['metadata']['type'] == 'image':
                print(f"   이미지: {result['metadata']['filename']}")
                print(f"   페이지: {result['metadata']['page']}")
                print(f"   캡션: {result['metadata'].get('caption', 'N/A')[:100]}...")
            else:
                print(f"   내용: {result['content'][:200]}...")
    
    elif args.search_image:
        # 이미지로 검색
        results = rag.search_similar_images(args.search_image)
        
        print(f"\n🖼️ 유사 이미지 검색: {args.search_image}")
        print("=" * 60)
        
        for i, result in enumerate(results[:5], 1):
            print(f"\n{i}. 논문: {result['metadata']['paper_id']}")
            print(f"   이미지: {result['metadata']['filename']}")
            print(f"   페이지: {result['metadata']['page']}")
            print(f"   유사도: {result['similarity']:.3f}")
            print(f"   캡션: {result['metadata'].get('caption', 'N/A')[:100]}...")