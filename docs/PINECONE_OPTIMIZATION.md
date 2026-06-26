# 📊 Pinecone 무료 플랜 최적화 가이드

## 🎯 Pinecone Starter (무료) 플랜 제한

| 항목 | 제한 | 설명 |
|------|------|------|
| **벡터 수** | 100,000개 | 총 벡터 개수 제한 |
| **인덱스** | 1개 | 하나의 인덱스만 생성 가능 |
| **차원** | 제한 없음 | 384차원 (sentence-transformers) 사용 |
| **메타데이터** | 40KB/벡터 | 각 벡터당 메타데이터 크기 |
| **네임스페이스** | 무제한 | 논리적 분리 가능 |

## 📈 논문 수용 능력 계산

### 현재 청킹 전략 (기본값)
- **청크 크기**: 500 단어 (overlap 50)
- **평균 청크 수/논문**: 20-30개
- **최대 논문 수**: 100,000 ÷ 25 = **약 4,000개 논문**

### 최적화된 청킹 전략
- **청크 크기**: 1000 단어 (overlap 100)
- **평균 청크 수/논문**: 10-15개
- **최대 논문 수**: 100,000 ÷ 12 = **약 8,300개 논문**

## 🚀 최적화 전략

### 1. 스마트 청킹 (50% 벡터 절감)
```python
# 기존: 모든 섹션을 동일하게 청킹
chunks = chunker.chunk_by_sections(text, chunk_size=500)

# 최적화: 중요 섹션만 세밀하게
important_sections = extract_important_sections(text)  # Abstract, Results, Conclusion
chunks = chunker.chunk_important_only(important_sections, chunk_size=1000)
```

### 2. 선택적 논문 저장
```python
# 중요도 기반 필터링
def should_store_in_pinecone(paper):
    # 최근 논문 우선
    if paper['year'] >= '2020':
        return True
    # 높은 인용수
    if paper.get('citations', 0) > 50:
        return True
    # 특정 컬렉션
    if 'Important' in paper.get('collections', []):
        return True
    return False
```

### 3. 계층적 저장 전략
```python
class TieredStorage:
    def process_paper(self, paper):
        # Tier 1: 최신/중요 논문 → Pinecone (빠른 검색)
        if paper['year'] >= '2022' or paper['importance'] == 'high':
            self.store_in_pinecone(paper, detailed=True)
        
        # Tier 2: 일반 논문 → Pinecone (요약만)
        elif paper['year'] >= '2018':
            self.store_in_pinecone(paper, abstract_only=True)
        
        # Tier 3: 오래된 논문 → ChromaDB만
        else:
            self.store_in_chroma_only(paper)
```

### 4. 압축 메타데이터
```python
# 기존: 전체 텍스트 저장 (2000자)
metadata = {
    'text': chunk['text'][:2000],
    'title': paper['title'],
    'authors': paper['authors'],
    # ...
}

# 최적화: 핵심만 저장 (500자)
metadata = {
    'text': summarize_chunk(chunk['text'], max_chars=500),
    'title': paper['title'][:100],
    'authors': paper['authors'][:3],  # 주요 저자만
    'year': paper['year'],
    'doi': paper['doi']
}
```

## 💰 비용 대비 효과 분석

### 무료 플랜으로 가능한 시나리오

| 시나리오 | 논문 수 | 적합성 |
|----------|---------|---------|
| 개인 연구 (1-2개 주제) | 500-1,000 | ✅ 충분 |
| 연구실 (5-10개 주제) | 2,000-4,000 | ✅ 가능 |
| 학과 전체 | 10,000+ | ❌ 부족 |

### 추천 구성

1. **소규모 (< 1,000 논문)**
   - Pinecone: 모든 논문 전체 텍스트
   - ChromaDB: 백업용

2. **중규모 (1,000-5,000 논문)**
   - Pinecone: 최신 2년 + 중요 논문
   - ChromaDB: 전체 논문

3. **대규모 (> 5,000 논문)**
   - Pinecone: Abstract + 핵심 논문만
   - ChromaDB: 전체 논문 (로컬 검색)

## 🛠️ 구현 코드

### 최적화된 빌더
```python
# optimized_pinecone_builder.py
class OptimizedPineconeBuilder:
    def __init__(self, max_vectors=100000):
        self.max_vectors = max_vectors
        self.current_vectors = self.get_current_count()
        self.vectors_per_paper = 12  # 최적화된 청킹
    
    def can_add_paper(self):
        return self.current_vectors + self.vectors_per_paper < self.max_vectors
    
    def optimize_paper(self, paper):
        # 1. 중요 섹션만 추출
        text = extract_key_sections(paper['text'])
        
        # 2. 큰 청크로 분할
        chunks = chunk_optimally(text, size=1000)
        
        # 3. 압축된 메타데이터
        metadata = compress_metadata(paper)
        
        return chunks, metadata
    
    def smart_store(self, papers):
        # 우선순위 정렬
        papers.sort(key=lambda p: (
            -int(p['year']),  # 최신 우선
            -p.get('citations', 0),  # 인용 많은 것
        ))
        
        stored = []
        for paper in papers:
            if not self.can_add_paper():
                print(f"⚠️ Pinecone 용량 한계 도달: {self.current_vectors}/{self.max_vectors}")
                break
            
            chunks, metadata = self.optimize_paper(paper)
            self.store(chunks, metadata)
            stored.append(paper['key'])
        
        return stored
```

### 용량 모니터링
```python
# monitor_pinecone.py
def check_pinecone_usage():
    pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
    index = pc.Index("literature-rag")
    stats = index.describe_index_stats()
    
    total = stats['total_vector_count']
    limit = 100000
    usage_pct = (total / limit) * 100
    
    print(f"""
    📊 Pinecone 사용량
    ==================
    현재: {total:,} / {limit:,} 벡터
    사용률: {usage_pct:.1f}%
    남은 용량: {limit - total:,} 벡터
    추가 가능 논문: ~{(limit - total) // 12}개
    """)
    
    if usage_pct > 80:
        print("⚠️ 경고: 80% 이상 사용 중!")
        print("권장: 오래된 논문 정리 또는 유료 플랜 고려")
    
    return stats
```

### 자동 정리 스크립트
```python
# cleanup_pinecone.py
def cleanup_old_papers(keep_years=3):
    """오래된 논문 자동 삭제"""
    current_year = datetime.now().year
    cutoff_year = current_year - keep_years
    
    # 삭제할 벡터 찾기
    index.delete(
        filter={
            "year": {"$lt": str(cutoff_year)}
        }
    )
    
    print(f"✅ {cutoff_year}년 이전 논문 삭제 완료")
```

## 📊 실제 사용 예시

### 연구 분야별 평균 논문 수

| 분야 | 연간 논문 수 | 5년 누적 | Pinecone 적합성 |
|------|-------------|----------|-----------------|
| 특정 단백질 연구 | 50-100 | 250-500 | ✅ 매우 적합 |
| LNP/mRNA | 200-500 | 1,000-2,500 | ✅ 적합 |
| Cancer 전체 | 5,000+ | 25,000+ | ❌ 부적합 |
| AI/ML | 10,000+ | 50,000+ | ❌ 부적합 |

## 🎯 결론 및 추천

### Pinecone 무료 플랜이 적합한 경우:
- ✅ 특정 주제 연구 (< 5,000 논문)
- ✅ 최신 논문 위주 검색
- ✅ 프로토타입/POC 개발
- ✅ 개인 연구자

### 하이브리드 전략 추천:
- 🔥 **Pinecone**: 최근 2-3년 + 중요 논문 (빠른 검색)
- 💾 **ChromaDB**: 전체 아카이브 (완전성)

### 대안 고려:
- **Weaviate Cloud**: 무료 티어 더 관대함
- **Qdrant Cloud**: 1GB 무료 (약 300,000 벡터)
- **자체 호스팅**: Milvus, Elasticsearch

## 💡 실전 팁

1. **정기적인 정리**: 매월 오래된/사용 안 하는 논문 삭제
2. **네임스페이스 활용**: 주제별로 분리하여 관리
3. **압축 우선**: 텍스트 요약으로 벡터 수 절감
4. **선택적 인덱싱**: 정말 중요한 논문만 Pinecone에

```bash
# 최적화 모드로 실행
python scripts/rag_query.py --build --optimize-for-free-tier
```