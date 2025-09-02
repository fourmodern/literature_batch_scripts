# Literature Batch Processing System

A high-performance batch processing system that extracts metadata and PDFs from Zotero, generates AI summaries using GPT, and creates Obsidian-compatible markdown notes.

## Features

- 🚀 **Parallel Processing**: Process multiple papers simultaneously (5-10x faster)
- 📚 **Zotero Integration**: Direct API access, no export files needed
- 🤖 **AI Summaries**: Korean language summaries with GPT-4o-mini
- 📁 **Smart Organization**: Mirrors Zotero collection structure
- 🔄 **Resume Support**: Continue from interruptions
- 📊 **Progress Tracking**: Real-time progress with checkpoint saves

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

## Documentation

See [CLAUDE.md](CLAUDE.md) for detailed documentation and troubleshooting.