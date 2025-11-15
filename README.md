# Literature Batch Processing System

A comprehensive literature processing system that extracts metadata and PDFs from Zotero, generates AI summaries using GPT or Gemini, and creates Obsidian-compatible markdown notes with automatic synchronization.

## Features

- 🚀 **Parallel Processing**: Process multiple papers simultaneously (5-10x faster)
- 📚 **Zotero Integration**: Direct API access, supports journal articles, preprints, and conference papers
- 🤖 **AI Summaries**: Korean language summaries with GPT-4o-mini or Gemini
- 📁 **Smart Organization**: Mirrors Zotero collection structure
- 🔄 **Auto-Sync**: Automatic background synchronization with macOS launchd
- 📊 **Progress Tracking**: Real-time progress with checkpoint saves
- 🔁 **Resume Support**: Continue from interruptions

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your API keys

# Process all papers (fast mode)
python scripts/run_literature_batch.py --workers 10

# Process specific collection
python scripts/run_literature_batch.py --collection "TYK2" --limit 50
```

## Performance Tips

For processing hundreds of papers:

```bash
# Maximum speed (10 parallel workers + skip PDF downloads)
python scripts/run_literature_batch.py --workers 10 --no-pdf-download

# Balanced (5 workers with PDF downloads)
python scripts/run_literature_batch.py --workers 5

# Skip GPT for metadata-only extraction
python scripts/run_literature_batch.py --skip-gpt --workers 10
```

## Auto-Sync Setup (macOS)

Automatically sync Zotero changes every 30 minutes:

```bash
# Configure and install
bash scripts/setup_plist.sh

# Or manually sync anytime
python scripts/zotero_auto_sync.py
```

## Core Scripts

- `run_literature_batch.py` - Main batch processing
- `zotero_auto_sync.py` - Automatic synchronization
- `sync_checker.py` - Compare Zotero vs Obsidian
- `sync_executor.py` - Execute sync operations
- `process_single_pdf.py` - Process individual PDFs
- `process_zotero_pdf.py` - Process Zotero storage PDFs

## Documentation

- [CLAUDE.md](CLAUDE.md) - Detailed documentation and commands
- [docs/AUTO_SYNC_SETUP.md](docs/AUTO_SYNC_SETUP.md) - Auto-sync configuration
- [docs/SETUP_ON_ANOTHER_MAC.md](docs/SETUP_ON_ANOTHER_MAC.md) - Multi-machine setup