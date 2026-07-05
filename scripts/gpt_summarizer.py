"""
Generate summaries using OpenAI API with retry logic.
- 주요 수정:
  * stdin 블로킹 방지
  * chat.completions 파라미터: max_completion_tokens → max_tokens
  * timeout은 클라이언트 옵션으로 지정
  * 예외 클래스 정리
"""

import json
import os
import re
import time
import sys
import base64
from typing import List, Dict

from openai import OpenAI
# 예외는 상황별로 세분화해 처리
from openai import (
    RateLimitError, APITimeoutError, APIConnectionError,
    APIError, BadRequestError, AuthenticationError, InternalServerError
)
from api_cost_optimizer import APICostOptimizer, TextOptimizer, get_optimized_model_choice


class SummarizationFailed(Exception):
    """Raised when summarization cannot be completed after all retries.
    Callers MUST NOT mark the paper as done when this is raised."""


def _encode_image_b64(image_path: str) -> str:
    """Encode a local image file to a data URL for OpenAI Responses API.
    Returns empty string on missing file, oversize (>4MB), or unsupported format."""
    try:
        if not image_path or not os.path.exists(image_path):
            return ""
        if os.path.getsize(image_path) > 4 * 1024 * 1024:
            return ""
        ext = os.path.splitext(image_path)[1].lower().lstrip('.')
        if ext == 'jpg':
            ext = 'jpeg'
        if ext not in ('png', 'jpeg', 'webp', 'gif'):
            return ""
        with open(image_path, 'rb') as f:
            b64 = base64.b64encode(f.read()).decode('ascii')
        return f"data:image/{ext};base64,{b64}"
    except Exception:
        return ""


def _build_image_content_blocks(images, max_images: int = 3):
    """Convert a list of image dicts (each with a 'path' key) to OpenAI Responses
    API input_image content blocks. Skips missing/oversize/unsupported.
    Caps at max_images."""
    blocks = []
    for img in (images or [])[:max_images]:
        if not isinstance(img, dict):
            continue
        url = _encode_image_b64(img.get('path', ''))
        if url:
            blocks.append({"type": "input_image", "image_url": url})
    return blocks


_SYSTEM_PROMPT_DATA_FOCUSED = (
    "당신은 데이터 중심 논문 분석 전문가입니다. 수치와 구체적 정보만 추출합니다.\n\n"
    "🔴 절대 금지 (위반 시 실패):\n"
    "❌ '유의미한 결과를 보였다' - 수치 없는 표현\n"
    "❌ '높은 성능을 달성했다' - 구체적 수치 없음\n"
    "❌ '다양한 데이터를 사용했다' - 데이터셋명, n 없음\n"
    "❌ '새로운 방법을 제안했다' - 방법명 없음\n"
    "❌ '임상적 의의가 있다' - 근거 없는 일반화\n\n"
    "✅ 올바른 예시:\n"
    "✓ 'TCGA 데이터셋(n=3,621)을 사용하여'\n"
    "✓ 'XGBoost 모델이 AUC 0.85 (95% CI: 0.82-0.88)를 달성'\n"
    "✓ 'HR 0.52 (p=0.003)로 생존율 향상'\n"
    "✓ '5-fold cross-validation으로 검증'\n\n"
    "📋 필수 추출 항목:\n"
    "- 샘플 수 (n=?)\n"
    "- 모델/알고리즘 이름\n"
    "- 성능 지표 (AUC, accuracy, p-value, HR, OR)\n"
    "- 신뢰구간 (95% CI)\n"
    "- 비교 baseline과의 차이\n\n"
    "논문에 없는 정보: '[명시되지 않음]' 표기"
)


def summarize_text_with_retry(
    text: str,
    prompt: str,
    model: str = None,
    max_tokens: int = 500,
    max_retries: int = 3,
    request_timeout: int = 300,  # 5분으로 증가
    use_cache: bool = True,
    use_optimizer: bool = True,
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

    # 비용 최적화 도구 초기화
    if use_optimizer:
        optimizer = APICostOptimizer()
        
        # 캐시 확인
        if use_cache:
            cached = optimizer.get_cached_response(text, prompt, model or os.getenv("MODEL", "gpt-4o-mini"))
            if cached:
                return cached
    
    # 모델 자동 선택 (최적화 모드)
    if use_optimizer and not model:
        task_type = "keywords" if "키워드" in prompt else "summary"
        model = get_optimized_model_choice(len(text), task_type)
        print(f"📊 Selected model: {model} for {len(text)} chars")
    else:
        model = model or os.getenv("MODEL", "gpt-4o-mini")

    # 클라이언트에 timeout 지정 (요청마다 timeout을 주고 싶다면 with_options 사용)
    client = OpenAI(
        api_key=os.getenv("OPENAI_API_KEY"),
        max_retries=0,           # 수동 재시도 제어
        timeout=request_timeout, # 전체 요청 타임아웃 (기본 5분)
    )

    # 텍스트 최적화 (스마트 트렁케이션)
    if use_optimizer:
        original_length = len(text)
        text = TextOptimizer.smart_truncate(text, max_chars=28000, preserve_sections=True)
        if len(text) < original_length:
            print(f"✂️ Text optimized: {original_length} → {len(text)} chars")
    else:
        # 기존 단순 트렁케이션
        max_input_length = 30000  # ~7.5k 토큰 수준 가정
        if len(text) > max_input_length:
            text = text[:max_input_length] + "... [truncated]"

    messages = [
        {
            "role": "system",
            "content": _SYSTEM_PROMPT_DATA_FOCUSED,
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
                    reasoning={"effort": "medium"},  # 적절한 추론 수준
                )
                # Response에서 텍스트 추출 (null 체크 추가)
                text_parts = []
                if resp.output:
                    for output_item in resp.output:
                        if hasattr(output_item, 'content') and output_item.content:
                            for content_item in output_item.content:
                                if hasattr(content_item, 'text') and content_item.text:
                                    text_parts.append(content_item.text)
                result = ''.join(text_parts).strip()

                # 빈 응답인 경우 재시도 유도
                if not result:
                    raise ValueError("Empty response from GPT-5")

                # 성공 시 캐시 저장 및 비용 로깅
                if use_optimizer:
                    optimizer.save_to_cache(text, prompt, model, result)
                    cost = optimizer.log_api_usage(model, text + prompt, result)
                    print(f"💰 Estimated cost: ${cost:.4f}")

                return result
            else:
                resp = client.chat.completions.create(
                    model=model,
                    messages=messages,
                    max_tokens=max_tokens,
                )
                result = resp.choices[0].message.content.strip()
                
                # 성공 시 캐시 저장 및 비용 로깅
                if use_optimizer:
                    optimizer.save_to_cache(text, prompt, model, result)
                    cost = optimizer.log_api_usage(model, text + prompt, result)
                    print(f"💰 Estimated cost: ${cost:.4f}")
                
                return result

        except RateLimitError as e:
            # 429 → 지수 백오프
            if attempt < max_retries - 1:
                wait = min(5 * (2**attempt), 60)
                print(f"[RateLimit] Waiting {wait}s... ({attempt+1}/{max_retries})")
                time.sleep(wait)
                continue
            raise SummarizationFailed(f"Rate limit exceeded after {max_retries} retries")

        except (APITimeoutError,) as e:
            if attempt < max_retries - 1:
                print(f"[Timeout] Retrying... ({attempt+1}/{max_retries})")
                time.sleep(2)
                continue
            raise SummarizationFailed(f"API timeout after {max_retries} retries")

        except (APIConnectionError,) as e:
            if attempt < max_retries - 1:
                print(f"[Connection] {e} → retry ({attempt+1}/{max_retries})")
                time.sleep(2)
                continue
            raise SummarizationFailed(f"Connection error after {max_retries} retries")

        except (BadRequestError, AuthenticationError) as e:
            # 400/401 범주 → 재시도 무의미
            raise SummarizationFailed(f"Request error: {type(e).__name__}: {e}")

        except (InternalServerError, APIError) as e:
            # 5xx 또는 기타 APIError → 1~2회 재시도 후 중단
            if attempt < max_retries - 1:
                print(f"[Server/APIError] retry ({attempt+1}/{max_retries})")
                time.sleep(2)
                continue
            raise SummarizationFailed(f"API error after {max_retries} retries: {type(e).__name__}")

        except Exception as e:
            if attempt < max_retries - 1:
                print(f"[Unexpected] {e} → retry ({attempt+1}/{max_retries})")
                time.sleep(2)
                continue
            raise SummarizationFailed(f"Unexpected error after {max_retries} retries: {type(e).__name__}: {e}")


def summarize_text_with_images_retry(
    text: str,
    images,
    prompt: str,
    model: str = None,
    max_tokens: int = 500,
    max_retries: int = 3,
    request_timeout: int = 300,
    use_cache: bool = True,
    use_optimizer: bool = True,
    max_images: int = 3,
) -> str:
    """
    Multimodal version of summarize_text_with_retry.
    Always uses Responses API (assumes vision-capable model: gpt-5*, gpt-4o*).
    Sends up to `max_images` images alongside the text.
    """
    if not text or not text.strip():
        return "No text available for summarization."

    # Build image signature for cache differentiation
    img_signature = ":".join(
        (img.get('filename', '') or os.path.basename(img.get('path', '')))
        for img in (images or [])[:max_images]
        if isinstance(img, dict)
    )
    cache_text_key = text + f"\n[IMG:{img_signature}]"

    # 비용 최적화 도구 초기화
    if use_optimizer:
        optimizer = APICostOptimizer()

        # 캐시 확인
        if use_cache:
            cached = optimizer.get_cached_response(
                cache_text_key, prompt, model or os.getenv("MODEL", "gpt-5.5")
            )
            if cached:
                return cached

    # 모델 자동 선택 (최적화 모드)
    if use_optimizer and not model:
        task_type = "keywords" if "키워드" in prompt else "summary"
        model = get_optimized_model_choice(len(text), task_type)
        print(f"📊 Selected model: {model} for {len(text)} chars (multimodal)")
    else:
        model = model or os.getenv("MODEL", "gpt-5.5")

    # 클라이언트에 timeout 지정
    client = OpenAI(
        api_key=os.getenv("OPENAI_API_KEY"),
        max_retries=0,
        timeout=request_timeout,
    )

    # 텍스트 최적화 (멀티모달은 이미지 토큰 여유분 확보를 위해 24000자로 제한)
    if use_optimizer:
        original_length = len(text)
        text = TextOptimizer.smart_truncate(text, max_chars=24000, preserve_sections=True)
        if len(text) < original_length:
            print(f"✂️ Text optimized (multimodal): {original_length} → {len(text)} chars")
    else:
        max_input_length = 24000
        if len(text) > max_input_length:
            text = text[:max_input_length] + "... [truncated]"

    # 이미지 컨텐츠 블록 생성
    image_blocks = _build_image_content_blocks(images, max_images)
    print(f"🖼️ Sending {len(image_blocks)} image(s) to {model}")

    # Responses API용 messages: user content는 input_text + input_image 블록 리스트
    messages = [
        {
            "role": "system",
            "content": _SYSTEM_PROMPT_DATA_FOCUSED,
        },
        {
            "role": "user",
            "content": [
                {"type": "input_text", "text": f"{prompt}\n\n논문 내용:\n{text}"},
                *image_blocks,
            ],
        },
    ]

    for attempt in range(max_retries):
        try:
            resp = client.responses.create(
                model=model,
                input=messages,
                max_output_tokens=max_tokens,
                reasoning={"effort": "medium"},
            )
            text_parts = []
            if resp.output:
                for output_item in resp.output:
                    if hasattr(output_item, 'content') and output_item.content:
                        for content_item in output_item.content:
                            if hasattr(content_item, 'text') and content_item.text:
                                text_parts.append(content_item.text)
            result = ''.join(text_parts).strip()

            if not result:
                raise ValueError("Empty response from GPT-5 (multimodal)")

            if use_optimizer:
                optimizer.save_to_cache(cache_text_key, prompt, model, result)
                cost = optimizer.log_api_usage(model, text + prompt, result)
                print(f"💰 Estimated cost (multimodal): ${cost:.4f}")

            return result

        except RateLimitError as e:
            if attempt < max_retries - 1:
                wait = min(5 * (2**attempt), 60)
                print(f"[RateLimit/MM] Waiting {wait}s... ({attempt+1}/{max_retries})")
                time.sleep(wait)
                continue
            raise SummarizationFailed(f"Rate limit exceeded after {max_retries} retries (multimodal)")

        except (APITimeoutError,) as e:
            if attempt < max_retries - 1:
                print(f"[Timeout/MM] Retrying... ({attempt+1}/{max_retries})")
                time.sleep(2)
                continue
            raise SummarizationFailed(f"API timeout after {max_retries} retries (multimodal)")

        except (APIConnectionError,) as e:
            if attempt < max_retries - 1:
                print(f"[Connection/MM] {e} → retry ({attempt+1}/{max_retries})")
                time.sleep(2)
                continue
            raise SummarizationFailed(f"Connection error after {max_retries} retries (multimodal)")

        except (BadRequestError, AuthenticationError) as e:
            raise SummarizationFailed(f"Request error (multimodal): {type(e).__name__}: {e}")

        except (InternalServerError, APIError) as e:
            if attempt < max_retries - 1:
                print(f"[Server/APIError MM] retry ({attempt+1}/{max_retries})")
                time.sleep(2)
                continue
            raise SummarizationFailed(f"API error after {max_retries} retries (multimodal): {type(e).__name__}")

        except Exception as e:
            if attempt < max_retries - 1:
                print(f"[Unexpected/MM] {e} → retry ({attempt+1}/{max_retries})")
                time.sleep(2)
                continue
            raise SummarizationFailed(f"Unexpected error after {max_retries} retries (multimodal): {type(e).__name__}: {e}")


def summarize_text(text: str, prompt: str, model: str = None, max_tokens: int = 500) -> str:
    """Backward compatibility wrapper."""
    return summarize_text_with_retry(text, prompt, model, max_tokens)


def detect_paper_type(text: str, title: str = None, folder_hint: str = None) -> str:
    """
    논문 유형 감지 (단순화): experimental, review, computational
    - experimental: 실험/임상 연구 (환자, 샘플, 실험 데이터)
    - review: 리뷰/서베이 논문
    - computational: 모델/방법론/알고리즘 제안 (데이터셋 포함)

    folder_hint: 컬렉션 경로 (예: '600.Geninus/610.review'). 폴더에 review/survey가
    명시된 경우 강한 사전 신호로 사용.
    """
    text_lower = text.lower()
    title_lower = (title or "").lower()
    combined = text_lower + " " + title_lower
    hint_lower = (folder_hint or "").lower()

    # 폴더 힌트: /review/ 또는 /survey/ 가 있으면 review 강한 신호 (단, 강제 X)
    folder_review = bool(re.search(r'(^|/)(\d+\.)?(review|survey)(/|$)', hint_lower))

    # 제목 또는 첫 문단의 review 자기 선언 (가장 강한 신호)
    title_review_terms = [
        'a survey', ': a survey', 'a review', ': a review',
        'systematic review', 'meta-analysis', 'meta analysis',
        'literature review', 'narrative review', 'scoping review',
        'umbrella review',
    ]
    strong_title = any(t in title_lower for t in title_review_terms)

    # 제목에서 명확한 computational/prediction 신호 (review override)
    title_comp_terms = [
        'prediction of', 'predicting', 'a predictor', 'predictor for',
        'we propose', 'we present', 'we introduce', 'we develop',
        ': a model', 'a framework for', 'novel method', 'novel approach',
    ]
    title_comp = any(t in title_lower for t in title_comp_terms)

    # 본문에서 self-declaration (저자가 직접 review/survey임을 선언)
    body_review_declarations = [
        'this systematic review', 'we conducted a systematic review',
        'we performed a meta-analysis', 'this meta-analysis',
        'in this review, we', 'in this survey, we', 'this survey aims',
        'this review aims', 'this paper presents a survey',
        'we surveyed', 'this scoping review',
    ]
    body_decl = sum(1 for kw in body_review_declarations if kw in combined)

    # review 판정 우선순위
    # 1. 제목에 명확한 review 자기-선언 → review (가장 신뢰할 수 있는 신호)
    if strong_title:
        return 'review'
    # 2. 본문에서 명확한 self-declaration → review
    if body_decl >= 1 and not title_comp:
        return 'review'
    # 3. 폴더 힌트만으로 결정하지 않음 — 제목/본문이 method를 시사하면 우선
    if folder_review and not title_comp:
        return 'review'

    # 실험/임상 연구 신호
    experimental_signals = [
        'patients', 'participants', 'subjects', 'clinical trial', 'cohort study',
        'case-control', 'randomized', 'prospective', 'retrospective',
        'blood samples', 'tissue samples', 'biopsy', 'enrolled', 'recruited',
        'inclusion criteria', 'exclusion criteria', 'informed consent',
        'we collected', 'we measured', 'we analyzed'
    ]
    experimental_score = sum(1 for kw in experimental_signals if kw in combined)

    # computational 신호 (예측 모델 / 방법론 제안)
    computational_signals = [
        'we propose', 'we present', 'we introduce', 'we develop',
        'we propose a', 'we present a', 'our model', 'our method',
        'we build a', 'we trained', 'we train', 'predictive model',
        'classification model', 'we benchmark', 'foundation model',
    ]
    computational_score = sum(1 for kw in computational_signals if kw in combined)

    # computational 신호가 강하면 우선 (예측 모델 / 신규 방법론)
    if computational_score >= 2:
        return 'computational'

    # 실험 논문 (환자/샘플 수집이 핵심)
    if experimental_score >= 2:
        return 'experimental'

    # 나머지는 computational (모델, 알고리즘, 데이터셋, 방법론)
    return 'computational'


def classify_paper_type_llm(text: str, title: str = None, use_cache: bool = True,
                            folder_hint: str = None) -> str:
    """LLM 기반 논문 유형 분류 (gpt-5-mini, 논문 본문 전체를 읽고 판정).
    Returns one of: 'experimental', 'review', 'computational'.
    Falls back to the detect_paper_type keyword heuristic ONLY on API failure or
    an unparsable response — the LLM reading the full text is the primary path.

    folder_hint: 컬렉션 경로 (예: '600.Geninus/610.review'). 폴더가 review/survey를
    가리키는 경우 LLM 프롬프트에 강한 우선순위로 전달.
    """
    if not text or not text.strip():
        return detect_paper_type(text, title, folder_hint=folder_hint)

    # 폴더 힌트는 LLM 프롬프트에 전달 (강한 편향이지만 최종 결정은 LLM이 내림).
    # 잘못 폴더에 들어간 method/prediction 논문도 내용으로 재판단 가능.
    hint_lower = (folder_hint or "").lower()
    folder_says_review = bool(
        re.search(r'(^|/)(\d+\.)?(review|survey)(/|$)', hint_lower)
    )

    # Let the model read the actual paper, not just the cover page. The
    # review-vs-research signal lives in the abstract, introduction and
    # conclusion — a 1500-char slice was usually just the journal masthead and
    # author list, so reviews whose titles don't say "review" (e.g. "Beyond
    # image alignment: Challenges and emerging solutions ...") were misread as
    # experimental. Send a large span: the informative front plus the tail
    # (conclusions restate the contribution), trimming only very long papers.
    body = text or ""
    if len(body) > 45000:
        sample = body[:33000] + "\n\n[...중략...]\n\n" + body[-12000:]
    else:
        sample = body
    if folder_says_review:
        hint_line = (
            f"Collection folder hint: {folder_hint}\n"
            "↑ This folder is organized for reviews/surveys. STRONG PRIOR toward "
            "'review' — but OVERRIDE to 'computational' if the title says "
            "'Prediction of X', 'Models for X', 'A Predictor', 'We propose/develop X', "
            "or the first section clearly introduces a new model/method/dataset rather "
            "than surveying prior work.\n\n"
        )
    elif folder_hint:
        hint_line = f"Collection folder (organizational hint): {folder_hint}\n\n"
    else:
        hint_line = ""
    user_text = f"{hint_line}Title: {title or '[no title]'}\n\nPaper text:\n{sample}"

    classification_prompt = (
        "Classify this academic paper into ONE category based on its PRIMARY CONTRIBUTION:\n\n"
        "- review: The paper's PRIMARY goal is to systematically survey or synthesize existing "
        "literature. Must satisfy AT LEAST ONE of:\n"
        "    (a) Title contains 'A Survey', 'A Review', 'Systematic Review', 'Meta-analysis', "
        "'Literature Review', 'Scoping Review', 'Umbrella Review'.\n"
        "    (b) Abstract/first section says 'we conducted a systematic review', "
        "'this survey covers', 'we surveyed N papers', 'we performed a meta-analysis'.\n"
        "    (c) The paper's primary deliverable is a taxonomy/comparison of prior methods, "
        "NOT a new model or experimental result.\n"
        "- experimental: The paper's main goal is to report new findings from data collection "
        "involving patients, biological samples, clinical trials, or wet-lab experiments "
        "(e.g., 'we enrolled patients', 'we collected biopsies').\n"
        "- computational: The paper's main goal is to introduce a new model, algorithm, "
        "predictor, dataset, framework, or computational method (e.g., 'we introduce', "
        "'we propose', 'we develop', 'we present a foundation model', 'we build a predictor', "
        "'we trained a classifier').\n\n"
        "CRITICAL TIE-BREAKERS (apply in order):\n"
        "1. If the title contains 'Prediction of X', 'Predicting X', 'A Model for X', "
        "'X classifier', 'X predictor', 'X framework' — classify as 'computational'.\n"
        "2. If the paper says 'we propose/introduce/develop/present/build/train X' where X is "
        "a method, model, algorithm, predictor, or dataset, classify as 'computational' EVEN "
        "IF the paper also says 'we review' or 'overview of'.\n"
        "3. A Related Work / Background / Introduction section that briefly summarizes prior "
        "approaches is NORMAL in original research and does NOT make a paper a review.\n"
        "4. Phrases like 'overview of', 'state of the art', 'comprehensive analysis', "
        "'we provide ... insights' are NOT sufficient evidence for review classification.\n"
        "5. Only classify as 'review' if surveying/synthesizing literature is the paper's "
        "PRIMARY contribution AND there is no new experimental cohort or new model proposed.\n"
        "6. If the 'Collection folder' hint above contains 'review' or 'survey', lean toward "
        "review unless the paper clearly proposes a new method.\n\n"
        "Output ONLY one word: review, experimental, or computational. No other text."
    )

    try:
        result = summarize_text_with_retry(
            user_text, classification_prompt,
            model="gpt-5-mini",
            # GPT-5 reasoning models spend completion tokens on hidden reasoning
            # first; 50 left nothing for the visible answer, so every call came
            # back empty and silently fell through to the keyword heuristic.
            max_tokens=2000,
            max_retries=2,
            use_optimizer=use_cache,
        )
        normalized = (result or "").strip().lower()
        for tag in ('review', 'experimental', 'computational'):
            if tag in normalized:
                return tag
    except SummarizationFailed:
        pass
    except Exception:
        pass

    return detect_paper_type(text, title, folder_hint=folder_hint)


def get_prompts_for_paper_type(paper_type: str, title: str = None):
    """논문 유형별 프롬프트 반환 (3가지 유형: experimental, review, computational)"""

    title_prefix = f"Paper Title: {title}\n\n" if title else ""

    # ============ 실험/임상 연구 (Experimental) ============
    if paper_type == 'experimental':
        short_prompt = (
            "이 실험/임상 연구 논문의 핵심 내용을 8-10문장으로 요약해주세요.\n\n"
            "🔴 반드시 포함할 정보:\n"
            "1️⃣ [연구 목적] 구체적 연구 질문/가설\n"
            "2️⃣ [연구 설계] 연구 유형 (코호트, RCT, case-control 등)\n"
            "3️⃣ [대상] 샘플 크기(n=?), 환자 특성, 포함/제외 기준\n"
            "4️⃣ [방법] 측정/분석 방법, 사용 도구/알고리즘\n"
            "5️⃣ [핵심 결과 1] 주요 발견 + 수치 (p-value, HR, OR, CI 등)\n"
            "6️⃣ [핵심 결과 2] 추가 발견 + 수치\n"
            "7️⃣ [비교] 기존 연구와의 비교 (있다면)\n"
            "8️⃣ [결론] 저자의 핵심 발견과 임상적 의의\n\n"
            "⚠️ 규칙: 모든 수치는 원문 그대로, 모호한 표현 금지"
        )

        long_prompt = (
            "이 실험/임상 연구 논문을 데이터 중심으로 상세 요약해주세요 (A4 1-2페이지 분량).\n\n"
            "## 1. 연구 배경 및 목적\n"
            "- 연구의 배경과 필요성\n"
            "- 해결하려는 구체적 연구 질문/가설\n"
            "- 기존 연구의 한계점\n\n"
            "## 2. 연구 설계 및 대상\n"
            "- 연구 설계 (RCT, 코호트, case-control, cross-sectional 등)\n"
            "- 연구 기간 및 기관\n"
            "- 대상자 수 (n=?) 및 그룹 분류\n"
            "- 포함/제외 기준 (Inclusion/Exclusion criteria)\n"
            "- 환자 특성 (연령, 성별, 질환 단계 등)\n\n"
            "## 3. 연구 방법\n"
            "- 측정 변수 및 측정 방법\n"
            "- 사용한 도구, 기기, 바이오마커\n"
            "- 통계 분석 방법\n"
            "- Primary/Secondary endpoints\n\n"
            "## 4. 핵심 결과 (수치 필수)\n"
            "- 주요 결과 1: [수치 + 통계적 유의성]\n"
            "- 주요 결과 2: [수치 + 통계적 유의성]\n"
            "- 주요 결과 3: [수치 + 통계적 유의성]\n"
            "- Subgroup 분석 결과 (있다면)\n"
            "| 지표 | 결과 | p-value | 95% CI |\n|------|------|---------|--------|\n\n"
            "## 5. 고찰 및 결론\n"
            "- 결과의 해석 및 의미\n"
            "- 기존 연구와의 비교\n"
            "- 임상적 의의\n"
            "- 저자가 명시한 한계점\n\n"
            "⚠️ 모든 수치는 원문 그대로, 영어 의학 용어 유지"
        )

    # ============ 리뷰/서베이 논문 (Review) ============
    elif paper_type == 'review':
        short_prompt = (
            "이 리뷰/서베이 논문의 핵심 내용을 10-12문장으로 요약해주세요.\n\n"
            "🔴 반드시 포함할 정보 (각 문장은 구체적 정보 포함):\n"
            "1️⃣ [리뷰 주제] 무엇에 대한 리뷰인가? (도메인 + 응용 영역)\n"
            "2️⃣ [동기] 왜 지금 이 리뷰가 필요한가? (어떤 문제/공백을 다루는가)\n"
            "3️⃣ [범위·시기] 대상 분야의 연구 시기, 다룬 방법론 카테고리 수\n"
            "4️⃣ [분류 1·대표 방법명] 첫 번째 대분류 — 구체적 방법/모델/도구명 3개 이상 나열\n"
            "5️⃣ [분류 2·대표 방법명] 두 번째 대분류 — 구체적 방법/모델/도구명 3개 이상 나열\n"
            "6️⃣ [분류 3·대표 방법명] 추가 분류 — 구체적 방법/모델/도구명 3개 이상 나열\n"
            "7️⃣ [데이터/벤치마크] 자주 사용된 데이터셋, 벤치마크, 평가 지표\n"
            "8️⃣ [성능 비교] 정량적 비교 결과 (수치/순위/best 방법)\n"
            "9️⃣ [핵심 트렌드] 시간/성능 측면의 주요 진화 패턴\n"
            "🔟 [공백·미해결] 저자가 지적한 핵심 한계와 미해결 문제\n"
            "1️⃣1️⃣ [향후 방향] 저자가 제안한 유망한 연구 방향\n"
            "1️⃣2️⃣ [실무 권장] 사용자/연구자를 위한 실용적 권장 사항 (있다면)\n\n"
            "⚠️ 규칙:\n"
            "- 모든 문장에 구체적 방법/도구/데이터셋 이름 영문 그대로 포함 (예: 'Mamba', 'Llama-3', 'BraTS')\n"
            "- '다양한 방법', '여러 접근', '효과적인' 같은 모호한 표현 금지\n"
            "- 검색 전략/PRISMA/데이터베이스는 본문에 명시된 경우에만 짧게 언급\n"
            "- 리뷰가 아닌 항목 (예: 검색 DB)에 대해 [명시되지 않음] 답변은 짧게 한 줄로만"
        )

        long_prompt = (
            "이 리뷰/서베이 논문을 깊이 있게 요약해주세요 (A4 2-3페이지 분량).\n"
            "본문에 등장한 구체적 방법명/도구명/데이터셋명/수치를 최대한 보존하는 것이 최우선입니다.\n"
            "본문에 명시되지 않은 항목 (검색 DB, PRISMA flow, 포함 논문 수 등)은 한 줄 '[명시되지 않음]'으로만 처리하고, 해당 섹션에 시간 낭비하지 마세요.\n\n"
            "## 1. 리뷰 주제·동기·범위\n"
            "- **다루는 문제 영역**: (도메인 + 구체적 응용)\n"
            "- **저자가 밝힌 동기**: 어떤 공백/한계를 해결하려 하는가\n"
            "- **시간 범위·다룬 방법 수**: 본문 또는 그림에서 추론 가능한 범위\n"
            "- **(선택) 검색 전략**: 명시된 경우만 한 줄로\n\n"
            "## 2. Taxonomy: 저자의 분류 체계\n"
            "본문 또는 그림/표(특히 Figure 1, Table 1)의 분류를 계층적으로 옮겨주세요.\n"
            "각 하위 분류에는 본문에 등장한 대표 방법명을 **최소 3개 이상** 영문 그대로 포함하세요.\n"
            "방법명이 본문에 없는 하위 분류는 한 줄로 '[대표 방법: 본문 미등장]'만 기재하고 넘어가세요.\n"
            "예:\n"
            "### 대분류 1: <이름>\n"
            "- 하위 1-1: <설명> — 대표 방법: <A, B, C>\n"
            "- 하위 1-2: <설명> — 대표 방법: <D, E, F>\n\n"
            "## 3. 핵심 방법론 deep-dive (8개 이상)\n"
            "리뷰에서 가장 비중 있게 다룬 방법/모델/프레임워크 8개 이상을 골라, 다음을 각각 작성:\n"
            "- **<방법명>** (출처/연도)\n"
            "  - 핵심 아이디어: (1-2문장, 본문 문구 기반)\n"
            "  - 입력/출력 또는 입력 데이터: \n"
            "  - 모델 규모·복잡도: 파라미터 수, 레이어 수, 시간복잡도 (본문 명시 시)\n"
            "  - 보고된 강점/약점: (저자가 비교에서 강조한 것)\n"
            "  - 적용 도메인·연구 그룹\n\n"
            "## 4. 데이터셋·벤치마크·평가 지표\n"
            "리뷰에서 반복적으로 등장한 데이터셋과 벤치마크를 정리:\n"
            "| 데이터셋/벤치마크 | 도메인 | 크기·특성 | 사용한 대표 방법 |\n"
            "|------|------|------|------|\n"
            "본문에 등장한 모든 평가 지표 (정확도/AUC/F1/BLEU 등) 나열\n\n"
            "## 5. 정량적 비교 (표 우선)\n"
            "리뷰에 등장한 모든 비교 표/수치를 다음 형태로 옮겨주세요:\n"
            "| 방법 | 데이터셋 | 지표 | 수치 | 출처 |\n"
            "|------|----------|------|------|------|\n"
            "수치가 1개도 없으면 한 줄로 '본문에 정량 비교 미제시'만 적고 다음 섹션으로 넘어가세요.\n\n"
            "## 6. 방법론 진화·트렌드\n"
            "- 시간 축 또는 성능 축에서의 주요 변화 (예: 'CNN→Transformer→FM 전환', '2019년부터 self-supervised 비중 급증')\n"
            "- 현재 SOTA를 차지하는 접근법과 그 이유\n"
            "- 떠오르는 신규 트렌드 (예: agentic 접근, multimodal fusion)\n\n"
            "## 7. 한계 및 미해결 문제\n"
            "- 저자가 명시한 분야 차원의 한계 (데이터, 평가, 일반화)\n"
            "- 방법론별 알려진 실패 케이스\n"
            "- 재현성·표준화 이슈\n\n"
            "## 8. 향후 연구 방향·실무 권장\n"
            "- 저자가 제안한 future directions (구체적 연구 질문)\n"
            "- (있다면) 실무자에게 주는 권장 사항 / 방법 선택 가이드\n\n"
            "⚠️ 절대 규칙:\n"
            "- 모든 방법명/도구명/데이터셋명은 영문 그대로 (예: 'Mamba', 'BraTS-2020', 'UNI')\n"
            "- '효과적인', '강력한', '다양한' 등 일반적 형용사 금지 — 본문 표현을 인용\n"
            "- 표·수치가 본문에 있으면 반드시 옮기기 (실제 숫자 누락 금지)\n"
            "- 명시되지 않은 항목은 짧게 처리하고, 본문 등장 정보로 다른 섹션을 깊게\n"
            "- 본문에 인용된 참고문헌 번호(예: [123])는 가능하면 유지"
        )

    # ============ 컴퓨테이셔널/방법론 논문 (Computational) ============
    # 모델 제안, 알고리즘, 데이터셋, 파이프라인 등
    elif paper_type == 'computational':
        short_prompt = (
            "이 컴퓨테이셔널/방법론 논문의 핵심 내용을 8-10문장으로 요약해주세요.\n\n"
            "🔴 반드시 포함할 정보:\n"
            "1️⃣ [제안 내용] 제안하는 모델/방법/데이터셋의 정확한 이름\n"
            "2️⃣ [문제 정의] 해결하려는 문제\n"
            "3️⃣ [핵심 아이디어] 기존 방법과 다른 핵심 차별점\n"
            "4️⃣ [방법론 1] 주요 기술적 컴포넌트/모듈\n"
            "5️⃣ [방법론 2] 추가 기술적 특징\n"
            "6️⃣ [데이터] 사용한 데이터셋, 규모\n"
            "7️⃣ [성능] 벤치마크 결과 (정확한 수치와 비교 baseline)\n"
            "8️⃣ [기여] 저자가 주장하는 핵심 기여\n\n"
            "⚠️ 규칙: 기술 용어 영어 유지, 성능 수치 필수"
        )

        long_prompt = (
            "이 컴퓨테이셔널/방법론 논문을 기술적으로 상세 요약해주세요 (A4 1-2페이지 분량).\n\n"
            "## 1. 연구 개요\n"
            "- 제안하는 모델/방법/데이터셋 이름\n"
            "- 해결하려는 문제 정의\n"
            "- 기존 방법의 한계와 본 연구의 motivation\n"
            "- 핵심 기여 (contributions) 요약\n\n"
            "## 2. 관련 연구\n"
            "- 기존 주요 방법들과의 비교\n"
            "- 본 연구의 차별점\n\n"
            "## 3. 제안 방법론\n"
            "### 3.1 전체 구조\n"
            "- 전체 파이프라인/아키텍처 개요\n"
            "- 입력/출력 형식\n\n"
            "### 3.2 핵심 컴포넌트\n"
            "- **모듈 A**: 역할, 구조, 수식 (있다면)\n"
            "- **모듈 B**: 역할, 구조, 수식 (있다면)\n"
            "- **모듈 C**: 역할, 구조, 수식 (있다면)\n\n"
            "### 3.3 학습 전략\n"
            "- Loss function\n"
            "- 최적화 방법\n"
            "- 하이퍼파라미터\n\n"
            "## 4. 실험 설정\n"
            "- 데이터셋: 이름, 크기, 특성\n"
            "- 비교 baseline 모델들\n"
            "- 평가 지표\n"
            "- 구현 상세 (GPU, 학습 시간 등)\n\n"
            "## 5. 실험 결과\n"
            "### 주요 결과 테이블\n"
            "| 데이터셋 | 제안 모델 | Baseline 1 | Baseline 2 | 향상 |\n"
            "|----------|-----------|------------|------------|------|\n"
            "\n### Ablation Study\n"
            "- 각 컴포넌트의 기여도 분석\n\n"
            "### 정성적 분석\n"
            "- Case study 또는 시각화 결과\n\n"
            "## 6. 한계점 및 Future Work\n"
            "- 저자가 인정한 한계점\n"
            "- 향후 연구 방향\n\n"
            "⚠️ 기술 용어 영어 유지, 아키텍처 세부사항 포함, 성능 수치 필수"
        )

    else:  # fallback
        short_prompt = (
            "이 논문의 핵심 내용을 8-10문장으로 요약해주세요.\n\n"
            "각 문장은 구체적 정보를 담아야 합니다:\n"
            "- 연구 목적, 방법, 결과, 결론\n"
            "- 가능한 수치와 구체적 이름 포함"
        )
        long_prompt = (
            "이 논문을 상세히 요약해주세요 (A4 1-2페이지 분량).\n\n"
            "## 1. 연구 개요\n## 2. 방법론\n## 3. 핵심 결과\n## 4. 결론 및 시사점\n"
        )

    return title_prefix + short_prompt, title_prefix + long_prompt


def generate_short_long(text: str, title: str = None, use_optimizer: bool = True,
                        folder_hint: str = None, paper_type: str = None):
    """Generate both short and long summaries of the text.

    folder_hint: 컬렉션 경로 — 분류기에 힌트로 전달.
    paper_type: 명시적으로 paper_type을 지정하고 싶을 때 (분류 단계 스킵).
    """
    if not paper_type:
        # 논문 유형 감지 (LLM 기반, 휴리스틱 fallback)
        paper_type = classify_paper_type_llm(text, title, use_cache=use_optimizer,
                                             folder_hint=folder_hint)
    print(f"📄 Detected paper type: {paper_type}")

    # 유형별 프롬프트 가져오기 (title 이미 포함됨)
    short_prompt, long_prompt = get_prompts_for_paper_type(paper_type, title)

    # 모델 선택: 환경변수 우선, 기본값은 gpt-5.2-pro
    model = os.getenv("MODEL", "gpt-5.2-pro")

    # 모든 요약에 동일한 모델 사용 (최신 모델로 품질 향상)
    short_model = model
    long_model = model

    # 토큰 수: 리뷰는 깊이 있는 요약을 위해 추가 헤드룸
    short_tokens = 1200
    long_tokens = 9000 if paper_type == 'review' else 6000

    short = summarize_text_with_retry(text, short_prompt, model=short_model,
                                      max_tokens=short_tokens, use_optimizer=use_optimizer)
    long = summarize_text_with_retry(text, long_prompt, model=long_model,
                                     max_tokens=long_tokens, use_optimizer=use_optimizer)
    return short, long


def generate_short_long_with_images(text: str, images, captions, title: str = None,
                                    use_optimizer: bool = True, folder_hint: str = None,
                                    paper_type: str = None):
    """Multimodal version of generate_short_long: sends up to 3 images to GPT-5.x via Responses API."""
    if not paper_type:
        paper_type = classify_paper_type_llm(text, title, use_cache=use_optimizer,
                                             folder_hint=folder_hint)
    print(f"📄 Detected paper type: {paper_type} (multimodal, {len(images or [])} images)")
    short_prompt, long_prompt = get_prompts_for_paper_type(paper_type, title)

    # Optionally append caption hints to the long prompt (helps when images are abstract diagrams)
    if captions:
        caption_block = "\n\n📷 그림 캡션 (참고):\n" + "\n".join(f"- {c}" for c in captions[:10])
        long_prompt = long_prompt + caption_block

    model = os.getenv("MODEL", "gpt-5.5")
    short_tokens = 1200
    long_tokens = 9000 if paper_type == 'review' else 6000
    short = summarize_text_with_images_retry(
        text, images, short_prompt, model=model, max_tokens=short_tokens, use_optimizer=use_optimizer
    )
    long = summarize_text_with_images_retry(
        text, images, long_prompt, model=model, max_tokens=long_tokens, use_optimizer=use_optimizer
    )
    return short, long


def _section_prompt_texts(title: str = None):
    """The contribution / limitations / ideas / keywords instruction blocks.

    Factored out so both the legacy per-section path (generate_sections) and the
    consolidated single-call path (generate_all*) share one source of truth.
    """
    prefix = f"Paper Title: {title}\n\n" if title else ""

    contribution_prompt = (
        prefix +
        "이 논문의 핵심 기여를 bullet point로 정리 (수치 필수):\n\n"
        "각 기여는 다음 형식으로:\n"
        "• [기여 유형] 구체적 내용 (수치/비교 포함)\n\n"
        "예시:\n"
        "• [방법론] HiTME clustering으로 ccRCC 5개 subtype 정의\n"
        "• [성능] 기존 baseline 대비 AUC 0.78 → 0.85 향상 (+9%)\n"
        "• [데이터] 14개 코호트 통합, 최대 규모 데이터베이스 구축 (n=3,621)\n"
        "• [검증] 독립 코호트 WU-RCC (n=193)에서 외부 검증\n\n"
        "⚠️ 수치 없는 기여는 작성 금지"
    )

    limitations_prompt = (
        prefix +
        "저자가 Limitations/Discussion에서 직접 언급한 한계점만 추출:\n\n"
        "각 한계점은 다음 형식:\n"
        "• [유형] 한계점 내용 - \"원문 인용\"\n\n"
        "예시:\n"
        "• [샘플] 단일 기관 데이터로 일반화 제한 - \"single-center study\"\n"
        "• [검증] 전향적 검증 부재 - \"prospective validation is needed\"\n"
        "• [데이터] 후향적 분석의 한계 - \"retrospective nature of the study\"\n\n"
        "⚠️ 저자가 언급하지 않은 한계점은 추측하지 말 것\n"
        "찾을 수 없으면: '[저자가 명시한 한계점 없음]'"
    )

    ideas_prompt = (
        prefix +
        "저자가 Future Work/Discussion에서 제안한 후속 연구만 추출:\n\n"
        "각 항목은 다음 형식:\n"
        "• [유형] 내용 - \"원문 인용\"\n\n"
        "유형 분류:\n"
        "- [Future Work] 저자가 명시적으로 제안한 후속 연구\n"
        "- [Open Question] 해결되지 않은 질문\n"
        "- [Extension] 확장 가능성\n\n"
        "예시:\n"
        "• [Future Work] 전향적 임상 시험 필요 - \"prospective clinical trials are warranted\"\n"
        "• [Extension] 다른 암종으로 확장 가능 - \"could be extended to other tumor types\"\n\n"
        "⚠️ 저자가 언급하지 않은 아이디어는 추측 금지\n"
        "찾을 수 없으면: '[저자가 제안한 후속 연구 없음]'"
    )

    keywords_prompt = prefix + (
        "논문의 핵심 키워드 10개를 추출하세요.\n\n"
        "규칙 (엄격히 준수):\n"
        "- 각 키워드는 영어 소문자와 하이픈만 사용\n"
        "- 숫자, 괄호, 콜론, 등호 등 특수문자 금지\n"
        "- 각 키워드는 1-4 단어로 구성 (최대 40자)\n"
        "- 쉼표로 구분하여 한 줄로 출력\n\n"
        "올바른 예시:\n"
        "deep-learning, transformer-model, cancer-classification, survival-prediction, tcga-dataset\n\n"
        "잘못된 예시 (금지):\n"
        "❌ sample-size-(n=256) - 괄호와 등호 포함\n"
        "❌ auc:0.85 - 콜론과 숫자 포함\n"
        "❌ TCGA-BRCA - 대문자 사용\n"
        "❌ 딥러닝 - 한글 사용"
    )
    return contribution_prompt, limitations_prompt, ideas_prompt, keywords_prompt


def generate_sections(text: str, title: str = None, use_optimizer: bool = True):
    """Generate contributions, limitations, ideas, keywords (legacy 4-call path).

    Retained as the fallback for generate_all* when the single consolidated call
    can't be parsed. Kept behavior-identical to the original implementation.
    """
    contribution_prompt, limitations_prompt, ideas_prompt, _ = _section_prompt_texts(title)

    # 섹션 추출은 gpt-4o-mini 사용 (비용 절감: contributions/limitations/ideas는 간단한 추출 작업)
    model = "gpt-4o-mini"
    section_tokens = 1500  # 섹션별 요약용
    keyword_tokens = 300   # 키워드용

    contributions = summarize_text_with_retry(text, contribution_prompt, model=model,
                                             max_tokens=section_tokens, use_optimizer=use_optimizer)
    limitations = summarize_text_with_retry(text, limitations_prompt, model=model,
                                           max_tokens=section_tokens, use_optimizer=use_optimizer)
    ideas = summarize_text_with_retry(text, ideas_prompt, model=model,
                                     max_tokens=section_tokens, use_optimizer=use_optimizer)
    keywords = generate_keywords_only(text, keyword_tokens)
    return contributions, limitations, ideas, keywords


def generate_sections_with_images(text: str, images, captions, title: str = None, use_optimizer: bool = True):
    """Multimodal-compatible signature for generate_sections.
    Sections (contributions/limitations/ideas) are text-quote-driven and don't benefit much
    from image input, so this delegates to text-only generate_sections after appending caption
    hints to the text. Keeps cost low (gpt-4o-mini hardcoded inside generate_sections)."""
    if captions:
        text = text + "\n\n📷 [그림 캡션 요약]:\n" + "\n".join(f"- {c}" for c in captions[:10])
    return generate_sections(text, title, use_optimizer)


def _build_combined_prompt(paper_type: str, title: str = None) -> str:
    """Compose ONE prompt that yields short + long summaries, the three analysis
    sections and keywords as a single JSON object. Reuses the exact type-specific
    summary prompts and the shared section prompts so per-type quality is kept."""
    short_prompt, long_prompt = get_prompts_for_paper_type(paper_type, title)
    contrib, limits, ideas, keywords = _section_prompt_texts(title)
    return (
        "당신은 학술 논문을 읽고 아래 6개 필드를 담은 JSON 객체 **하나만** 출력합니다.\n"
        "코드펜스(```), 설명, 그 외 어떤 텍스트도 붙이지 마세요. 유효한 JSON만 출력합니다.\n"
        "JSON 문자열 값 안에서는 줄바꿈을 \\n 으로 이스케이프하고 큰따옴표를 \\\" 로 이스케이프하세요.\n\n"
        "각 필드의 작성 지침은 다음과 같습니다.\n\n"
        "━━━ short_summary (문자열, 마크다운) ━━━\n" + short_prompt + "\n\n"
        "━━━ long_summary (문자열, 마크다운) ━━━\n" + long_prompt + "\n\n"
        "━━━ contributions (문자열, 마크다운 불릿) ━━━\n" + contrib + "\n\n"
        "━━━ limitations (문자열, 마크다운 불릿) ━━━\n" + limits + "\n\n"
        "━━━ ideas (문자열, 마크다운 불릿) ━━━\n" + ideas + "\n\n"
        "━━━ keywords (문자열 10개의 JSON 배열) ━━━\n" + keywords + "\n\n"
        "최종 출력은 정확히 이 형태의 JSON 하나입니다:\n"
        '{"short_summary": "...", "long_summary": "...", "contributions": "...", '
        '"limitations": "...", "ideas": "...", "keywords": ["kw1", "kw2", "..."]}'
    )


def _extract_json_obj(s: str):
    """Best-effort parse of a JSON object out of a model response (tolerates code
    fences and leading/trailing prose). Returns dict or None."""
    if not s:
        return None
    t = s.strip()
    if t.startswith('```'):
        t = re.sub(r'^```[a-zA-Z]*\n?', '', t)
        t = re.sub(r'\n?```$', '', t).strip()
    start, end = t.find('{'), t.rfind('}')
    if start < 0 or end <= start:
        return None
    try:
        return json.loads(t[start:end + 1])
    except Exception:
        return None


def _unpack_combined(data: dict):
    """Turn the parsed JSON into the 6-tuple the pipeline expects."""
    kw = data.get('keywords', [])
    if isinstance(kw, list):
        kw = ", ".join(str(k).strip() for k in kw if str(k).strip())
    return (
        str(data.get('short_summary', '')).strip(),
        str(data.get('long_summary', '')).strip(),
        str(data.get('contributions', '')).strip(),
        str(data.get('limitations', '')).strip(),
        str(data.get('ideas', '')).strip(),
        str(kw or "").strip(),
    )


def generate_all_with_images(text, images, captions, title=None, use_optimizer=True,
                             folder_hint=None, paper_type=None):
    """Consolidated generation: 1 classification call + 1 structured JSON call
    returning (short, long, contributions, limitations, ideas, keywords).

    Cuts the per-paper GPT calls from ~7 (classify + short + long + 3 sections +
    keywords) down to 2. If the single call can't be parsed into usable JSON, it
    falls back to the legacy multi-call path so a note is never left broken."""
    if not paper_type:
        paper_type = classify_paper_type_llm(text, title, use_cache=use_optimizer,
                                             folder_hint=folder_hint)
    print(f"📄 Detected paper type: {paper_type} (consolidated, {len(images or [])} images)")

    prompt = _build_combined_prompt(paper_type, title)
    if captions:
        prompt += "\n\n📷 그림 캡션 (참고):\n" + "\n".join(f"- {c}" for c in captions[:10])

    model = os.getenv("MODEL", "gpt-5.5")
    max_tokens = 14000 if paper_type == 'review' else 11000
    try:
        raw = summarize_text_with_images_retry(text, images, prompt, model=model,
                                               max_tokens=max_tokens, use_optimizer=use_optimizer)
        data = _extract_json_obj(raw)
        if data and data.get('short_summary') and data.get('long_summary'):
            return _unpack_combined(data)
        print("⚠️ Consolidated JSON unusable; falling back to multi-call path")
    except SummarizationFailed:
        print("⚠️ Consolidated call failed; falling back to multi-call path")

    short, long = generate_short_long_with_images(text, images, captions, title,
                                                  use_optimizer=use_optimizer,
                                                  folder_hint=folder_hint, paper_type=paper_type)
    contributions, limitations, ideas, keywords = generate_sections_with_images(
        text, images, captions, title, use_optimizer)
    return short, long, contributions, limitations, ideas, keywords


def generate_all(text, title=None, use_optimizer=True, folder_hint=None, paper_type=None):
    """Text-only consolidated generation (mirrors generate_all_with_images)."""
    if not paper_type:
        paper_type = classify_paper_type_llm(text, title, use_cache=use_optimizer,
                                             folder_hint=folder_hint)
    print(f"📄 Detected paper type: {paper_type} (consolidated)")

    prompt = _build_combined_prompt(paper_type, title)
    model = os.getenv("MODEL", "gpt-5.2-pro")
    max_tokens = 14000 if paper_type == 'review' else 11000
    try:
        raw = summarize_text_with_retry(text, prompt, model=model,
                                        max_tokens=max_tokens, use_optimizer=use_optimizer)
        data = _extract_json_obj(raw)
        if data and data.get('short_summary') and data.get('long_summary'):
            return _unpack_combined(data)
        print("⚠️ Consolidated JSON unusable; falling back to multi-call path")
    except SummarizationFailed:
        print("⚠️ Consolidated call failed; falling back to multi-call path")

    short, long = generate_short_long(text, title, use_optimizer=use_optimizer,
                                      folder_hint=folder_hint, paper_type=paper_type)
    contributions, limitations, ideas, keywords = generate_sections(text, title, use_optimizer)
    return short, long, contributions, limitations, ideas, keywords


def generate_keywords_only(text: str, max_tokens: int = 300) -> str:
    """Generate specific, paper-relevant keywords from academic papers."""
    from openai import OpenAI

    client = OpenAI(
        api_key=os.getenv("OPENAI_API_KEY"),
        timeout=60,
    )

    # Truncate text for keyword extraction
    if len(text) > 10000:
        text = text[:10000]

    messages = [
        {
            "role": "system",
            "content": (
                "You extract SPECIFIC keywords from academic papers for indexing.\n\n"
                "PRIORITIZE (in order):\n"
                "1. Named methods/models (e.g., gigatime, alphafold, bert-base)\n"
                "2. Specific techniques (e.g., cross-modal-translation, multiplex-immunofluorescence)\n"
                "3. Disease/target names (e.g., ccrcc, egfr-mutation, pd-l1)\n"
                "4. Dataset names (e.g., tcga, bindingdb, chembl)\n"
                "5. Specific metrics/concepts (e.g., tumor-microenvironment, survival-analysis)\n\n"
                "AVOID generic terms like: deep-learning, machine-learning, cancer, ai, model, method, analysis\n\n"
                "Rules:\n"
                "- Output ONLY keywords, nothing else\n"
                "- Use lowercase English with hyphens\n"
                "- NO numbers, NO parentheses, NO colons, NO Korean\n"
                "- Separate keywords with commas on a SINGLE line\n"
                "- Output exactly 10 specific keywords"
            ),
        },
        {
            "role": "user",
            "content": f"Extract 10 SPECIFIC keywords (method names, techniques, diseases, datasets) from this paper:\n\n{text[:8000]}",
        },
    ]

    # 키워드 추출은 항상 gpt-4o-mini 사용 (비용 절감: $0.15/M vs $1.75/M)
    model = "gpt-4o-mini"

    try:
        resp = client.chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=0.2,
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        print(f"⚠️ Keyword generation failed: {e}")
        return ""


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
