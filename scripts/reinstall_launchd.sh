#!/bin/bash
# Zotero Auto-Sync LaunchAgent 재설치 스크립트
# 기존 launchd 제거 후 새로 설치

set -e  # 에러 발생 시 즉시 중단

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
PLIST_NAME="com.user.zotero-sync.plist"
LAUNCHD_DIR="$HOME/Library/LaunchAgents"
LAUNCHD_PLIST="$LAUNCHD_DIR/$PLIST_NAME"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Zotero Auto-Sync LaunchAgent 재설치"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo

# 1. 기존 launchd 확인 및 제거
echo "📋 [1/5] 기존 LaunchAgent 확인 중..."
if [ -f "$LAUNCHD_PLIST" ]; then
    echo "   ✓ 기존 plist 파일 발견: $LAUNCHD_PLIST"

    # 실행 중인지 확인
    if launchctl list | grep -q "com.user.zotero-sync\|com.fourmodern.zotero-sync"; then
        echo "   ⚠️  실행 중인 서비스 중지 중..."
        launchctl unload "$LAUNCHD_PLIST" 2>/dev/null || true

        # fourmodern 이름의 구버전도 확인
        OLD_PLIST="$LAUNCHD_DIR/com.fourmodern.zotero-sync.plist"
        if [ -f "$OLD_PLIST" ]; then
            echo "   ⚠️  구버전 plist 중지 중..."
            launchctl unload "$OLD_PLIST" 2>/dev/null || true
            rm -f "$OLD_PLIST"
            echo "   ✓ 구버전 plist 삭제 완료"
        fi

        sleep 2
        echo "   ✓ 서비스 중지 완료"
    else
        echo "   ℹ️  실행 중인 서비스 없음"
    fi

    # 기존 plist 파일 삭제
    rm -f "$LAUNCHD_PLIST"
    echo "   ✓ 기존 plist 파일 삭제 완료"
else
    echo "   ℹ️  기존 LaunchAgent 없음 (새로 설치)"
fi
echo

# 2. Python 경로 자동 감지
echo "🐍 [2/5] Python 환경 감지 중..."
PYTHON_PATH=""

# Conda 환경 확인 (zot)
if command -v conda &> /dev/null; then
    CONDA_ZOT="/opt/homebrew/anaconda3/envs/zot/bin/python"
    if [ -f "$CONDA_ZOT" ]; then
        PYTHON_PATH="$CONDA_ZOT"
        echo "   ✓ Conda 환경 발견: zot"
    fi
fi

# Conda 없으면 시스템 Python 사용
if [ -z "$PYTHON_PATH" ]; then
    if command -v python3 &> /dev/null; then
        PYTHON_PATH="$(which python3)"
        echo "   ✓ 시스템 Python 사용"
    else
        echo "   ❌ Python을 찾을 수 없습니다!"
        exit 1
    fi
fi

echo "   Python 경로: $PYTHON_PATH"
echo

# 3. 로그 디렉토리 생성
echo "📁 [3/5] 로그 디렉토리 생성 중..."
LOG_DIR="$PROJECT_ROOT/logs/auto_sync"
mkdir -p "$LOG_DIR"
echo "   ✓ 로그 디렉토리: $LOG_DIR"
echo

# 4. 새 plist 파일 생성
echo "📝 [4/5] 새 LaunchAgent 설정 파일 생성 중..."

# LaunchAgents 디렉토리 생성
mkdir -p "$LAUNCHD_DIR"

# plist 파일 작성
cat > "$LAUNCHD_PLIST" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <!-- 서비스 식별자 -->
    <key>Label</key>
    <string>com.user.zotero-sync</string>

    <!-- 실행할 프로그램 -->
    <key>ProgramArguments</key>
    <array>
        <string>$PYTHON_PATH</string>
        <string>$PROJECT_ROOT/scripts/zotero_auto_sync.py</string>
    </array>

    <!-- 작업 디렉토리 -->
    <key>WorkingDirectory</key>
    <string>$PROJECT_ROOT</string>

    <!-- 환경 변수 -->
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>$(dirname $PYTHON_PATH):/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
    </dict>

    <!-- 실행 스케줄: 30분마다 (1800초) -->
    <key>StartInterval</key>
    <integer>1800</integer>

    <!-- 부팅 시 자동 시작 -->
    <key>RunAtLoad</key>
    <true/>

    <!-- 종료 시 자동 재시작 안 함 -->
    <key>KeepAlive</key>
    <false/>

    <!-- 표준 출력 로그 -->
    <key>StandardOutPath</key>
    <string>$LOG_DIR/launchd_stdout.log</string>

    <!-- 표준 에러 로그 -->
    <key>StandardErrorPath</key>
    <string>$LOG_DIR/launchd_stderr.log</string>

    <!-- 낮은 우선순위 (CPU 점유 최소화) -->
    <key>Nice</key>
    <integer>10</integer>

    <!-- 유저 에이전트 (백그라운드에서 실행) -->
    <key>ProcessType</key>
    <string>Background</string>
</dict>
</plist>
EOF

chmod 644 "$LAUNCHD_PLIST"
echo "   ✓ 설정 파일 생성: $LAUNCHD_PLIST"
echo

# 5. LaunchAgent 로드 및 시작
echo "🚀 [5/5] LaunchAgent 로드 및 시작 중..."
launchctl load "$LAUNCHD_PLIST"
sleep 2

# 실행 확인
if launchctl list | grep -q "com.user.zotero-sync"; then
    PID=$(launchctl list | grep "com.user.zotero-sync" | awk '{print $1}')
    echo "   ✓ LaunchAgent 로드 완료!"
    echo "   ✓ PID: $PID"
else
    echo "   ⚠️  LaunchAgent가 로드되었지만 아직 실행 전입니다."
    echo "   ℹ️  30분 후 첫 실행이 시작됩니다."
fi
echo

# 완료 메시지
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ LaunchAgent 재설치 완료!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo
echo "📌 설정 정보:"
echo "   • 서비스 이름: com.user.zotero-sync"
echo "   • 실행 주기: 30분마다"
echo "   • Python: $PYTHON_PATH"
echo "   • 스크립트: $PROJECT_ROOT/scripts/zotero_auto_sync.py"
echo "   • 로그: $LOG_DIR/"
echo
echo "📋 유용한 명령어:"
echo "   • 상태 확인: launchctl list | grep zotero-sync"
echo "   • 수동 실행: python $PROJECT_ROOT/scripts/zotero_auto_sync.py"
echo "   • 로그 확인: tail -f $LOG_DIR/sync_\$(date +%Y%m%d).log"
echo "   • 서비스 중지: launchctl unload $LAUNCHD_PLIST"
echo "   • 서비스 시작: launchctl load $LAUNCHD_PLIST"
echo
echo "💡 팁: 지금 바로 테스트하려면 다음 명령어를 실행하세요:"
echo "   python $PROJECT_ROOT/scripts/zotero_auto_sync.py"
echo
