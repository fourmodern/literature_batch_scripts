#!/usr/bin/env python3
"""
Count total preprints in Zotero
"""
import os
import sys
import sqlite3

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from scripts.zotero_path_finder import find_zotero_data_directory

def count_preprints():
    zotero_dir = find_zotero_data_directory()
    if not zotero_dir:
        print("❌ Zotero 디렉토리를 찾을 수 없습니다.")
        return

    db_path = os.path.join(zotero_dir, 'zotero.sqlite')

    try:
        conn = sqlite3.connect(f'file:{db_path}?mode=ro', uri=True)
        cursor = conn.cursor()

        # Get preprint type ID
        cursor.execute("SELECT itemTypeID FROM itemTypes WHERE typeName = 'preprint'")
        preprint_type_id = cursor.fetchone()

        if not preprint_type_id:
            print("❌ preprint type not found")
            return

        preprint_type_id = preprint_type_id[0]

        # Count total preprints
        cursor.execute("""
            SELECT COUNT(*)
            FROM items
            WHERE itemTypeID = ? AND itemID NOT IN (SELECT itemID FROM deletedItems)
        """, (preprint_type_id,))

        total_count = cursor.fetchone()[0]
        print(f"📊 Total preprints in Zotero: {total_count}")

        # Count by collection
        cursor.execute("""
            SELECT c.collectionName, COUNT(i.itemID) as cnt
            FROM collections c
            JOIN collectionItems ci ON c.collectionID = ci.collectionID
            JOIN items i ON ci.itemID = i.itemID
            WHERE i.itemTypeID = ? AND i.itemID NOT IN (SELECT itemID FROM deletedItems)
            GROUP BY c.collectionID, c.collectionName
            ORDER BY cnt DESC
        """, (preprint_type_id,))

        collections = cursor.fetchall()
        if collections:
            print(f"\n📁 Preprints by collection:")
            for name, count in collections[:20]:
                print(f"  • {name}: {count}")
            if len(collections) > 20:
                print(f"  ... and {len(collections) - 20} more collections")

        conn.close()

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    count_preprints()
