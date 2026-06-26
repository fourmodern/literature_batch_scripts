"""
Zotero-Obsidian 동기화 상태 비교 도구

Zotero API 또는 SQLite 데이터베이스와 Obsidian 폴더를 비교하여:
- 추가된 항목 (Zotero에만 있음)
- 삭제된 항목 (Obsidian에만 있음)
- 이동된 항목 (collection이 변경됨)
을 찾아서 리스트합니다.

--use-api 옵션: Zotero Web API 직접 호출 (Zotero 앱 없이도 동작)
기본값: 로컬 SQLite 읽기 (빠르지만 앱 동기화 필요)
"""

import os
import sys
import sqlite3
import argparse
import json
from pathlib import Path
from collections import defaultdict
from dotenv import load_dotenv

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scripts.zotero_path_finder import find_zotero_data_directory


class ZoteroAPIReader:
    """Zotero Web API를 통해 데이터 읽기 (로컬 앱 불필요)"""

    def __init__(self):
        from pyzotero import zotero

        user_id = os.getenv('ZOTERO_USER_ID')
        api_key = os.getenv('ZOTERO_API_KEY')

        if not user_id or not api_key:
            raise ValueError("ZOTERO_USER_ID와 ZOTERO_API_KEY 환경 변수가 필요합니다.")

        self.zot = zotero.Zotero(user_id, 'user', api_key)
        self._collection_cache = None

    def get_collection_hierarchy(self):
        """Build collection hierarchy dict: collectionKey -> path"""
        if self._collection_cache:
            return self._collection_cache

        # Fetch ALL collections with pagination. zot.collections() returns only
        # the first 100; libraries with >100 collections lose top-level parents,
        # which truncates nested paths (e.g. '600.Geninus/629.IHC' instead of
        # '000.Papers/600.Geninus/629.IHC').
        collections = self.zot.everything(self.zot.collections())

        # Build lookup by key
        coll_by_key = {}
        for coll in collections:
            data = coll['data']
            coll_by_key[data['key']] = {
                'name': data['name'],
                'parent': data.get('parentCollection', False)
            }

        # Build paths
        collection_paths = {}

        def get_path(coll_key):
            if coll_key in collection_paths:
                return collection_paths[coll_key]

            coll = coll_by_key.get(coll_key)
            if not coll:
                return ""

            parent_key = coll['parent']
            if parent_key and parent_key in coll_by_key:
                parent_path = get_path(parent_key)
                path = os.path.join(parent_path, coll['name'])
            else:
                path = coll['name']

            collection_paths[coll_key] = path
            return path

        # Build all paths
        for coll_key in coll_by_key:
            get_path(coll_key)

        self._collection_cache = collection_paths
        return collection_paths

    def get_journal_articles(self):
        """Get all journal articles from Zotero API with their collections"""
        collection_paths = self.get_collection_hierarchy()

        # Fetch all items with pagination
        articles = {}
        item_types = ['journalArticle', 'preprint', 'conferencePaper']

        for item_type in item_types:
            start = 0
            limit = 100

            while True:
                items = self.zot.items(itemType=item_type, start=start, limit=limit)
                if not items:
                    break

                for item in items:
                    data = item['data']
                    key = data['key']
                    title = data.get('title', 'Untitled')

                    # Get collections for this item
                    item_collections = []
                    for coll_key in data.get('collections', []):
                        if coll_key in collection_paths:
                            item_collections.append(collection_paths[coll_key])

                    # Use the deepest (most specific) collection path
                    if item_collections:
                        collection = max(item_collections, key=lambda x: x.count('/'))
                    else:
                        collection = 'Uncategorized'

                    articles[key] = {
                        'title': title,
                        'collection': collection,
                        'all_collections': item_collections
                    }

                start += limit
                if len(items) < limit:
                    break

        return articles

    def close(self):
        pass  # No cleanup needed for API


def sanitize_folder_name(name):
    """Sanitize folder name for filesystem (same as run_literature_batch.py)"""
    name = name.replace('/', '-').replace('\\', '-').replace(':', '-')
    name = name.replace('*', '').replace('?', '').replace('"', '').replace('<', '').replace('>', '').replace('|', '')
    return name.strip()


class ZoteroReader:
    """Zotero SQLite 데이터베이스 읽기"""

    def __init__(self, zotero_dir):
        self.db_path = os.path.join(zotero_dir, 'zotero.sqlite')
        if not os.path.exists(self.db_path):
            raise FileNotFoundError(f"Zotero database not found at: {self.db_path}")
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row

    def get_collection_hierarchy(self):
        """Build collection hierarchy dict: collectionID -> path"""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT collectionID, collectionName, parentCollectionID
            FROM collections
        """)

        collections = {}
        for row in cursor.fetchall():
            collections[row['collectionID']] = {
                'name': row['collectionName'],
                'parent': row['parentCollectionID']
            }

        # Build paths
        collection_paths = {}

        def get_path(coll_id):
            if coll_id in collection_paths:
                return collection_paths[coll_id]

            coll = collections.get(coll_id)
            if not coll:
                return ""

            parent_id = coll['parent']
            if parent_id and parent_id in collections:
                parent_path = get_path(parent_id)
                path = os.path.join(parent_path, coll['name'])
            else:
                path = coll['name']

            collection_paths[coll_id] = path
            return path

        # Build all paths
        for coll_id in collections:
            get_path(coll_id)

        return collection_paths

    def get_journal_articles(self):
        """Get all journal articles, preprints, and conference papers with their collections"""
        cursor = self.conn.cursor()

        # Get itemTypeIDs for journalArticle, preprint, and conferencePaper
        cursor.execute("""
            SELECT itemTypeID FROM itemTypes
            WHERE typeName IN ('journalArticle', 'preprint', 'conferencePaper')
        """)
        type_ids = [row['itemTypeID'] for row in cursor.fetchall()]
        if not type_ids:
            return {}

        # Get collection hierarchy
        collection_paths = self.get_collection_hierarchy()

        # Get all academic papers (journal articles, preprints, conference papers)
        placeholders = ','.join('?' * len(type_ids))
        cursor.execute(f"""
            SELECT items.itemID, items.key,
                   itemDataValues.value as title
            FROM items
            LEFT JOIN itemData ON items.itemID = itemData.itemID
            LEFT JOIN fields ON itemData.fieldID = fields.fieldID
            LEFT JOIN itemDataValues ON itemData.valueID = itemDataValues.valueID
            WHERE items.itemTypeID IN ({placeholders})
            AND fields.fieldName = 'title'
        """, type_ids)

        articles = {}
        for row in cursor.fetchall():
            item_id = row['itemID']
            key = row['key']
            title = row['title'] or 'Untitled'

            # Get collections for this item
            cursor.execute("""
                SELECT collectionID
                FROM collectionItems
                WHERE itemID = ?
            """, (item_id,))

            item_collections = []
            for coll_row in cursor.fetchall():
                coll_id = coll_row['collectionID']
                if coll_id in collection_paths:
                    item_collections.append(collection_paths[coll_id])

            # Use the deepest (most specific) collection path
            # This handles cases where an item is in both parent and child collections
            if item_collections:
                collection = max(item_collections, key=lambda x: x.count('/'))
            else:
                collection = 'Uncategorized'

            articles[key] = {
                'title': title,
                'collection': collection,
                'all_collections': item_collections
            }

        return articles

    def close(self):
        self.conn.close()


class ObsidianScanner:
    """Obsidian 폴더 스캔"""

    def __init__(self, output_dir):
        self.output_dir = output_dir
        if not os.path.exists(output_dir):
            raise FileNotFoundError(f"Obsidian output directory not found: {output_dir}")

    def scan_markdown_files(self):
        """Scan all markdown files and extract key and collection path"""
        articles = {}

        for root, dirs, files in os.walk(self.output_dir):
            # Skip img and _archived folders
            dirs_to_skip = []
            for dir_name in dirs:
                if dir_name == 'img' or dir_name.startswith('_archived'):
                    dirs_to_skip.append(dir_name)
            for skip_dir in dirs_to_skip:
                dirs.remove(skip_dir)

            # Also skip if current path contains these folders
            path_parts = root.split(os.sep)
            if 'img' in path_parts or any(part.startswith('_archived') for part in path_parts):
                continue

            for filename in files:
                if not filename.endswith('.md'):
                    continue

                # Extract key from filename: {title}_{KEY}.md
                if '_' in filename:
                    parts = filename.rsplit('_', 1)
                    if len(parts) == 2:
                        key = parts[1].replace('.md', '')

                        # Get collection path from folder structure
                        rel_path = os.path.relpath(root, self.output_dir)
                        collection = rel_path if rel_path != '.' else 'Uncategorized'

                        # Extract title from filename (approximate)
                        title_part = parts[0]

                        articles[key] = {
                            'filename': filename,
                            'collection': collection,
                            'title': title_part,
                            'full_path': os.path.join(root, filename)
                        }

        return articles


def normalize_collection_path(collection_path):
    """
    Normalize collection path for comparison.
    Apply the same sanitization that would be used when creating folders.
    """
    # Split path into parts
    parts = collection_path.split(os.sep)
    # Sanitize each part
    sanitized_parts = [sanitize_folder_name(part) for part in parts]
    # Rejoin with os.sep
    normalized = os.path.join(*sanitized_parts) if sanitized_parts else ''
    return os.path.normpath(normalized) if normalized else 'Uncategorized'


def compare_sync_status(zotero_articles, obsidian_articles):
    """Compare Zotero and Obsidian to find differences"""

    zotero_keys = set(zotero_articles.keys())
    obsidian_keys = set(obsidian_articles.keys())

    # Added: in Zotero but not in Obsidian
    added_keys = zotero_keys - obsidian_keys
    added = []
    for key in added_keys:
        article = zotero_articles[key]
        added.append({
            'key': key,
            'title': article['title'],
            'collection': article['collection']
        })

    # Deleted: in Obsidian but not in Zotero
    deleted_keys = obsidian_keys - zotero_keys
    deleted = []
    for key in deleted_keys:
        article = obsidian_articles[key]
        # Uncategorized의 orphan PDF 파일은 무시 (parent item 없는 attachment)
        title = article.get('title', '')
        collection = article.get('collection', '')
        if collection == 'Uncategorized' and (title == 'PDF' or title.startswith('PDF_')):
            continue  # orphan PDF는 삭제 대상에서 제외
        deleted.append({
            'key': key,
            'title': title,
            'collection': collection,
            'file_path': article['full_path']
        })

    # Moved: same key but different collection
    common_keys = zotero_keys & obsidian_keys
    moved = []
    for key in common_keys:
        # Normalize both paths for proper comparison
        zot_coll_raw = zotero_articles[key]['collection']
        zot_coll_normalized = normalize_collection_path(zot_coll_raw)

        obs_coll_raw = obsidian_articles[key]['collection']
        obs_coll_normalized = os.path.normpath(obs_coll_raw)

        if zot_coll_normalized != obs_coll_normalized:
            moved.append({
                'key': key,
                'title': zotero_articles[key]['title'],
                'old_collection': obs_coll_raw,
                'new_collection': zot_coll_raw,
                'file_path': obsidian_articles[key]['full_path']
            })

    return {
        'added': sorted(added, key=lambda x: x['collection']),
        'deleted': sorted(deleted, key=lambda x: x['collection']),
        'moved': sorted(moved, key=lambda x: x['new_collection'])
    }


def print_report(comparison, zotero_total, obsidian_total):
    """Print comparison report"""

    print("\n" + "="*80)
    print("  Zotero ↔ Obsidian 동기화 상태 비교")
    print("="*80)

    print(f"\n📊 통계:")
    print(f"  • Zotero 항목 수: {zotero_total}")
    print(f"  • Obsidian 파일 수: {obsidian_total}")
    print(f"  • 동기화됨: {zotero_total - len(comparison['added'])}")

    print(f"\n🔍 차이점:")
    print(f"  • 추가 필요 (Zotero에만 있음): {len(comparison['added'])}")
    print(f"  • 삭제됨 (Obsidian에만 있음): {len(comparison['deleted'])}")
    print(f"  • 이동됨 (Collection 변경): {len(comparison['moved'])}")

    # Added items
    if comparison['added']:
        print("\n" + "-"*80)
        print(f"📝 추가 필요한 항목 ({len(comparison['added'])}개)")
        print("-"*80)

        by_collection = defaultdict(list)
        for item in comparison['added']:
            by_collection[item['collection']].append(item)

        for collection in sorted(by_collection.keys()):
            items = by_collection[collection]
            print(f"\n  [{collection}] ({len(items)}개)")
            for item in items[:10]:  # Show first 10
                print(f"    • {item['title'][:60]} (key: {item['key']})")
            if len(items) > 10:
                print(f"    ... and {len(items) - 10} more")

    # Deleted items
    if comparison['deleted']:
        print("\n" + "-"*80)
        print(f"🗑️  삭제된 항목 (Zotero에 없음) ({len(comparison['deleted'])}개)")
        print("-"*80)

        by_collection = defaultdict(list)
        for item in comparison['deleted']:
            by_collection[item['collection']].append(item)

        for collection in sorted(by_collection.keys()):
            items = by_collection[collection]
            print(f"\n  [{collection}] ({len(items)}개)")
            for item in items[:10]:
                print(f"    • {item['title'][:60]} (key: {item['key']})")
                print(f"      파일: {item['file_path']}")
            if len(items) > 10:
                print(f"    ... and {len(items) - 10} more")

    # Moved items
    if comparison['moved']:
        print("\n" + "-"*80)
        print(f"📦 이동된 항목 (Collection 변경) ({len(comparison['moved'])}개)")
        print("-"*80)

        for item in comparison['moved'][:20]:  # Show first 20
            print(f"\n  • {item['title'][:60]} (key: {item['key']})")
            print(f"    {item['old_collection']} → {item['new_collection']}")

        if len(comparison['moved']) > 20:
            print(f"\n  ... and {len(comparison['moved']) - 20} more")

    print("\n" + "="*80)


def save_json_report(comparison, output_file):
    """Save comparison report as JSON"""
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(comparison, f, ensure_ascii=False, indent=2)
    print(f"\n✅ JSON 리포트 저장됨: {output_file}")


def compare_zotero_obsidian(output_dir=None, collection_filter=None, use_api=True):
    """
    Zotero와 Obsidian을 비교하여 변동사항을 반환 (프로그래밍 인터페이스)

    Args:
        output_dir: Obsidian 출력 디렉토리 (None이면 환경변수 사용)
        collection_filter: 특정 컬렉션만 비교 (선택사항)
        use_api: True면 Zotero Web API 사용, False면 로컬 SQLite 읽기

    Returns:
        dict: {'added': [...], 'deleted': [...], 'moved': [...]}
    """
    # Load environment
    load_dotenv()

    if output_dir is None:
        output_dir = os.getenv('OUTPUT_DIR')
        if not output_dir:
            raise ValueError("OUTPUT_DIR 환경 변수가 설정되지 않았습니다.")

    output_dir = os.path.expanduser(output_dir)

    # Read Zotero data (API or SQLite)
    if use_api:
        zotero_reader = ZoteroAPIReader()
    else:
        zotero_dir = find_zotero_data_directory()
        if not zotero_dir:
            raise FileNotFoundError("Zotero 디렉토리를 찾을 수 없습니다.")
        zotero_reader = ZoteroReader(zotero_dir)

    zotero_articles = zotero_reader.get_journal_articles()
    zotero_reader.close()

    # Filter by collection if specified
    if collection_filter:
        filtered = {}
        for key, article in zotero_articles.items():
            if collection_filter.lower() in article['collection'].lower():
                filtered[key] = article
        zotero_articles = filtered

    # Scan Obsidian folder
    obsidian_scanner = ObsidianScanner(output_dir)
    obsidian_articles = obsidian_scanner.scan_markdown_files()

    # Filter Obsidian by collection if specified
    if collection_filter:
        filtered = {}
        for key, article in obsidian_articles.items():
            if collection_filter.lower() in article['collection'].lower():
                filtered[key] = article
        obsidian_articles = filtered

    # Compare
    comparison = compare_sync_status(zotero_articles, obsidian_articles)

    return comparison


def main():
    parser = argparse.ArgumentParser(
        description='Zotero와 Obsidian 폴더의 동기화 상태를 비교합니다.'
    )
    parser.add_argument(
        '--output', '-o',
        help='결과를 JSON 파일로 저장 (선택사항)'
    )
    parser.add_argument(
        '--collection', '-c',
        help='특정 컬렉션만 비교 (선택사항)'
    )
    parser.add_argument(
        '--use-api', '-a',
        action='store_true',
        default=True,
        help='Zotero Web API 사용 (기본값, Zotero 앱 불필요)'
    )
    parser.add_argument(
        '--use-sqlite', '-s',
        action='store_true',
        help='로컬 SQLite DB 사용 (빠르지만 Zotero 앱 동기화 필요)'
    )

    args = parser.parse_args()

    # --use-sqlite가 지정되면 API 비활성화
    use_api = not args.use_sqlite

    # Load environment
    load_dotenv()

    output_dir = os.getenv('OUTPUT_DIR')
    if not output_dir:
        print("❌ OUTPUT_DIR 환경 변수가 설정되지 않았습니다.")
        print("   .env 파일을 확인하세요.")
        sys.exit(1)

    output_dir = os.path.expanduser(output_dir)

    if use_api:
        print("🌐 Zotero Web API 사용 (클라우드 직접 연결)")
    else:
        zotero_dir = find_zotero_data_directory()
        if not zotero_dir:
            print("❌ Zotero 디렉토리를 찾을 수 없습니다.")
            print("   --use-api 옵션을 사용하거나 Zotero를 설치하세요.")
            sys.exit(1)
        print(f"📂 Zotero 디렉토리: {zotero_dir}")

    print(f"📂 Obsidian 출력 디렉토리: {output_dir}")

    try:
        # Read Zotero data
        if use_api:
            print("\n🔍 Zotero API에서 데이터 가져오는 중...")
            zotero_reader = ZoteroAPIReader()
        else:
            print("\n🔍 Zotero 데이터베이스 읽는 중...")
            zotero_reader = ZoteroReader(zotero_dir)

        zotero_articles = zotero_reader.get_journal_articles()
        zotero_reader.close()
        print(f"   ✓ {len(zotero_articles)}개의 논문 발견")

        # Filter by collection if specified
        if args.collection:
            filtered = {}
            for key, article in zotero_articles.items():
                if args.collection.lower() in article['collection'].lower():
                    filtered[key] = article
            zotero_articles = filtered
            print(f"   ✓ '{args.collection}' 컬렉션 필터링: {len(zotero_articles)}개")

        # Scan Obsidian folder
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

        # Compare
        print("\n🔍 비교 중...")
        comparison = compare_sync_status(zotero_articles, obsidian_articles)

        # Print report
        print_report(comparison, len(zotero_articles), len(obsidian_articles))

        # Save JSON if requested
        if args.output:
            save_json_report(comparison, args.output)

    except FileNotFoundError as e:
        print(f"\n❌ 오류: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ 예상치 못한 오류: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
