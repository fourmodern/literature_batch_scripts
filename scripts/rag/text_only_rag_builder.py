"""
Vector Database Builder for RAG System
논문 PDF를 벡터 DB로 변환하여 RAG 검색 시스템 구축
"""

import os
import sys
import json
import hashlib
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from datetime import datetime
import numpy as np

# .env 파일 로드
from dotenv import load_dotenv
load_dotenv()

# Vector DB options
try:
    import chromadb
    from chromadb.config import Settings
    CHROMA_AVAILABLE = True
except ImportError:
    CHROMA_AVAILABLE = False

try:
    from pinecone import Pinecone, ServerlessSpec
    PINECONE_AVAILABLE = True
except ImportError:
    PINECONE_AVAILABLE = False

# Embedding models
try:
    from sentence_transformers import SentenceTransformer
    SENTENCE_TRANSFORMERS_AVAILABLE = True
except ImportError:
    SENTENCE_TRANSFORMERS_AVAILABLE = False

try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False

from text_extractor import extract_text_from_pdf, extract_text_and_images


class TextChunker:
    """논문 텍스트를 의미 있는 청크로 분할"""
    
    @staticmethod
    def chunk_by_sections(text: str, chunk_size: int = 1000, 
                          overlap: int = 200) -> List[Dict]:
        """
        섹션별로 텍스트를 청크로 분할
        학술 논문의 구조를 고려한 스마트 청킹
        """
        chunks = []
        
        # 섹션 마커 정의
        section_markers = [
            'abstract', 'introduction', 'background', 'related work',
            'methodology', 'methods', 'materials and methods',
            'results', 'experiments', 'evaluation',
            'discussion', 'conclusion', 'future work',
            'references', 'appendix'
        ]
        
        lines = text.split('\n')
        current_section = 'unknown'
        section_text = []
        
        for line in lines:
            lower_line = line.lower().strip()
            
            # 새 섹션 감지
            section_found = False
            for marker in section_markers:
                if marker in lower_line and len(lower_line) < 50:
                    # 이전 섹션 처리
                    if section_text:
                        section_content = '\n'.join(section_text)
                        chunks.extend(
                            TextChunker._split_section(
                                section_content, 
                                current_section, 
                                chunk_size, 
                                overlap
                            )
                        )
                    
                    # 새 섹션 시작
                    current_section = marker
                    section_text = [line]
                    section_found = True
                    break
            
            if not section_found:
                section_text.append(line)
        
        # 마지막 섹션 처리
        if section_text:
            section_content = '\n'.join(section_text)
            chunks.extend(
                TextChunker._split_section(
                    section_content, 
                    current_section, 
                    chunk_size, 
                    overlap
                )
            )
        
        return chunks
    
    @staticmethod
    def _split_section(text: str, section_name: str, 
                       chunk_size: int, overlap: int) -> List[Dict]:
        """섹션을 청크로 분할"""
        chunks = []
        words = text.split()
        
        if len(words) == 0:
            return chunks
        
        for i in range(0, len(words), chunk_size - overlap):
            chunk_words = words[i:i + chunk_size]
            chunk_text = ' '.join(chunk_words)
            
            chunks.append({
                'text': chunk_text,
                'section': section_name,
                'word_count': len(chunk_words),
                'char_count': len(chunk_text),
                'chunk_index': len(chunks)
            })
        
        return chunks
    
    @staticmethod
    def chunk_by_paragraphs(text: str, min_size: int = 100, 
                           max_size: int = 500) -> List[Dict]:
        """
        단락 단위로 청킹 (자연스러운 의미 단위 보존)
        """
        chunks = []
        paragraphs = text.split('\n\n')
        
        current_chunk = []
        current_size = 0
        
        for para in paragraphs:
            para_size = len(para.split())
            
            if current_size + para_size > max_size and current_chunk:
                # 현재 청크 저장
                chunks.append({
                    'text': '\n\n'.join(current_chunk),
                    'word_count': current_size,
                    'chunk_index': len(chunks)
                })
                current_chunk = [para]
                current_size = para_size
            else:
                current_chunk.append(para)
                current_size += para_size
        
        # 마지막 청크 저장
        if current_chunk:
            chunks.append({
                'text': '\n\n'.join(current_chunk),
                'word_count': current_size,
                'chunk_index': len(chunks)
            })
        
        return chunks


class EmbeddingGenerator:
    """텍스트/이미지 임베딩 생성"""
    
    def __init__(self, model_type: str = "sentence-transformers"):
        self.model_type = model_type
        
        if model_type == "sentence-transformers" and SENTENCE_TRANSFORMERS_AVAILABLE:
            # 한국어/영어 다국어 모델
            self.model = SentenceTransformer('sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2')
        elif model_type == "clip" and SENTENCE_TRANSFORMERS_AVAILABLE:
            # CLIP 멀티모달 모델 (텍스트 + 이미지)
            self.model = SentenceTransformer('clip-ViT-B-32-multilingual-v1')
            print("✅ Using CLIP multimodal model for text+image embeddings")
        elif model_type == "openai" and OPENAI_AVAILABLE:
            self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        else:
            raise ValueError(f"Embedding model {model_type} not available")
    
    def generate_embeddings(self, texts: List[str]) -> np.ndarray:
        """텍스트 리스트를 임베딩으로 변환"""
        if self.model_type in ["sentence-transformers", "clip"]:
            return self.model.encode(texts, show_progress_bar=True)
        
        elif self.model_type == "openai":
            embeddings = []
            for text in texts:
                response = self.client.embeddings.create(
                    model="text-embedding-3-small",
                    input=text[:8000]  # OpenAI 임베딩 길이 제한
                )
                embeddings.append(response.data[0].embedding)
            return np.array(embeddings)
    
    def generate_image_embeddings(self, image_paths: List[str]) -> np.ndarray:
        """이미지 파일을 임베딩으로 변환 (CLIP 모델용)"""
        if self.model_type == "clip":
            from PIL import Image
            images = []
            for path in image_paths:
                try:
                    img = Image.open(path)
                    images.append(img)
                except:
                    # 이미지 로드 실패시 빈 이미지 사용
                    images.append(Image.new('RGB', (224, 224), color='white'))
            return self.model.encode(images, show_progress_bar=True)
        else:
            raise ValueError(f"Image embedding not supported for {self.model_type}")


class VectorDBManager:
    """벡터 데이터베이스 관리"""
    
    def __init__(self, db_type: str = "chroma", persist_dir: str = "./vector_db"):
        self.db_type = db_type
        self.persist_dir = Path(persist_dir)
        self.persist_dir.mkdir(exist_ok=True)
        
        if db_type == "chroma" and CHROMA_AVAILABLE:
            self.client = chromadb.PersistentClient(
                path=str(self.persist_dir),
                settings=Settings(anonymized_telemetry=False)
            )
            self.collection = None
        elif db_type == "pinecone" and PINECONE_AVAILABLE:
            # Pinecone 초기화 (새로운 SDK 방식)
            self.pc = Pinecone(
                api_key=os.getenv("PINECONE_API_KEY")
            )
            self.index_name = os.getenv("PINECONE_INDEX_NAME", "literature-rag")
            self.index = None
        else:
            raise ValueError(f"Vector DB {db_type} not available")
    
    def create_collection(self, name: str = "papers"):
        """컬렉션/인덱스 생성"""
        if self.db_type == "chroma":
            # 기존 컬렉션 삭제 후 재생성
            try:
                self.client.delete_collection(name)
            except:
                pass
            
            self.collection = self.client.create_collection(
                name=name,
                metadata={"hnsw:space": "cosine"}
            )
            
        elif self.db_type == "pinecone":
            # Pinecone 인덱스 생성 또는 연결
            existing_indexes = [idx.name for idx in self.pc.list_indexes()]
            
            if self.index_name not in existing_indexes:
                print(f"Creating new Pinecone index: {self.index_name}")
                self.pc.create_index(
                    name=self.index_name,
                    dimension=384,  # sentence-transformers 차원
                    metric="cosine",
                    spec=ServerlessSpec(
                        cloud="aws",
                        region="us-east-1"  # 무료 플랜 지원 리전
                    )
                )
                # 인덱스 생성 대기
                import time
                time.sleep(10)
            
            self.index = self.pc.Index(self.index_name)
            print(f"✅ Connected to Pinecone index: {self.index_name}")
            
            # 인덱스 통계 출력
            stats = self.index.describe_index_stats()
            print(f"   Vectors in index: {stats.get('total_vector_count', 0)}")
    
    def add_documents(self, chunks: List[Dict], embeddings: np.ndarray, 
                     metadata: Dict):
        """문서 청크와 임베딩을 DB에 추가"""
        if self.db_type == "chroma":
            if not self.collection:
                self.create_collection()
            
            # ChromaDB에 추가
            ids = [f"{metadata['paper_id']}_{i}" for i in range(len(chunks))]
            
            metadatas = []
            for i, chunk in enumerate(chunks):
                # metadata의 dict 값들을 플랫하게 변환
                flat_metadata = {}
                for key, value in metadata.items():
                    if isinstance(value, dict):
                        # dict인 경우 문자열로 변환하거나 개별 필드로 분리
                        if key == 'metadata':
                            flat_metadata['filename'] = value.get('filename', 'unknown')
                            flat_metadata['storage_key'] = value.get('storage_key', 'unknown')
                        else:
                            flat_metadata[key] = str(value)
                    elif value is None:
                        flat_metadata[key] = ''
                    else:
                        flat_metadata[key] = value
                
                chunk_metadata = {
                    **flat_metadata,
                    'chunk_index': i,
                    'section': chunk.get('section', 'unknown'),
                    'word_count': chunk.get('word_count', 0)
                }
                metadatas.append(chunk_metadata)
            
            self.collection.add(
                embeddings=embeddings.tolist(),
                documents=[chunk['text'] for chunk in chunks],
                metadatas=metadatas,
                ids=ids
            )
            
        elif self.db_type == "pinecone":
            if not self.index:
                self.create_collection()
            
            # Pinecone에 추가 (새로운 형식)
            vectors = []
            for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
                vector_id = f"{metadata['paper_id']}_{i}"
                
                # 메타데이터 크기 제한 (40KB)
                chunk_text = chunk['text'][:2000]  # 텍스트 길이 제한
                vector_metadata = {
                    'paper_id': metadata.get('paper_id', ''),
                    'title': metadata.get('title', '')[:200],
                    'authors': str(metadata.get('authors', []))[:500],
                    'year': str(metadata.get('year', '')),
                    'text': chunk_text,
                    'section': chunk.get('section', 'unknown'),
                    'chunk_index': i,
                    'word_count': chunk.get('word_count', 0)
                }
                
                vectors.append({
                    "id": vector_id,
                    "values": embedding.tolist(),
                    "metadata": vector_metadata
                })
            
            # 배치로 업로드 (100개씩)
            batch_size = 100
            for i in range(0, len(vectors), batch_size):
                batch = vectors[i:i+batch_size]
                self.index.upsert(vectors=batch)
            
            print(f"   Uploaded {len(vectors)} vectors to Pinecone")
    
    def search(self, query: str, embedder: EmbeddingGenerator, 
              k: int = 5) -> List[Dict]:
        """쿼리로 유사한 청크 검색"""
        # 쿼리 임베딩 생성
        query_embedding = embedder.generate_embeddings([query])[0]
        
        if self.db_type == "chroma":
            if not self.collection:
                raise ValueError("Collection not initialized")
            
            results = self.collection.query(
                query_embeddings=[query_embedding.tolist()],
                n_results=k
            )
            
            # 결과 포맷팅
            formatted_results = []
            for i in range(len(results['ids'][0])):
                formatted_results.append({
                    'id': results['ids'][0][i],
                    'text': results['documents'][0][i],
                    'metadata': results['metadatas'][0][i],
                    'distance': results['distances'][0][i] if 'distances' in results else None
                })
            
            return formatted_results
            
        elif self.db_type == "pinecone":
            if not self.index:
                self.create_collection()
            
            # Pinecone 쿼리 (새로운 형식)
            results = self.index.query(
                vector=query_embedding.tolist(),
                top_k=k,
                include_metadata=True
            )
            
            formatted_results = []
            for match in results['matches']:
                formatted_results.append({
                    'id': match['id'],
                    'text': match['metadata'].get('text', ''),
                    'metadata': match['metadata'],
                    'distance': 1 - match['score']  # cosine similarity to distance
                })
            
            return formatted_results


class PaperRAGBuilder:
    """논문 RAG 시스템 구축 통합 클래스"""
    
    def __init__(self, db_type: str = "chroma", 
                 embedding_model: str = "sentence-transformers"):
        self.db_manager = VectorDBManager(db_type)
        self.embedder = EmbeddingGenerator(embedding_model)
        self.chunker = TextChunker()
        self.processed_papers = self._load_processed_papers()
    
    def _load_processed_papers(self) -> set:
        """이미 처리된 논문 목록 로드"""
        processed_file = Path("./vector_db/processed_papers.json")
        if processed_file.exists():
            with open(processed_file, 'r') as f:
                return set(json.load(f))
        return set()
    
    def _save_processed_papers(self):
        """처리된 논문 목록 저장"""
        processed_file = Path("./vector_db/processed_papers.json")
        processed_file.parent.mkdir(exist_ok=True)
        with open(processed_file, 'w') as f:
            json.dump(list(self.processed_papers), f)
    
    def process_pdf(self, pdf_path: str, metadata: Dict) -> bool:
        """PDF를 처리하여 벡터 DB에 추가"""
        # 중복 처리 방지
        paper_id = metadata.get('key', hashlib.md5(pdf_path.encode()).hexdigest())
        if paper_id in self.processed_papers:
            print(f"✓ Already processed: {paper_id}")
            return False
        
        try:
            # 1. 텍스트와 이미지 추출
            print(f"📄 Extracting text and images from {pdf_path}")
            
            # 이미지 저장 디렉토리
            image_dir = f"./extracted_images/{paper_id}"
            os.makedirs(image_dir, exist_ok=True)
            
            # extract_text_and_images 함수 사용
            text, images, captions, featured_image = extract_text_and_images(pdf_path, image_dir)
            
            if len(text) < 100:
                print(f"⚠️ Text too short, skipping")
                return False
            
            print(f"  📝 Text: {len(text)} chars")
            print(f"  🖼️ Images: {len(images)} found")
            print(f"  📌 Captions: {len(captions)} found")
            
            # 2. 텍스트 청킹
            print(f"✂️ Chunking content...")
            text_chunks = self.chunker.chunk_by_sections(text, chunk_size=500, overlap=50)
            
            # 이미지와 캡션을 추가 청크로 생성
            all_chunks = text_chunks.copy()
            
            # 이미지 정보를 청크로 추가 (논문 정보 포함)
            for idx, img in enumerate(images):
                img_text = f"[IMAGE {idx+1}] "
                img_text += f"Paper ID: {paper_id}, "
                img_text += f"PDF: {os.path.basename(pdf_path)}, "
                img_text += f"Page {img.get('page', '?')}, "
                img_text += f"File: {img.get('filename', 'unknown')}"
                
                # 관련 캡션 찾기
                for cap in captions:
                    if cap.get('page') == img.get('page'):
                        img_text += f"\nCaption: {cap.get('text', '')}"
                        break
                
                all_chunks.append({
                    'text': img_text,
                    'section': 'image',
                    'metadata': {'type': 'image', 'index': idx}
                })
            
            # 캡션을 별도 청크로 추가
            for idx, cap in enumerate(captions):
                cap_text = f"[{cap.get('type', 'FIGURE').upper()} CAPTION] "
                cap_text += f"Page {cap.get('page', '?')}: "
                cap_text += cap.get('text', '')
                
                all_chunks.append({
                    'text': cap_text,
                    'section': 'caption',
                    'metadata': {'type': 'caption', 'index': idx}
                })
            
            chunks = all_chunks
            print(f"  Created {len(chunks)} total chunks (text + images + captions)")
            
            # 3. 임베딩 생성
            print(f"🧮 Generating embeddings...")
            texts = [chunk['text'] for chunk in chunks]
            embeddings = self.embedder.generate_embeddings(texts)
            
            # 4. DB에 저장
            print(f"💾 Saving to vector DB...")
            enhanced_metadata = {
                **metadata,
                'paper_id': paper_id,
                'pdf_path': pdf_path,
                'processed_at': datetime.now().isoformat(),
                'total_chunks': len(chunks)
            }
            
            self.db_manager.add_documents(chunks, embeddings, enhanced_metadata)
            
            # 5. 처리 완료 표시
            self.processed_papers.add(paper_id)
            self._save_processed_papers()
            
            print(f"✅ Successfully processed: {paper_id}")
            return True
            
        except Exception as e:
            print(f"❌ Error processing {pdf_path}: {e}")
            return False
    
    def batch_process_papers(self, papers: List[Dict]) -> Dict:
        """여러 논문 일괄 처리"""
        results = {
            'success': 0,
            'failed': 0,
            'skipped': 0
        }
        
        for paper in papers:
            pdf_path = paper.get('pdf_path')
            if not pdf_path or not os.path.exists(pdf_path):
                results['skipped'] += 1
                continue
            
            if self.process_pdf(pdf_path, paper):
                results['success'] += 1
            else:
                results['failed'] += 1
        
        return results
    
    def search_papers(self, query: str, k: int = 5) -> List[Dict]:
        """논문 검색"""
        return self.db_manager.search(query, self.embedder, k)


# CLI 인터페이스
if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Build vector DB for papers')
    parser.add_argument('--pdf', type=str, help='Single PDF to process')
    parser.add_argument('--batch', type=str, help='JSON file with paper list')
    parser.add_argument('--search', type=str, help='Search query')
    parser.add_argument('--db', type=str, default='chroma', 
                       choices=['chroma', 'pinecone'])
    parser.add_argument('--embedding', type=str, default='sentence-transformers',
                       choices=['sentence-transformers', 'openai'])
    
    args = parser.parse_args()
    
    # RAG 시스템 초기화
    rag_builder = PaperRAGBuilder(db_type=args.db, embedding_model=args.embedding)
    
    if args.pdf:
        # 단일 PDF 처리
        metadata = {
            'title': Path(args.pdf).stem,
            'source': 'manual'
        }
        rag_builder.process_pdf(args.pdf, metadata)
        
    elif args.batch:
        # 배치 처리
        with open(args.batch, 'r') as f:
            papers = json.load(f)
        results = rag_builder.batch_process_papers(papers)
        print(f"\n📊 Batch processing results:")
        print(f"  ✅ Success: {results['success']}")
        print(f"  ❌ Failed: {results['failed']}")
        print(f"  ⏭️ Skipped: {results['skipped']}")
        
    elif args.search:
        # 검색
        rag_builder.db_manager.create_collection()  # 기존 컬렉션 로드
        results = rag_builder.search_papers(args.search)
        
        print(f"\n🔍 Search results for: '{args.search}'")
        print("=" * 60)
        for i, result in enumerate(results, 1):
            print(f"\n{i}. {result['metadata'].get('title', 'Unknown')}")
            print(f"   Section: {result['metadata'].get('section', 'unknown')}")
            print(f"   Text: {result['text'][:200]}...")
            if 'distance' in result:
                print(f"   Similarity: {1 - result['distance']:.3f}")