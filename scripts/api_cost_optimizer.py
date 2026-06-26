"""
API Cost Optimization Module
Strategies to reduce API costs while maintaining quality
"""

import os
import json
import hashlib
import time
from pathlib import Path
from typing import Dict, Optional, Tuple
from datetime import datetime, timedelta

class APICostOptimizer:
    """API 비용 최적화를 위한 유틸리티 클래스"""
    
    def __init__(self, cache_dir: str = "./cache/api_responses"):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.cost_log_file = Path("logs/api_costs.json")
        self.cost_log_file.parent.mkdir(exist_ok=True)
        
        # 모델별 비용 (1K 토큰당 USD) - 2026년 5월 기준
        self.model_costs = {
            # GPT-5.5 시리즈 (2026-04-23 출시, 1M 컨텍스트)
            "gpt-5.5": {"input": 0.005, "output": 0.030},          # $5/M input, $30/M output
            "gpt-5.5-pro": {"input": 0.030, "output": 0.180},      # $30/M input, $180/M output
            # GPT-5.4 시리즈 (2026-03-05)
            "gpt-5.4": {"input": 0.0025, "output": 0.015},         # $2.50/M input, $15/M output
            "gpt-5.4-mini": {"input": 0.00075, "output": 0.0045},  # $0.75/M input, $4.50/M output
            "gpt-5.4-nano": {"input": 0.00020, "output": 0.00125}, # $0.20/M input, $1.25/M output
            # GPT-5 base 시리즈 (mini는 분류기용)
            "gpt-5-mini": {"input": 0.00025, "output": 0.002},     # $0.25/M input, $2/M output
            # GPT-5.2 시리즈 (2025년 12월)
            "gpt-5.2-pro": {"input": 0.00175, "output": 0.014},    # $1.75/M input, $14/M output
            "gpt-5.2-pro-2025-12-11": {"input": 0.00175, "output": 0.014},
            "gpt-5.2": {"input": 0.00175, "output": 0.014},
            # GPT-4.1 시리즈
            "gpt-4.1-2025-04-14": {"input": 0.002, "output": 0.008},
            "gpt-4.1-mini-2025-04-14": {"input": 0.0004, "output": 0.0016},
            "gpt-4.1-nano-2025-04-14": {"input": 0.0001, "output": 0.0004},
            # GPT-4o 시리즈
            "gpt-4o": {"input": 0.005, "output": 0.015},
            "gpt-4o-mini": {"input": 0.00015, "output": 0.0006},
            # 이전 모델
            "gpt-3.5-turbo": {"input": 0.0005, "output": 0.0015},
            # Gemini
            "gemini-1.5-flash": {"input": 0.000075, "output": 0.00015},
            "gemini-1.5-pro": {"input": 0.00125, "output": 0.005},
            "gemini-2.0-flash": {"input": 0.0001, "output": 0.0004}
        }
        
    def get_cache_key(self, text: str, prompt: str, model: str) -> str:
        """캐시 키 생성 (full text hashed to prevent cross-paper collisions)."""
        h = hashlib.sha256()
        h.update(model.encode('utf-8'))
        h.update(b'\x00')
        h.update(prompt.encode('utf-8'))
        h.update(b'\x00')
        h.update(text.encode('utf-8'))
        return h.hexdigest()
    
    def get_cached_response(self, text: str, prompt: str, model: str, 
                           cache_duration_hours: int = 24) -> Optional[str]:
        """캐시된 응답 조회"""
        cache_key = self.get_cache_key(text, prompt, model)
        cache_file = self.cache_dir / f"{cache_key}.json"
        
        if cache_file.exists():
            with open(cache_file, 'r', encoding='utf-8') as f:
                cached = json.load(f)
            
            # 캐시 유효성 검사
            cached_time = datetime.fromisoformat(cached['timestamp'])
            if datetime.now() - cached_time < timedelta(hours=cache_duration_hours):
                print(f"✓ Using cached response (saved {cached_time.strftime('%Y-%m-%d %H:%M')})")
                return cached['response']
        
        return None
    
    def save_to_cache(self, text: str, prompt: str, model: str, response: str):
        """응답을 캐시에 저장"""
        cache_key = self.get_cache_key(text, prompt, model)
        cache_file = self.cache_dir / f"{cache_key}.json"
        
        cache_data = {
            'timestamp': datetime.now().isoformat(),
            'model': model,
            'prompt_preview': prompt[:200],
            'response': response
        }
        
        with open(cache_file, 'w', encoding='utf-8') as f:
            json.dump(cache_data, f, ensure_ascii=False, indent=2)
    
    def estimate_tokens(self, text: str) -> int:
        """텍스트의 토큰 수 추정 (대략적인 계산)"""
        # 한국어/영어 혼용 시 평균적으로 4자 = 1토큰
        return len(text) // 4
    
    def log_api_usage(self, model: str, input_text: str, output_text: str):
        """API 사용량 로깅 (에러 방지 개선)"""
        input_tokens = self.estimate_tokens(input_text)
        output_tokens = self.estimate_tokens(output_text)
        
        if model in self.model_costs:
            cost = (
                (input_tokens / 1000) * self.model_costs[model]["input"] +
                (output_tokens / 1000) * self.model_costs[model]["output"]
            )
        else:
            cost = 0
        
        log_entry = {
            'timestamp': datetime.now().isoformat(),
            'model': model,
            'input_tokens': input_tokens,
            'output_tokens': output_tokens,
            'estimated_cost_usd': round(cost, 6)
        }
        
        # 기존 로그 읽기 (에러 처리 강화)
        logs = []
        if self.cost_log_file.exists():
            try:
                with open(self.cost_log_file, 'r') as f:
                    content = f.read()
                    if content.strip():  # 빈 파일이 아닌 경우만
                        logs = json.loads(content)
                        # 리스트가 아닌 경우 리스트로 변환
                        if not isinstance(logs, list):
                            logs = [logs]
            except (json.JSONDecodeError, ValueError) as e:
                print(f"⚠️ Warning: Corrupted cost log file, creating new one. Error: {e}")
                # 백업 생성
                backup_file = self.cost_log_file.with_suffix('.json.backup')
                if self.cost_log_file.exists():
                    import shutil
                    shutil.copy(self.cost_log_file, backup_file)
                    print(f"  Backup saved to: {backup_file}")
                logs = []
        
        logs.append(log_entry)
        
        # 로그 저장 (안전하게)
        try:
            with open(self.cost_log_file, 'w') as f:
                json.dump(logs, f, indent=2)
        except Exception as e:
            print(f"⚠️ Failed to save cost log: {e}")
        
        return cost
    
    def get_cost_summary(self) -> Dict:
        """비용 요약 정보 조회 (에러 처리 강화)"""
        if not self.cost_log_file.exists():
            return {"total_cost_usd": 0, "total_requests": 0, "by_model": {}}
        
        try:
            with open(self.cost_log_file, 'r') as f:
                content = f.read()
                if not content.strip():
                    return {"total_cost_usd": 0, "total_requests": 0, "by_model": {}}
                logs = json.loads(content)
                if not isinstance(logs, list):
                    logs = [logs]
        except (json.JSONDecodeError, ValueError) as e:
            print(f"⚠️ Warning: Cannot read cost log: {e}")
            return {"total_cost_usd": 0, "total_requests": 0, "by_model": {}}
        
        total_cost = 0
        by_model = {}
        
        for log in logs:
            if not isinstance(log, dict):
                continue
            
            cost = log.get('estimated_cost_usd', 0)
            total_cost += cost
            
            model = log.get('model', 'unknown')
            if model not in by_model:
                by_model[model] = {'count': 0, 'cost': 0, 'tokens': 0}
            
            by_model[model]['count'] += 1
            by_model[model]['cost'] += cost
            by_model[model]['tokens'] += log.get('input_tokens', 0) + log.get('output_tokens', 0)
        
        return {
            'total_cost_usd': round(total_cost, 2),
            'total_requests': len(logs),
            'by_model': {
                model: {
                    'requests': stats['count'],
                    'cost_usd': round(stats['cost'], 2),
                    'total_tokens': stats['tokens']
                }
                for model, stats in by_model.items()
            }
        }

class TextOptimizer:
    """텍스트 최적화 전략"""
    
    @staticmethod
    def smart_truncate(text: str, max_chars: int = 20000, 
                       preserve_sections: bool = True) -> str:
        """
        지능적 텍스트 트렁케이션
        - Introduction과 Conclusion은 보존
        - Methods와 Results는 압축
        """
        if len(text) <= max_chars:
            return text
        
        if not preserve_sections:
            return text[:max_chars] + "... [truncated]"
        
        # 섹션 분리 시도
        sections = {
            'intro': '',
            'methods': '',
            'results': '',
            'discussion': '',
            'conclusion': ''
        }
        
        # 간단한 섹션 감지 (개선 가능)
        lines = text.split('\n')
        current_section = 'intro'
        
        for line in lines:
            lower_line = line.lower()
            if any(word in lower_line for word in ['method', 'material']):
                current_section = 'methods'
            elif 'result' in lower_line:
                current_section = 'results'
            elif 'discussion' in lower_line:
                current_section = 'discussion'
            elif 'conclusion' in lower_line:
                current_section = 'conclusion'
            
            sections[current_section] += line + '\n'
        
        # 우선순위에 따라 재구성 (수치 정보 보존을 위해 더 많이 포함)
        prioritized = []

        # 1. Introduction (핵심 배경)
        if sections['intro']:
            prioritized.append(sections['intro'][:6000])

        # 2. Results (가장 중요 - 수치 데이터 포함)
        if sections['results']:
            prioritized.append(sections['results'][:8000])

        # 3. Methods (데이터, 모델 정보)
        if sections['methods']:
            prioritized.append(sections['methods'][:6000])

        # 4. Discussion (해석)
        if sections['discussion']:
            prioritized.append(sections['discussion'][:5000])

        # 5. Conclusion (핵심 결론)
        if sections['conclusion']:
            prioritized.append(sections['conclusion'][:3000])
        
        result = '\n'.join(prioritized)
        if len(result) > max_chars:
            result = result[:max_chars] + "... [truncated]"
        
        return result
    
    @staticmethod
    def extract_key_content(text: str) -> str:
        """
        핵심 콘텐츠만 추출
        - Abstract
        - 주요 findings
        - Conclusions
        """
        key_parts = []
        lines = text.split('\n')
        
        # Abstract 찾기
        in_abstract = False
        for i, line in enumerate(lines):
            if 'abstract' in line.lower():
                in_abstract = True
                continue
            if in_abstract:
                if any(word in line.lower() for word in ['introduction', 'background', '1.']):
                    break
                key_parts.append(line)
        
        # 주요 findings 찾기 (Results의 마지막 부분)
        for i, line in enumerate(lines):
            if any(phrase in line.lower() for phrase in 
                   ['in conclusion', 'in summary', 'our findings', 'we found']):
                # 해당 단락 포함
                for j in range(max(0, i-2), min(len(lines), i+5)):
                    key_parts.append(lines[j])
        
        return '\n'.join(key_parts)

def get_optimized_model_choice(text_length: int, task_type: str = "summary") -> str:
    """
    텍스트 길이와 작업 유형에 따른 최적 모델 선택
    기본값: gpt-5.2-pro (2025년 12월 최신 모델)
    """
    # 환경변수에서 설정 확인
    force_cheap = os.getenv("FORCE_CHEAP_MODEL", "false").lower() == "true"
    default_model = os.getenv("MODEL", "gpt-5.2-pro")

    if force_cheap:
        return "gpt-5.2"  # 기본 GPT-5.2 모델 (더 저렴)

    # 작업별 모델 추천 - 모든 작업에 최신 모델 사용 (품질 우선)
    return default_model

# 사용 예시를 위한 헬퍼 함수
def optimize_api_call(text: str, prompt: str, model: str = None, 
                      use_cache: bool = True, smart_truncate: bool = True) -> Tuple[str, float]:
    """
    최적화된 API 호출
    
    Returns:
        (response, estimated_cost)
    """
    optimizer = APICostOptimizer()
    
    # 1. 캐시 확인
    if use_cache:
        cached = optimizer.get_cached_response(text, prompt, model)
        if cached:
            return cached, 0  # 캐시 사용 시 비용 0
    
    # 2. 텍스트 최적화
    if smart_truncate:
        text = TextOptimizer.smart_truncate(text)
    
    # 3. 모델 자동 선택
    if not model:
        model = get_optimized_model_choice(len(text))
    
    # 4. 실제 API 호출 (여기서는 시뮬레이션)
    # response = actual_api_call(text, prompt, model)
    response = f"[Simulated response for {model}]"
    
    # 5. 캐시 저장
    if use_cache:
        optimizer.save_to_cache(text, prompt, model, response)
    
    # 6. 비용 로깅
    cost = optimizer.log_api_usage(model, text + prompt, response)
    
    return response, cost

if __name__ == "__main__":
    # 비용 요약 출력
    optimizer = APICostOptimizer()
    summary = optimizer.get_cost_summary()
    
    print("=== API Cost Summary ===")
    print(f"Total Cost: ${summary['total_cost_usd']}")
    print(f"Total Requests: {summary['total_requests']}")
    print("\nBy Model:")
    for model, stats in summary['by_model'].items():
        print(f"  {model}:")
        print(f"    Requests: {stats['requests']}")
        print(f"    Cost: ${stats['cost_usd']}")
        print(f"    Tokens: {stats['total_tokens']:,}")