# Implementation brief — `scripts/prepare_knowledge_base.py`

Not written yet. Realistically 200–300 lines of stdlib Python. It carries **no rubric row of its
own**, yet it produces every artifact worth 35 points.

Splitting rules referenced below are owned by [`05-chunking-strategy.md`](05-chunking-strategy.md);
field rules by [`06-chunk-schema.md`](06-chunk-schema.md). **Resolve
[`09-open-defects.md`](09-open-defects.md) D1 and D2 before writing `merge_short`.**

## Dependencies

Standard library only: `argparse`, `json`, `os`, `pathlib`, `re`, `unicodedata`, `dataclasses`,
`sys`. Requires Python ≥ 3.9. `requirements.txt` stays empty.

The corpus is 100% self-authored Markdown by design, so the loader is markdown-only — no
HTML/PDF/plaintext readers for inputs that cannot occur.

## Data model

```python
from dataclasses import dataclass

@dataclass
class Config:
    raw_dir: Path
    out_path: Path
    chunk_size: int = 800      # target, measured on the body
    overlap: int = 150
    min_chunk: int = 500
    hard_cap: int = 1000       # measured on the final text, breadcrumb included
    dry_run: bool = False
    verbose: bool = False

@dataclass
class Doc:
    document_id: str
    source_file: str
    source_type: str           # "markdown"
    title: str
    language: str              # "en"
    domain: str                # "logistics-engineering"
    document_type: str
    sections: list[tuple[str, str]]   # [(header, body), ...]

@dataclass
class ValidationReport:
    docs: int
    chunks: int
    len_min: int
    len_avg: float
    len_max: int
    per_doc: dict[str, int]
    warnings: list[str]
    errors: list[str]
```

A chunk is emitted as a plain dict matching [`assets/chunk.schema.json`](assets/chunk.schema.json)
exactly — do not wrap it in a dataclass, since it is serialized verbatim.

## Functions, in pipeline order

### `discover_raw_files(raw_dir: Path) -> list[Path]`
Glob `data/raw/*.md`, sorted by name for determinism.
**Errors:** fewer than 3 files → exit non-zero with a clear message (the spec requires ≥3).

### `normalize_text(text: str) -> str`
NFC-normalize · strip HTML comments · collapse 3+ blank lines to 2 · strip trailing spaces ·
line endings → `\n`.

### `read_markdown(text: str) -> tuple[str, list[tuple[str, str]]]`
Split on ATX headers H1–H3 (`^#{1,3}\s`), skipping heading-like lines inside ``` code fences.
**Returns** `(title, sections)`. The first H1 is the title; body before the first H2 is emitted as
a section named `"Introduction"`; H2/H3 headings name their own sections.

### `load_document(path: Path) -> Doc`
Read → `normalize_text` → `read_markdown` → assemble the `Doc`.
`document_id = re.sub(r"[^a-z0-9]+", "_", path.stem.lower()).strip("_")`.
**Errors:** empty file → diagnostic error, never a silent zero-chunk pass.

### `split_section(body: str, max_chars: int = 800, overlap: int = 150) -> list[str]`
Recursive fallback splitter on `["\n\n", "\n", ". ", " "]` — paragraph → line → sentence → word
boundary, never mid-word. A raw character cut only for a single token longer than `max_chars`.
Greedy-packs up to `max_chars`, carrying `overlap` tail characters into the next piece.
Overlap is within-section only.

### `merge_short(pieces: list[str], min_chars: int = 500, cap: int = 1000) -> list[str]`
Merges undersized fragments **forward**, and a document's final short piece **backward**, only
while the merged piece stays ≤ `cap`. The caller passes `cap = 1000 − len(breadcrumb)`, so the cap
is prefix-aware. On a within-section merge, strips the later piece's leading overlap carry — only
when it actually repeats the predecessor's tail. A cross-section merge has no carry, so nothing
is stripped.

### `chunk_document(doc: Doc, cfg: Config) -> list[dict]`
Header-aware pass: split per section (section name → `metadata.section`), run `merge_short` over
the document's piece stream with the prefix-aware cap (merged chunks keep the **first** section's
name), prepend the breadcrumb, assign 1-based `chunk_index` and
`chunk_id = f"{document_id}_chunk_{i:03d}"`.

### `write_jsonl(chunks: list[dict], out_path: Path) -> None`
Atomic write — temp file + `os.replace`. One `json.dumps(ensure_ascii=False)` per line.

### `validate(out_path: Path, cfg: Config) -> ValidationReport`
Re-reads the written file line by line. Rules:

| # | Rule | Severity | Exit | Message |
|---|---|---|---|---|
| 1 | Line parses as JSON | hard | ≠0 | `line {n}: invalid JSON` |
| 2 | All 5 required fields present and non-empty | hard | ≠0 | `line {n}: missing field {name}` |
| 3 | `chunk_id` unique | hard | ≠0 | `duplicate chunk_id: {id}` |
| 4 | `chunk_index` contiguous 1..N within its `document_id` | hard | ≠0 | `{doc}: chunk_index gap at {i}` |
| 5 | `len(text) <= 1000` (breadcrumb included) | hard | ≠0 | `{id}: text {n} chars exceeds 1000` |
| 6 | Body ≥ 500 chars | **soft** | 0 | `{id}: {n}-char residual (merge policy)` |

Returns stats: document count, chunk count, length min/avg/max, per-document counts, warnings.

### `main(argv: list[str]) -> int`
`argparse` → discover → load → normalize → chunk → write → validate → print summary.
Non-zero exit on hard validation failure; soft warnings are reported with exit 0.

## CLI

```bash
python scripts/prepare_knowledge_base.py \
  --raw-dir data/raw --out data/processed/chunks.jsonl \
  --chunk-size 800 --overlap 150 --min-chunk 500 [--dry-run] [--verbose]
```

## Idempotency

Output is a pure function of (raw files, config): deterministic file ordering, IDs derived from
filename stem + index — no UUIDs, no timestamps — and a full atomic overwrite. Rerunning on
unchanged input yields a **byte-identical** file. No append mode, no partial state.

## Error-handling stance

Surface real errors; never mask them with an empty result. Fewer than 3 source files, an empty
document, or a hard validation failure must each exit non-zero with a diagnostic message. A
zero-chunk run is never a silent success.
