#!/bin/bash
# Auto-sync wrapper script
# Ensures proper environment loading for LaunchAgent

cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
/opt/homebrew/anaconda3/envs/zot/bin/python scripts/zotero_auto_sync.py
