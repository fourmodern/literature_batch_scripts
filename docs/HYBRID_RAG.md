# 🔀 Hybrid RAG System (ChromaDB + Pinecone)

로컬 개발과 클라우드 배포를 위한 듀얼 벡터 DB 시스템

## 🎯 왜 두 개의 DB를 사용하나요?

| 용도 | ChromaDB | Pinecone |
|------|----------|----------|
| **개발/테스트** | ✅ 최적 (무료, 빠름) | ❌ API 제한 |
| **프로덕션** | ⚠️ 서버 필요 | ✅ 최적 (관리형) |
| **대용량 처리** | ⚠️ 메모리 제한 | ✅ 무제한 확장 |
| **팀 협업** | ❌ 로컬 전용 | ✅ API 공유 |
| **오프라인 작업** | ✅ 가능 | ❌ 인터넷 필요 |

## 🚀 Quick Start

### 1. 환경 설정
```bash
# .env 파일
PINECONE_API_KEY=your-pinecone-key
PINECONE_INDEX_NAME=literature-rag

# ChromaDB는 별도 설정 불필요 (로컬)
```

### 2. 의존성 설치
```bash
pip install -r requirements_rag.txt
```

### 3. 하이브리드 시스템 구축
```bash
# 두 DB 모두에 논문 저장
python scripts/hybrid_rag.py --build

# ChromaDB를 주 DB로 설정
python scripts/hybrid_rag.py --build --primary chroma

# Pinecone을 주 DB로 설정
python scripts/hybrid_rag.py --build --primary pinecone
```

## 💻 사용 시나리오

### 시나리오 1: 로컬 개발
```python
from hybrid_rag import HybridRAGEngine

# ChromaDB 우선 사용 (빠른 개발)
engine = HybridRAGEngine(primary_db="chroma")
result = engine.query("LNP 관련 최신 연구")
```

### 시나리오 2: 프로덕션 배포
```python
# Pinecone 우선 사용 (안정적인 서비스)
engine = HybridRAGEngine(primary_db="pinecone")
result = engine.query("mRNA delivery systems")
```

### 시나리오 3: 자동 Failover
```python
# Primary DB 실패 시 자동으로 Secondary 사용
engine = HybridRAGEngine(primary_db="pinecone")
result = engine.query("gene therapy")  # Pinecone 실패 시 ChromaDB 사용
```

### 시나리오 4: 성능 비교
```bash
# 두 DB 성능 벤치마크
python scripts/hybrid_rag.py --benchmark
```

## 🔄 동기화 전략

### 자동 동기화
```python
from hybrid_rag import HybridVectorDB

hybrid_db = HybridVectorDB(enable_sync=True)
# PDF 처리 시 자동으로 두 DB에 저장
```

### 수동 동기화
```bash
# 양방향 동기화
python scripts/hybrid_rag.py --sync

# ChromaDB → Pinecone만
python scripts/hybrid_rag.py --sync --direction chroma_to_pinecone
```

## 📊 DB 선택 전략

### 1. 자동 선택 (추천)
```python
# 시스템이 최적의 DB 자동 선택
result = engine.query("your question")
```

### 2. 강제 선택
```python
# ChromaDB만 사용
result = engine.query("your question", use_db="chroma")

# Pinecone만 사용
result = engine.query("your question", use_db="pinecone")
```

### 3. 하이브리드 검색
```python
# 두 DB에서 검색 후 결과 병합
results_chroma = engine.query("question", use_db="chroma")
results_pinecone = engine.query("question", use_db="pinecone")
# 결과 통합 로직
```

## 🛠️ 고급 기능

### 통계 모니터링
```bash
# 두 DB 상태 확인
python scripts/hybrid_rag.py --stats

# 출력 예시:
# ChromaDB: 1,234 papers (local)
# Pinecone: 1,234 vectors (cloud)
# Sync status: ✅ Synchronized
```

### 벤치마크 결과 예시
```
⚡ Performance Benchmark
==========================
CHROMA:
  Average time: 0.125s
  Min time: 0.098s
  Max time: 0.203s

PINECONE:
  Average time: 0.089s
  Min time: 0.065s
  Max time: 0.134s
```

### 비용 최적화
```python
# 개발 중: ChromaDB 사용 (무료)
if os.getenv("ENVIRONMENT") == "development":
    engine = HybridRAGEngine(primary_db="chroma")
else:
    # 프로덕션: Pinecone 사용
    engine = HybridRAGEngine(primary_db="pinecone")
```

## 📈 운영 가이드

### 개발 워크플로우
1. **로컬 개발**: ChromaDB로 빠른 프로토타이핑
2. **테스트**: 소량 데이터로 두 DB 테스트
3. **스테이징**: Pinecone에 전체 데이터 업로드
4. **프로덕션**: Pinecone 주 DB, ChromaDB 백업

### 백업 전략
```bash
# ChromaDB 백업 (로컬 파일)
cp -r ./vector_db ./vector_db_backup

# Pinecone 백업 (export 스크립트)
python scripts/export_pinecone.py --output backup.json
```

### 마이그레이션
```bash
# ChromaDB → Pinecone
python scripts/hybrid_rag.py --sync --direction chroma_to_pinecone

# Pinecone → ChromaDB
python scripts/hybrid_rag.py --sync --direction pinecone_to_chroma
```

## 🎯 Best Practices

### 1. DB 선택 기준
- **개발/테스트**: ChromaDB
- **소규모 프로젝트** (<10만 벡터): ChromaDB
- **대규모 프로젝트**: Pinecone
- **팀 협업 필요**: Pinecone
- **오프라인 필수**: ChromaDB

### 2. 성능 최적화
```python
# 캐싱 레이어 추가
from functools import lru_cache

@lru_cache(maxsize=100)
def cached_query(question: str):
    return engine.query(question)
```

### 3. 에러 처리
```python
try:
    # Pinecone 우선 시도
    result = engine.query(question, use_db="pinecone")
except Exception as e:
    # ChromaDB로 폴백
    result = engine.query(question, use_db="chroma")
    log_error(f"Pinecone failed, using ChromaDB: {e}")
```

## 🔧 트러블슈팅

### ChromaDB 문제
```bash
# DB 초기화
rm -rf ./vector_db/chroma
python scripts/hybrid_rag.py --build --primary chroma
```

### Pinecone 문제
```bash
# 연결 테스트
python scripts/pinecone_test.py

# 인덱스 재생성
python scripts/reset_pinecone.py
```

### 동기화 문제
```bash
# 동기화 로그 확인
cat ./vector_db/sync_log.json

# 강제 재동기화
rm ./vector_db/sync_log.json
python scripts/hybrid_rag.py --sync
```

## 📊 모니터링 대시보드

```python
# monitoring.py
from hybrid_rag import HybridVectorDB

hybrid_db = HybridVectorDB()
stats = hybrid_db.get_statistics()

print(f"""
=== Hybrid RAG System Status ===
ChromaDB:  {stats['chroma']['total_papers']} papers (Local)
Pinecone:  {stats['pinecone']['total_vectors']} vectors (Cloud)
Sync:      {stats['sync_status']['last_sync']}
===================================
""")
```

## 🚀 로드맵

- [ ] 실시간 동기화
- [ ] 자동 백업 스케줄러
- [ ] 웹 기반 관리 UI
- [ ] 멀티 인덱스 지원
- [ ] A/B 테스트 프레임워크