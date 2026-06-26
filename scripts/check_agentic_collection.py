#!/usr/bin/env python3
"""
Check if agenticAI collection exists in Zotero
"""
import os
import sys
import sqlite3

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from scripts.zotero_path_finder import find_zotero_data_directory

def check_agentic_collection():
    zotero_dir = find_zotero_data_directory()
    if not zotero_dir:
        print("❌ Zotero 디렉토리를 찾을 수 없습니다.")
        return

    db_path = os.path.join(zotero_dir, 'zotero.sqlite')
    if not os.path.exists(db_path):
        print(f"❌ Database not found: {db_path}")
        return

    print(f"📂 Zotero DB: {db_path}")

    try:
        conn = sqlite3.connect(f'file:{db_path}?mode=ro', uri=True)
        cursor = conn.cursor()

        # Find all collections with "agentic" in the name
        cursor.execute("""
            SELECT collectionID, collectionName, parentCollectionID
            FROM collections
            WHERE collectionName LIKE '%agentic%'
            OR collectionName LIKE '%Agentic%'
        """)

        agentic_collections = cursor.fetchall()

        if not agentic_collections:
            print("\n❌ 'agentic' 이름을 가진 컬렉션을 찾을 수 없습니다.")

            # Show all collections under 500.AI
            cursor.execute("""
                SELECT c1.collectionID, c1.collectionName, c2.collectionName as parent
                FROM collections c1
                LEFT JOIN collections c2 ON c1.parentCollectionID = c2.collectionID
                WHERE c2.collectionName LIKE '%500.AI%'
                OR c1.collectionName LIKE '%500.AI%'
                ORDER BY c2.collectionName, c1.collectionName
            """)

            ai_collections = cursor.fetchall()
            print(f"\n📁 500.AI 관련 컬렉션 ({len(ai_collections)}개):")
            for coll_id, name, parent in ai_collections:
                parent_str = f" (under {parent})" if parent else ""
                print(f"  - {name}{parent_str}")
        else:
            print(f"\n✅ 'agentic' 컬렉션 발견 ({len(agentic_collections)}개):")
            for coll_id, name, parent_id in agentic_collections:
                # Get parent collection name
                if parent_id:
                    cursor.execute("SELECT collectionName FROM collections WHERE collectionID = ?", (parent_id,))
                    parent_result = cursor.fetchone()
                    parent_name = parent_result[0] if parent_result else "Unknown"
                    print(f"  - {name} (under {parent_name})")
                else:
                    print(f"  - {name} (top-level)")

                # Check how many items in this collection
                cursor.execute("""
                    SELECT COUNT(*) FROM collectionItems WHERE collectionID = ?
                """, (coll_id,))
                item_count = cursor.fetchone()[0]
                print(f"    📊 Items: {item_count}")

        conn.close()

    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == '__main__':
    check_agentic_collection()
