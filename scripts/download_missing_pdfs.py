"""
Attempt to download PDFs for notes whose 'Open PDF locally' link was never
created (the original processing fell back to abstract because no PDF was
available locally OR on Zotero).

For each Zotero item key:
  1. Fetch parent item metadata
  2. List child attachments via zot.children(key)
  3. For each PDF attachment, call pdf_downloader.ensure_pdf_available with
     download_enabled=True so it pulls the file from the Zotero API.
  4. Record success/failure to cache/missing_pdf_download_report.json.

Usage:
    python scripts/download_missing_pdfs.py \\
        --keys-file cache/missing_pdf_keys.txt \\
        --output cache/missing_pdf_download_report.json
"""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Dict, List

from dotenv import load_dotenv
from pyzotero import zotero

load_dotenv()

SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from pdf_downloader import ensure_pdf_available
from app_config import get_zotero_client


def find_pdf_dir() -> str:
    """Return the Zotero storage base dir (parent of `storage/`)."""
    env_pdf = os.getenv('PDF_DIR')
    if env_pdf and os.path.isdir(env_pdf):
        return env_pdf
    # Default: ~/Zotero
    return os.path.expanduser('~/Zotero')


def process_one(zot: zotero.Zotero, key: str, pdf_base_dir: str) -> Dict:
    """Return dict with status for this key."""
    result = {'key': key, 'status': 'unknown', 'pdf_path': None, 'note': ''}
    try:
        # Fetch parent item
        item = zot.item(key)
    except Exception as e:
        result['status'] = 'parent_fetch_failed'
        result['note'] = str(e)[:200]
        return result

    try:
        children = zot.children(key)
    except Exception as e:
        result['status'] = 'children_fetch_failed'
        result['note'] = str(e)[:200]
        return result

    # Find a PDF attachment
    pdf_attachments = [
        c for c in children
        if c['data'].get('itemType') == 'attachment'
        and c['data'].get('contentType') == 'application/pdf'
    ]

    if not pdf_attachments:
        result['status'] = 'no_pdf_attachment'
        result['note'] = f"{len(children)} children, none PDF"
        return result

    # Try the first PDF attachment
    for att in pdf_attachments:
        att_data = att['data']
        att_meta = {
            'path': att_data.get('path', ''),
            'fileKey': att.get('key', ''),
            'filename': att_data.get('filename', 'document.pdf'),
        }
        try:
            pdf_path = ensure_pdf_available(
                zot=zot, item=item['data'], attachment=att_meta,
                pdf_base_dir=pdf_base_dir, download_enabled=True,
            )
            if pdf_path and os.path.exists(pdf_path):
                result['status'] = 'downloaded'
                result['pdf_path'] = pdf_path
                return result
        except Exception as e:
            result['note'] = f"download error: {str(e)[:200]}"

    result['status'] = 'download_failed'
    if not result['note']:
        result['note'] = f"tried {len(pdf_attachments)} PDF attachment(s)"
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--keys-file', required=True, help='File with one Zotero key per line')
    parser.add_argument('--output', default='cache/missing_pdf_download_report.json',
                        help='JSON report path')
    parser.add_argument('--pdf-dir', default=None, help='Override PDF base dir')
    args = parser.parse_args()

    user_id = os.getenv('ZOTERO_USER_ID')
    api_key = os.getenv('ZOTERO_API_KEY')
    if not user_id or not api_key:
        print('❌ Missing ZOTERO_USER_ID / ZOTERO_API_KEY in .env', file=sys.stderr)
        sys.exit(2)

    pdf_base_dir = args.pdf_dir or find_pdf_dir()
    print(f'📂 PDF base dir: {pdf_base_dir}')

    with open(args.keys_file, 'r', encoding='utf-8') as f:
        keys = [line.strip() for line in f if line.strip() and not line.startswith('#')]
    print(f'🔑 Keys to try: {len(keys)}')

    zot = get_zotero_client()

    results: List[Dict] = []
    counters = {'downloaded': 0, 'no_pdf_attachment': 0, 'download_failed': 0,
                'parent_fetch_failed': 0, 'children_fetch_failed': 0, 'unknown': 0}

    for i, key in enumerate(keys, 1):
        print(f'[{i}/{len(keys)}] {key}', end=' ... ', flush=True)
        r = process_one(zot, key, pdf_base_dir)
        results.append(r)
        counters[r['status']] = counters.get(r['status'], 0) + 1
        print(f'{r["status"]}', flush=True)

    print()
    print('=' * 60)
    print('Status breakdown:')
    for status, count in sorted(counters.items(), key=lambda kv: -kv[1]):
        print(f'  {status:30s} {count}')
    print('=' * 60)

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps({'counters': counters, 'results': results}, indent=2, ensure_ascii=False),
        encoding='utf-8',
    )
    print(f'\n💾 Report: {out_path}')

    # Emit a list of newly-downloaded PDFs (note paths reachable via key)
    downloaded_keys = [r['key'] for r in results if r['status'] == 'downloaded']
    if downloaded_keys:
        keys_out = out_path.parent / 'downloaded_keys.txt'
        keys_out.write_text('\n'.join(downloaded_keys), encoding='utf-8')
        print(f'📥 {len(downloaded_keys)} newly available — keys at {keys_out}')


if __name__ == '__main__':
    main()
