"""
Generate summaries using Google Gemini API with multimodal support.
"""
import os
import time
import base64
from typing import List, Dict, Optional
import google.generativeai as genai
from text_extractor import encode_image_to_base64

def configure_gemini():
    """Configure Gemini API with API key from environment."""
    api_key = os.getenv('GEMINI_API_KEY')
    if not api_key:
        raise ValueError("GEMINI_API_KEY environment variable not set")
    genai.configure(api_key=api_key)

def summarize_text_with_retry(text: str, prompt: str, model: str = None, max_tokens: int = 500, max_retries: int = 3) -> str:
    """Generate summary using Gemini API with retry logic for rate limits and errors."""
    if not text or not text.strip():
        return "No text available for summarization."
    
    model_name = model or os.getenv('GEMINI_MODEL', 'gemini-2.5-pro')
    
    configure_gemini()
    model = genai.GenerativeModel(model_name)
    
    # Truncate text if too long
    max_input_length = 800000  # Gemini 1.5 Pro supports ~1M tokens
    if len(text) > max_input_length:
        text = text[:max_input_length] + "... [truncated]"
    
    full_prompt = f"""당신은 최고 수준의 학술 논문 분석 전문가입니다.

🔴 절대 규칙:
1. 오직 제공된 논문 텍스트에 명시된 내용만 사용하세요
2. 논문에 없는 정보는 추측하거나 만들어내지 마세요
3. 불확실한 경우 반드시 "논문에 명시되지 않음"으로 표기하세요
4. 일반적인 지식이나 배경정보를 추가하지 마세요
5. 논문의 실제 문장과 데이터를 정확히 인용하세요

✅ 작성 원칙:
- 구체적인 수치, 통계, 실험 결과를 정확히 포함
- 저자가 사용한 용어와 표현을 그대로 사용
- 논문의 각 섹션(Introduction, Methods, Results, Discussion)에서 정보 추출
- 한국어로 명확하고 전문적으로 작성
- 학술적 정확성과 객관성 유지

{prompt}

논문 내용:
{text}"""
    
    for attempt in range(max_retries):
        try:
            response = model.generate_content(
                full_prompt,
                generation_config=genai.types.GenerationConfig(
                    max_output_tokens=max_tokens,
                    temperature=0.3,
                )
            )
            
            if response.text:
                return response.text.strip()
            else:
                return "[No response generated]"
        
        except Exception as e:
            if "quota" in str(e).lower() or "rate" in str(e).lower():
                if attempt < max_retries - 1:
                    wait_time = min(2 ** attempt * 5, 60)
                    print(f"Rate limit hit. Waiting {wait_time} seconds before retry...")
                    time.sleep(wait_time)
                else:
                    print(f"Rate limit error after {max_retries} attempts: {e}")
                    return "[Rate limit exceeded - summary unavailable]"
            else:
                if attempt < max_retries - 1:
                    print(f"Error generating summary: {e}. Retrying ({attempt + 1}/{max_retries})...")
                    time.sleep(2)
                else:
                    print(f"Error generating summary after {max_retries} attempts: {e}")
                    return f"[Error generating summary: {type(e).__name__}]"

def summarize_with_images(text: str, images: List[Dict], prompt: str, model: str = None, max_tokens: int = 3000) -> str:
    """Generate summary using text and images with Gemini multimodal capabilities."""
    if not text or not text.strip():
        return "No text available for summarization."
    
    model_name = model or os.getenv('GEMINI_MODEL', 'gemini-1.5-pro')
    
    configure_gemini()
    model = genai.GenerativeModel(model_name)
    
    # Truncate text if too long
    max_input_length = 800000
    if len(text) > max_input_length:
        text = text[:max_input_length] + "... [truncated]"
    
    # Prepare content list with text and images
    content_parts = []
    
    # Add system prompt and text
    full_prompt = f"""당신은 학술 논문을 정확하게 요약하는 전문가입니다. 

중요한 규칙:
1. 제공된 텍스트와 이미지에 명시적으로 보이는 내용만을 요약하세요.
2. 이미지의 그래프, 차트, 표, 다이어그램을 분석하여 핵심 정보를 추출하세요.
3. 이미지에 나타난 수치 데이터, 트렌드, 패턴을 정확히 설명하세요.
4. 텍스트와 이미지 정보를 종합하여 일관성 있게 요약하세요.
5. 추측하거나 일반적인 지식을 추가하지 마세요.
6. 한국어로 명확하고 간결하게 작성하세요.

{prompt}

논문 텍스트:
{text}

아래는 논문에서 추출된 이미지들입니다. 각 이미지를 분석하여 요약에 포함하세요:"""
    
    content_parts.append(full_prompt)
    
    # Add images (limit to 5 images to avoid token limits and safety issues)
    valid_images = 0
    for i, img_info in enumerate(images[:5]):
        try:
            image_path = img_info['path']
            if os.path.exists(image_path):
                # Read and encode image
                with open(image_path, "rb") as f:
                    image_data = f.read()
                
                # Create image part
                image_part = {
                    'mime_type': 'image/png',
                    'data': image_data
                }
                content_parts.append(f"\n\n[이미지 {i+1}: 페이지 {img_info['page']}, {img_info['width']}x{img_info['height']}]")
                content_parts.append(image_part)
                valid_images += 1
        except Exception as e:
            print(f"Failed to load image {img_info.get('filename', 'unknown')}: {e}")
            continue
    
    if valid_images == 0:
        print("No valid images found, falling back to text-only summarization")
        return summarize_text_with_retry(text, prompt, model, max_tokens)
    
    print(f"Generating summary with {valid_images} images...")
    
    try:
        # Configure safety settings to be less restrictive for academic content
        safety_settings = [
            {
                "category": "HARM_CATEGORY_HARASSMENT",
                "threshold": "BLOCK_NONE"
            },
            {
                "category": "HARM_CATEGORY_HATE_SPEECH",
                "threshold": "BLOCK_NONE"
            },
            {
                "category": "HARM_CATEGORY_SEXUALLY_EXPLICIT",
                "threshold": "BLOCK_NONE"
            },
            {
                "category": "HARM_CATEGORY_DANGEROUS_CONTENT",
                "threshold": "BLOCK_NONE"
            }
        ]
        
        response = model.generate_content(
            content_parts,
            generation_config=genai.types.GenerationConfig(
                max_output_tokens=max_tokens,
                temperature=0.3,
            ),
            safety_settings=safety_settings
        )
        
        if response.text:
            return response.text.strip()
        else:
            # Check for safety blocks or other issues
            if hasattr(response, 'candidates') and response.candidates:
                candidate = response.candidates[0]
                if hasattr(candidate, 'finish_reason'):
                    print(f"Response blocked - Finish reason: {candidate.finish_reason}")
                    if hasattr(candidate, 'safety_ratings'):
                        print(f"Safety ratings: {candidate.safety_ratings}")
            return "[No response generated with images - falling back to text only]"
    
    except Exception as e:
        print(f"Multimodal generation failed: {e}")
        if hasattr(e, '__dict__'):
            print(f"Error details: {e.__dict__}")
        print("Falling back to text-only summarization...")
        return summarize_text_with_retry(text, prompt, model, max_tokens)

def generate_short_long_with_images(text: str, images: List[Dict] = None, captions: List[Dict] = None, title: str = None):
    """Generate both short and long summaries with image analysis."""
    
    # Include captions in text if available
    if captions:
        caption_text = "\n\n=== 이미지 및 표 캡션 ===\n"
        for caption in captions:
            caption_text += f"페이지 {caption['page']}: {caption['text']}\n"
        text = text + caption_text
    
    # Short summary prompt
    short_prompt = """이 논문의 핵심 내용을 3-5개의 문장으로 정확하게 요약해주세요.

📋 요약 체크리스트:
□ 연구의 구체적 목적 (Introduction에서 "aim", "objective", "purpose" 찾기)
□ 핵심 방법론 (Methods에서 실험명, 모델명, 데이터셋 찾기)
□ 주요 발견 (Results에서 가장 중요한 수치적 결과 1-2개)
□ 임상적/과학적 의의 (Discussion/Conclusion에서 저자의 주장)

⚠️ 필수 준수사항:
- 논문과 이미지에 직접 명시된 내용만 사용 (페이지나 섹션 참조 가능)
- 구체적 수치 포함 (예: "50% 감소", "p<0.001", "n=100")
- 저자가 사용한 정확한 용어 사용 (약물명, 단백질명, 질병명 등)
- 배경지식이나 일반적 설명 추가 금지
- 찾을 수 없는 정보는 생략 (억지로 채우지 말 것)

형식: 각 문장은 논문의 다른 측면을 다루며, 구체적이고 정보가 풍부해야 함"""
    
    # Long summary prompt
    long_prompt = """이 논문을 깊이 있게 분석하여 상세한 학술 요약을 작성해주세요.

📚 **요약 작성 지침**

**1. 연구 배경 및 필요성** (Introduction 섹션 기반)
□ 해결하려는 구체적 문제 (저자가 제시한 research gap)
□ 기존 연구의 한계 (논문에서 인용한 선행연구와 그 한계점)
□ 이 연구의 필요성 (저자의 rationale)
□ 명확한 연구 목적/가설 ("We hypothesized...", "This study aims..." 문장 찾기)

**2. 연구 설계 및 방법론** (Methods/Materials 섹션 기반)
□ 연구 디자인 (RCT, cohort, case-control, in vitro, in vivo 등)
□ 대상/샘플 (환자수, 세포주, 동물모델 - 구체적 수치 포함)
□ 주요 실험 방법/프로토콜 (사용된 기법명, 장비, 시약)
□ 통계 분석 방법 (사용된 검정법, 유의수준)
□ 중요 파라미터/조건 (농도, 시간, 온도 등)
□ 이미지에 나타난 실험 설계도나 워크플로우

**3. 핵심 연구 결과** (Results 섹션 + Figures/Tables 기반)
□ Primary outcome (주요 결과를 수치와 함께)
□ Secondary outcomes (부가적 발견사항)
□ 통계적 유의성 (p-values, CI, effect size)
□ 예상치 못한 발견 (논문에 명시된 경우)
□ Figure/Table에서 가장 중요한 데이터 2-3개 인용
□ 이미지의 그래프/차트에서 추출한 구체적 수치

**4. 결과의 해석 및 의의** (Discussion 섹션 기반)
□ 저자의 주요 해석 ("Our findings suggest...", "This indicates...")
□ 기존 연구와의 일치/불일치점 (저자가 비교한 내용)
□ 메커니즘 설명 (저자가 제안한 경우)
□ 임상적/과학적 함의 (저자가 주장하는 impact)

**5. 연구의 강점과 한계** (Discussion/Limitations 섹션 기반)
□ 저자가 제시한 연구의 강점
□ 저자가 인정한 한계점 ("limitation", "weakness" 키워드)
□ 향후 연구 방향 ("future studies", "further research" 문장)

⚠️ **절대 준수사항:**
- 각 항목별로 논문에서 해당 내용을 찾을 수 없으면 "[해당 내용 논문에 명시되지 않음]" 표기
- 모든 수치는 정확히 인용 (반올림하거나 변경하지 말 것)
- 저자가 사용한 전문용어 그대로 사용
- 논문 외부의 지식으로 보충하지 말 것
- 각 섹션마다 최소 2-3개의 구체적 정보 포함"""
    
    # Add title context if available
    if title:
        short_prompt = f"Paper Title: {title}\n\n{short_prompt}"
        long_prompt = f"Paper Title: {title}\n\n{long_prompt}"
    
    # Use multimodal if images are available
    if images and len(images) > 0:
        short = summarize_with_images(text, images, short_prompt, max_tokens=400)
        long = summarize_with_images(text, images, long_prompt, max_tokens=3000)
    else:
        short = summarize_text_with_retry(text, short_prompt, max_tokens=400)
        long = summarize_text_with_retry(text, long_prompt, max_tokens=3000)
    
    return short, long

def generate_sections_with_images(text: str, images: List[Dict] = None, captions: List[Dict] = None, title: str = None):
    """Generate specific sections like contributions, limitations, ideas, and keywords with image analysis."""
    
    # Include captions in text if available
    if captions:
        caption_text = "\n\n=== 이미지 및 표 캡션 ===\n"
        for caption in captions:
            caption_text += f"페이지 {caption['page']}: {caption['text']}\n"
        text = text + caption_text
    
    contribution_prompt = """논문에서 저자가 주장하는 핵심 기여도(contributions)를 체계적으로 추출해주세요.

🔍 **찾아야 할 내용:**
1. **명시적 기여도 선언**
   - "Our contributions are...", "We contribute...", "This paper makes the following contributions..."
   - "For the first time...", "Novel...", "We are the first to..."
   - "We demonstrate...", "We show...", "We establish..."

2. **과학적 발견**
   - 새로운 메커니즘, 경로, 관계성
   - 기존 이론의 확장 또는 반박
   - 새로운 바이오마커, 타겟, 치료법
   - 이미지에서 보여주는 혁신적 결과

3. **방법론적 혁신**
   - 새로운 실험 기법, 분석 방법
   - 기존 방법의 개선
   - 새로운 모델, 알고리즘, 프로토콜

4. **임상적/실용적 기여**
   - 진단, 치료, 예후에 대한 새로운 통찰
   - 가이드라인 변경 제안
   - 실제 적용 가능성

📝 **작성 형식:**
• [기여 유형]: 구체적 내용 (논문의 정확한 표현 인용)
• 각 기여도는 bullet point로 구분
• 저자의 원문 표현을 최대한 보존
• 이미지에서 입증된 기여도도 포함

⚠️ 논문에서 명확한 기여도를 찾을 수 없는 경우:
"저자가 명시적으로 기술한 기여도를 찾을 수 없음. Discussion/Conclusion에서도 명확한 contribution statement 부재."""
    
    limitations_prompt = """논문에서 저자가 인정한 연구의 한계점(limitations)을 상세히 분석해주세요.

🔍 **탐색 전략:**
1. **키워드 검색**
   - "limitation", "limited", "constraint", "shortcoming"
   - "weakness", "drawback", "caveat", "challenge"
   - "could not", "unable to", "failed to", "did not"
   - "should be interpreted with caution", "preliminary"

2. **일반적 위치**
   - Discussion 후반부
   - Conclusion 섹션
   - "Study Limitations" 별도 섹션
   - Results 섹션의 해석 주의 문구

3. **한계점 유형**
   □ 샘플 관련 (크기, 대표성, 선택 편향)
   □ 방법론적 한계 (디자인, 측정, 분석)
   □ 시간적/공간적 제약
   □ 일반화 가능성 제한
   □ 데이터 불완전성
   □ 기술적 제약
   □ 이미지 품질이나 해상도 문제

📝 **작성 형식:**
• [한계 유형]: 구체적 내용 (저자의 원문 표현)
• 각 한계점이 결과 해석에 미치는 영향 (저자가 언급한 경우)
• 저자가 제시한 보완 방법 (있는 경우)

⚠️ 찾을 수 없는 경우:
"저자가 명시적으로 언급한 연구 한계점을 Discussion, Conclusion, 또는 별도 Limitations 섹션에서 찾을 수 없음."""
    
    ideas_prompt = """논문에서 저자가 제시한 향후 연구 방향과 미해결 질문들을 체계적으로 정리해주세요.

🔍 **탐색 키워드:**
1. **직접적 제안**
   - "future studies/research/work should..."
   - "it would be interesting/important to..."
   - "further investigation is needed/warranted"
   - "remains to be determined/elucidated/investigated"

2. **미해결 질문**
   - "unclear", "unknown", "not fully understood"
   - "warrants further study", "merits investigation"
   - "open question", "unanswered", "yet to be"

3. **확장 가능성**
   - "could be extended to", "may be applied to"
   - "potential for", "promising avenue"
   - "next step", "logical extension"

📋 **분류 체계:**
**A. 즉시 가능한 연구**
- 현재 기술/방법으로 수행 가능한 연구

**B. 장기적 연구 방향**
- 새로운 기술이나 리소스가 필요한 연구

**C. 임상 적용 연구**
- 번역 연구, 임상시험 제안

**D. 메커니즘 규명**
- 더 깊은 이해가 필요한 부분

📝 **작성 형식:**
• [카테고리]: 구체적 제안 내용 (저자의 원문 인용)
• 각 제안의 근거나 중요성 (저자가 언급한 경우)

⚠️ 찾을 수 없는 경우:
"저자가 명시적으로 제안한 향후 연구 방향이나 미래 과제를 Discussion 또는 Conclusion에서 찾을 수 없음."""
    
    keywords_prompt = """이 논문에서 다른 논문과 연결할 수 있는 핵심 키워드 5-8개를 쉼표로 구분하여 한 줄로 나열하세요.

🎯 **키워드 선택 기준:**
다른 논문에서도 공통으로 사용될 만한 키워드를 선택하세요:

1. **핵심 개념** (2-3개)
   - 질병명: diabetes, cancer, alzheimer
   - 연구분야: immunology, neuroscience, metabolism
   - 핵심기술: crispr, proteomics, single-cell

2. **특정 용어** (2-3개)  
   - 단백질/유전자: p53, tnf, jak2
   - 약물: metformin, aspirin, tofacitinib
   - 경로: nf-kb, mapk, jak-stat

3. **방법론** (1-2개)
   - rna-seq, western-blot, flow-cytometry
   - clinical-trial, meta-analysis, cohort-study

📝 **형식:**
- 영어 소문자
- 하이픈으로 연결 (jak-stat, rna-seq)
- 간단하고 명확한 단어
- **반드시 쉼표로 구분하여 한 줄로 나열**
- 예: machine-learning, deep-neural-networks, computer-vision, image-classification
- 이미지에 나타난 핵심 용어도 고려

⚠️ 주의:
- 너무 구체적인 용어 회피 (예: "jak2-v617f-mutation" → "jak2")
- 일반적 단어 회피 (study, research, analysis)
- 논문 제목의 특수한 문구 회피"""
    
    # Use multimodal if images are available
    if images and len(images) > 0:
        contributions = summarize_with_images(text, images, contribution_prompt, max_tokens=500)
        limitations = summarize_with_images(text, images, limitations_prompt, max_tokens=500)
        ideas = summarize_with_images(text, images, ideas_prompt, max_tokens=500)
        keywords = summarize_with_images(text, images, keywords_prompt, max_tokens=200)
    else:
        contributions = summarize_text_with_retry(text, contribution_prompt, max_tokens=500)
        limitations = summarize_text_with_retry(text, limitations_prompt, max_tokens=500)
        ideas = summarize_text_with_retry(text, ideas_prompt, max_tokens=500)
        keywords = summarize_text_with_retry(text, keywords_prompt, max_tokens=200)
    
    return contributions, limitations, ideas, keywords

# Keep compatibility with existing code
def summarize_text(text: str, prompt: str, model: str = None, max_tokens: int = 500) -> str:
    """Generate summary using Gemini API with custom prompt."""
    return summarize_text_with_retry(text, prompt, model, max_tokens)

def generate_short_long(text: str, title: str = None):
    """Generate both short and long summaries (text-only for backward compatibility)."""
    return generate_short_long_with_images(text, None, None, title)

def generate_sections(text: str, title: str = None):
    """Generate specific sections (text-only for backward compatibility)."""
    return generate_sections_with_images(text, None, None, title)

if __name__ == '__main__':
    import sys
    txt = sys.stdin.read()
    s, l = generate_short_long(txt, "Test Paper")
    print("---SHORT SUMMARY---\n", s)
    print("\n---LONG SUMMARY---\n", l)