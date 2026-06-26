#!/bin/bash
# Zotero Auto-Sync LaunchAgent 문제 해결 스크립트

set -e

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Zotero Auto-Sync 문제 해결"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo

# 1. 실행 중인 모든 zotero-sync 서비스 중지
echo "🛑 [1/4] 중복 서비스 중지 중..."

# com.fourmodern.zotero-sync (구버전) 중지
if launchctl list | grep -q "com.fourmodern.zotero-sync"; then
    echo "   중지 중: com.fourmodern.zotero-sync"
    launchctl unload ~/Library/LaunchAgents/com.fourmodern.zotero-sync.plist 2>/dev/null || true
    sleep 1
fi

# com.user.zotero-sync (신버전) 중지
if launchctl list | grep -q "com.user.zotero-sync"; then
    echo "   중지 중: com.user.zotero-sync"
    launchctl unload ~/Library/LaunchAgents/com.user.zotero-sync.plist 2>/dev/null || true
    sleep 1
fi

echo "   ✓ 모든 서비스 중지 완료"
echo

# 2. 구버전 plist 파일 삭제
echo "🗑️  [2/4] 구버전 파일 삭제 중..."
if [ -f ~/Library/LaunchAgents/com.fourmodern.zotero-sync.plist ]; then
    rm -f ~/Library/LaunchAgents/com.fourmodern.zotero-sync.plist
    echo "   ✓ 구버전 plist 삭제: com.fourmodern.zotero-sync.plist"
else
    echo "   ℹ️  구버전 plist 없음"
fi
echo

# 3. 손상된 JSON 파일 정리
echo "🧹 [3/4] 손상된 JSON 파일 정리 중..."
TEMP_JSON="$HOME/literature_batch_scripts/logs/auto_sync/temp_changes.json"
if [ -f "$TEMP_JSON" ]; then
    # JSON 유효성 검사
    if ! python3 -m json.tool "$TEMP_JSON" > /dev/null 2>&1; then
        echo "   ⚠️  손상된 temp_changes.json 발견, 삭제합니다"
        rm -f "$TEMP_JSON"
        echo "   ✓ 손상된 파일 삭제 완료"
    else
        echo "   ✓ temp_changes.json 정상"
    fi
else
    echo "   ℹ️  temp_changes.json 없음 (정상)"
fi
echo

# 4. reinstall_launchd.sh 실행
echo "🔄 [4/4] LaunchAgent 재설치 중..."
cd "$(dirname "$0")"
bash scripts/reinstall_launchd.sh

echo
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ 문제 해결 완료!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo
echo "📋 서비스 상태 확인:"
launchctl list | grep zotero || echo "   ⚠️  아직 실행 전 (30분 후 자동 시작)"
echo
echo "💡 지금 바로 테스트:"
echo "   cd $HOME/literature_batch_scripts"
echo "   /opt/homebrew/anaconda3/envs/zot/bin/python scripts/zotero_auto_sync.py"
echo
