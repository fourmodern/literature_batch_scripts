#!/bin/bash
# 모든 진행 상황 모니터링

clear
echo "📊 전체 작업 모니터링"
echo "================================"
echo ""

while true; do
    # RAG 구축 상태
    if ps -p 60570 > /dev/null 2>&1; then
        RAG_STATUS="🔄 진행 중"
        RAG_PROGRESS=$(tail -1 logs/rag_build.log | grep "추출 진행" | tail -1)
        if [ -z "$RAG_PROGRESS" ]; then
            RAG_PROGRESS=$(tail -1 logs/rag_build.log)
        fi
    else
        RAG_STATUS="✅ 완료"
        RAG_PROGRESS="처리 완료"
    fi
    
    # 마크다운 재처리 상태
    if ps -p $(cat logs/reprocess_pid.txt 2>/dev/null) > /dev/null 2>&1; then
        MD_STATUS="🔄 진행 중"
        MD_PROGRESS=$(tail -1 logs/reprocess.log | grep "Processing\|papers" | tail -1)
        if [ -z "$MD_PROGRESS" ]; then
            MD_PROGRESS="시작 중..."
        fi
    else
        MD_STATUS="✅ 완료"
        MD_PROGRESS="처리 완료"
    fi
    
    # 현재 마크다운 파일 수
    OBSIDIAN_DIR="$HOME/ObsidianVault/LiteratureNotes"
    MD_COUNT=$(find "$OBSIDIAN_DIR" -name "*.md" 2>/dev/null | wc -l | tr -d ' ')
    
    # 화면 업데이트
    clear
    echo "📊 전체 작업 모니터링"
    echo "================================"
    echo ""
    echo "1️⃣ RAG 구축 (PDF 원본 텍스트)"
    echo "   상태: $RAG_STATUS"
    echo "   진행: $RAG_PROGRESS"
    echo ""
    echo "2️⃣ 마크다운 재생성 (실패한 논문)"
    echo "   상태: $MD_STATUS"
    echo "   진행: $MD_PROGRESS"
    echo ""
    echo "📄 현재 마크다운 파일: $MD_COUNT개"
    echo "   목표: 869개 중 가능한 최대"
    echo ""
    echo "🔄 5초마다 업데이트 (Ctrl+C로 종료)"
    
    # 모두 완료되면 종료
    if [ "$RAG_STATUS" = "✅ 완료" ] && [ "$MD_STATUS" = "✅ 완료" ]; then
        echo ""
        echo "🎉 모든 작업 완료!"
        break
    fi
    
    sleep 5
done