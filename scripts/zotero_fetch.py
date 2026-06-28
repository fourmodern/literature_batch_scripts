"""
Backward-compatible free-function API for Zotero metadata.

The implementation now lives in ``zotero_client.ZoteroClient``; the functions
below are thin shims that preserve the historical signatures (including the
``return_zot_instance`` tuple form) so existing callers keep working unchanged.
"""
import os

from zotero_client import ZoteroClient, extract_year, format_authors  # noqa: F401 (re-export)


def build_collection_hierarchy(zot):
    """Build a dict of collection paths keyed by collection key."""
    return ZoteroClient.from_raw(zot).collection_hierarchy()


def get_collection_key_by_name(zot, collection_name):
    """Find collection key by name (case-insensitive partial match)."""
    return ZoteroClient.from_raw(zot).collection_key_by_name(collection_name)


def fetch_zotero_items(user_id, api_key, library_type='user', limit=None,
                       collection_filter=None, return_zot_instance=False,
                       item_types=None):
    """Fetch items from Zotero as a list of metadata dicts."""
    client = ZoteroClient.from_credentials(user_id, api_key, library_type)
    results = client.items(limit=limit, collection_filter=collection_filter,
                           item_types=item_types)
    if return_zot_instance:
        return results, client.raw
    return results


def fetch_zotero_items_by_keys(user_id, api_key, keys, library_type='user',
                               return_zot_instance=False):
    """Fast path: fetch only the specified item keys."""
    client = ZoteroClient.from_credentials(user_id, api_key, library_type)
    results = client.items_by_keys(keys)
    if return_zot_instance:
        return results, client.raw
    return results


def list_all_collections(user_id, api_key, library_type='user'):
    """List all collections with (path, paper_count)."""
    return ZoteroClient.from_credentials(user_id, api_key, library_type).list_collections()


if __name__ == '__main__':
    import dotenv
    dotenv.load_dotenv()
    USER_ID = os.getenv('ZOTERO_USER_ID')
    API_KEY = os.getenv('ZOTERO_API_KEY')

    print("Available Zotero Collections:")
    print("-" * 50)
    collections = list_all_collections(USER_ID, API_KEY)
    for path, count in collections:
        indent = "  " * path.count(os.sep)
        print(f"{indent}{os.path.basename(path)} ({count} papers)")

    print("\nTotal collections:", len(collections))
