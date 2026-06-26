# 🌲 Pinecone RAG 시스템 설정 가이드

클라우드 기반 벡터 데이터베이스 Pinecone을 사용한 논문 RAG 시스템 구축

## 🚀 Quick Start

### 1. Pinecone 계정 설정

1. [Pinecone 가입](https://www.pinecone.io/) (무료 Starter 플랜 제공)
2. API Key 발급:
   - Dashboard → API Keys → Create API Key
3. 환경 확인:
   - Dashboard에서 Environment 확인 (예: `gcp-starter`)

### 2. 환경 변수 설정

```bash
# .env 파일에 추가
PINECONE_API_KEY=your-api-key-here
PINECONE_ENVIRONMENT=gcp-starter
PINECONE_INDEX_NAME=literature-rag
```

### 3. 의존성 설치

```bash
# Pinecone 클라이언트 설치
pip install pinecone-client

# 또는 전체 RAG 의존성
pip install -r requirements_rag.txt
```

### 4. 인덱스 생성 및 논문 업로드

```bash
# Pinecone 인덱스 생성 및 논문 벡터화
python scripts/rag_query.py --build --db pinecone

# 특정 컬렉션만 처리
python scripts/rag_query.py --build --db pinecone --collection "LNP"
```

## 📊 Pinecone vs ChromaDB 비교

| 특징 | Pinecone | ChromaDB |
|------|----------|----------|
| **호스팅** | 클라우드 (관리형) | 로컬/자체 호스팅 |
| **확장성** | 무제한 (자동 스케일링) | 서버 용량 제한 |
| **속도** | 매우 빠름 (최적화된 인프라) | 로컬 속도 |
| **비용** | 무료 시작, 유료 플랜 | 완전 무료 |
| **설정** | API Key만 필요 | 설치 필요 |
| **백업** | 자동 | 수동 |
| **협업** | 팀 공유 가능 | 로컬 전용 |

## 🔧 Pinecone 고급 설정

### 인덱스 설정 최적화

```python
from pinecone import Pinecone, ServerlessSpec

pc = Pinecone(api_key="your-api-key")

# 고성능 인덱스 생성
pc.create_index(
    name="literature-rag",
    dimension=384,  # sentence-transformers 차원
    metric="cosine",  # 코사인 유사도
    spec=ServerlessSpec(
        cloud="gcp",
        region="us-central1"  # 가장 가까운 region 선택
    )
)
```

### 메타데이터 필터링

```python
# 특정 연도 이후 논문만 검색
results = index.query(
    vector=query_embedding,
    top_k=5,
    filter={
        "year": {"$gte": "2020"}
    },
    include_metadata=True
)

# 특정 저자 논문 검색
results = index.query(
    vector=query_embedding,
    top_k=5,
    filter={
        "authors": {"$in": ["Kim", "Lee"]}
    }
)
```

### 네임스페이스 활용

```python
# 컬렉션별로 네임스페이스 분리
index.upsert(
    vectors=vectors,
    namespace="LNP_papers"  # 컬렉션별 분리
)

# 특정 네임스페이스에서 검색
results = index.query(
    vector=query_embedding,
    namespace="LNP_papers",
    top_k=5
)
```

## 💻 사용 예시

### 1. 논문 벡터화 및 업로드

```python
from vector_db_builder import PaperRAGBuilder

# Pinecone RAG 시스템 초기화
rag = PaperRAGBuilder(db_type="pinecone")

# PDF 처리 및 업로드
metadata = {
    'title': 'mRNA Delivery Systems',
    'authors': ['Author1', 'Author2'],
    'year': '2024',
    'doi': '10.1234/example'
}
rag.process_pdf('/path/to/paper.pdf', metadata)
```

### 2. 질의응답

```python
from rag_query import RAGQueryEngine

# Pinecone 기반 엔진 초기화
engine = RAGQueryEngine(db_type="pinecone")

# 질의
result = engine.query("LNP의 PEG 대체 물질은?")
print(result['answer'])
```

### 3. 대량 처리 스크립트

```bash
#!/bin/bash
# batch_upload.sh

# Zotero 전체 논문을 Pinecone에 업로드
python scripts/rag_query.py --build --db pinecone --workers 5

# 진행 상황 모니터링
watch -n 5 'python scripts/pinecone_stats.py'
```

## 📈 모니터링 및 관리

### 인덱스 통계 확인

```python
from pinecone import Pinecone

pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
index = pc.Index("literature-rag")

# 인덱스 통계
stats = index.describe_index_stats()
print(f"Total vectors: {stats['total_vector_count']}")
print(f"Index fullness: {stats['index_fullness']}")
print(f"Namespaces: {stats['namespaces']}")
```

### 벡터 삭제

```python
# 특정 논문 삭제
index.delete(ids=["paper123_0", "paper123_1"])

# 조건부 삭제
index.delete(filter={"year": {"$lt": "2020"}})

# 전체 삭제 (주의!)
index.delete(delete_all=True)
```

## 🚨 주의사항 및 제한

### Pinecone Starter (무료) 플랜 제한
- **벡터 수**: 100,000개까지
- **인덱스**: 1개
- **환경**: gcp-starter만 사용 가능
- **API 호출**: 분당 제한 있음

### 메타데이터 제한
- **크기**: 메타데이터당 최대 40KB
- **필드 수**: 제한 없음
- **타입**: string, number, boolean, list

### 최적화 팁
1. **배치 업로드**: 100개씩 묶어서 업로드
2. **메타데이터 최소화**: 필수 정보만 저장
3. **텍스트 압축**: 긴 텍스트는 요약 저장

## 🔄 마이그레이션

### ChromaDB → Pinecone

```python
# migration_script.py
from vector_db_builder import PaperRAGBuilder

# ChromaDB에서 데이터 추출
chroma_rag = PaperRAGBuilder(db_type="chroma")
# ... 데이터 추출 로직

# Pinecone으로 업로드
pinecone_rag = PaperRAGBuilder(db_type="pinecone")
# ... 업로드 로직
```

## 📊 성능 벤치마크

| 작업 | ChromaDB | Pinecone |
|------|----------|----------|
| 1000개 벡터 업로드 | ~30초 | ~10초 |
| 10만개 중 검색 | ~200ms | ~50ms |
| 메타데이터 필터링 | ~500ms | ~100ms |

## 🛠️ 트러블슈팅

### "Index not found" 오류
```python
# 인덱스 목록 확인
pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
print(pc.list_indexes())

# 인덱스 재생성
pc.create_index(...)
```

### API Rate Limit 오류
```python
import time

# Retry 로직 추가
for i in range(3):
    try:
        index.upsert(vectors)
        break
    except Exception as e:
        if "rate limit" in str(e).lower():
            time.sleep(2 ** i)  # Exponential backoff
```

### 메타데이터 크기 초과
```python
# 텍스트 트렁케이션
metadata['text'] = metadata['text'][:2000]  # 2000자로 제한
```

## 📚 추가 리소스

- [Pinecone 공식 문서](https://docs.pinecone.io/)
- [Pinecone Python SDK](https://github.com/pinecone-io/pinecone-python-client)
- [벡터 DB 비교 가이드](https://www.pinecone.io/learn/vector-database/)

## 🎯 다음 단계

1. **하이브리드 검색**: 키워드 + 벡터 검색 결합
2. **실시간 업데이트**: 새 논문 자동 인덱싱
3. **다중 인덱스**: 주제별 인덱스 분리
4. **캐싱 레이어**: Redis로 자주 검색되는 결과 캐싱