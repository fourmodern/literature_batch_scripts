"""
Fetch metadata and PDF attachment info from Zotero using pyzotero.
"""
import os
import re
from pyzotero import zotero

def extract_year(date_str):
    """Extract year from various date formats."""
    if not date_str:
        return ''
    match = re.search(r'\b(19|20)\d{2}\b', date_str)
    return match.group(0) if match else date_str

def format_authors(creators):
    """Format author names properly."""
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

def build_collection_hierarchy(zot):
    """Build a dictionary of collection paths keyed by collection key."""
    collections = zot.collections()
    collection_dict = {c['key']: c for c in collections}
    collection_paths = {}
    
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
    
    # Build all paths
    for key in collection_dict:
        get_collection_path(key)
    
    return collection_paths

def get_collection_key_by_name(zot, collection_name):
    """Find collection key by collection name (case-insensitive partial match)."""
    collections = zot.collections()
    collection_name_lower = collection_name.lower()
    
    matches = []
    for coll in collections:
        coll_name = coll['data']['name']
        if collection_name_lower in coll_name.lower():
            matches.append((coll['key'], coll_name))
    
    if not matches:
        return None, None
    elif len(matches) == 1:
        return matches[0]
    else:
        # Multiple matches, try exact match first
        for key, name in matches:
            if name.lower() == collection_name_lower:
                return key, name
        # Return first match if no exact match
        print(f"Multiple collections found for '{collection_name}': {[m[1] for m in matches]}")
        print(f"Using first match: {matches[0][1]}")
        return matches[0]

def fetch_zotero_items(user_id: str, api_key: str, library_type: str = 'user', limit: int = None, collection_filter: str = None, return_zot_instance: bool = False, item_types: list = None):
    """
    Fetch items from Zotero and return list of metadata dicts.

    Args:
        collection_filter: If provided, only fetch items from this collection (by name)
        return_zot_instance: If True, return (items, zot) tuple instead of just items
        item_types: List of item types to fetch (default: ['journalArticle', 'preprint', 'conferencePaper'])
    """
    if item_types is None:
        item_types = ['journalArticle', 'preprint', 'conferencePaper']

    zot = zotero.Zotero(user_id, library_type, api_key)
    
    # Build collection hierarchy first
    collection_paths = build_collection_hierarchy(zot)
    
    if collection_filter:
        # Find the collection key
        collection_key, collection_name = get_collection_key_by_name(zot, collection_filter)
        if not collection_key:
            print(f"Collection '{collection_filter}' not found.")
            available = [c['data']['name'] for c in zot.collections()]
            print(f"Available collections: {', '.join(sorted(available))}")
            if return_zot_instance:
                return [], zot
            return []

        print(f"Fetching items from collection: {collection_name}")
        # Fetch items from specific collection with pagination
        items = []

        # Fetch items for each item type
        for item_type in item_types:
            start = 0
            batch_size = 100

            # Get total count for this collection and item type
            try:
                test_items = zot.collection_items(collection_key, itemType=item_type, limit=1)
                if test_items:
                    total_items = int(zot.request.headers.get('Total-Results', 0))
                    print(f"Total {item_type}s in collection '{collection_name}': {total_items}")
                else:
                    total_items = 0
            except:
                total_items = 0

            if total_items == 0:
                continue

            # Fetch all items in batches
            while True:
                try:
                    remaining_limit = limit - len(items) if limit else None
                    if remaining_limit is not None and remaining_limit <= 0:
                        break

                    batch = zot.collection_items(
                        collection_key,
                        itemType=item_type,
                        start=start,
                        limit=min(batch_size, remaining_limit if remaining_limit else batch_size)
                    )
                    if not batch:
                        break

                    items.extend(batch)
                    print(f"Fetched {len(items)} total items from {collection_name} ({item_type})...")

                    # Check if we've reached the user-specified limit
                    if limit and len(items) >= limit:
                        items = items[:limit]
                        break

                    # Check if we've fetched all items
                    if len(batch) < batch_size:
                        break

                    start += batch_size

                except Exception as e:
                    print(f"Error fetching {item_type} items from collection: {e}")
                    break

            # If we've hit the limit, stop fetching other types
            if limit and len(items) >= limit:
                break
    else:
        # Fetch all items with pagination
        items = []

        # Fetch items for each item type
        for item_type in item_types:
            start = 0
            batch_size = 100  # Zotero API limit per request

            # First, get total count
            try:
                # Get a single item to check total available
                test_items = zot.items(itemType=item_type, limit=1)
                if test_items:
                    total_items = int(zot.request.headers.get('Total-Results', 0))
                    print(f"Total {item_type}s in Zotero: {total_items}")
                else:
                    total_items = 0
            except:
                total_items = 0

            if total_items == 0:
                continue

            # Now fetch all items in batches
            while True:
                remaining_limit = limit - len(items) if limit else None
                if remaining_limit is not None and remaining_limit <= 0:
                    break

                params = {
                    'itemType': item_type,
                    'start': start,
                    'limit': min(batch_size, remaining_limit if remaining_limit else batch_size)
                }

                try:
                    batch = zot.items(**params)
                    if not batch:
                        break

                    items.extend(batch)
                    print(f"Fetched {len(items)} total items ({item_type})...")

                    # Check if we've reached the user-specified limit
                    if limit and len(items) >= limit:
                        items = items[:limit]
                        break

                    # Check if we've fetched all items
                    if len(batch) < batch_size:
                        break

                    start += batch_size

                except Exception as e:
                    print(f"Error fetching {item_type} items from Zotero: {e}")
                    break

            # If we've hit the limit, stop fetching other types
            if limit and len(items) >= limit:
                break
    
    results = []
    for item in items:
        data = item['data']
        # Extract tags from Zotero
        tags = []
        if 'tags' in data:
            tags = [tag['tag'] for tag in data['tags'] if 'tag' in tag]
        
        # extract basic fields
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
            'tags': tags,  # Add Zotero tags
            'attachments': []
        }
        
        # fetch attachments (PDF)
        try:
            children = zot.children(item['key'])
            for child in children:
                cdata = child['data']
                if cdata.get('contentType') == 'application/pdf':
                    # For Zotero storage, construct the path
                    attachment_info = {
                        'filename': cdata.get('filename', 'document.pdf'),
                        'linkMode': cdata.get('linkMode'),
                        'itemKey': item['key'],
                        'fileKey': child['key']
                    }
                    
                    # If stored in Zotero (linkMode == 'imported_file' or 'imported_url')
                    if cdata.get('linkMode') in ['imported_file', 'imported_url']:
                        # Zotero storage path: /Zotero/storage/[8-char-key]/filename.pdf
                        storage_key = child['key']
                        attachment_info['path'] = f"storage/{storage_key}/{cdata.get('filename', 'document.pdf')}"
                    else:
                        # Linked file
                        attachment_info['path'] = cdata.get('path', '')
                    
                    record['attachments'].append(attachment_info)
        except Exception as e:
            print(f"Error fetching attachments for {item['key']}: {e}")
        
        # Get collections this item belongs to
        item_collections = data.get('collections', [])
        collection_paths_list = []
        for coll_key in item_collections:
            if coll_key in collection_paths:
                collection_paths_list.append(collection_paths[coll_key])
        
        record['collections'] = collection_paths_list
        record['collection_path'] = collection_paths_list[0] if collection_paths_list else 'Uncategorized'
        
        results.append(record)
    
    if return_zot_instance:
        return results, zot
    return results

def list_all_collections(user_id: str, api_key: str, library_type: str = 'user'):
    """List all collections with their hierarchy."""
    zot = zotero.Zotero(user_id, library_type, api_key)
    collection_paths = build_collection_hierarchy(zot)

    # Get item counts for each collection (journalArticle + preprint)
    collection_counts = {}
    for key, path in collection_paths.items():
        count = 0
        for item_type in ['journalArticle', 'preprint']:
            try:
                # Just get count, not all items
                test_items = zot.collection_items(key, itemType=item_type, limit=1)
                if test_items:
                    count += int(zot.request.headers.get('Total-Results', 0))
            except:
                pass
        collection_counts[path] = count

    # Sort by path for hierarchical display
    sorted_paths = sorted(collection_paths.values())

    return [(path, collection_counts.get(path, 0)) for path in sorted_paths]

if __name__ == '__main__':
    import dotenv
    dotenv.load_dotenv()
    USER_ID = os.getenv('ZOTERO_USER_ID')
    API_KEY = os.getenv('ZOTERO_API_KEY')
    
    # List collections
    print("Available Zotero Collections:")
    print("-" * 50)
    collections = list_all_collections(USER_ID, API_KEY)
    for path, count in collections:
        indent = "  " * path.count(os.sep)
        print(f"{indent}{os.path.basename(path)} ({count} papers)")
    
    print("\nTotal collections:", len(collections))
