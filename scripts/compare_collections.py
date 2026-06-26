"""
Zotero와 Obsidian의 컬렉션 폴더 구조를 비교합니다.
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load environment
load_dotenv()

from scripts.sync_checker import ZoteroReader, sanitize_folder_name
from scripts.zotero_path_finder import find_zotero_data_directory


def get_obsidian_collections(output_dir):
    """Obsidian 폴더에서 실제 존재하는 컬렉션 폴더 추출"""
    collections = set()

    for root, dirs, files in os.walk(output_dir):
        # Skip archived folders
        if '_archived' in root:
            continue

        # Get relative path from output_dir
        rel_path = os.path.relpath(root, output_dir)

        # Skip if it's the root
        if rel_path == '.':
            continue

        # Skip img folders
        if 'img' in rel_path.split(os.sep):
            continue

        # Only add if there are markdown files in this directory
        if any(f.endswith('.md') for f in files):
            collections.add(rel_path)

    return collections


def get_zotero_collections(zotero_reader, zotero_articles):
    """Zotero에서 사용 중인 컬렉션 추출"""
    collections = set()

    for key, article in zotero_articles.items():
        collection_path = article.get('collection', 'Uncategorized')
        if collection_path:
            # Sanitize the same way as sync_checker
            sanitized = sanitize_folder_name(collection_path)
            collections.add(sanitized)

    return collections


def main():
    # Get directories
    zotero_dir = find_zotero_data_directory()
    output_dir = os.getenv('OUTPUT_DIR')

    if not zotero_dir:
        print("❌ Zotero 디렉토리를 찾을 수 없습니다.")
        sys.exit(1)

    if not output_dir:
        print("❌ OUTPUT_DIR 환경 변수가 설정되지 않았습니다.")
        sys.exit(1)

    output_dir = os.path.expanduser(output_dir)

    print(f"📂 Zotero 디렉토리: {zotero_dir}")
    print(f"📂 Obsidian 출력 디렉토리: {output_dir}")

    # Read Zotero collections
    print("\n🔍 Zotero 컬렉션 읽는 중...")
    zotero_reader = ZoteroReader(zotero_dir)
    zotero_articles = zotero_reader.get_journal_articles()
    zotero_collections = get_zotero_collections(zotero_reader, zotero_articles)
    zotero_reader.close()
    print(f"   ✓ {len(zotero_collections)}개의 컬렉션 발견")

    # Read Obsidian collections
    print("\n🔍 Obsidian 폴더 구조 읽는 중...")
    obsidian_collections = get_obsidian_collections(output_dir)
    print(f"   ✓ {len(obsidian_collections)}개의 폴더 발견")

    # Compare
    print("\n" + "="*80)
    print("  컬렉션 비교 결과")
    print("="*80)

    print(f"\n📊 통계:")
    print(f"  • Zotero 컬렉션 수: {len(zotero_collections)}")
    print(f"  • Obsidian 폴더 수: {len(obsidian_collections)}")
    print(f"  • 공통: {len(zotero_collections & obsidian_collections)}")

    # Collections only in Zotero
    only_zotero = zotero_collections - obsidian_collections
    if only_zotero:
        print(f"\n📝 Zotero에만 있는 컬렉션 ({len(only_zotero)}개):")
        print("-"*80)
        for coll in sorted(only_zotero):
            # Count papers in this collection
            count = sum(1 for a in zotero_articles.values()
                       if sanitize_folder_name(a.get('collection', '')) == coll)
            print(f"  • {coll} ({count}개 논문)")

    # Collections only in Obsidian
    only_obsidian = obsidian_collections - zotero_collections
    if only_obsidian:
        print(f"\n🗑️  Obsidian에만 있는 폴더 ({len(only_obsidian)}개):")
        print("-"*80)
        for coll in sorted(only_obsidian):
            # Count files in this folder
            folder_path = os.path.join(output_dir, coll)
            count = len([f for f in os.listdir(folder_path) if f.endswith('.md')])
            print(f"  • {coll} ({count}개 파일)")

    print("\n" + "="*80)


if __name__ == '__main__':
    main()
