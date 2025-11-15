# 📦 설치 가이드

## 🚀 Quick Install (전체 기능)

```bash
# 1. 기본 패키지 설치
pip install -r requirements.txt

# 2. RAG 시스템 패키지 설치 (선택)
pip install -r requirements_rag.txt
```

## 📋 필수 패키지 (기본 기능)

이미 `requirements.txt`에 포함됨:
- ✅ **pyzotero**: Zotero API 연동
- ✅ **PyMuPDF, pdfplumber**: PDF 텍스트 추출
- ✅ **openai**: GPT 요약
- ✅ **google-generativeai**: Gemini 지원
- ✅ **jinja2**: 템플릿 렌더링
- ✅ **python-dotenv**: 환경변수 관리
- ✅ **tqdm**: 진행 표시

## 🆕 추가 설치 필요 패키지

### 1. RAG 시스템 (벡터 DB)
```bash
# ChromaDB (로컬 벡터 DB)
pip install chromadb

# Pinecone (클라우드 벡터 DB)
pip install pinecone-client

# 임베딩 모델
pip install sentence-transformers
pip install torch  # CPU 버전

# 또는 GPU 사용 시
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118
```

### 2. 데이터 처리
```bash
# 수치 계산 및 ML 유틸리티
pip install numpy scikit-learn
```

## 💻 운영체제별 설치

### macOS (Apple Silicon)
```bash
# PyTorch M1/M2 최적화 버전
pip install torch torchvision torchaudio

# ChromaDB 의존성
pip install chromadb
```

### Windows
```bash
# Visual C++ 재배포 패키지 필요 (PyMuPDF용)
# https://visualstudio.microsoft.com/visual-cpp-build-tools/

pip install -r requirements.txt
pip install -r requirements_rag.txt
```

### Linux
```bash
# 시스템 패키지 (Ubuntu/Debian)
sudo apt-get install python3-dev build-essential

pip install -r requirements.txt
pip install -r requirements_rag.txt
```

## 🔧 기능별 설치

### 최소 설치 (PDF 처리 + GPT 요약만)
```bash
pip install pyzotero PyMuPDF openai python-dotenv jinja2 tqdm
```

### 중간 설치 (+ Gemini 멀티모달)
```bash
pip install -r requirements.txt
```

### 전체 설치 (+ RAG 시스템)
```bash
pip install -r requirements.txt
pip install -r requirements_rag.txt
```

## ⚠️ 일반적인 설치 문제 해결

### 1. ChromaDB 설치 오류
```bash
# sqlite3 버전 문제 시
pip install pysqlite3-binary
```

### 2. PyTorch 설치 오류
```bash
# CPU 전용 버전 설치
pip install torch --index-url https://download.pytorch.org/whl/cpu
```

### 3. Pinecone 설치 오류
```bash
# 최신 버전 강제 설치
pip install --upgrade pinecone-client
```

### 4. sentence-transformers 오류
```bash
# 의존성 개별 설치
pip install transformers huggingface-hub
pip install sentence-transformers
```

## 📊 설치 확인

```bash
# Python 스크립트로 확인
python -c "
import pyzotero
import chromadb
import pinecone
import sentence_transformers
import openai
print('✅ 모든 패키지 정상 설치됨!')
"
```

## 🎯 권장 Python 버전

- **Python 3.8 이상** (3.9 ~ 3.11 권장)
- Python 3.12는 일부 패키지 호환성 문제 가능

## 📝 가상환경 사용 권장

```bash
# venv 생성
python -m venv venv

# 활성화
# macOS/Linux:
source venv/bin/activate
# Windows:
venv\Scripts\activate

# 패키지 설치
pip install -r requirements.txt
pip install -r requirements_rag.txt
```

## 🚨 설치 후 확인

```bash
# 기본 기능 테스트
python scripts/run_literature_batch.py --list-collections

# RAG 시스템 테스트
python scripts/pinecone_test.py

# AI 도구 링크 테스트
python scripts/ai_tool_links.py
```