"""
Generate summaries using OpenAI API with retry logic.
- 주요 수정:
  * stdin 블로킹 방지
  * chat.completions 파라미터: max_completion_tokens → max_tokens
  * timeout은 클라이언트 옵션으로 지정
  * 예외 클래스 정리
"""

import os
import time
import sys
from typing import List, Dict

from openai import OpenAI
# 예외는 상황별로 세분화해 처리
from openai import (
    RateLimitError, APITimeoutError, APIConnectionError,
    APIError, BadRequestError, AuthenticationError, InternalServerError
)


def summarize_text_with_retry(
    text: str,
    prompt: str,
    model: str = None,
    max_tokens: int = 500,
    max_retries: int = 3,
    request_timeout: int = 300,  # 5분으로 증가
) -> str:
    """
    Generate summary using OpenAI API with retry logic for rate limits and errors.
    - text: 요약 대상 원문
    - prompt: 시스템/사용자 지시
    - model: 모델명 (미지정 시 환경변수 MODEL 또는 기본값 'gpt-5-mini')
    - max_tokens: 출력 토큰 상한 (chat.completions: max_tokens)
    - max_retries: 수동 재시도 횟수
    - request_timeout: 요청 타임아웃(초)
    """
    if not text or not text.strip():
        return "No text available for summarization."

    model = model or os.getenv("MODEL", "gpt-4o")

    # 클라이언트에 timeout 지정 (요청마다 timeout을 주고 싶다면 with_options 사용)
    client = OpenAI(
        api_key=os.getenv("OPENAI_API_KEY"),
        max_retries=0,           # 수동 재시도 제어
        timeout=request_timeout, # 전체 요청 타임아웃 (기본 5분)
    )

    # 매우 긴 입력의 보수적 트렁케이션 (문자 길이 기준; 실제 토큰과 다를 수 있음)
    max_input_length = 30000  # ~7.5k 토큰 수준 가정
    if len(text) > max_input_length:
        text = text[:max_input_length] + "... [truncated]"

    messages = [
        {
            "role": "system",
            "content": (
                "당신은 최고 수준의 학술 논문 분석 전문가입니다.\n\n"
                "🔴 절대 규칙:\n"
                "1. 오직 제공된 논문 텍스트에 명시된 내용만 사용하세요\n"
                "2. 논문에 없는 정보는 추측하거나 만들어내지 마세요\n"
                "3. 불확실한 경우 반드시 \"논문에 명시되지 않음\"으로 표기하세요\n"
                "4. 일반적인 지식이나 배경정보를 추가하지 마세요\n"
                "5. 논문의 실제 문장과 데이터를 정확히 인용하세요\n\n"
                "✅ 작성 원칙:\n"
                "- 구체적인 수치, 통계, 실험 결과를 정확히 포함\n"
                "- 저자가 사용한 용어와 표현을 그대로 사용\n"
                "- 논문의 각 섹션(Introduction, Methods, Results, Discussion)에서 정보 추출\n"
                "- 한국어로 명확하고 전문적으로 작성\n"
                "- 학술적 정확성과 객관성 유지"
            ),
        },
        {
            "role": "user",
            "content": f"{prompt}\n\n논문 내용:\n{text}",
        },
    ]

    for attempt in range(max_retries):
        try:
            # gpt-5 시리즈는 Responses API 사용
            if 'gpt-5' in model:
                resp = client.responses.create(
                    model=model,
                    input=messages,
                    max_output_tokens=max_tokens,
                    reasoning={"effort": "minimal"},  # 내부 추론 최소화
                )
                # Response에서 텍스트 추출
                text_parts = []
                for output_item in resp.output:
                    if hasattr(output_item, 'content'):
                        for content_item in output_item.content:
                            if hasattr(content_item, 'text'):
                                text_parts.append(content_item.text)
                return ''.join(text_parts).strip()
            else:
                resp = client.chat.completions.create(
                    model=model,
                    messages=messages,
                    max_tokens=max_tokens,
                )
                return resp.choices[0].message.content.strip()

        except RateLimitError as e:
            # 429 → 지수 백오프
            if attempt < max_retries - 1:
                wait = min(5 * (2**attempt), 60)
                print(f"[RateLimit] Waiting {wait}s... ({attempt+1}/{max_retries})")
                time.sleep(wait)
                continue
            return "[Rate limit exceeded - summary unavailable]"

        except (APITimeoutError,) as e:
            if attempt < max_retries - 1:
                print(f"[Timeout] Retrying... ({attempt+1}/{max_retries})")
                time.sleep(2)
                continue
            return "[API timeout - summary unavailable]"

        except (APIConnectionError,) as e:
            if attempt < max_retries - 1:
                print(f"[Connection] {e} → retry ({attempt+1}/{max_retries})")
                time.sleep(2)
                continue
            return "[Connection error - summary unavailable]"

        except (BadRequestError, AuthenticationError) as e:
            # 400/401 범주 → 재시도 무의미
            return f"[Request error - {type(e).__name__}]"

        except (InternalServerError, APIError) as e:
            # 5xx 또는 기타 APIError → 1~2회 재시도 후 중단
            if attempt < max_retries - 1:
                print(f"[Server/APIError] retry ({attempt+1}/{max_retries})")
                time.sleep(2)
                continue
            return f"[API error - {type(e).__name__}]"

        except Exception as e:
            if attempt < max_retries - 1:
                print(f"[Unexpected] {e} → retry ({attempt+1}/{max_retries})")
                time.sleep(2)
                continue
            return f"[Error generating summary: {type(e).__name__}]"


def summarize_text(text: str, prompt: str, model: str = None, max_tokens: int = 500) -> str:
    """Backward compatibility wrapper."""
    return summarize_text_with_retry(text, prompt, model, max_tokens)


def generate_short_long(text: str, title: str = None):
    """Generate both short and long summaries of the text."""
    short_prompt = (
        "이 논문의 핵심 내용을 3-5개의 문장으로 정확하게 요약해주세요.\n\n"
        "📋 요약 체크리스트:\n"
        "□ 연구의 구체적 목적 (Introduction에서 'aim', 'objective', 'purpose' 찾기)\n"
        "□ 핵심 방법론 (Methods에서 실험명, 모델명, 데이터셋 찾기)\n"
        "□ 주요 발견 (Results에서 가장 중요한 수치적 결과 1-2개)\n"
        "□ 임상적/과학적 의의 (Discussion/Conclusion에서 저자의 주장)\n\n"
        "⚠️ 필수 준수사항:\n"
        "- 논문에 직접 명시된 내용만 사용\n"
        "- 구체적 수치 포함\n"
        "- 저자의 정확한 용어 사용\n"
        "- 배경지식 추가 금지\n"
        "- 찾을 수 없는 정보는 생략\n"
        "형식: 각 문장은 논문의 다른 측면을 다루며, 구체적이고 정보가 풍부해야 함"
    )

    long_prompt = (
        "이 논문을 깊이 있게 분석하여 상세한 학술 요약을 작성해주세요.\n\n"
        "1) 연구 배경 및 필요성\n"
        "2) 연구 설계 및 방법론\n"
        "3) 핵심 연구 결과\n"
        "4) 결과 해석 및 의의\n"
        "5) 연구의 강점과 한계\n"
        "⚠️ 각 항목별로 찾을 수 없으면 '[해당 내용 논문에 명시되지 않음]' 표기"
    )

    if title:
        short_prompt = f"Paper Title: {title}\n\n{short_prompt}"
        long_prompt = f"Paper Title: {title}\n\n{long_prompt}"

    # GPT-5-mini는 더 많은 토큰이 필요 (Responses API 사용 시)
    model = os.getenv("MODEL", "gpt-4o-mini")
    # GPT-5는 Responses API로 충분한 출력 토큰 확보
    if 'gpt-5' in model:
        short_tokens = 1200  # 간단 요약용
        long_tokens = 2000   # 상세 요약용
    else:
        short_tokens = 400
        long_tokens = 3000
    
    short = summarize_text(text, short_prompt, max_tokens=short_tokens)
    long = summarize_text(text, long_prompt, max_tokens=long_tokens)
    return short, long


def generate_sections(text: str, title: str = None):
    """Generate contributions, limitations, ideas, keywords."""
    # title 파라미터 활용
    prefix = f"Paper Title: {title}\n\n" if title else ""
    
    contribution_prompt = prefix + "논문 기여도를 bullet로 정리. 원문 표현을 최대한 보존."
    limitations_prompt = prefix + "논문 한계점을 정리. 원문 인용 포함."
    ideas_prompt = prefix + "향후 연구 방향/미해결 질문을 분류(A/B/C/D)하여 정리."
    keywords_prompt = prefix + "다른 논문과 연결 가능한 핵심 키워드 5-8개를 쉼표로 구분하여 나열(소문자, 하이픈 사용). 예: machine-learning, deep-neural-networks, computer-vision"

    # GPT-5-mini는 Responses API로 적절한 토큰 설정
    model = os.getenv("MODEL", "gpt-4o-mini")
    if 'gpt-5' in model:
        section_tokens = 1500  # 섹션별 요약용
        keyword_tokens = 500   # 키워드용
    else:
        section_tokens = 500
        keyword_tokens = 200
    
    contributions = summarize_text(text, contribution_prompt, max_tokens=section_tokens)
    limitations = summarize_text(text, limitations_prompt, max_tokens=section_tokens)
    ideas = summarize_text(text, ideas_prompt, max_tokens=section_tokens)
    keywords = summarize_text(text, keywords_prompt, max_tokens=keyword_tokens)
    return contributions, limitations, ideas, keywords


def translate_captions(captions: List[Dict], caption_type: str = "figure") -> List[Dict]:
    """Translate figure/table captions to Korean."""
    import logging
    log = logging.getLogger(__name__)

    if not captions:
        return captions

    client = OpenAI(timeout=60)  # 번역은 더 짧은 타임아웃

    translated = []
    for cap in captions:
        title = cap.get("title", "")
        if not title:
            translated.append(cap)
            continue

        full_prompt = (
            f"다음 논문 {'그림' if caption_type == 'figure' else '표'} 제목을 한국어로 번역.\n"
            f"전문용어는 영어 병기.\n\n원문: {title}\n\n"
            "번역된 한국어 제목만 출력:"
        )
        try:
            # 번역은 항상 gpt-4o-mini 사용 (빠르고 저렴)
            resp = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "You are a professional academic translator."},
                    {"role": "user", "content": full_prompt},
                ],
                max_tokens=200,  # gpt-4o-mini는 max_tokens 사용
            )
            title_kr = resp.choices[0].message.content.strip()
        except Exception as e:
            # API 할당량 초과 등의 에러 시 원문 사용
            if "insufficient_quota" in str(e):
                log.warning(f"API quota exceeded - using original title")
            else:
                log.warning(f"Translation failed for '{title[:50]}...': {e}")
            title_kr = title

        new_cap = cap.copy()
        new_cap["title_kr"] = title_kr
        translated.append(new_cap)

    return translated


if __name__ == "__main__":
    # 표준입력 블로킹 방지: 파이프 입력이 없으면 안내 메시지 또는 샘플 처리
    if sys.stdin.isatty():
        # a) 파일 경로 인자를 받는 방식
        if len(sys.argv) >= 2 and os.path.exists(sys.argv[1]):
            with open(sys.argv[1], "r", encoding="utf-8") as f:
                txt = f.read()
        else:
            # b) 샘플 텍스트로 대체하거나 사용법 안내 후 종료
            print("Usage: python script.py < paper.txt  또는  python script.py paper.txt")
            sys.exit(1)
    else:
        txt = sys.stdin.read()

    s, l = generate_short_long(txt, "Test Paper")
    print("---SHORT SUMMARY---\n", s)
    print("\n---LONG SUMMARY---\n", l)
