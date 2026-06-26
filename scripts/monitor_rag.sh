#!/bin/bash
# RAG 구축 진행 상황 모니터링 스크립트

clear
echo "📊 PDF → RAG 구축 실시간 모니터링"
echo "================================"
echo ""

# PID 확인
PID=$(cat logs/rag_pid.txt 2>/dev/null)

if [ -z "$PID" ]; then
    echo "❌ 실행 중인 프로세스가 없습니다"
    exit 1
fi

# 프로세스 확인
if ! ps -p $PID > /dev/null; then
    echo "✅ 프로세스가 완료되었습니다!"
    echo ""
    echo "로그 마지막 부분:"
    tail -20 logs/rag_build.log
    exit 0
fi

echo "🔄 실행 중... (PID: $PID)"
echo "   Ctrl+C로 모니터링 종료 (백그라운드 작업은 계속됨)"
echo ""

# 실시간 모니터링
while true; do
    # 현재 진행 상황
    LAST_LINE=$(tail -1 logs/rag_build.log 2>/dev/null | grep "추출 진행")
    if [ ! -z "$LAST_LINE" ]; then
        echo -ne "\r$LAST_LINE"
    fi
    
    # 프로세스 종료 확인
    if ! ps -p $PID > /dev/null; then
        echo ""
        echo ""
        echo "✅ 처리 완료!"
        tail -20 logs/rag_build.log
        break
    fi
    
    sleep 2
done