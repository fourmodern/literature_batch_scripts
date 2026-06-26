#!/bin/bash

echo "📊 멀티모달 RAG 구축 모니터링"
echo "================================="

while true; do
    if ps aux | grep -q "[7]6990"; then
        # 처리된 논문 수 카운트
        PROCESSED=$(grep -c "✅.*저장" logs/full_multimodal_complete.log 2>/dev/null || echo "0")
        TOTAL=711
        PERCENT=$((PROCESSED * 100 / TOTAL))
        
        # 현재 처리 중인 논문
        CURRENT=$(tail -1 logs/full_multimodal_complete.log | grep -o "Starting.*pdf" | cut -d' ' -f3 || echo "대기중...")
        
        # 진행 바 생성
        BAR=""
        for i in $(seq 1 20); do
            if [ $((i * 5)) -le $PERCENT ]; then
                BAR="${BAR}█"
            else
                BAR="${BAR}░"
            fi
        done
        
        clear
        echo "🚀 멀티모달 RAG 구축 진행 상황"
        echo "================================="
        echo ""
        echo "진행률: [$BAR] ${PERCENT}%"
        echo "처리 완료: ${PROCESSED}/${TOTAL} 논문"
        echo ""
        echo "현재 처리 중: ${CURRENT}"
        echo ""
        echo "로그 위치: logs/full_multimodal_complete.log"
        echo "DB 위치: ./real_multimodal_db/"
        echo ""
        echo "종료: Ctrl+C"
        
        sleep 10
    else
        echo "✅ 처리 완료!"
        echo "총 처리: $(grep -c "✅.*저장" logs/full_multimodal_complete.log 2>/dev/null || echo "0") 논문"
        break
    fi
done