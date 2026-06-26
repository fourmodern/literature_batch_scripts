"""
Fetch each paper's `referenced_works` list from OpenAlex and resolve the
referenced OpenAlex IDs back to DOIs. Output a reference map keyed by our
papers' DOIs.

OpenAlex API (free, no key):
  - Polite pool when you include mailto=<email>: 10 req/sec
  - `GET /works/doi:<DOI>` returns the work with referenced_works (array of
    OpenAlex IDs, e.g. "https://openalex.org/W2741809807")
  - Batch resolve: `GET /works?filter=openalex:W1|W2|...&select=id,doi&per-page=50`

Inputs:
  cache/doi_index.json (from build_doi_index.py)
Outputs:
  cache/openalex/per_work/<doi_safe>.json — raw per-paper response (cached)
  cache/openalex/id_to_doi.json — OpenAlex ID → DOI map (cached)
  cache/reference_map.json — { our_doi: [referenced_doi, ...] }

Re-running is safe: anything already cached is skipped.
"""

import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path
from typing import Dict, Iterable, List, Optional

import requests
from dotenv import load_dotenv

load_dotenv()

OPENALEX_BASE = 'https://api.openalex.org'
MAILTO = os.getenv('OPENALEX_MAILTO', 'fourmodern@gmail.com')
DEFAULT_SLEEP = 0.1  # 10 req/s polite-pool limit

ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = ROOT / 'cache' / 'openalex'
PER_WORK_DIR = CACHE_DIR / 'per_work'
ID_TO_DOI_PATH = CACHE_DIR / 'id_to_doi.json'
REF_MAP_PATH = ROOT / 'cache' / 'reference_map.json'


def doi_safe(doi: str) -> str:
    """Safe filename from a DOI (just hash; DOIs can be very long/wonky)."""
    return hashlib.sha1(doi.encode('utf-8')).hexdigest()[:16]


def openalex_id_strip(url: str) -> Optional[str]:
    """'https://openalex.org/W123' -> 'W123'."""
    if not url:
        return None
    if url.startswith('https://openalex.org/'):
        return url[len('https://openalex.org/'):]
    if url.startswith('http://openalex.org/'):
        return url[len('http://openalex.org/'):]
    if url.startswith('W'):
        return url
    return None


class OpenAlexClient:
    def __init__(self, mailto: str, sleep: float = DEFAULT_SLEEP):
        self.session = requests.Session()
        self.session.headers.update({'User-Agent': f'literature-batch-scripts ({mailto})'})
        self.params = {'mailto': mailto} if mailto else {}
        self.sleep = sleep
        self._last_call = 0.0

    def _throttle(self):
        elapsed = time.time() - self._last_call
        if elapsed < self.sleep:
            time.sleep(self.sleep - elapsed)
        self._last_call = time.time()

    def get(self, path: str, params: Optional[dict] = None) -> Optional[dict]:
        self._throttle()
        all_params = dict(self.params)
        if params:
            all_params.update(params)
        url = OPENALEX_BASE + path
        for attempt in range(3):
            try:
                r = self.session.get(url, params=all_params, timeout=30)
                if r.status_code == 404:
                    return None
                if r.status_code == 429:
                    # Rate limit; back off
                    time.sleep(2 ** attempt)
                    continue
                r.raise_for_status()
                return r.json()
            except requests.RequestException as e:
                if attempt == 2:
                    print(f'   ⚠️  request failed for {url}: {e}', file=sys.stderr)
                    return None
                time.sleep(2 ** attempt)
        return None


def fetch_papers(client: OpenAlexClient, dois: Iterable[str], force: bool = False) -> int:
    """For each DOI, save the OpenAlex work response to cache. Returns count fetched (not cached hits)."""
    PER_WORK_DIR.mkdir(parents=True, exist_ok=True)
    fetched = 0
    skipped = 0
    failed = []
    dois = list(dois)
    for i, doi in enumerate(dois, 1):
        cache_path = PER_WORK_DIR / f'{doi_safe(doi)}.json'
        if cache_path.exists() and not force:
            skipped += 1
            if i % 100 == 0:
                print(f'   [{i}/{len(dois)}] cached={skipped} fetched={fetched} failed={len(failed)}')
            continue
        data = client.get(f'/works/doi:{doi}', params={'select': 'id,doi,referenced_works,cited_by_count,title'})
        if data is None:
            failed.append(doi)
            # Cache the failure so we don't retry every run
            cache_path.write_text(json.dumps({'_not_found': True, 'doi': doi}), encoding='utf-8')
        else:
            cache_path.write_text(json.dumps(data), encoding='utf-8')
            fetched += 1
        if i % 100 == 0 or i == len(dois):
            print(f'   [{i}/{len(dois)}] cached={skipped} fetched={fetched} failed={len(failed)}')
    if failed:
        print(f'   ⚠️  {len(failed)} DOIs not found in OpenAlex (cached as _not_found)')
    return fetched


def collect_referenced_ids(dois: Iterable[str]) -> set:
    """Walk all cached responses and collect the unique referenced OpenAlex IDs."""
    seen = set()
    for doi in dois:
        cache_path = PER_WORK_DIR / f'{doi_safe(doi)}.json'
        if not cache_path.exists():
            continue
        try:
            data = json.loads(cache_path.read_text(encoding='utf-8'))
        except json.JSONDecodeError:
            continue
        if data.get('_not_found'):
            continue
        for ref_url in data.get('referenced_works', []) or []:
            oa_id = openalex_id_strip(ref_url)
            if oa_id:
                seen.add(oa_id)
    return seen


def load_id_to_doi() -> Dict[str, Optional[str]]:
    if ID_TO_DOI_PATH.exists():
        try:
            return json.loads(ID_TO_DOI_PATH.read_text(encoding='utf-8'))
        except json.JSONDecodeError:
            return {}
    return {}


def save_id_to_doi(mapping: Dict[str, Optional[str]]):
    ID_TO_DOI_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = ID_TO_DOI_PATH.with_suffix(ID_TO_DOI_PATH.suffix + '.tmp')
    tmp.write_text(json.dumps(mapping, indent=2, ensure_ascii=False), encoding='utf-8')
    tmp.replace(ID_TO_DOI_PATH)


def resolve_ids_to_dois(client: OpenAlexClient, ids: Iterable[str], existing: Dict[str, Optional[str]], batch_size: int = 50) -> Dict[str, Optional[str]]:
    """Batch-resolve OpenAlex IDs to DOIs. Skip IDs we already have."""
    remaining = [i for i in ids if i not in existing]
    if not remaining:
        print(f'   ✅ All {len(list(ids))} IDs already resolved (from cache)')
        return existing
    print(f'   🔍 Resolving {len(remaining)} new OpenAlex IDs (batch={batch_size})...')
    resolved = 0
    for offset in range(0, len(remaining), batch_size):
        batch = remaining[offset: offset + batch_size]
        filter_str = '|'.join(batch)
        data = client.get('/works', params={
            'filter': f'openalex:{filter_str}',
            'select': 'id,doi',
            'per-page': batch_size,
        })
        if not data:
            # Mark all in batch as unresolved (so we don't loop forever)
            for i in batch:
                existing[i] = None
            continue
        returned_ids = set()
        for work in data.get('results', []):
            oa_id = openalex_id_strip(work.get('id', ''))
            doi_url = work.get('doi')  # may be None or full URL
            doi_norm = None
            if doi_url:
                doi_norm = doi_url.lower().replace('https://doi.org/', '').replace('http://doi.org/', '').strip()
            if oa_id:
                existing[oa_id] = doi_norm
                returned_ids.add(oa_id)
                if doi_norm:
                    resolved += 1
        # Anything in batch that didn't come back: mark None (e.g. deleted work)
        for i in batch:
            if i not in returned_ids:
                existing.setdefault(i, None)
        if (offset // batch_size) % 20 == 0:
            print(f'   [{offset + len(batch)}/{len(remaining)}] resolved with DOI: {resolved}')
            # Periodic save in case of interruption
            save_id_to_doi(existing)
    save_id_to_doi(existing)
    print(f'   ✅ Resolved {resolved}/{len(remaining)} new IDs to DOIs')
    return existing


def build_reference_map(dois: Iterable[str], id_to_doi: Dict[str, Optional[str]]) -> Dict[str, List[str]]:
    """For each of our DOIs, list referenced DOIs (resolved via the ID map)."""
    ref_map = {}
    for doi in dois:
        cache_path = PER_WORK_DIR / f'{doi_safe(doi)}.json'
        if not cache_path.exists():
            continue
        try:
            data = json.loads(cache_path.read_text(encoding='utf-8'))
        except json.JSONDecodeError:
            continue
        if data.get('_not_found'):
            ref_map[doi] = []
            continue
        refs = []
        for ref_url in data.get('referenced_works', []) or []:
            oa_id = openalex_id_strip(ref_url)
            if not oa_id:
                continue
            ref_doi = id_to_doi.get(oa_id)
            if ref_doi:
                refs.append(ref_doi)
        ref_map[doi] = refs
    return ref_map


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        '--doi-index',
        default=str(ROOT / 'cache' / 'doi_index.json'),
        help='Path to doi_index.json (from build_doi_index.py)',
    )
    parser.add_argument('--force', action='store_true', help='Re-fetch even if cached')
    parser.add_argument('--limit', type=int, default=None, help='Process only first N DOIs')
    parser.add_argument('--skip-resolve', action='store_true', help='Skip the ID→DOI resolve step (only fetch papers)')
    args = parser.parse_args()

    doi_index_path = Path(args.doi_index)
    if not doi_index_path.exists():
        print(f'❌ DOI index not found: {doi_index_path}. Run build_doi_index.py first.', file=sys.stderr)
        sys.exit(2)
    doi_index = json.loads(doi_index_path.read_text(encoding='utf-8'))
    dois = list(doi_index.keys())
    if args.limit:
        dois = dois[: args.limit]
        print(f'   Limit applied: {len(dois)} DOIs')

    client = OpenAlexClient(mailto=MAILTO)
    print(f'🌐 OpenAlex (mailto={MAILTO})')

    # Step 1: Fetch each of our papers (with caching)
    print(f'\n📥 Step 1: Fetching {len(dois)} papers from OpenAlex...')
    fetch_papers(client, dois, force=args.force)

    # Step 2: Collect unique referenced OpenAlex IDs
    print(f'\n🔗 Step 2: Collecting referenced OpenAlex IDs...')
    referenced_ids = collect_referenced_ids(dois)
    print(f'   Found {len(referenced_ids)} unique referenced OpenAlex IDs')

    # Step 3: Resolve IDs → DOIs
    id_to_doi = load_id_to_doi()
    print(f'\n🔍 Step 3: Resolving IDs to DOIs (existing cache: {len(id_to_doi)})...')
    if args.skip_resolve:
        print('   (skipped)')
    else:
        id_to_doi = resolve_ids_to_dois(client, referenced_ids, id_to_doi)

    # Step 4: Build reference map
    print(f'\n🗺️  Step 4: Building reference map...')
    ref_map = build_reference_map(dois, id_to_doi)
    total_links = sum(len(v) for v in ref_map.values())
    REF_MAP_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = REF_MAP_PATH.with_suffix(REF_MAP_PATH.suffix + '.tmp')
    tmp.write_text(json.dumps(ref_map, indent=2, ensure_ascii=False), encoding='utf-8')
    tmp.replace(REF_MAP_PATH)
    print(f'   Total ref→DOI edges: {total_links}')
    print(f'💾 Wrote: {REF_MAP_PATH}')


if __name__ == '__main__':
    main()
