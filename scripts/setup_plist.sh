#!/bin/bash
# plist 파일을 현재 Mac 환경에 맞게 자동 설정하는 스크립트

set -e  # 에러 발생 시 중단

echo "======================================"
echo "Zotero Sync plist 자동 설정"
echo "======================================"
echo ""

# 현재 스크립트 위치에서 프로젝트 루트 찾기
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PLIST_TEMPLATE="$PROJECT_ROOT/config/com.username.zotero-sync.plist"
PLIST_OUTPUT="$PROJECT_ROOT/config/com.username.zotero-sync.plist.configured"

echo "프로젝트 경로: $PROJECT_ROOT"
echo ""

# 1. Python 경로 찾기
echo "1. Python 경로 확인 중..."

# 현재 활성화된 Python 찾기
PYTHON_PATH=$(which python 2>/dev/null || which python3 2>/dev/null || echo "")

if [ -z "$PYTHON_PATH" ]; then
    echo "❌ Python을 찾을 수 없습니다!"
    echo "   conda activate zot 또는 가상환경을 먼저 활성화하세요."
    exit 1
fi

echo "   ✅ Python 경로: $PYTHON_PATH"
echo ""

# 2. 사용자 이름 확인
echo "2. 사용자 정보 확인 중..."
USERNAME=$(whoami)
USER_HOME="$HOME"
echo "   ✅ 사용자: $USERNAME"
echo "   ✅ 홈 디렉토리: $USER_HOME"
echo ""

# 3. OUTPUT_DIR 확인 (.env 파일에서)
echo "3. Obsidian vault 경로 확인 중..."
if [ -f "$PROJECT_ROOT/.env" ]; then
    OUTPUT_DIR=$(grep "^OUTPUT_DIR=" "$PROJECT_ROOT/.env" | cut -d'=' -f2- | tr -d '"' | tr -d "'")
    if [ -n "$OUTPUT_DIR" ]; then
        # 틸다 확장
        OUTPUT_DIR="${OUTPUT_DIR/#\~/$USER_HOME}"
        echo "   ✅ OUTPUT_DIR: $OUTPUT_DIR"
    else
        echo "   ⚠️  .env 파일에 OUTPUT_DIR이 없습니다."
        OUTPUT_DIR="$USER_HOME/Documents/ObsidianVault/LiteratureNotes"
        echo "   ℹ️  기본값 사용: $OUTPUT_DIR"
    fi
else
    echo "   ⚠️  .env 파일을 찾을 수 없습니다."
    OUTPUT_DIR="$USER_HOME/Documents/ObsidianVault/LiteratureNotes"
    echo "   ℹ️  기본값 사용: $OUTPUT_DIR"
fi
echo ""

# 4. PATH 환경 변수 구성
echo "4. PATH 환경 변수 구성 중..."
PYTHON_BIN_DIR=$(dirname "$PYTHON_PATH")
NEW_PATH="$PYTHON_BIN_DIR:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
echo "   ✅ PATH: $NEW_PATH"
echo ""

# 5. plist 파일 생성
echo "5. plist 파일 생성 중..."

# 템플릿 읽기
if [ ! -f "$PLIST_TEMPLATE" ]; then
    echo "❌ 템플릿 파일을 찾을 수 없습니다: $PLIST_TEMPLATE"
    exit 1
fi

# sed로 교체 (macOS 호환)
sed \
    -e "s|/opt/homebrew/anaconda3/envs/zot/bin/python|$PYTHON_PATH|g" \
    -e "s|/Users/username/literature_batch_scripts|$PROJECT_ROOT|g" \
    -e "s|/opt/homebrew/anaconda3/envs/zot/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin|$NEW_PATH|g" \
    "$PLIST_TEMPLATE" > "$PLIST_OUTPUT"

echo "   ✅ 설정 파일 생성: $PLIST_OUTPUT"
echo ""

# 6. 요약 출력
echo "======================================"
echo "설정 요약"
echo "======================================"
echo "Python 경로:     $PYTHON_PATH"
echo "프로젝트 경로:   $PROJECT_ROOT"
echo "출력 디렉토리:   $OUTPUT_DIR"
echo "로그 디렉토리:   $PROJECT_ROOT/logs/auto_sync"
echo "설정 파일:       $PLIST_OUTPUT"
echo ""

# 7. 다음 단계 안내
echo "======================================"
echo "다음 단계"
echo "======================================"
echo ""
echo "1. 설정 파일 확인:"
echo "   cat $PLIST_OUTPUT"
echo ""
echo "2. LaunchAgents에 복사:"
echo "   cp $PLIST_OUTPUT ~/Library/LaunchAgents/com.username.zotero-sync.plist"
echo ""
echo "3. 권한 설정:"
echo "   chmod 644 ~/Library/LaunchAgents/com.username.zotero-sync.plist"
echo ""
echo "4. launchd 등록:"
echo "   launchctl load ~/Library/LaunchAgents/com.username.zotero-sync.plist"
echo ""
echo "5. 상태 확인:"
echo "   launchctl list | grep zotero-sync"
echo ""

# 8. 자동 설치 옵션
echo "자동으로 설치하시겠습니까? (y/N): "
read -r response
if [[ "$response" =~ ^[Yy]$ ]]; then
    echo ""
    echo "자동 설치 시작..."

    # 로그 디렉토리 생성
    mkdir -p "$PROJECT_ROOT/logs/auto_sync"
    echo "✅ 로그 디렉토리 생성"

    # plist 복사
    cp "$PLIST_OUTPUT" ~/Library/LaunchAgents/com.username.zotero-sync.plist
    echo "✅ plist 파일 복사"

    # 권한 설정
    chmod 644 ~/Library/LaunchAgents/com.username.zotero-sync.plist
    echo "✅ 권한 설정"

    # 기존 등록 해제 (있을 경우)
    launchctl unload ~/Library/LaunchAgents/com.username.zotero-sync.plist 2>/dev/null || true

    # launchd 등록
    launchctl load ~/Library/LaunchAgents/com.username.zotero-sync.plist
    echo "✅ launchd 등록"

    # 상태 확인
    echo ""
    echo "등록 상태:"
    launchctl list | grep zotero-sync || echo "❌ 등록되지 않음"

    echo ""
    echo "✅ 설치 완료!"
    echo ""
    echo "테스트 실행:"
    echo "   launchctl start com.username.zotero-sync"
    echo ""
    echo "로그 확인:"
    echo "   tail -f $PROJECT_ROOT/logs/auto_sync/sync_*.log"
else
    echo ""
    echo "수동 설치를 선택하셨습니다."
    echo "위의 '다음 단계'를 참고하세요."
fi

echo ""
echo "======================================"
echo "완료!"
echo "======================================"
