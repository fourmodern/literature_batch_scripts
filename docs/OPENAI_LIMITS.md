# 🚦 OpenAI API 사용 제한 및 대응 방법

## 📊 OpenAI API 제한 사항

### 1. **Rate Limits (속도 제한)**

#### Tier별 제한 (GPT-4o-mini)
| Tier | RPM (분당 요청) | TPM (분당 토큰) | 일일 요청 | 월 지출 |
|------|---------------|---------------|----------|---------|
| Free | 3 | 200,000 | 200 | $0 |
| Tier 1 | 500 | 2,000,000 | 10,000 | $100 |
| Tier 2 | 5,000 | 4,000,000 | - | $500 |
| Tier 3 | 10,000 | 12,000,000 | - | $1,000 |
| Tier 4 | 10,000 | 30,000,000 | - | $5,000 |
| Tier 5 | 30,000 | 150,000,000 | - | $50,000+ |

#### Tier별 제한 (GPT-4o)
| Tier | RPM | TPM | 일일 요청 |
|------|-----|-----|----------|
| Free | 3 | 10,000 | 100 |
| Tier 1 | 500 | 30,000 | - |
| Tier 2 | 5,000 | 450,000 | - |
| Tier 3 | 10,000 | 2,000,000 | - |
| Tier 4 | 10,000 | 10,000,000 | - |
| Tier 5 | 30,000 | 50,000,000 | - |

### 2. **현재 구현된 대응 방법**

#### 자동 재시도 (gpt_summarizer.py)
```python
# RateLimitError 발생 시 자동 재시도
- 지수 백오프: 20초 → 40초 → 80초
- 최대 3회 재시도
- 재시도 간 대기 시간 자동 조절
```

#### 에러별 처리
- **RateLimitError**: 자동 대기 후 재시도
- **APITimeoutError**: 즉시 재시도 (최대 3회)
- **APIConnectionError**: 2초 대기 후 재시도
- **InternalServerError**: 5초 대기 후 재시도

### 3. **사용량 최적화 방법 (이미 구현됨)**

#### API 비용 최적화 (api_cost_optimizer.py)
```python
# 1. 응답 캐싱
- 동일한 요청 24시간 캐싱
- 캐시 히트 시 API 호출 없음

# 2. 스마트 모델 선택
- 짧은 텍스트 → gpt-4o-mini
- 긴 텍스트 → gpt-4o-mini
- 복잡한 분석 → gpt-4o (선택적)

# 3. 텍스트 최적화
- 스마트 트렁케이션 (중요 섹션 보존)
- 중복 제거
- 불필요한 공백 제거
```

## 🛡️ 제한 회피 전략

### 1. **병렬 처리 조절**
```bash
# 기본 (5 workers) - 안전
python scripts/run_literature_batch.py --workers 5

# Tier 1 사용자 (느리지만 안전)
python scripts/run_literature_batch.py --workers 2

# Tier 2+ 사용자 (빠른 처리)
python scripts/run_literature_batch.py --workers 10
```

### 2. **GPT 사용 건너뛰기**
```bash
# 메타데이터만 추출 (API 사용 안함)
python scripts/run_literature_batch.py --skip-gpt

# 나중에 개별 처리
python scripts/process_single_pdf.py paper.pdf
```

### 3. **모델 다운그레이드**
```bash
# .env 파일
MODEL=gpt-4o-mini  # 기본값, 저렴하고 빠름
# MODEL=gpt-4o     # 필요시만 사용
```

### 4. **캐싱 활용**
```bash
# 캐시 디렉토리 확인
ls logs/api_cache/

# 재처리 시 캐시 자동 활용
python scripts/run_literature_batch.py --overwrite
# (동일한 논문은 캐시에서 로드)
```

## 📈 사용량 모니터링

### 현재 사용량 확인
```bash
# API 비용 로그 확인
cat logs/api_costs.json | jq '.'

# 일일 사용량 요약
python -c "
import json
with open('logs/api_costs.json') as f:
    data = json.load(f)
    print(f'Total calls: {data.get(\"total_calls\", 0)}')
    print(f'Cache hits: {data.get(\"cache_hits\", 0)}')
    print(f'Estimated cost: ${data.get(\"estimated_cost\", 0):.2f}')
"
```

### OpenAI 대시보드
- https://platform.openai.com/usage
- 실시간 사용량 및 제한 확인
- Tier 업그레이드 상태

## 🚨 문제 해결

### "Rate limit exceeded" 에러
1. **즉시 조치**
   ```bash
   # Workers 줄이기
   python scripts/run_literature_batch.py --workers 1
   ```

2. **장기 해결**
   - OpenAI Tier 업그레이드 (더 많은 사용 → 자동 업그레이드)
   - Gemini로 전환 (`SUMMARIZER=gemini`)

### "Quota exceeded" 에러
- Free Tier: 일일 한도 초과
- 해결: 다음날 재시도 또는 유료 전환

### "Timeout" 에러
```python
# .env에서 타임아웃 늘리기
REQUEST_TIMEOUT=600  # 10분
```

## 💡 최적화 팁

### 1. **대량 처리 시**
```bash
# 1단계: 메타데이터만 추출
python scripts/run_literature_batch.py --skip-gpt --workers 10

# 2단계: 중요 논문만 GPT 처리
python scripts/run_literature_batch.py --collection "Important" --overwrite
```

### 2. **비용 절감**
```bash
# Gemini 사용 (무료 티어 관대함)
SUMMARIZER=gemini python scripts/run_literature_batch.py

# 짧은 요약만
MODEL=gpt-4o-mini python scripts/run_literature_batch.py
```

### 3. **안정성 우선**
```bash
# 느리지만 안정적
python scripts/run_literature_batch.py \
  --workers 2 \
  --limit 10 \
  --resume
```

## 📊 예상 사용량

| 논문 수 | GPT-4o-mini | GPT-4o | 예상 시간 |
|---------|------------|--------|-----------|
| 10 | $0.10 | $2.00 | 2분 |
| 100 | $1.00 | $20.00 | 20분 |
| 1000 | $10.00 | $200.00 | 3시간 |

**참고**: 캐싱 사용 시 비용 50-70% 절감 가능

## 🔗 참고 자료
- [OpenAI Rate Limits](https://platform.openai.com/docs/guides/rate-limits)
- [OpenAI Pricing](https://openai.com/pricing)
- [Usage Dashboard](https://platform.openai.com/usage)