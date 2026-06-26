# API 비용 최적화 가이드

## 📊 현재 비용 모니터링

```bash
# 전체 비용 요약 보기
python scripts/cost_monitor.py

# 최근 7일 비용 보기
python scripts/cost_monitor.py --days 7

# CSV로 내보내기
python scripts/cost_monitor.py --export

# JSON 형식으로 보기
python scripts/cost_monitor.py --json
```

## 💰 비용 절감 방법

### 1. 저렴한 모델 강제 사용
```bash
# .env 파일에 추가
FORCE_CHEAP_MODEL=true
MODEL=gpt-4o-mini  # 기본 모델을 mini로 설정
```

### 2. 캐싱 활용
- API 응답이 자동으로 캐시됨 (24시간)
- 동일한 논문 재처리 시 API 호출 없이 캐시 사용
- 캐시 디렉토리: `./cache/api_responses/`

### 3. 스마트 텍스트 트렁케이션
- Introduction과 Conclusion 우선 보존
- Methods와 Results는 압축
- 자동으로 20,000자로 최적화

### 4. 작업별 모델 자동 선택
- 키워드 추출: 항상 gpt-4o-mini
- 번역: 항상 gpt-4o-mini  
- 짧은 텍스트 (<5000자): gpt-4o-mini
- 긴 텍스트 (>20000자): gpt-4o

### 5. GPT 없이 메타데이터만 추출
```bash
# GPT 요약 건너뛰기 (메타데이터만)
python scripts/run_literature_batch.py --skip-gpt
```

### 6. 배치 처리 최적화
```bash
# 병렬 처리로 시간 단축
python scripts/run_literature_batch.py --workers 10

# PDF 다운로드 건너뛰기
python scripts/run_literature_batch.py --no-pdf-download
```

## 📈 비용 비교

| 모델 | 입력 (1K 토큰) | 출력 (1K 토큰) | 평균 논문당 비용 |
|------|----------------|----------------|------------------|
| gpt-4o | $0.005 | $0.015 | ~$0.15 |
| gpt-4o-mini | $0.00015 | $0.0006 | ~$0.005 |
| gpt-3.5-turbo | $0.0005 | $0.0015 | ~$0.015 |

**💡 gpt-4o-mini 사용 시 gpt-4o 대비 96% 비용 절감!**

## 🎯 추천 설정

### 대량 처리 (100+ 논문)
```bash
# .env 설정
FORCE_CHEAP_MODEL=true
MODEL=gpt-4o-mini

# 실행
python scripts/run_literature_batch.py --workers 10
```

### 고품질 요약 (중요 논문)
```bash
# .env 설정
FORCE_CHEAP_MODEL=false
MODEL=gpt-4o

# 실행
python scripts/run_literature_batch.py --collection "Important Papers"
```

### 테스트/개발
```bash
# 캐시 활용 + mini 모델
FORCE_CHEAP_MODEL=true
python scripts/run_literature_batch.py --limit 5
```

## 📊 예상 비용 계산

| 논문 수 | gpt-4o | gpt-4o-mini | 절감액 |
|---------|--------|-------------|--------|
| 10 | $1.50 | $0.05 | $1.45 |
| 50 | $7.50 | $0.25 | $7.25 |
| 100 | $15.00 | $0.50 | $14.50 |
| 500 | $75.00 | $2.50 | $72.50 |
| 1000 | $150.00 | $5.00 | $145.00 |

## 🔧 고급 설정

### 환경 변수
```bash
# 강제로 저렴한 모델 사용
export FORCE_CHEAP_MODEL=true

# 캐시 유효 기간 (시간)
export CACHE_DURATION_HOURS=48

# 텍스트 최대 길이
export MAX_TEXT_LENGTH=20000
```

### Python에서 직접 사용
```python
from api_cost_optimizer import optimize_api_call

# 최적화된 API 호출
response, cost = optimize_api_call(
    text="논문 내용...",
    prompt="요약해주세요",
    use_cache=True,
    smart_truncate=True
)
print(f"예상 비용: ${cost:.4f}")
```

## 📝 비용 로그 분석

로그 파일 위치: `logs/api_costs.json`

각 요청마다 기록되는 정보:
- timestamp: 요청 시간
- model: 사용된 모델
- input_tokens: 입력 토큰 수
- output_tokens: 출력 토큰 수  
- estimated_cost_usd: 예상 비용 (USD)

## 🚀 Quick Start

```bash
# 1. 비용 최적화 모드 활성화
echo "FORCE_CHEAP_MODEL=true" >> .env
echo "MODEL=gpt-4o-mini" >> .env

# 2. 논문 처리
python scripts/run_literature_batch.py --workers 10

# 3. 비용 확인
python scripts/cost_monitor.py
```