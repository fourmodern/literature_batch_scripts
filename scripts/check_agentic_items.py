#!/usr/bin/env python3
"""
Check items in agenticAI collection
"""
import os
import sys
import sqlite3

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from scripts.zotero_path_finder import find_zotero_data_directory

def check_agentic_items():
    zotero_dir = find_zotero_data_directory()
    if not zotero_dir:
        print("❌ Zotero 디렉토리를 찾을 수 없습니다.")
        return

    db_path = os.path.join(zotero_dir, 'zotero.sqlite')

    try:
        conn = sqlite3.connect(f'file:{db_path}?mode=ro', uri=True)
        cursor = conn.cursor()

        # Find agenticAI collection
        cursor.execute("""
            SELECT collectionID, collectionName
            FROM collections
            WHERE collectionName = 'agenticAI'
        """)

        result = cursor.fetchone()
        if not result:
            print("❌ agenticAI 컬렉션을 찾을 수 없습니다.")
            return

        coll_id, coll_name = result
        print(f"✅ Collection: {coll_name} (ID: {coll_id})")

        # Get all items in this collection with their types
        cursor.execute("""
            SELECT i.itemID, i.key, it.typeName,
                   (SELECT value FROM itemDataValues idv
                    JOIN itemData id ON idv.valueID = id.valueID
                    WHERE id.itemID = i.itemID AND id.fieldID = 1 LIMIT 1) as title
            FROM items i
            JOIN collectionItems ci ON i.itemID = ci.itemID
            JOIN itemTypes it ON i.itemTypeID = it.itemTypeID
            WHERE ci.collectionID = ? AND i.itemID NOT IN (SELECT itemID FROM deletedItems)
            ORDER BY it.typeName, i.dateAdded DESC
        """, (coll_id,))

        items = cursor.fetchall()

        print(f"\n📊 총 {len(items)}개 항목:")

        # Group by type
        by_type = {}
        for item_id, key, type_name, title in items:
            if type_name not in by_type:
                by_type[type_name] = []
            by_type[type_name].append((key, title))

        for type_name, item_list in sorted(by_type.items()):
            print(f"\n  [{type_name}] ({len(item_list)}개)")
            for key, title in item_list[:5]:
                title_str = (title[:60] + "...") if title and len(title) > 60 else (title or "No title")
                print(f"    • {title_str}")
                print(f"      Key: {key}")
            if len(item_list) > 5:
                print(f"    ... and {len(item_list) - 5} more")

        conn.close()

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    check_agentic_items()
