# 📚 논문 RAG 시스템 가이드

PDF 파싱 데이터를 활용한 벡터 DB 기반 논문 검색 및 질의응답 시스템

## 🚀 Quick Start

### 1. RAG 의존성 설치
```bash
pip install -r requirements_rag.txt
```

### 2. 벡터 DB 구축
```bash
# Zotero 전체 논문을 벡터 DB로 변환
python scripts/rag_query.py --build

# 특정 컬렉션만 처리
python scripts/rag_query.py --build --collection "Machine Learning"

# 처리 개수 제한
python scripts/rag_query.py --build --limit 50
```

### 3. 질의응답 시작
```bash
# 대화형 모드
python scripts/rag_query.py --interactive

# 단일 질의
python scripts/rag_query.py --query "LNP의 최신 연구 동향은?"
```

## 🏗️ 시스템 구조

### 1. 텍스트 처리 파이프라인
```
PDF → 텍스트 추출 → 청킹 → 임베딩 → 벡터 DB
```

### 2. 청킹 전략
- **섹션 기반 청킹**: Abstract, Introduction, Methods 등 논문 구조 활용
- **단락 기반 청킹**: 자연스러운 의미 단위 보존
- **오버랩 청킹**: 문맥 연속성 유지 (200자 중첩)

### 3. 임베딩 모델
- **Sentence Transformers** (기본): 다국어 지원, 빠른 속도
- **OpenAI Embeddings**: 높은 정확도, API 비용 발생

### 4. 벡터 데이터베이스
- **ChromaDB** (기본): 로컬 저장, 무료
- **Pinecone**: 클라우드 기반, 확장성

## 💻 사용 예시

### 단일 PDF 처리
```python
from vector_db_builder import PaperRAGBuilder

# RAG 시스템 초기화
rag = PaperRAGBuilder()

# PDF 처리
metadata = {
    'title': 'Deep Learning Paper',
    'authors': ['Author1', 'Author2'],
    'year': '2024'
}
rag.process_pdf('/path/to/paper.pdf', metadata)
```

### 질의응답
```python
from rag_query import RAGQueryEngine

# 엔진 초기화
engine = RAGQueryEngine()

# 질의
result = engine.query("What are the main findings about LNP delivery?")
print(result['answer'])

# 출처 확인
for source in result['sources']:
    print(f"- {source['title']} ({source['year']})")
```

### 배치 처리
```python
from rag_query import BatchRAGProcessor

processor = BatchRAGProcessor()
processor.process_from_zotero(collection="RNA Therapeutics", limit=100)
```

## 🔍 검색 기능

### 유사도 검색
```bash
# 벡터 DB에서 직접 검색
python scripts/vector_db_builder.py --search "CRISPR gene editing"
```

### 멀티턴 대화
```bash
python scripts/rag_query.py --interactive

# 예시 대화:
❓ LNP의 구조는 어떻게 되나요?
💡 [답변 생성...]

❓ 그렇다면 PEG의 역할은?
💡 [이전 문맥을 고려한 답변...]
```

## 📊 성능 최적화

### 청킹 크기 조정
```python
# 작은 청크 (정확도 높음, 속도 느림)
chunks = chunker.chunk_by_sections(text, chunk_size=300, overlap=100)

# 큰 청크 (속도 빠름, 문맥 풍부)
chunks = chunker.chunk_by_sections(text, chunk_size=1000, overlap=200)
```

### 임베딩 캐싱
```python
# 이미 처리된 논문은 자동으로 스킵
# processed_papers.json에 기록
```

### 검색 개수 조정
```python
# 더 많은 컨텍스트 검색 (정확도 상승, 비용 증가)
result = engine.query(question, k=10)
```

## 🛠️ 고급 설정

### 환경 변수
```bash
# .env 파일
CHROMA_PERSIST_DIR=./vector_db
EMBEDDING_MODEL=sentence-transformers
OPENAI_API_KEY=sk-...  # GPT 답변 생성용
```

### 커스텀 청킹
```python
class CustomChunker(TextChunker):
    def chunk_by_custom_logic(self, text: str) -> List[Dict]:
        # 커스텀 청킹 로직 구현
        pass
```

### 메타데이터 필터링
```python
# 특정 연도 이후 논문만 검색
results = db_manager.search(
    query="gene therapy",
    filter={"year": {"$gte": "2020"}}
)
```

## 📈 모니터링

### 벡터 DB 상태 확인
```python
# 저장된 논문 수
processed_papers = len(rag.processed_papers)
print(f"Total papers in DB: {processed_papers}")

# DB 크기
import os
db_size = sum(
    os.path.getsize(f) 
    for f in Path("./vector_db").rglob("*")
)
print(f"DB size: {db_size / 1024 / 1024:.2f} MB")
```

### 검색 품질 평가
```python
# 검색 결과의 관련도 점수 확인
results = engine.query("immunotherapy")
for r in results['sources']:
    print(f"Relevance: {r['relevance_score']:.2%}")
```

## 🔧 트러블슈팅

### 메모리 부족
```bash
# 배치 크기 줄이기
python scripts/rag_query.py --build --limit 10
```

### 임베딩 속도 개선
```python
# GPU 사용 (CUDA 필요)
embedder = EmbeddingGenerator("sentence-transformers")
embedder.model = embedder.model.to('cuda')
```

### ChromaDB 초기화 오류
```bash
# DB 리셋
rm -rf ./vector_db
python scripts/rag_query.py --build
```

## 📚 활용 사례

### 1. 논문 리뷰 자동화
```python
# 특정 주제의 최신 연구 동향 파악
result = engine.query(
    "What are the recent advances in mRNA delivery systems?"
)
```

### 2. 연구 가설 검증
```python
# 기존 연구에서 근거 찾기
result = engine.query(
    "Is there evidence for PEGylation reducing immunogenicity?"
)
```

### 3. 메타 분석
```python
# 여러 논문의 결과 종합
result = engine.query(
    "Compare the efficacy of different LNP formulations"
)
```

## 🎯 로드맵

- [ ] 그래프 RAG 구현 (논문 간 관계 분석)
- [ ] 하이브리드 검색 (키워드 + 벡터)
- [ ] 실시간 논문 업데이트
- [ ] 웹 인터페이스 구축
- [ ] 멀티모달 RAG (그림/표 포함)