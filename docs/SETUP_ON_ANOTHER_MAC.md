# 다른 Mac에서 Zotero 자동 동기화 설정하기

이 가이드는 현재 개발 Mac이 아닌 **다른 Mac**에서 자동 동기화를 설정하는 방법입니다.

## 📋 사전 준비

다른 Mac에 다음이 설치되어 있어야 합니다:
- Python 3.8 이상 (Anaconda 또는 시스템 Python)
- Zotero (로컬에 설치 및 동기화 완료)
- Git (선택사항, 코드 전송용)

## 🚀 설정 단계

### 1. 프로젝트 파일 전송

**방법 A: Git 사용 (추천)**
```bash
# 다른 Mac에서
cd ~/Documents  # 또는 원하는 위치
git clone https://github.com/your-repo/literature_batch_scripts.git
cd literature_batch_scripts
```

**방법 B: 직접 복사**
```bash
# 현재 Mac에서 압축
cd /Users/username
tar -czf literature_batch_scripts.tar.gz literature_batch_scripts/

# 다른 Mac으로 복사 (AirDrop, USB, scp 등)
# 다른 Mac에서 압축 해제
cd ~/Documents
tar -xzf literature_batch_scripts.tar.gz
```

**방법 C: 필수 파일만 복사 (최소 구성)**

다음 파일들만 복사:
```
literature_batch_scripts/
├── scripts/
│   ├── zotero_auto_sync.py          # 메인 스크립트
│   ├── sync_checker.py               # 변동 감지
│   ├── sync_executor.py              # 동기화 실행
│   ├── run_literature_batch.py       # 논문 처리
│   ├── zotero_fetch.py               # Zotero API
│   ├── text_extractor.py             # PDF 추출
│   ├── gpt_summarizer.py             # GPT 요약
│   ├── markdown_writer.py            # 마크다운 생성
│   ├── utils.py                      # 유틸리티
│   └── zotero_path_finder.py         # 경로 찾기
├── templates/
│   └── literature_note.md            # 노트 템플릿
├── config/
│   └── com.username.zotero-sync.plist  # launchd 설정
├── .env.example                      # 환경 변수 예시
└── requirements.txt                  # Python 패키지
```

### 2. Python 환경 설정

**방법 A: Anaconda 사용 (추천)**
```bash
# 가상환경 생성
conda create -n zot python=3.11
conda activate zot

# 패키지 설치
cd ~/Documents/literature_batch_scripts
pip install -r requirements.txt
```

**방법 B: 시스템 Python 사용**
```bash
# venv 생성
python3 -m venv ~/zot_env
source ~/zot_env/bin/activate

# 패키지 설치
cd ~/Documents/literature_batch_scripts
pip install -r requirements.txt
```

### 3. 환경 변수 설정

```bash
# .env 파일 생성
cd ~/Documents/literature_batch_scripts
cp .env.example .env

# 편집
nano .env  # 또는 vi, code, etc.
```

**.env 파일 내용 (다른 Mac 환경에 맞게 수정):**
```bash
# Zotero API 설정
ZOTERO_USER_ID=your_user_id
ZOTERO_API_KEY=your_api_key

# 출력 디렉토리 (다른 Mac의 Obsidian vault 경로)
OUTPUT_DIR=/Users/YOUR_USERNAME/Documents/ObsidianVault/LiteratureNotes

# PDF 디렉토리 (보통 자동 감지되지만 필요시 설정)
# PDF_DIR=/Users/YOUR_USERNAME/Zotero/storage

# OpenAI API (GPT 요약용)
OPENAI_API_KEY=your_openai_key
MODEL=gpt-4o-mini

# 요약 엔진 선택 (gpt 또는 gemini)
SUMMARIZER=gpt
```

**경로 확인 방법:**
```bash
# Obsidian vault 위치 확인
# Obsidian 앱 → 설정 → 파일 및 링크 → Vault 경로

# Zotero storage 위치
ls ~/Zotero/storage  # 기본 위치
# 또는 Zotero → 환경설정 → 고급 → 파일 및 폴더 → 데이터 디렉토리 위치
```

### 4. launchd plist 파일 수정

**다른 Mac의 경로에 맞게 수정:**
```bash
cd ~/Documents/literature_batch_scripts
nano config/com.username.zotero-sync.plist
```

**수정할 부분:**

1. **Python 경로** (중요!)
```xml
<key>ProgramArguments</key>
<array>
    <!-- Anaconda 사용 시 -->
    <string>/Users/YOUR_USERNAME/anaconda3/envs/zot/bin/python</string>

    <!-- 또는 venv 사용 시 -->
    <!-- <string>/Users/YOUR_USERNAME/zot_env/bin/python</string> -->

    <!-- 또는 시스템 Python -->
    <!-- <string>/usr/local/bin/python3</string> -->

    <string>/Users/YOUR_USERNAME/Documents/literature_batch_scripts/scripts/zotero_auto_sync.py</string>
</array>
```

2. **작업 디렉토리**
```xml
<key>WorkingDirectory</key>
<string>/Users/YOUR_USERNAME/Documents/literature_batch_scripts</string>
```

3. **로그 파일 경로**
```xml
<key>StandardOutPath</key>
<string>/Users/YOUR_USERNAME/Documents/literature_batch_scripts/logs/auto_sync/launchd_stdout.log</string>

<key>StandardErrorPath</key>
<string>/Users/YOUR_USERNAME/Documents/literature_batch_scripts/logs/auto_sync/launchd_stderr.log</string>
```

4. **PATH 환경 변수** (Python 경로 포함)
```xml
<key>EnvironmentVariables</key>
<dict>
    <key>PATH</key>
    <!-- Anaconda 사용 시 -->
    <string>/Users/YOUR_USERNAME/anaconda3/envs/zot/bin:/usr/local/bin:/usr/bin:/bin</string>

    <!-- venv 사용 시 -->
    <!-- <string>/Users/YOUR_USERNAME/zot_env/bin:/usr/local/bin:/usr/bin:/bin</string> -->
</dict>
```

**Python 경로 찾는 방법:**
```bash
# Anaconda 환경
conda activate zot
which python
# 출력: /Users/YOUR_USERNAME/anaconda3/envs/zot/bin/python

# venv
source ~/zot_env/bin/activate
which python
# 출력: /Users/YOUR_USERNAME/zot_env/bin/python
```

### 5. 로그 디렉토리 생성

```bash
mkdir -p ~/Documents/literature_batch_scripts/logs/auto_sync
mkdir -p ~/Documents/literature_batch_scripts/logs/literature_processing
mkdir -p ~/Documents/literature_batch_scripts/logs/rag_builds
```

### 6. 수동 테스트 (필수!)

launchd 등록 전에 반드시 수동으로 테스트하세요:

```bash
# 가상환경 활성화
conda activate zot  # 또는 source ~/zot_env/bin/activate

# 프로젝트 디렉토리로 이동
cd ~/Documents/literature_batch_scripts

# 스크립트 실행
python scripts/zotero_auto_sync.py
```

**예상 출력:**
```
============================================================
Zotero Auto Sync Started
============================================================
Output directory: /Users/YOUR_USERNAME/Documents/ObsidianVault/LiteratureNotes
Checking for changes...
✅ No changes detected. Everything is in sync!
```

**문제 발생 시:**
- `.env` 파일 경로 확인
- Zotero 동기화 상태 확인
- Python 패키지 설치 확인: `pip list | grep pyzotero`

### 7. launchd 등록

```bash
# plist 파일 복사
cp ~/Documents/literature_batch_scripts/config/com.username.zotero-sync.plist \
   ~/Library/LaunchAgents/

# 권한 설정
chmod 644 ~/Library/LaunchAgents/com.username.zotero-sync.plist

# launchd 등록
launchctl load ~/Library/LaunchAgents/com.username.zotero-sync.plist

# 등록 확인
launchctl list | grep zotero-sync
```

**출력 예시:**
```
-    0    com.username.zotero-sync
```

### 8. 작동 확인

**즉시 실행 (테스트용):**
```bash
launchctl start com.username.zotero-sync
```

**로그 확인:**
```bash
# 실시간 로그 모니터링
tail -f ~/Documents/literature_batch_scripts/logs/auto_sync/sync_*.log

# launchd 표준 출력
tail -f ~/Documents/literature_batch_scripts/logs/auto_sync/launchd_stdout.log

# 에러 로그
tail -f ~/Documents/literature_batch_scripts/logs/auto_sync/launchd_stderr.log
```

## 🔧 트러블슈팅

### 문제 1: "Python not found" 에러

**원인:** plist의 Python 경로가 잘못됨

**해결:**
```bash
# Python 경로 확인
conda activate zot
which python

# plist 수정
nano ~/Library/LaunchAgents/com.username.zotero-sync.plist

# 재등록
launchctl unload ~/Library/LaunchAgents/com.username.zotero-sync.plist
launchctl load ~/Library/LaunchAgents/com.username.zotero-sync.plist
```

### 문제 2: "Missing environment variables" 에러

**원인:** `.env` 파일을 찾지 못함

**해결:**
```bash
# .env 파일 위치 확인
ls -la ~/Documents/literature_batch_scripts/.env

# 경로가 다르면 심볼릭 링크 생성
ln -s /actual/path/to/.env ~/Documents/literature_batch_scripts/.env
```

### 문제 3: "Zotero database not found" 에러

**원인:** Zotero 데이터 디렉토리 경로가 다름

**해결:**
```bash
# Zotero 데이터 디렉토리 찾기
ls ~/Zotero
ls ~/Library/Application\ Support/Zotero

# .env 파일에 명시적으로 설정
echo 'ZOTERO_DATA_DIR=/Users/YOUR_USERNAME/Zotero' >> .env
```

### 문제 4: 수동 실행은 되는데 launchd에서 안 됨

**원인:** 환경 변수 또는 PATH 문제

**해결:**
```bash
# plist에 절대 경로 사용 확인
# 모든 경로를 /Users/YOUR_USERNAME/... 형태로 변경
# ~는 사용하지 말 것!

# EnvironmentVariables 섹션에 필요한 경로 추가
nano ~/Library/LaunchAgents/com.username.zotero-sync.plist
```

## 📱 macOS 알림 설정

1. **시스템 설정** 열기
2. **알림 및 Focus** 클릭
3. **터미널** 또는 **Python** 찾기
4. **알림 허용** 활성화
5. **알림 스타일**: 배너 또는 알림

## 🎛️ 설정 커스터마이징

### 실행 주기 변경

```xml
<!-- 30분마다 (기본) -->
<key>StartInterval</key>
<integer>1800</integer>

<!-- 1시간마다 -->
<key>StartInterval</key>
<integer>3600</integer>

<!-- 특정 시간에만 실행 (예: 매일 오전 9시, 오후 6시) -->
<key>StartCalendarInterval</key>
<array>
    <dict>
        <key>Hour</key>
        <integer>9</integer>
        <key>Minute</key>
        <integer>0</integer>
    </dict>
    <dict>
        <key>Hour</key>
        <integer>18</integer>
        <key>Minute</key>
        <integer>0</integer>
    </dict>
</array>
<!-- StartInterval은 삭제 -->
```

### 부팅 시 자동 시작 비활성화

```xml
<key>RunAtLoad</key>
<false/>
```

## 📊 모니터링

### 상태 확인 스크립트

편리하게 상태를 확인하는 alias 추가:

```bash
# ~/.zshrc 또는 ~/.bashrc에 추가
alias zotero-status='launchctl list | grep zotero-sync'
alias zotero-log='tail -f ~/Documents/literature_batch_scripts/logs/auto_sync/sync_*.log'
alias zotero-stop='launchctl unload ~/Library/LaunchAgents/com.username.zotero-sync.plist'
alias zotero-start='launchctl load ~/Library/LaunchAgents/com.username.zotero-sync.plist'
alias zotero-restart='zotero-stop && zotero-start'

# 적용
source ~/.zshrc
```

사용법:
```bash
zotero-status   # 상태 확인
zotero-log      # 로그 보기
zotero-stop     # 중지
zotero-start    # 시작
zotero-restart  # 재시작
```

## 🔄 업데이트 방법

코드가 업데이트되면:

```bash
# Git 사용 시
cd ~/Documents/literature_batch_scripts
git pull

# 수동 복사 시
# 새 파일 받아서 덮어쓰기

# launchd 재시작
launchctl unload ~/Library/LaunchAgents/com.username.zotero-sync.plist
launchctl load ~/Library/LaunchAgents/com.username.zotero-sync.plist
```

## 💾 백업 권장사항

정기적으로 백업:
- `.env` 파일 (API 키 포함)
- `~/Library/LaunchAgents/com.username.zotero-sync.plist`
- Obsidian vault 전체

Time Machine 또는 iCloud Drive 사용 권장.

## ⚡ 성능 최적화 (다른 Mac용)

### 낮은 사양 Mac인 경우

```xml
<!-- CPU 우선순위 더 낮춤 -->
<key>Nice</key>
<integer>15</integer>

<!-- 실행 주기 늘림 (2시간) -->
<key>StartInterval</key>
<integer>7200</integer>
```

### 고성능 Mac인 경우

```xml
<!-- CPU 우선순위 보통 -->
<key>Nice</key>
<integer>5</integer>

<!-- 실행 주기 줄임 (10분) -->
<key>StartInterval</key>
<integer>600</integer>
```

## 🎯 체크리스트

설정 완료 확인:

- [ ] 프로젝트 파일 복사됨
- [ ] Python 환경 설정됨 (`pip list` 확인)
- [ ] `.env` 파일 수정됨 (API 키, 경로)
- [ ] plist 파일 경로 수정됨 (Python, 디렉토리)
- [ ] 로그 디렉토리 생성됨
- [ ] 수동 실행 테스트 성공
- [ ] launchd 등록 완료
- [ ] 로그에서 정상 작동 확인
- [ ] macOS 알림 작동 확인

모두 체크되면 설정 완료! 🎉
