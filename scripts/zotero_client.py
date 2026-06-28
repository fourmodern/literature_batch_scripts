"""
Object-oriented Zotero access.

Two classes:
  - ``ZoteroClient``  : wraps a pyzotero Web-API client (``self.raw``) and owns
                        the canonical metadata-fetching logic (collection
                        hierarchy, item fetch, by-key fetch, collection listing).
  - ``ZoteroDatabase``: read-only access to the local Zotero SQLite database
                        (collection hierarchy + item→collection membership),
                        used for detecting collection moves when the Web API is
                        behind.

``zotero_fetch.py`` re-exports the free-function API (fetch_zotero_items, …) as
thin shims delegating here, so existing callers keep working unchanged.
"""

import os
import re
import sqlite3
import sys
from typing import List, Optional, Tuple

# Make sibling modules importable whether this file is imported flat
# (``import zotero_client``) or as part of the package (``from scripts import …``).
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def extract_year(date_str: str) -> str:
    """Extract a 4-digit year from various date formats."""
    if not date_str:
        return ''
    match = re.search(r'\b(19|20)\d{2}\b', date_str)
    return match.group(0) if match else date_str


def format_authors(creators: list) -> List[str]:
    """Format Zotero creator entries as 'Last, First' author strings."""
    authors = []
    for c in creators:
        if c.get('creatorType') == 'author':
            last = c.get('lastName', '')
            first = c.get('firstName', '')
            if last and first:
                authors.append(f"{last}, {first}")
            elif last:
                authors.append(last)
            elif c.get('name'):  # Single field name
                authors.append(c.get('name'))
    return authors


class ZoteroClient:
    """Wrapper around a pyzotero Web-API client."""

    def __init__(self, raw):
        self.raw = raw

    # --- constructors --------------------------------------------------------

    @classmethod
    def from_raw(cls, zot) -> 'ZoteroClient':
        """Wrap an already-constructed pyzotero client."""
        return cls(zot)

    @classmethod
    def from_credentials(cls, user_id: str, api_key: str,
                         library_type: str = 'user') -> 'ZoteroClient':
        from pyzotero import zotero
        return cls(zotero.Zotero(user_id, library_type, api_key))

    @classmethod
    def from_env(cls) -> 'ZoteroClient':
        from app_config import get_zotero_client
        return cls(get_zotero_client())

    # --- collections ---------------------------------------------------------

    def collection_hierarchy(self) -> dict:
        """Return {collection_key: 'A/B/C' path} for every collection.

        Fetches ALL collections with pagination. zot.collections() returns only
        the first 100; with >100 collections, top-level parents fall off the
        page and nested paths lose their prefix (e.g. '600.Geninus/629.IHC'
        instead of '000.Papers/600.Geninus/629.IHC').
        """
        collections = self.raw.everything(self.raw.collections())
        collection_dict = {c['key']: c for c in collections}
        collection_paths: dict = {}

        def get_collection_path(key):
            if key in collection_paths:
                return collection_paths[key]
            collection = collection_dict.get(key)
            if not collection:
                return ""
            parent_key = collection['data'].get('parentCollection')
            if parent_key and parent_key != 'false':
                parent_path = get_collection_path(parent_key)
                path = os.path.join(parent_path, collection['data']['name'])
            else:
                path = collection['data']['name']
            collection_paths[key] = path
            return path

        for key in collection_dict:
            get_collection_path(key)
        return collection_paths

    def collection_key_by_name(self, collection_name: str) -> Tuple[Optional[str], Optional[str]]:
        """Find a collection (key, name) by case-insensitive partial match."""
        collections = self.raw.everything(self.raw.collections())
        target = collection_name.lower()

        matches = []
        for coll in collections:
            coll_name = coll['data']['name']
            if target in coll_name.lower():
                matches.append((coll['key'], coll_name))

        if not matches:
            return None, None
        if len(matches) == 1:
            return matches[0]
        # Multiple matches: prefer an exact match, else first.
        for key, name in matches:
            if name.lower() == target:
                return key, name
        print(f"Multiple collections found for '{collection_name}': {[m[1] for m in matches]}")
        print(f"Using first match: {matches[0][1]}")
        return matches[0]

    def list_collections(self) -> List[Tuple[str, int]]:
        """Return [(path, paper_count)] sorted by path (journalArticle+preprint)."""
        collection_paths = self.collection_hierarchy()
        collection_counts = {}
        for key, path in collection_paths.items():
            count = 0
            for item_type in ['journalArticle', 'preprint']:
                try:
                    test_items = self.raw.collection_items(key, itemType=item_type, limit=1)
                    if test_items:
                        count += int(self.raw.request.headers.get('Total-Results', 0))
                except Exception:
                    pass
            collection_counts[path] = count
        sorted_paths = sorted(collection_paths.values())
        return [(path, collection_counts.get(path, 0)) for path in sorted_paths]

    # --- items ---------------------------------------------------------------

    def _record_from_item(self, item: dict, collection_paths: dict) -> dict:
        """Build the flat metadata record (incl. attachments + collections)."""
        data = item['data']
        tags = [t['tag'] for t in data.get('tags', []) if 'tag' in t]

        record = {
            'key': data.get('key'),
            'title': data.get('title', 'Untitled'),
            'authors': format_authors(data.get('creators', [])),
            'abstract': data.get('abstractNote', ''),
            'publicationTitle': data.get('publicationTitle', ''),
            'year': extract_year(data.get('date', '')),
            'doi': data.get('DOI', ''),
            'date': data.get('date', 'now'),
            'citekey': data.get('citationKey', data.get('key')),
            'itemType': data.get('itemType', 'journalArticle'),
            'volume': data.get('volume', ''),
            'issue': data.get('issue', ''),
            'pages': data.get('pages', ''),
            'publisher': data.get('publisher', ''),
            'tags': tags,
            'attachments': [],
        }

        try:
            children = self.raw.children(item['key'])
            for child in children:
                cdata = child['data']
                if cdata.get('contentType') == 'application/pdf':
                    attachment_info = {
                        'filename': cdata.get('filename', 'document.pdf'),
                        'linkMode': cdata.get('linkMode'),
                        'itemKey': item['key'],
                        'fileKey': child['key'],
                    }
                    if cdata.get('linkMode') in ['imported_file', 'imported_url']:
                        storage_key = child['key']
                        attachment_info['path'] = f"storage/{storage_key}/{cdata.get('filename', 'document.pdf')}"
                    else:
                        attachment_info['path'] = cdata.get('path', '')
                    record['attachments'].append(attachment_info)
        except Exception as e:
            print(f"Error fetching attachments for {item.get('key')}: {e}")

        item_collections = data.get('collections', [])
        collection_paths_list = [collection_paths[c] for c in item_collections if c in collection_paths]
        record['collections'] = collection_paths_list
        record['collection_path'] = collection_paths_list[0] if collection_paths_list else 'Uncategorized'
        return record

    def items(self, limit: int = None, collection_filter: str = None,
              item_types: list = None) -> list:
        """Fetch items as flat metadata records.

        ``collection_filter`` restricts to a collection by name; ``item_types``
        defaults to all types. Mirrors the historical fetch_zotero_items().
        """
        if item_types is None or item_types == []:
            item_types = ['']  # empty string => no itemType filter

        collection_paths = self.collection_hierarchy()
        zot = self.raw

        if collection_filter:
            collection_key, collection_name = self.collection_key_by_name(collection_filter)
            if not collection_key:
                print(f"Collection '{collection_filter}' not found.")
                available = [c['data']['name'] for c in zot.everything(zot.collections())]
                print(f"Available collections: {', '.join(sorted(available))}")
                return []

            print(f"Fetching items from collection: {collection_name}")
            items = []
            for item_type in item_types:
                start = 0
                batch_size = 100
                try:
                    if item_type:
                        test_items = zot.collection_items(collection_key, itemType=item_type, limit=1)
                        if test_items:
                            total_items = int(zot.request.headers.get('Total-Results', 0))
                            print(f"Total {item_type}s in collection '{collection_name}': {total_items}")
                        else:
                            total_items = 0
                    else:
                        test_items = zot.collection_items(collection_key, limit=1)
                        if test_items:
                            total_items = int(zot.request.headers.get('Total-Results', 0))
                            print(f"Total items in collection '{collection_name}': {total_items}")
                        else:
                            total_items = 0
                except Exception:
                    total_items = 0

                if total_items == 0:
                    continue

                while True:
                    remaining_limit = limit - len(items) if limit else None
                    if remaining_limit is not None and remaining_limit <= 0:
                        break
                    try:
                        if item_type:
                            batch = zot.collection_items(
                                collection_key, itemType=item_type, start=start,
                                limit=min(batch_size, remaining_limit if remaining_limit else batch_size))
                        else:
                            batch = zot.collection_items(
                                collection_key, start=start,
                                limit=min(batch_size, remaining_limit if remaining_limit else batch_size))
                        if not batch:
                            break
                        items.extend(batch)
                        print(f"Fetched {len(items)} total items from {collection_name} ({item_type})...")
                        if limit and len(items) >= limit:
                            items = items[:limit]
                            break
                        if len(batch) < batch_size:
                            break
                        start += batch_size
                    except Exception as e:
                        print(f"Error fetching {item_type} items from collection: {e}")
                        break
                if limit and len(items) >= limit:
                    break
        else:
            items = []
            for item_type in item_types:
                start = 0
                batch_size = 100
                try:
                    if item_type:
                        test_items = zot.items(itemType=item_type, limit=1)
                        if test_items:
                            total_items = int(zot.request.headers.get('Total-Results', 0))
                            print(f"Total {item_type}s in Zotero: {total_items}")
                        else:
                            total_items = 0
                    else:
                        test_items = zot.items(limit=1)
                        if test_items:
                            total_items = int(zot.request.headers.get('Total-Results', 0))
                            print(f"Total items in Zotero: {total_items}")
                        else:
                            total_items = 0
                except Exception:
                    total_items = 0

                if total_items == 0:
                    continue

                while True:
                    remaining_limit = limit - len(items) if limit else None
                    if remaining_limit is not None and remaining_limit <= 0:
                        break
                    if item_type:
                        params = {'itemType': item_type, 'start': start,
                                  'limit': min(batch_size, remaining_limit if remaining_limit else batch_size)}
                    else:
                        params = {'start': start,
                                  'limit': min(batch_size, remaining_limit if remaining_limit else batch_size)}
                    try:
                        batch = zot.items(**params)
                        if not batch:
                            break
                        items.extend(batch)
                        print(f"Fetched {len(items)} total items ({item_type})...")
                        if limit and len(items) >= limit:
                            items = items[:limit]
                            break
                        if len(batch) < batch_size:
                            break
                        start += batch_size
                    except Exception as e:
                        print(f"Error fetching {item_type} items from Zotero: {e}")
                        break
                if limit and len(items) >= limit:
                    break

        return [self._record_from_item(item, collection_paths) for item in items]

    def items_by_keys(self, keys) -> list:
        """Fast path: fetch only the given item keys (1 API call each).

        Skips items that 404 (deleted). Returns the same record format as items().
        """
        collection_paths = self.collection_hierarchy()
        results = []
        for key in keys:
            try:
                item = self.raw.item(key)
            except Exception as e:
                print(f"Skipping {key}: cannot fetch item ({e})")
                continue
            results.append(self._record_from_item(item, collection_paths))
        return results

    def download_pdf(self, item_key: str, file_key: str, dest_path: str) -> None:
        """Download an attachment's file bytes to dest_path."""
        with open(dest_path, 'wb') as f:
            f.write(self.raw.file(file_key))


class ZoteroDatabase:
    """Read-only access to the local Zotero SQLite database."""

    def __init__(self, zotero_dir: str):
        self.db_path = os.path.join(zotero_dir, 'zotero.sqlite')
        if not os.path.exists(self.db_path):
            raise FileNotFoundError(f"Zotero database not found at: {self.db_path}")
        # immutable=1 lets us read even while the Zotero app holds a lock.
        self.conn = sqlite3.connect(f'file:{self.db_path}?immutable=1', uri=True)
        self.conn.row_factory = sqlite3.Row

    def collection_hierarchy(self) -> dict:
        """Build {collectionID: 'A/B/C' path} from the collections table."""
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT collectionID, collectionName, parentCollectionID FROM collections"
        )
        rows = {row['collectionID']: (row['collectionName'], row['parentCollectionID'])
                for row in cursor.fetchall()}

        def path_of(cid):
            parts = []
            seen = set()
            while cid in rows and cid not in seen:
                seen.add(cid)
                name, parent = rows[cid]
                parts.append(name)
                cid = parent
            return '/'.join(reversed(parts))

        return {cid: path_of(cid) for cid in rows}

    def item_collections(self) -> dict:
        """Return {item_key: set(collection_path)} for every collected item."""
        paths = self.collection_hierarchy()
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT items.key, collectionItems.collectionID "
            "FROM items JOIN collectionItems ON collectionItems.itemID = items.itemID"
        )
        from collections import defaultdict
        out = defaultdict(set)
        for row in cursor.fetchall():
            out[row['key']].add(paths.get(row['collectionID'], ''))
        return out

    def close(self) -> None:
        self.conn.close()
