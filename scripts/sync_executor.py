"""
Zotero-Obsidian 동기화 실행 스크립트

sync_checker.py의 결과를 받아서 실제로 파일을 이동/업데이트합니다.
- 이동된 항목: Obsidian 파일을 새 collection 폴더로 이동
- 삭제된 항목: Obsidian 파일을 archive 폴더로 이동 (삭제하지 않음)
- 추가된 항목: 정보 출력 (수동으로 처리하거나 batch script 실행)
"""

import os
import sys
import json
import shutil
import argparse
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scripts.sync_checker import ZoteroReader, ObsidianScanner, compare_sync_status, sanitize_folder_name


class SyncExecutor:
    """동기화 실행기"""

    def __init__(self, output_dir, dry_run=False, create_backup=True):
        self.output_dir = output_dir
        self.dry_run = dry_run
        self.create_backup = create_backup
        self.stats = {
            'moved': 0,
            'archived': 0,
            'errors': 0
        }

    def _sanitize_single_folder(self, name):
        """Sanitize a single folder name (NOT a path with /)"""
        # Remove/replace invalid characters but keep the structure
        name = name.replace('\\', '-').replace(':', '-')
        name = name.replace('*', '').replace('?', '').replace('"', '')
        name = name.replace('<', '').replace('>', '').replace('|', '')
        return name.strip()

    def execute_sync(self, comparison):
        """동기화 실행"""
        print("\n" + "="*80)
        print("  동기화 실행 시작")
        print("="*80)

        if self.dry_run:
            print("\n⚠️  DRY RUN 모드: 실제로 파일을 변경하지 않습니다\n")

        # Backup 생성
        if self.create_backup and not self.dry_run:
            self.create_backup_archive()

        # 1. 이동된 항목 처리
        if comparison['moved']:
            print(f"\n📦 이동할 파일: {len(comparison['moved'])}개")
            print("-"*80)
            self.process_moved_items(comparison['moved'])

        # 2. 삭제된 항목 처리 (archive로 이동)
        if comparison['deleted']:
            print(f"\n🗑️  Archive할 파일: {len(comparison['deleted'])}개")
            print("-"*80)
            self.process_deleted_items(comparison['deleted'])

        # 3. 추가된 항목 안내
        if comparison['added']:
            print(f"\n📝 처리 필요한 새 항목: {len(comparison['added'])}개")
            print("-"*80)
            self.show_added_items(comparison['added'])

        # 결과 요약
        self.print_summary()

    def create_backup_archive(self):
        """백업 아카이브 생성"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_dir = os.path.join(os.path.dirname(self.output_dir), 'backups')
        backup_path = os.path.join(backup_dir, f'obsidian_backup_{timestamp}.tar.gz')

        os.makedirs(backup_dir, exist_ok=True)

        print(f"\n💾 백업 생성 중: {backup_path}")

        try:
            import tarfile
            with tarfile.open(backup_path, 'w:gz') as tar:
                tar.add(self.output_dir, arcname=os.path.basename(self.output_dir))
            print(f"✅ 백업 완료: {backup_path}")
        except Exception as e:
            print(f"⚠️  백업 실패: {e}")
            print("계속 진행하시겠습니까? (y/n): ", end='')
            if input().lower() != 'y':
                sys.exit(1)

    def _archive_stale_duplicate(self, file_path, key):
        """Archive a stale duplicate markdown file for the same Zotero key."""
        timestamp = datetime.now().strftime('%Y%m%d')
        archive_dir = os.path.join(self.output_dir, '_archived', f'stale_duplicates_{timestamp}')
        filename = os.path.basename(file_path)
        archive_path = os.path.join(archive_dir, filename)

        if self.dry_run:
            print(f"    [DRY RUN] Would archive stale duplicate: {file_path} → {archive_path}")
            return

        os.makedirs(archive_dir, exist_ok=True)
        base, ext = os.path.splitext(archive_path)
        i = 1
        while os.path.exists(archive_path):
            archive_path = f"{base}.{i}{ext}"
            i += 1
        shutil.move(file_path, archive_path)
        print(f"    🗄️  중복 stale 파일 archive: {filename}")

    def _cleanup_duplicate_key_files(self, key, expected_dir, keep_path=None):
        """Clean duplicate md files for a moved Zotero key.

        Older runs may have created more than one markdown file with the same
        Zotero key. The scanner stores only one file per key, so a move can look
        successful while stale duplicates remain in the old Obsidian folder.
        Keep files in the expected collection folder and archive duplicates in
        other folders so Obsidian reflects the Zotero collection move.
        """
        if not key:
            return

        expected_dir = os.path.abspath(expected_dir)
        keep_path = os.path.abspath(keep_path) if keep_path else None

        expected_files = []

        for root, dirs, files in os.walk(self.output_dir):
            # Do not touch archived files or images.
            path_parts = root.split(os.sep)
            if '_archived' in path_parts or 'img' in path_parts:
                dirs[:] = []
                continue

            for filename in files:
                if not filename.endswith(f'_{key}.md'):
                    continue

                file_path = os.path.abspath(os.path.join(root, filename))
                if os.path.abspath(root) == expected_dir:
                    expected_files.append(file_path)
                    continue

                self._archive_stale_duplicate(file_path, key)

        # If multiple copies already exist in the correct destination folder,
        # keep the explicit keep_path if present, otherwise keep the largest
        # note (usually the most complete) and archive the rest.
        if len(expected_files) > 1:
            if keep_path and keep_path in expected_files:
                keeper = keep_path
            else:
                keeper = max(expected_files, key=lambda p: os.path.getsize(p))
            for file_path in expected_files:
                if file_path != keeper:
                    self._archive_stale_duplicate(file_path, key)

    def process_moved_items(self, moved_items):
        """이동된 항목 처리"""
        for item in moved_items:
            old_path = item.get('file_path') or item.get('filePath')
            key = item.get('key')

            # 새 경로 구성
            new_collection = item.get('new_collection') or item.get('newCollection')
            # Split by '/' first, then sanitize each part individually
            collection_parts = new_collection.split('/')
            collection_parts_sanitized = [self._sanitize_single_folder(part) for part in collection_parts]
            new_dir = os.path.join(self.output_dir, *collection_parts_sanitized)
            filename = os.path.basename(old_path)
            new_path = os.path.join(new_dir, filename)

            old_collection = item.get('old_collection') or item.get('oldCollection')

            print(f"\n  • {item['title'][:60]}")
            print(f"    From: {old_collection}")
            print(f"    To:   {new_collection}")

            if self.dry_run:
                print(f"    [DRY RUN] Would move:")
                print(f"      {old_path}")
                print(f"      → {new_path}")
                self._cleanup_duplicate_key_files(key, new_dir, keep_path=new_path)
            else:
                try:
                    # 새 디렉토리 생성
                    os.makedirs(new_dir, exist_ok=True)

                    # 파일 이동. If an expected copy already exists, treat old_path
                    # as a stale duplicate instead of overwriting it.
                    if os.path.abspath(old_path) == os.path.abspath(new_path):
                        print(f"    ✅ 이미 올바른 위치")
                    elif os.path.exists(new_path):
                        self._archive_stale_duplicate(old_path, key)
                    else:
                        shutil.move(old_path, new_path)
                        print(f"    ✅ 이동 완료")
                        self.stats['moved'] += 1

                    # 같은 key가 예전 폴더에 중복으로 남아 있으면 정리
                    self._cleanup_duplicate_key_files(key, new_dir, keep_path=new_path)

                    # 빈 디렉토리 정리
                    self.cleanup_empty_dirs(os.path.dirname(old_path))

                except Exception as e:
                    print(f"    ❌ 오류: {e}")
                    self.stats['errors'] += 1

    def process_deleted_items(self, deleted_items):
        """삭제된 항목 처리 (archive로 이동)"""
        archive_dir = os.path.join(self.output_dir, '_archived')
        timestamp = datetime.now().strftime('%Y%m%d')
        archive_subdir = os.path.join(archive_dir, timestamp)

        for item in deleted_items:
            file_path = item.get('file_path') or item.get('filePath')
            filename = os.path.basename(file_path)
            archive_path = os.path.join(archive_subdir, filename)

            print(f"\n  • {item['title'][:60]}")
            print(f"    Collection: {item['collection']}")

            if self.dry_run:
                print(f"    [DRY RUN] Would archive:")
                print(f"      {file_path}")
                print(f"      → {archive_path}")
            else:
                try:
                    # Archive 디렉토리 생성
                    os.makedirs(archive_subdir, exist_ok=True)

                    # 파일 이동
                    shutil.move(file_path, archive_path)
                    print(f"    ✅ Archive 완료")
                    self.stats['archived'] += 1

                    # 빈 디렉토리 정리
                    self.cleanup_empty_dirs(os.path.dirname(file_path))

                except Exception as e:
                    print(f"    ❌ 오류: {e}")
                    self.stats['errors'] += 1

    def show_added_items(self, added_items):
        """추가된 항목 안내"""
        # Collection별로 그룹화
        by_collection = {}
        for item in added_items:
            coll = item['collection']
            if coll not in by_collection:
                by_collection[coll] = []
            by_collection[coll].append(item)

        for collection in sorted(by_collection.keys()):
            items = by_collection[collection]
            print(f"\n  [{collection}] ({len(items)}개)")
            for item in items[:5]:
                print(f"    • {item['title'][:60]} (key: {item['key']})")
            if len(items) > 5:
                print(f"    ... and {len(items) - 5} more")

        print(f"\n  💡 이 항목들을 처리하려면:")
        print(f"     python scripts/run_literature_batch.py --overwrite")
        print(f"     또는 특정 컬렉션만:")
        print(f"     python scripts/run_literature_batch.py --collection \"컬렉션명\"")

    def cleanup_empty_dirs(self, dir_path):
        """빈 디렉토리 정리"""
        try:
            # img 폴더는 건너뛰기
            if 'img' in dir_path or '_archived' in dir_path:
                return

            # 디렉토리가 비어있으면 삭제
            while dir_path != self.output_dir and os.path.exists(dir_path):
                if not os.listdir(dir_path):
                    os.rmdir(dir_path)
                    print(f"    🗑️  빈 폴더 삭제: {os.path.basename(dir_path)}")
                    dir_path = os.path.dirname(dir_path)
                else:
                    break
        except Exception as e:
            # 조용히 실패 (중요하지 않은 작업)
            pass

    def print_summary(self):
        """결과 요약 출력"""
        print("\n" + "="*80)
        print("  동기화 완료")
        print("="*80)

        if self.dry_run:
            print("\n⚠️  DRY RUN 모드였습니다. 실제로 변경되지 않았습니다.")
        else:
            print(f"\n📊 처리 결과:")
            print(f"  • 이동됨: {self.stats['moved']}개")
            print(f"  • Archive됨: {self.stats['archived']}개")
            print(f"  • 오류: {self.stats['errors']}개")

        print("\n" + "="*80)


def main():
    parser = argparse.ArgumentParser(
        description='Zotero-Obsidian 동기화를 실행합니다 (파일 이동/archive)'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='실제로 파일을 변경하지 않고 미리보기만 표시'
    )
    parser.add_argument(
        '--no-backup',
        action='store_true',
        help='백업을 생성하지 않음 (권장하지 않음)'
    )
    parser.add_argument(
        '--collection', '-c',
        help='특정 컬렉션만 처리'
    )
    parser.add_argument(
        '--from-json',
        help='sync_checker.py의 JSON 출력을 입력으로 사용'
    )

    args = parser.parse_args()

    # Load environment
    load_dotenv()

    output_dir = os.getenv('OUTPUT_DIR')
    if not output_dir:
        print("❌ OUTPUT_DIR 환경 변수가 설정되지 않았습니다.")
        sys.exit(1)

    output_dir = os.path.expanduser(output_dir)

    # Get comparison data
    if args.from_json:
        # JSON 파일에서 읽기
        print(f"📂 JSON 파일에서 읽는 중: {args.from_json}")
        with open(args.from_json, 'r', encoding='utf-8') as f:
            comparison = json.load(f)
    else:
        # 직접 비교 수행
        from scripts.zotero_path_finder import find_zotero_data_directory

        zotero_dir = find_zotero_data_directory()
        if not zotero_dir:
            print("❌ Zotero 디렉토리를 찾을 수 없습니다.")
            sys.exit(1)

        print(f"📂 Zotero 디렉토리: {zotero_dir}")
        print(f"📂 Obsidian 출력 디렉토리: {output_dir}")

        # Read and compare
        print("\n🔍 Zotero 데이터베이스 읽는 중...")
        zotero_reader = ZoteroReader(zotero_dir)
        zotero_articles = zotero_reader.get_journal_articles()
        zotero_reader.close()
        print(f"   ✓ {len(zotero_articles)}개의 journal article 발견")

        # Filter by collection if specified
        if args.collection:
            filtered = {}
            for key, article in zotero_articles.items():
                if args.collection.lower() in article['collection'].lower():
                    filtered[key] = article
            zotero_articles = filtered
            print(f"   ✓ '{args.collection}' 컬렉션 필터링: {len(zotero_articles)}개")

        print("\n🔍 Obsidian 폴더 스캔 중...")
        obsidian_scanner = ObsidianScanner(output_dir)
        obsidian_articles = obsidian_scanner.scan_markdown_files()
        print(f"   ✓ {len(obsidian_articles)}개의 마크다운 파일 발견")

        # Filter Obsidian by collection if specified
        if args.collection:
            filtered = {}
            for key, article in obsidian_articles.items():
                if args.collection.lower() in article['collection'].lower():
                    filtered[key] = article
            obsidian_articles = filtered
            print(f"   ✓ '{args.collection}' 컬렉션 필터링: {len(obsidian_articles)}개")

        print("\n🔍 비교 중...")
        comparison = compare_sync_status(zotero_articles, obsidian_articles)

    # Execute sync
    executor = SyncExecutor(
        output_dir=output_dir,
        dry_run=args.dry_run,
        create_backup=not args.no_backup
    )
    executor.execute_sync(comparison)

    # 확인 프롬프트
    if not args.dry_run and executor.stats['errors'] > 0:
        print("\n⚠️  일부 오류가 발생했습니다. 로그를 확인하세요.")


if __name__ == '__main__':
    main()
