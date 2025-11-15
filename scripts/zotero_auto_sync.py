#!/usr/bin/env python3
"""
Zotero-Obsidian 자동 동기화 스크립트

변동사항을 감지하고 자동으로 처리:
- 추가된 논문 → run_literature_batch.py 실행
- 삭제/이동된 논문 → sync_executor.py 실행
"""

import os
import sys
import json
import subprocess
import logging
from datetime import datetime
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
from scripts.sync_checker import compare_zotero_obsidian

# Load environment
env_path = Path(__file__).parent.parent / '.env'
load_dotenv(env_path)

# Setup logging
LOG_DIR = Path(__file__).parent.parent / 'logs' / 'auto_sync'
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / f'sync_{datetime.now():%Y%m%d}.log'

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def send_macos_notification(title, message, sound=True):
    """macOS 알림 전송"""
    try:
        # 메시지에서 특수 문자 이스케이프
        title = title.replace('"', '\\"').replace('\\', '\\\\')
        message = message.replace('"', '\\"').replace('\\', '\\\\')

        # osascript 명령 구성
        if sound:
            script = f'display notification "{message}" with title "{title}" sound name "default"'
        else:
            script = f'display notification "{message}" with title "{title}"'

        result = subprocess.run(
            ['osascript', '-e', script],
            capture_output=True,
            text=True,
            check=False
        )

        if result.returncode != 0 and result.stderr:
            logger.debug(f"Notification warning: {result.stderr}")

    except Exception as e:
        logger.warning(f"Failed to send notification: {e}")

def process_changes(changes):
    """변동사항 처리"""
    stats = {
        'added': 0,
        'deleted': 0,
        'moved': 0,
        'errors': []
    }

    # 1. 먼저 삭제/이동된 논문 처리 (added 처리 전에!)
    # 이유: added가 새 파일을 생성하기 때문에, 먼저 정리해야 충돌 안 남
    if changes['deleted'] or changes['moved']:
        logger.info(f"Processing {len(changes['deleted'])} deleted, {len(changes['moved'])} moved papers...")

        try:
            # 임시 JSON 파일로 변동사항 저장
            temp_json = LOG_DIR / 'temp_changes.json'
            with open(temp_json, 'w', encoding='utf-8') as f:
                json.dump(changes, f, indent=2, ensure_ascii=False)

            # sync_executor.py 실행
            cmd = [
                sys.executable,
                str(Path(__file__).parent / 'sync_executor.py'),
                '--from-json', str(temp_json),
                '--no-backup'  # 빈번한 실행이므로 백업 생략
            ]

            logger.info(f"Running: {' '.join(cmd)}")
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

            if result.returncode == 0:
                stats['deleted'] = len(changes['deleted'])
                stats['moved'] = len(changes['moved'])
                logger.info(f"✅ Successfully synced deleted/moved papers")
            else:
                stats['errors'].append(f"Sync executor failed: {result.stderr}")
                logger.error(f"❌ Sync executor failed: {result.stderr}")

            # 임시 파일 삭제
            temp_json.unlink(missing_ok=True)

        except subprocess.TimeoutExpired:
            stats['errors'].append("Sync executor timeout (>5 min)")
            logger.error(f"❌ Sync executor timeout")
        except Exception as e:
            stats['errors'].append(f"Sync executor error: {str(e)}")
            logger.error(f"❌ Error processing deleted/moved papers: {e}")

    # 2. 추가된 논문 처리 (삭제/이동 처리 후!)
    if changes['added']:
        logger.info(f"Processing {len(changes['added'])} added papers...")
        added_keys = [item['key'] for item in changes['added']]

        try:
            # run_literature_batch.py 실행
            cmd = [
                sys.executable,
                str(Path(__file__).parent / 'run_literature_batch.py'),
                '--resume',  # 기존 완료 항목 건너뛰기
            ]

            # 타임아웃 계산: 논문당 5분 + 기본 10분 (최소 30분, 최대 4시간)
            timeout_minutes = min(max(len(added_keys) * 5 + 10, 30), 240)
            logger.info(f"Running: {' '.join(cmd)}")
            logger.info(f"⏱️  Timeout: {timeout_minutes} minutes for {len(added_keys)} papers")

            # 로그 파일로 출력 리다이렉트 (실시간 진행 상황 확인 가능)
            batch_log = LOG_DIR / f'batch_processing_{datetime.now():%Y%m%d_%H%M%S}.log'
            logger.info(f"📄 Batch log: {batch_log}")
            with open(batch_log, 'w') as f:
                result = subprocess.run(
                    cmd,
                    stdout=f,
                    stderr=subprocess.STDOUT,
                    text=True,
                    timeout=timeout_minutes * 60
                )

            if result.returncode == 0:
                stats['added'] = len(added_keys)
                logger.info(f"✅ Successfully processed {len(added_keys)} new papers")
            else:
                stats['errors'].append(f"Literature batch failed: {result.stderr}")
                logger.error(f"❌ Literature batch failed: {result.stderr}")

        except subprocess.TimeoutExpired:
            stats['errors'].append(f"Literature batch timeout (>{timeout_minutes} min)")
            logger.error(f"❌ Literature batch timeout after {timeout_minutes} minutes")
        except Exception as e:
            stats['errors'].append(f"Literature batch error: {str(e)}")
            logger.error(f"❌ Error processing added papers: {e}")

    return stats

def main():
    """메인 동기화 로직"""
    logger.info("=" * 60)
    logger.info("Zotero Auto Sync Started")
    logger.info("=" * 60)

    try:
        # 환경 변수 확인
        required_vars = ['OUTPUT_DIR']
        missing = [v for v in required_vars if not os.getenv(v)]
        if missing:
            logger.error(f"Missing environment variables: {', '.join(missing)}")
            send_macos_notification("Zotero Sync Error", "Missing environment variables", sound=True)
            return 1

        output_dir = os.getenv('OUTPUT_DIR')
        logger.info(f"Output directory: {output_dir}")

        # 변동사항 감지
        logger.info("Checking for changes...")
        changes = compare_zotero_obsidian(output_dir=output_dir)

        total_changes = len(changes['added']) + len(changes['deleted']) + len(changes['moved'])

        if total_changes == 0:
            logger.info("✅ No changes detected. Everything is in sync!")
            return 0

        # 변동사항 요약
        logger.info(f"📊 Changes detected:")
        logger.info(f"  - Added: {len(changes['added'])}")
        logger.info(f"  - Deleted: {len(changes['deleted'])}")
        logger.info(f"  - Moved: {len(changes['moved'])}")

        # 변동사항 저장 (디버깅용)
        changes_file = LOG_DIR / f'changes_{datetime.now():%Y%m%d_%H%M%S}.json'
        with open(changes_file, 'w', encoding='utf-8') as f:
            json.dump(changes, f, indent=2, ensure_ascii=False)
        logger.info(f"Changes saved to: {changes_file}")

        # 알림 전송
        send_macos_notification(
            "Zotero Sync",
            f"Processing {total_changes} changes...",
            sound=False
        )

        # 변동사항 처리
        stats = process_changes(changes)

        # 결과 요약
        logger.info("=" * 60)
        logger.info("Sync Results:")
        logger.info(f"  ✅ Added: {stats['added']}")
        logger.info(f"  ✅ Deleted: {stats['deleted']}")
        logger.info(f"  ✅ Moved: {stats['moved']}")
        if stats['errors']:
            logger.error(f"  ❌ Errors: {len(stats['errors'])}")
            for err in stats['errors']:
                logger.error(f"    - {err}")
        logger.info("=" * 60)

        # 최종 알림
        if stats['errors']:
            send_macos_notification(
                "Zotero Sync Completed with Errors",
                f"Processed {total_changes} changes with {len(stats['errors'])} errors",
                sound=True
            )
            return 1
        else:
            send_macos_notification(
                "Zotero Sync Completed",
                f"Successfully processed {total_changes} changes",
                sound=False
            )
            return 0

    except Exception as e:
        logger.exception(f"Fatal error: {e}")
        send_macos_notification("Zotero Sync Error", str(e), sound=True)
        return 1

if __name__ == '__main__':
    sys.exit(main())
