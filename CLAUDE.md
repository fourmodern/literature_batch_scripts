# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Purpose

A comprehensive literature processing system with two main capabilities:
1. **Batch Processing**: Extracts metadata and PDFs from Zotero, generates AI summaries using GPT or Gemini, and creates Obsidian-compatible markdown notes
2. **RAG System**: Builds searchable vector databases from academic papers for semantic search and question-answering

Optimized for Korean-language academic paper summarization but adaptable for other languages. Supports both text-only (GPT) and multimodal (Gemini/CLIP) processing for papers with important figures and images.

## Quick Reference

### Most Common Commands
```bash
# Standard workflow: Process new papers
python scripts/run_literature_batch.py --workers 5 --limit 50

# Check sync status and process missing papers
python scripts/sync_checker.py --output sync_report.json
python scripts/process_missing_papers.py --from-json sync_report.json

# Build RAG database for semantic search
python scripts/build_all_fast.py

# Test extraction on specific collection
python scripts/test_pdf_extraction.py "CollectionName"
```

## Section Index

The full documentation is split into focused subdocs (each under 200 lines). Claude Code loads them via the `@import` references below.

| Section | File | Contents |
|---------|------|----------|
| Commands | `docs/claude/commands.md` | Setup, env config, pipeline, single PDF, RAG commands, CLI args |
| Architecture | `docs/claude/architecture.md` | Pipelines, design decisions, module responsibilities |
| Data Flow | `docs/claude/data-flow.md` | Critical data flow, thread safety, error handling |
| Troubleshooting | `docs/claude/troubleshooting.md` | PDF extraction, sync workflow, PDF downloads |
| Debugging | `docs/claude/debugging.md` | Common debugging scenarios with copy-paste commands |
| Development | `docs/claude/development.md` | Coding conventions, adding features, template, structure, performance |
| RAG Config | `docs/claude/rag-config.md` | Vector DBs, embeddings, chunking, migration |

@docs/claude/commands.md
@docs/claude/architecture.md
@docs/claude/data-flow.md
@docs/claude/troubleshooting.md
@docs/claude/debugging.md
@docs/claude/development.md
@docs/claude/rag-config.md
