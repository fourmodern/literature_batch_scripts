# Code Review — 2026-05-04

**Reviewer:** `oh-my-claudecode:code-reviewer` (Opus)
**Scope:** Core literature processing pipeline (14 files)
**Verdict:** REQUEST CHANGES — 5 Blocker + 8 High issues found

## Files Reviewed

- `scripts/run_literature_batch.py` — main orchestrator
- `scripts/utils.py` — checkpoint, logging, done.txt
- `scripts/zotero_fetch.py` — pyzotero API client
- `scripts/text_extractor.py` — PDF text + image extraction
- `scripts/zotero_path_finder.py` — cross-platform Zotero dir detection
- `scripts/pdf_downloader.py` — Zotero file API downloads
- `scripts/gpt_summarizer.py` — OpenAI calls + retries + cache
- `scripts/gemini_summarizer.py` — Gemini multimodal
- `scripts/markdown_writer.py` — Jinja2 rendering
- `scripts/process_single_pdf.py`
- `scripts/process_zotero_pdf.py`
- `scripts/api_cost_optimizer.py` (read for cache-key analysis)
- `templates/literature_note.md`
- `.env.example`
- `requirements.txt`

> ⚠️ **Note on accuracy:** Findings are from static analysis. Line numbers and exact behavior should be **verified against current code** before patching — the reviewer occasionally misreads control flow.

---

## 🔴 BLOCKER (5)

### B1 — Path traversal: filename derived from Zotero `title` not anchored to output dir
**File:** `scripts/run_literature_batch.py:466-467` (and `process_zotero_pdf.py:158, 270-280`)
**What:** `safe_filename` is computed via `"".join(c for c in title if c.isalnum() or c in ' -_')[:80]`, then plugged into `os.path.join(folder_path, f"{safe_filename}_{key}.md")`. `collection_path` from Zotero is split by `os.sep` and each part is passed to `sanitize_folder_name()`, but that function only strips `/ \ : * ? " < > |`. A Zotero collection named `..` or `... /etc` would walk above `output_dir`.
**Why it matters:** Zotero collection names are user-controlled (esp. shared groups). With `--copy-pdfs`, this includes binary PDFs.
**Fix:**
```python
def sanitize_folder_name(name):
    name = name.replace('/', '-').replace('\\', '-').replace(':', '-')
    for c in '*?"<>|':
        name = name.replace(c, '')
    name = name.strip().strip('.')
    if name in ('', '.', '..'):
        name = '_'
    return name
```
Also add a containment check after constructing `file_path`:
```python
abs_out = os.path.realpath(output_dir)
abs_file = os.path.realpath(file_path)
if not abs_file.startswith(abs_out + os.sep):
    raise ValueError(f"Refusing to write outside output dir: {file_path}")
```

### B2 — `is_done()` reads entire `done.txt` on every call: O(N²) + race window
**File:** `scripts/utils.py:28-34`
**What:** Every worker calls `is_done(key)` (read `done.txt`, linear scan). N=10k → 100M line scans. Worse, `is_done()` is called *outside* `done_lock` while `mark_done()` is called *inside*. Two workers can both observe `is_done=False` for the same key, causing duplicate GPT spend.
**Fix:** Cache `done.txt` once into a module-level set behind the same lock as `mark_done`:
```python
_done_cache = None
_done_cache_lock = Lock()

def _load_done_cache(done_file):
    global _done_cache
    with _done_cache_lock:
        if _done_cache is None:
            if os.path.exists(done_file):
                with open(done_file) as f:
                    _done_cache = set(line.strip() for line in f if line.strip())
            else:
                _done_cache = set()

def is_done(key, done_file=None):
    done_file = done_file or os.path.join(PROJECT_ROOT, 'logs', 'done.txt')
    _load_done_cache(done_file)
    return key in _done_cache

def mark_done(key, done_file=None):
    done_file = done_file or os.path.join(PROJECT_ROOT, 'logs', 'done.txt')
    os.makedirs(os.path.dirname(done_file), exist_ok=True)
    with _done_cache_lock:
        if key in _done_cache:
            return
        _done_cache.add(key)
        with open(done_file, 'a') as f:
            f.write(key + '\n')
```

### B3 — Hard API failures returned as sentinel string → paper still marked done
**File:** `scripts/gpt_summarizer.py:65-69, 168, 175, 182`
**What:** When rate-limit / timeout / connection retries are exhausted, the function returns `"[Rate limit exceeded - summary unavailable]"`. In `run_literature_batch.py:368, 388-389`, this string is treated as a normal summary, written to markdown, and the paper is **marked done** in `done.txt` (line 506-507). User pays for nothing and loses retry signal forever.
**Fix:** Raise an exception on terminal failure and skip `mark_done()`:
```python
class SummarizationFailed(Exception):
    pass

# in summarize_text_with_retry, on terminal failure:
raise SummarizationFailed(f"Rate limit exceeded after {max_retries} retries")

# in process_item:
try:
    short_summary, long_summary = generate_short_long(text, title)
except SummarizationFailed as e:
    log.error(f"GPT failed for {key}, NOT marking as done: {e}")
    return False
```

### B4 — `.env.example` modified + uses `sk-xxxx` placeholder
**File:** `.env.example:2`
**What:** Recognizable OpenAI key prefix `sk-xxxx` invites copy-paste mistakes. `.env.example` is currently `M` in `git status`. If a real key gets pasted into `.env.example` instead of `.env`, it would commit.
**Fix:** Verify `.env` is in `.gitignore` and use unambiguous placeholders:
```
OPENAI_API_KEY=<paste-your-key-here>
GEMINI_API_KEY=<paste-your-key-here>
ZOTERO_API_KEY=<paste-your-key-here>
```

### B5 — Duplicate logger handlers on every `setup_logger()` call
**File:** `scripts/utils.py:12-19`
**What:** `logging.getLogger(name)` returns a singleton, but `addHandler(fh)` is called unconditionally. Each subsequent invocation adds another `FileHandler` → duplicated log lines, leaked file descriptors. `process_single_pdf.py:84` and `process_zotero_pdf.py:111` call from function bodies → vulnerable in any future "process directory of PDFs" wrapper.
**Fix:**
```python
def setup_logger(name, log_file, level=logging.INFO):
    logger = logging.getLogger(name)
    logger.setLevel(level)
    if not logger.handlers:
        fh = logging.FileHandler(log_file)
        fh.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        logger.addHandler(fh)
    logger.propagate = False
    return logger
```

---

## 🟠 HIGH (8)

### H6 — Cache key truncates input to 1000 chars → false cache hits
**File:** `scripts/api_cost_optimizer.py:44-47`
**What:** `content = f"{model}:{prompt}:{text[:1000]}"`. Two papers with identical first-1000-character intros (very common in same-journal preambles or arXiv headers) collide → second paper gets first paper's summary.
**Why it matters:** Silent cross-contamination on Korean batch runs. Hard to detect.
**Fix:** Hash the entire text:
```python
def get_cache_key(self, text, prompt, model):
    h = hashlib.sha256()
    h.update(model.encode())
    h.update(b'\x00')
    h.update(prompt.encode())
    h.update(b'\x00')
    h.update(text.encode())
    return h.hexdigest()
```

### H7 — `figure_captions` / `table_captions` undefined under specific control flow
**File:** `scripts/run_literature_batch.py:285-296, 425-426, 344-346`
**What:** Locals only set inside the `if EXTRACT_IMAGES` branch when `pdf_path` valid AND no exception before line 279. The `'figure_captions' in locals()` check is a band-aid hiding fragility. Under PDF-extraction-throws-after-line-268, `UnboundLocalError`.
**Fix:** Initialize at top of `process_item` next to `text = ''`:
```python
figure_captions = []
table_captions = []
```

### H8 — Image output dir keyed by sanitized title → race when titles collide
**File:** `scripts/run_literature_batch.py:273` and `text_extractor.py:271-275`
**What:** Two papers with the same sanitized title ("Editorial", "Erratum", "Letter to the editor") write images to the same folder concurrently. `pix.save(img_path)` and `f.write(img_data)` overwrite each other.
**Fix:** Include the Zotero key:
```python
img_output_dir = os.path.join(output_dir, "img", f"{sanitize_folder_name(title)}_{key}")
```

### H9 — `setup_logger` does not set `propagate=False` → duplicate output if root logger configured
**File:** `scripts/utils.py:12-19`
**Fix:** `logger.propagate = False` after handler is added (folded into B5 fix).

### H10 — Bare `except:` catches `KeyboardInterrupt` / `SystemExit`
**Files:**
- `scripts/zotero_fetch.py:140, 218, 357`
- `scripts/utils.py:54`
- `scripts/zotero_path_finder.py:93`
- `scripts/text_extractor.py:92`

**What:** CLAUDE.md guarantees graceful Ctrl+C, but bare `except:` swallows `KeyboardInterrupt` mid-pagination.
**Fix:** Replace all bare `except:` with `except Exception:`.

### H11 — Wrong exception class caught → 404 retry path is dead code
**File:** `scripts/pdf_downloader.py:30-78`
**What:** `pyzotero.zotero.Zotero.file()` raises `pyzotero.zotero_errors.*`, not `requests.exceptions.HTTPError`. The `HTTPError` block is dead. Real 404s consume 3 retries × wait time per missing file.
**Fix:**
```python
from pyzotero import zotero_errors
...
except zotero_errors.ResourceNotFound:
    return False
except zotero_errors.HTTPError as e:
    if getattr(e, 'status_code', None) == 429:
        ...
```

### H12 — Template rendered up to 3× with mutating context
**File:** `scripts/run_literature_batch.py:454, 488, 499`
**What:** `--copy-pdfs` branch mutates `context['pdf_path']` → re-renders. If the second render fails, stale first-render `md_content` is written. Also `include_ai_links=True` arg is misleading dead code (`render_note` ignores it).
**Fix:** Compute final `pdf_path` once before any render call, then render exactly once.

### H13 — Char-count truncation undercounts Korean tokens
**File:** `scripts/gpt_summarizer.py:74-81` and `gemini_summarizer.py:29-31, 97-99`
**What:** Truncation at 28k–30k chars (gpt) or 800k chars (gemini) uses character count. Korean Hangul is denser per-char than Latin; "30k char" Korean paper can be 70k+ tokens, exceeding gpt-4o-mini's 128k context with the prompt. Mid-batch BadRequestError → sentinel string returned (see B3).
**Fix:** Use `tiktoken` for OpenAI and Gemini token-counting API. Or be conservative for CJK:
```python
korean_chars = sum(1 for c in text[:1000] if '가' <= c <= '힣')
max_chars = 8000 if korean_chars > 100 else 28000
```

---

## 🟡 MEDIUM (11)

### M14 — Two divergent keyword parsers
**File:** `run_literature_batch.py:95-163` vs `process_zotero_pdf.py:188-215`
**What:** `parse_keywords_response` (run_literature_batch) handles Korean detection, English fallback, length filtering. `process_zotero_pdf` re-implements a much weaker parser inline with hardcoded special cases ("systems", "multi", "virtual" prefixes return canned lists).
**Fix:** Extract `parse_keywords_response` into `utils.py` and import in both.

### M15 — Hardcoded magic numbers in `text_extractor.py`
**File:** `text_extractor.py:247, 252, 258`
**What:** `200×200` min image size, `400` first-page height threshold, `0.2 / 5` aspect ratio. Korean chemistry/biology papers with smaller diagrams get silently dropped.
**Fix:** Hoist to module-level named constants.

### M16 — `print()` corrupts tqdm progress bar; missing from log file
**Files:** `text_extractor.py:29, 35, 38, 43, 49, 52` (and more); `pdf_downloader.py:59, 63, 71, 76`
**Fix:** Use `logging.getLogger(__name__)` at module top.

### M17 — `process_single_pdf` has parallel `metadata` and `item` dicts
**File:** `process_single_pdf.py:129-134, 149-172`
**What:** Two parallel dicts; `metadata['authors']`, `'year'`, `'keywords'` are initialized as defaults but never populated from PDF text. Notes silently produced with empty author lists.
**Fix:** Populate all metadata fields from PDF text in `extract_metadata_from_pdf`, or remove unused defaults.

### M18 — Validation rejects Korean-only papers (the core user persona)
**File:** `run_literature_batch.py:312-323`
**What:** `2 <= avg_word_length <= 30` check fails for CJK content (split words very short). `ascii_ratio >= 0.5` fails for Korean papers with mostly Hangul. The validation that's *supposed* to be lenient for Korean academic users is the opposite.
**Fix:** Detect language first; skip ASCII/word-length check for CJK text.

### M19 — Tight version pins miss security patches
**File:** `requirements.txt`
**What:** `jinja2==3.1.3`, `pdfplumber==0.10.4`, `tqdm==4.66.2`, `python-dotenv==1.0.1` exact pins. Jinja2 has had security patches in 3.1.4+.
**Fix:** Use compatible-release pins where security matters:
```
jinja2>=3.1.4,<4.0
pdfplumber>=0.10.4,<0.12
```

### M20 — `gemini_summarizer.summarize_with_images` reads images unbounded
**File:** `gemini_summarizer.py:126-141`
**What:** Loops `images[:5]` reading each fully. With `Matrix(2,2)` zoom in `text_extractor.py:310`, single PNG can be 50MB → 5 images × 5 workers → 1.25GB peak RSS.
**Fix:** `os.path.getsize()` check before read; skip > 5MB or downscale.

### M21 — `process_zotero_pdf.py:247` uses `collection_path` outside its init scope
**File:** `process_zotero_pdf.py:148-153, 247`
**What:** Set inside `if item['collections']:`. Used later under a different conditional. NameError if check order changes.
**Fix:** Initialize `collection_path = ''` at function top.

### M22 — Exception strings printed in logs may leak API keys
**File:** `gpt_summarizer.py:179, 198`
**What:** OpenAI SDK exceptions sometimes include request URL/headers in `__repr__`. `print(f"[Connection] {e} → ...")` may leak bearer token to logs.
**Fix:** Use `print(f"[Connection] {type(e).__name__} → ...")`.

### M23 — Skipped papers count as successes
**File:** `run_literature_batch.py:227-229, 691-694`
**What:** `is_done(key)=True` returns `True`, bumping `success_count`. "Successfully processed: N papers" includes skips.
**Fix:** Tri-state return (`'skipped'`, `True`, `False`); track skips separately.

### M24 — Massive Jinja2 keyword sanitization chain
**File:** `templates/literature_note.md:11-14`
**What:** Unmaintainable chain of `replace()` calls. `length > 1` accepts 2+ char keywords, `length < 50` accepts 49-char keywords. Different from `process_zotero_pdf` parser.
**Fix:** Move all sanitization into `sanitize_keywords` (Python). Template iterates clean keywords only.

---

## 🟢 LOW (7)

### L25 — `try: import pdfplumber` swallows non-ImportError
**File:** `text_extractor.py:9-13`
**Fix:** Use `except ImportError:` specifically.

### L26 — Tags in template don't deduplicate
**File:** `templates/literature_note.md:1-16`
**Fix:** Deduplicate keywords/collections before passing to template.

### L27 — Hardcoded `reasoning={"effort": "medium"}` for gpt-5
**File:** `gpt_summarizer.py:122`
**What:** If GPT-5 variant doesn't accept this, the `responses.create` call fails → sentinel returned → paper marked done.
**Fix:** Make conditional or env-driven.

### L28 — `get_collection_key_by_name` ambiguous match
**File:** `zotero_fetch.py:60-83`
**What:** Multiple matches → first-wins (depends on Zotero API order). Warns but proceeds.
**Fix:** Raise with list of matches; user disambiguates.

### L29 — `extract_metadata_from_pdf` title heuristic picks journal header
**File:** `process_single_pdf.py:30-36`
**What:** First 20–200 char line often is "Nature Reviews Drug Discovery | Vol 23 | March 2024".
**Fix:** Try `doc.metadata.get('title')` first; fall back to heuristic.

### L30 — `nl2br` filter outputs raw `<br>` HTML in markdown
**File:** `markdown_writer.py:24-28`
**What:** Breaks non-Obsidian markdown viewers (Pandoc, GitHub).
**Fix:** Use markdown's two-space line break or backslash + newline.

### L31 — `extract_year` regex picks first 4-digit year
**File:** `zotero_fetch.py:8-13`
**What:** `"published online 2024, originally 2003"` → `'2003'`.
**Fix:** Take last match or `max()`.

---

## Top 5 to Fix First

1. **B3 — GPT failures silently mark papers as done.** Highest user-facing $ cost.
2. **H6 — Cache key uses only first 1000 chars.** Silent correctness risk on same-journal batches.
3. **B1 — Path traversal via Zotero collection names.** Security.
4. **B2 — `is_done()` unlocked + O(N²).** Concurrency + perf.
5. **H7 — `figure_captions` UnboundLocalError.** Reliability.
