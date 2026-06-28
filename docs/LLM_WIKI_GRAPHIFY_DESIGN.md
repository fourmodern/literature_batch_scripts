# LLM Wiki + Graphify Design for Zotero–Obsidian Literature Workflow

_Last updated: 2026-05-04_

## 1. Goal

This document proposes a safe, incremental design for combining:

- Zotero as the canonical literature library
- `~/literature_batch_scripts` as the existing Zotero → PDF/metadata/summary → Obsidian pipeline
- Obsidian as the human-facing knowledge workspace
- Graphify-style graph extraction as a machine-readable relation layer
- LLM-wiki as a curated, Markdown-native research knowledge layer

The main goal is not to replace the current pipeline, but to add a second layer that turns accumulated paper notes into connected research knowledge.

## 2. Current Known Environment

### Repository

```text
~/literature_batch_scripts
```

This repository already supports:

- Zotero API integration
- PDF download/extraction
- GPT/Gemini summarization
- Obsidian-compatible Markdown output
- RAG/vector database construction
- sync checking between Zotero and Obsidian

### Active Obsidian Vault

```text
~/Library/Mobile Documents/iCloud~md~obsidian/Documents/<username>
```

Relevant existing folders include:

```text
80. References/81. zotero/
80. References/83. wiki/
04. 논문/zotero/
```

## 3. Design Principle

Do **not** modify existing Zotero records or existing Obsidian paper notes during the first implementation.

Instead, create derived artifacts under:

```text
80. References/83. wiki/
```

This keeps the experiment reversible. If the generated wiki or graph is poor, the derived folder can be deleted or regenerated without damaging the source notes.

## 4. Layered Architecture

```text
Zotero
  ↓
Existing literature_batch_scripts pipeline
  ↓
Obsidian paper notes
  ↓
Graphify layer
  ↓
LLM Wiki layer
  ↓
Human research synthesis / review / slides / hypotheses
```

## 5. Proposed Folder Structure

Inside the active Obsidian vault:

```text
80. References/83. wiki/
├── _graph/
│   ├── graph.json
│   ├── graph.md
│   ├── entity_index.md
│   ├── relation_index.md
│   └── runs/
│       └── YYYY-MM-DD_HHMM/
├── Concepts/
├── Papers/
├── Methods/
├── Datasets/
├── Diseases/
├── Drugs_Targets/
├── Pathways/
└── Questions/
```

### `_graph/`

Machine-readable and audit artifacts.

- `graph.json`: canonical node/edge graph
- `graph.md`: human-readable graph summary
- `entity_index.md`: sorted index of entities
- `relation_index.md`: sorted index of relation types
- `runs/`: timestamped snapshots for debugging and comparison

### Topic folders

Human-readable LLM-wiki pages grouped by entity type.

Examples:

```text
Concepts/TYK2.md
Methods/spatial transcriptomics.md
Drugs_Targets/deucravacitinib.md
Diseases/psoriasis.md
Pathways/JAK-STAT.md
Questions/TYK2 unresolved questions.md
```

## 6. Data Flow

### Step 1. Zotero → paper notes

Use the existing pipeline, for example:

```bash
python scripts/run_literature_batch.py --workers 5 --limit 50
```

or collection-specific:

```bash
python scripts/run_literature_batch.py --collection "TYK2" --limit 50
```

### Step 2. Paper notes → graph extraction

A new script should read existing paper notes from the Obsidian vault and extract:

- papers
- concepts
- methods
- diseases
- drugs
- targets
- pathways
- datasets
- key claims
- unresolved questions

Proposed script:

```text
scripts/build_llm_wiki_graph.py
```

Expected output:

```text
80. References/83. wiki/_graph/graph.json
80. References/83. wiki/_graph/entity_index.md
80. References/83. wiki/_graph/relation_index.md
```

### Step 3. Graph → LLM-wiki pages

A second pass generates or updates Markdown pages for important entities.

Proposed script:

```text
scripts/build_llm_wiki_pages.py
```

Expected output:

```text
80. References/83. wiki/Concepts/*.md
80. References/83. wiki/Methods/*.md
80. References/83. wiki/Drugs_Targets/*.md
...
```

## 7. Node Schema

Suggested `graph.json` node format:

```json
{
  "id": "concept:tyk2",
  "type": "concept",
  "name": "TYK2",
  "aliases": ["Tyrosine kinase 2"],
  "source_notes": ["[[Paper Note A]]", "[[Paper Note B]]"],
  "evidence_count": 2,
  "created_at": "2026-05-04T00:00:00+09:00",
  "updated_at": "2026-05-04T00:00:00+09:00"
}
```

Recommended node types:

- `paper`
- `concept`
- `method`
- `dataset`
- `disease`
- `drug`
- `target`
- `pathway`
- `claim`
- `question`
- `author`
- `collection`

## 8. Edge Schema

Suggested `graph.json` edge format:

```json
{
  "source": "paper:smith-2024-tyk2",
  "target": "concept:tyk2",
  "relation": "studies",
  "evidence": "The paper evaluates TYK2 inhibition in inflammatory disease models.",
  "source_note": "[[Smith 2024 TYK2 inhibition]]",
  "confidence": "medium"
}
```

Recommended relation types:

- `studies`
- `uses_method`
- `uses_dataset`
- `reports_biomarker`
- `targets`
- `inhibits`
- `activates`
- `associated_with`
- `supports`
- `contradicts`
- `extends`
- `reviews`
- `raises_question`
- `belongs_to_collection`

## 9. LLM-wiki Page Template

```markdown
---
type: llm-wiki
entity_type: concept
entity: TYK2
aliases:
  - Tyrosine kinase 2
updated: 2026-05-04
sources:
  - [[Paper Note A]]
  - [[Paper Note B]]
graph_id: concept:tyk2
---

# TYK2

## One-line summary

## Core concept

## Evidence from papers

- [[Paper Note A]] — brief evidence summary
- [[Paper Note B]] — brief evidence summary

## Connected entities

- Diseases: [[psoriasis]], [[IBD]]
- Drugs/targets: [[deucravacitinib]], [[JAK inhibitors]]
- Pathways: [[JAK-STAT]]

## Open questions

## Notes for future review
```

## 10. Safety and Quality Rules

1. Generated wiki pages must cite source notes.
2. Do not state unsupported conclusions as facts.
3. Keep uncertainty explicit.
4. Prefer small updates over rewriting large pages.
5. Preserve manual notes if a page has human-edited sections.
6. Keep generated sections clearly marked if needed.
7. Start with a small collection before full-vault processing.

## 11. Recommended First Experiment

Use one focused collection, not the whole library.

Good candidates:

- `TYK2`
- `AIDD`
- `LNP`

Initial target:

- 20–50 paper notes
- 100–300 extracted entities
- 5–10 generated wiki pages

Success criteria:

- Entity extraction is not too noisy
- Wiki pages are useful to read in Obsidian
- Links between papers/concepts are meaningful
- The system can be regenerated without damaging source notes

## 12. Proposed Implementation Phases

### Phase 0 — Dry-run inventory

- Locate active Obsidian vault
- Locate candidate paper-note directories
- Count notes by folder/collection
- Produce a dry-run report only

### Phase 1 — Graph prototype

Create:

```text
scripts/build_llm_wiki_graph.py
```

Features:

- read selected paper notes
- extract metadata/frontmatter where available
- identify candidate entities using rules + optional LLM
- write `graph.json`
- write `entity_index.md`

### Phase 2 — Wiki prototype

Create:

```text
scripts/build_llm_wiki_pages.py
```

Features:

- read `graph.json`
- choose top entities by evidence count
- generate wiki pages from source notes
- write only under `80. References/83. wiki/`

### Phase 3 — Obsidian integration

- Add backlinks from wiki pages to paper notes
- Optionally add lightweight links from paper notes to wiki pages
- Keep this optional until generated pages are trusted

### Phase 4 — Scheduled maintenance

- Run after Zotero sync
- Detect newly added/changed notes
- Update graph and selected wiki pages
- Keep timestamped snapshots under `_graph/runs/`

## 13. Open Questions

- Which Obsidian folder should be the canonical source of paper notes: `80. References/81. zotero/` or `04. 논문/zotero/`?
- Which Zotero collections should be tested first?
- Should the first extractor be rule-based, LLM-based, or hybrid?
- Should generated wiki pages be Korean, English, or bilingual?
- Should graph output target Obsidian only, or also external graph tools later?

## 14. Recommendation

Start with a conservative prototype:

1. Pick one collection, preferably `TYK2` or another narrow research theme.
2. Generate a dry-run graph report only.
3. Review entity noise and relation quality.
4. Generate 5–10 wiki pages under `80. References/83. wiki/`.
5. Only after quality is acceptable, consider automatic updates.

This approach preserves the current Zotero–Obsidian workflow while adding a reversible, inspectable knowledge-graph and LLM-wiki layer.
