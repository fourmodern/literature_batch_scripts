"""
누락된 논문들을 처리하여 마크다운 생성

sync_checker.py의 결과를 읽어서 added 항목들만 처리합니다.
"""

import os
import sys
import json
import argparse
from pathlib import Path
from dotenv import load_dotenv

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load environment
load_dotenv()

from scripts.zotero_fetch import fetch_zotero_items
from scripts.run_literature_batch import process_item, setup_logger
from scripts.zotero_path_finder import get_default_pdf_dir


def main():
    parser = argparse.ArgumentParser(
        description='누락된 논문들을 처리하여 마크다운 생성'
    )
    parser.add_argument(
        '--from-json',
        required=True,
        help='sync_checker.py의 JSON 출력 파일'
    )
    parser.add_argument(
        '--skip-gpt',
        action='store_true',
        help='GPT 요약 건너뛰기 (메타데이터만)'
    )
    parser.add_argument(
        '--limit',
        type=int,
        help='처리할 최대 논문 수'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='실제로 파일 생성하지 않고 미리보기만'
    )

    args = parser.parse_args()

    # Load sync report
    print(f"📂 JSON 파일 읽는 중: {args.from_json}")
    with open(args.from_json, 'r', encoding='utf-8') as f:
        sync_data = json.load(f)

    added_items = sync_data.get('added', [])
    print(f"✓ 누락된 논문: {len(added_items)}개")

    if not added_items:
        print("✅ 모든 논문이 동기화되어 있습니다!")
        return

    # Get keys
    added_keys = [item['key'] for item in added_items]

    if args.limit:
        added_keys = added_keys[:args.limit]
        print(f"⚠️  {args.limit}개만 처리합니다")

    # Environment setup
    output_dir = os.getenv('OUTPUT_DIR')
    pdf_base_dir = get_default_pdf_dir()

    if not output_dir:
        print("❌ OUTPUT_DIR 환경 변수가 설정되지 않았습니다.")
        sys.exit(1)

    os.makedirs(output_dir, exist_ok=True)
    os.makedirs('logs', exist_ok=True)

    log = setup_logger('missing_papers', './logs/missing_papers.log')
    log.info(f"Processing {len(added_keys)} missing papers")

    # Fetch all items from Zotero
    print("\n🔍 Zotero에서 전체 데이터 가져오는 중...")
    all_items, zot = fetch_zotero_items(
        os.getenv('ZOTERO_USER_ID'),
        os.getenv('ZOTERO_API_KEY'),
        return_zot_instance=True
    )
    print(f"✓ {len(all_items)}개 항목 가져옴")

    # Filter to only added items
    items_to_process = [item for item in all_items if item['key'] in added_keys]
    print(f"✓ 처리 대상: {len(items_to_process)}개")

    if not items_to_process:
        print("❌ 처리할 논문을 찾을 수 없습니다.")
        return

    # Create args object for process_item
    class ProcessArgs:
        def __init__(self):
            self.skip_gpt = args.skip_gpt
            self.dry_run = args.dry_run
            self.copy_pdfs = False
            self.no_pdf_download = False

    process_args = ProcessArgs()

    # Process each item
    print(f"\n🚀 논문 처리 시작...\n")
    print("="*80)

    success_count = 0
    error_count = 0

    for i, item in enumerate(items_to_process, 1):
        key = item['key']
        title = item['title']

        print(f"\n[{i}/{len(items_to_process)}] {title[:60]}...")
        print(f"  Key: {key}")
        print(f"  Collection: {item.get('collection_path', 'Uncategorized')}")

        try:
            result = process_item(
                item,
                process_args,
                log,
                output_dir,
                pdf_base_dir,
                zot
            )

            if result:
                success_count += 1
                print(f"  ✅ 완료")
            else:
                error_count += 1
                print(f"  ❌ 실패")

        except Exception as e:
            error_count += 1
            print(f"  ❌ 오류: {e}")
            log.error(f"Error processing {key}: {e}")

    # Summary
    print("\n" + "="*80)
    print("📊 처리 완료!")
    print("="*80)
    print(f"  • 성공: {success_count}개")
    print(f"  • 실패: {error_count}개")
    print(f"  • 출력 디렉토리: {output_dir}")
    print(f"  • 로그: ./logs/missing_papers.log")
    print("="*80)

    if args.dry_run:
        print("\n⚠️  DRY RUN 모드였습니다. 파일이 생성되지 않았습니다.")


if __name__ == '__main__':
    main()
