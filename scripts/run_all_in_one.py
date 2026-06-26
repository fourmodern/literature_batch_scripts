#!/usr/bin/env python3
"""
All-in-One Literature Processing + RAG Builder
논문 처리와 RAG 구축을 한 번에 실행
"""

import os
import sys
import argparse
from pathlib import Path
from dotenv import load_dotenv

# 환경변수 로드
load_dotenv()

def main():
    parser = argparse.ArgumentParser(
        description='논문 처리 + RAG 구축 통합 실행'
    )
    parser.add_argument('--collection', type=str, help='특정 컬렉션만 처리')
    parser.add_argument('--limit', type=int, help='처리할 논문 수 제한')
    parser.add_argument('--skip-gpt', action='store_true', 
                       help='GPT 요약 건너뛰기 (빠른 처리)')
    parser.add_argument('--skip-rag', action='store_true',
                       help='RAG 구축 건너뛰기')
    parser.add_argument('--rag-only', action='store_true',
                       help='RAG 구축만 실행')
    parser.add_argument('--workers', type=int, default=5,
                       help='병렬 처리 워커 수')
    
    args = parser.parse_args()
    
    print("="*60)
    print("🚀 All-in-One Literature Processing")
    print("="*60)
    
    # Step 1: 논문 처리 및 요약
    if not args.rag_only:
        print("\n📚 Step 1: 논문 처리 및 요약 생성")
        print("-"*40)
        
        from run_literature_batch import main as run_batch
        
        # 기존 argv 백업
        original_argv = sys.argv
        
        # 새 argv 구성
        sys.argv = ['run_literature_batch.py']
        if args.collection:
            sys.argv.extend(['--collection', args.collection])
        if args.limit:
            sys.argv.extend(['--limit', str(args.limit)])
        if args.skip_gpt:
            sys.argv.append('--skip-gpt')
        sys.argv.extend(['--workers', str(args.workers)])
        
        try:
            # 논문 처리 실행
            run_batch()
            print("\n✅ 논문 처리 완료!")
        except Exception as e:
            print(f"\n❌ 논문 처리 실패: {e}")
            sys.argv = original_argv
            return
        
        # argv 복원
        sys.argv = original_argv
    
    # Step 2: RAG 구축
    if not args.skip_rag:
        print("\n🔨 Step 2: RAG 시스템 구축")
        print("-"*40)
        
        # 논문 수 확인
        from zotero_fetch import fetch_zotero_items
        
        # Zotero 인증 정보
        user_id = os.getenv('ZOTERO_USER_ID')
        api_key = os.getenv('ZOTERO_API_KEY')
        
        papers = fetch_zotero_items(
            user_id=user_id,
            api_key=api_key,
            limit=args.limit,
            collection_filter=args.collection,
            return_zot_instance=False
        )
        
        num_papers = len(papers)
        print(f"논문 수: {num_papers}개")
        
        # 1000개 이하면 simple_dual_builder 사용
        if num_papers <= 1000:
            print("→ Simple Dual Builder 사용 (전체 저장)")
            
            from simple_dual_builder import SimpleDualBuilder
            from zotero_path_finder import get_default_pdf_dir
            
            pdf_base_dir = get_default_pdf_dir()
            builder = SimpleDualBuilder()
            
            # 용량 체크
            capacity = builder.check_capacity(num_papers)
            if capacity['fits']:
                print(f"  Pinecone 예상 사용량: {capacity['usage_after_percent']:.1f}%")
                stats = builder.batch_process(papers, pdf_base_dir)
                builder.print_statistics()
            else:
                print("⚠️ Pinecone 용량 부족, ChromaDB만 사용")
                # ChromaDB만 사용하도록 fallback
                builder.pinecone_builder = None
                stats = builder.batch_process(papers, pdf_base_dir)
                builder.print_statistics()
        
        else:
            # 1000개 초과면 smart_rag_builder 사용
            print("→ Smart RAG Builder 사용 (중요도 기반)")
            
            from smart_rag_builder import SmartRAGBuilder
            from zotero_path_finder import get_default_pdf_dir
            
            pdf_base_dir = get_default_pdf_dir()
            builder = SmartRAGBuilder(pinecone_threshold=60)
            
            # Dry run으로 먼저 확인
            print("\n📊 처리 계획 분석 중...")
            builder.batch_process_with_importance(papers, pdf_base_dir, dry_run=True)
            
            response = input("\n계속하시겠습니까? (y/n): ")
            if response.lower() == 'y':
                builder.batch_process_with_importance(papers, pdf_base_dir)
                builder.print_statistics()
        
        print("\n✅ RAG 구축 완료!")
    
    # Step 3: 최종 통계
    print("\n" + "="*60)
    print("📊 최종 요약")
    print("="*60)
    
    # Obsidian 노트 수 확인
    output_dir = os.getenv('OUTPUT_DIR', './ObsidianVault/LiteratureNotes/')
    if os.path.exists(output_dir):
        md_files = list(Path(output_dir).rglob("*.md"))
        print(f"✅ Obsidian 노트: {len(md_files)}개")
    
    # RAG 통계
    if not args.skip_rag:
        try:
            from pinecone_optimizer import PineconeOptimizer
            optimizer = PineconeOptimizer()
            usage = optimizer.get_usage_stats()
            print(f"✅ Pinecone 벡터: {usage['total_vectors']:,}개 ({usage['usage_percent']:.1f}%)")
        except:
            pass
        
        try:
            # ChromaDB 파일 확인
            chroma_path = Path("./vector_db/chroma")
            if chroma_path.exists():
                print(f"✅ ChromaDB: 활성")
        except:
            pass
    
    print("\n🎉 모든 작업 완료!")
    print("\n다음 명령으로 사용 가능:")
    print("  - 질의응답: python scripts/rag_query.py --interactive")
    print("  - 통계 확인: python scripts/pinecone_optimizer.py --report")


if __name__ == "__main__":
    main()