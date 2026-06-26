#!/bin/bash
# Run after reprocess_review_notes.py to finalize the vault:
#   1. Re-add iOS PDF wiki-links (📱 line stripped during re-render)
#   2. Mirror to llm-wiki vault (iOS)
#
# Usage: bash scripts/post_reprocess_finalize.sh
#
# Note: cross-link references (`related:` + `<!-- references-in-vault -->`)
# were preserved in-place by reprocess_review_notes.py, so we do NOT need to
# rebuild the DOI index or re-fetch OpenAlex.

set -euo pipefail
cd "$(dirname "$0")/.."

PYTHON="/opt/homebrew/anaconda3/envs/zot/bin/python"
TS=$(date +%Y%m%d_%H%M%S)

echo "[$(date '+%H:%M:%S')] Step 1: Re-add iOS PDF wiki-links..."
$PYTHON scripts/add_ios_pdf_links.py 2>&1 | tail -5 | tee -a "logs/post_reprocess_${TS}.log"

echo "[$(date '+%H:%M:%S')] Step 2: Mirror to llm-wiki vault..."
$PYTHON scripts/sync_to_llm_wiki.py 2>&1 | tail -20 | tee -a "logs/post_reprocess_${TS}.log"

echo "[$(date '+%H:%M:%S')] Done. Log: logs/post_reprocess_${TS}.log"
