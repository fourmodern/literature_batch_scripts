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
import fcntl
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

    # 안전장치: 대량 삭제/이동은 스킵 (오류 방지)
    MAX_SAFE_DELETED = 50
    MAX_SAFE_MOVED = 100

    if len(changes['deleted']) > MAX_SAFE_DELETED:
        logger.warning(f"⚠️ Too many deleted items ({len(changes['deleted'])}). Skipping to prevent data loss. Max: {MAX_SAFE_DELETED}")
        logger.warning("Run sync_executor.py manually with --dry-run to review changes")
        stats['errors'].append(f"Skipped {len(changes['deleted'])} deletions (safety limit)")
        changes['deleted'] = []  # 삭제 처리 스킵

    if len(changes['moved']) > MAX_SAFE_MOVED:
        logger.warning(f"⚠️ Too many moved items ({len(changes['moved'])}). Skipping to prevent data loss. Max: {MAX_SAFE_MOVED}")
        logger.warning("Run sync_executor.py manually with --dry-run to review changes")
        stats['errors'].append(f"Skipped {len(changes['moved'])} moves (safety limit)")
        changes['moved'] = []  # 이동 처리 스킵

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
            # 임시 JSON 파일로 added 논문 목록 저장
            temp_added_json = LOG_DIR / 'temp_added.json'
            with open(temp_added_json, 'w', encoding='utf-8') as f:
                json.dump(changes, f, indent=2, ensure_ascii=False)

            # process_missing_papers.py 실행 (done.txt 무시하고 강제 처리)
            cmd = [
                sys.executable,
                str(Path(__file__).parent / 'process_missing_papers.py'),
                '--from-json', str(temp_added_json),
            ]

            # 타임아웃 계산: 논문당 15분(GPT-5.5 reasoning 4회 호출) + 기본 15분(Zotero 전체 fetch)
            # (최소 45분, 최대 4시간)
            timeout_minutes = min(max(len(added_keys) * 15 + 15, 45), 240)
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

            # 임시 파일 삭제
            temp_added_json.unlink(missing_ok=True)

            if result.returncode == 0:
                stats['added'] = len(added_keys)
                logger.info(f"✅ Successfully processed {len(added_keys)} new papers")

                # 3. Pinecone DB 인덱싱 (Obsidian 마크다운 생성 후)
                logger.info(f"📊 Indexing {len(added_keys)} papers to Pinecone...")
                try:
                    index_cmd = [
                        sys.executable,
                        str(Path(__file__).parent / 'dual_db_indexer.py'),
                        '--keys', ','.join(added_keys),
                    ]

                    # 인덱싱 타임아웃: 논문당 3분 + 기본 5분
                    index_timeout = min(max(len(added_keys) * 3 + 5, 10), 120) * 60
                    logger.info(f"Running: {' '.join(index_cmd)}")

                    index_log = LOG_DIR / f'pinecone_indexing_{datetime.now():%Y%m%d_%H%M%S}.log'
                    with open(index_log, 'w') as f:
                        index_result = subprocess.run(
                            index_cmd,
                            stdout=f,
                            stderr=subprocess.STDOUT,
                            text=True,
                            timeout=index_timeout
                        )

                    if index_result.returncode == 0:
                        logger.info(f"✅ Successfully indexed to Pinecone")
                    else:
                        logger.warning(f"⚠️ Pinecone indexing completed with warnings")

                except subprocess.TimeoutExpired:
                    logger.warning(f"⚠️ Pinecone indexing timeout - will retry next sync")
                except Exception as e:
                    logger.warning(f"⚠️ Pinecone indexing error: {e}")

            else:
                stats['errors'].append(f"Literature batch failed: {result.stderr}")
                logger.error(f"❌ Literature batch failed: {result.stderr}")

        except subprocess.TimeoutExpired:
            stats['errors'].append(f"Literature batch timeout (>{timeout_minutes} min)")
            logger.error(f"❌ Literature batch timeout after {timeout_minutes} minutes")
        except Exception as e:
            stats['errors'].append(f"Literature batch error: {str(e)}")
            logger.error(f"❌ Error processing added papers: {e}")

    # 4. Refresh the in-vault reference graph (build_doi_index → fetch_openalex_refs
    # → inject_references) so newly-added notes get a `related:` block and a
    # `<!-- references-in-vault -->` body section pointing to other vault papers
    # they cite. Idempotent: existing notes only change when a NEW citation
    # becomes available in the vault. Runs only if papers were added (delete/move
    # alone doesn't create new citation targets).
    if stats['added']:
        logger.info(f"🔗 Refreshing in-vault reference graph...")
        ref_log = LOG_DIR / f'reference_refresh_{datetime.now():%Y%m%d_%H%M%S}.log'
        ref_steps = [
            ('build_doi_index.py', []),
            ('fetch_openalex_refs.py', []),
            ('inject_references.py', []),
        ]
        ref_ok = True
        with open(ref_log, 'w') as f:
            for script, extra_args in ref_steps:
                step_cmd = [sys.executable, str(Path(__file__).parent / script), *extra_args]
                f.write(f'\n=== {script} ===\n')
                f.flush()
                try:
                    step_result = subprocess.run(
                        step_cmd,
                        stdout=f,
                        stderr=subprocess.STDOUT,
                        text=True,
                        timeout=20 * 60,  # 20 min per step ceiling
                    )
                    if step_result.returncode != 0:
                        logger.warning(f"⚠️ {script} exited {step_result.returncode}")
                        ref_ok = False
                        break
                except subprocess.TimeoutExpired:
                    logger.warning(f"⚠️ {script} timeout")
                    ref_ok = False
                    break
                except Exception as e:
                    logger.warning(f"⚠️ {script} error: {e}")
                    ref_ok = False
                    break
        if ref_ok:
            logger.info(f"✅ Reference graph refreshed (log: {ref_log})")
        else:
            logger.warning(f"⚠️ Reference graph refresh incomplete (log: {ref_log})")

    # 5. Mirror the source vault into the llm-wiki/iOS vault (best-effort).
    # Runs after add/delete/move processing finishes so any kind of change is
    # picked up. Skipped if LLM_WIKI_SOURCES is unset, or if nothing changed.
    any_changes = stats['added'] or stats['deleted'] or stats['moved']
    if os.getenv('LLM_WIKI_SOURCES') and any_changes:
        logger.info(f"📦 Mirroring to llm-wiki vault (added={stats['added']}, deleted={stats['deleted']}, moved={stats['moved']})...")
        try:
            mirror_cmd = [
                sys.executable,
                str(Path(__file__).parent / 'sync_to_llm_wiki.py'),
            ]
            mirror_log = LOG_DIR / f'llm_wiki_mirror_{datetime.now():%Y%m%d_%H%M%S}.log'
            with open(mirror_log, 'w') as f:
                mirror_result = subprocess.run(
                    mirror_cmd,
                    stdout=f,
                    stderr=subprocess.STDOUT,
                    text=True,
                    timeout=30 * 60,  # 30 min ceiling; first-time PDF copy over iCloud is slow
                )
            if mirror_result.returncode == 0:
                logger.info(f"✅ Mirrored to llm-wiki vault")
            else:
                logger.warning(f"⚠️ llm-wiki mirror exited {mirror_result.returncode} (log: {mirror_log})")
        except subprocess.TimeoutExpired:
            logger.warning(f"⚠️ llm-wiki mirror timeout - will retry next sync")
        except Exception as e:
            logger.warning(f"⚠️ llm-wiki mirror error: {e}")
    elif os.getenv('LLM_WIKI_SOURCES'):
        logger.debug("llm-wiki mirror: no changes this run, skipping")

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
        # - Added는 Zotero Web API 기준을 사용한다. (새 논문 처리는 API에서 본문/첨부를 다시 가져오기 때문)
        # - Moved는 로컬 Zotero SQLite 기준을 우선 사용한다. 로컬 앱에서 컬렉션을 옮긴 직후에는
        #   Web API가 아직 동기화 전이라 moved=0으로 나오는 경우가 있어 Obsidian 폴더 이동이 누락된다.
        # - Deleted는 API 기준을 유지한다. 로컬 SQLite가 오래되었을 때 파일을 잘못 archive하지 않기 위해서다.
        logger.info("Checking for changes via Zotero API...")
        api_changes = compare_zotero_obsidian(output_dir=output_dir, use_api=True)

        try:
            logger.info("Checking local Zotero SQLite for collection moves...")
            local_changes = compare_zotero_obsidian(output_dir=output_dir, use_api=False)
            logger.info(
                "Local SQLite changes: added=%d, deleted=%d, moved=%d",
                len(local_changes.get('added', [])),
                len(local_changes.get('deleted', [])),
                len(local_changes.get('moved', [])),
            )
        except Exception as e:
            logger.warning(f"Could not read local Zotero SQLite; falling back to API moves: {e}")
            local_changes = api_changes

        changes = {
            'added': api_changes.get('added', []),
            'deleted': api_changes.get('deleted', []),
            'moved': local_changes.get('moved', []),
        }

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
    # Prevent duplicate execution with file lock
    lock_file = LOG_DIR / 'sync.lock'
    lock_fp = None
    try:
        lock_fp = open(lock_file, 'w')
        fcntl.flock(lock_fp.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        logger.info("🔒 Acquired lock, starting sync...")
        exit_code = main()
    except BlockingIOError:
        logger.warning("⚠️  Another sync process is already running. Skipping...")
        print("Another zotero_auto_sync is already running. Exiting.")
        exit_code = 0
    finally:
        if lock_fp:
            try:
                fcntl.flock(lock_fp.fileno(), fcntl.LOCK_UN)
                lock_fp.close()
                lock_file.unlink(missing_ok=True)
            except:
                pass
    sys.exit(exit_code)
