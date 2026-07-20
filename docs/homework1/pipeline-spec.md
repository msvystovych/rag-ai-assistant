# Pipeline spec — chunking rules, chunk contract, and `scripts/prepare_knowledge_base.py`

**This file is the sole owner of every splitting rule and every chunk field.** If a rule about size,
overlap, merging, section derivation, or metadata appears anywhere else in this repository, it is a
copy — change it here first. One sanctioned copy exists: the *Chunking strategy* section of the
repo-root `README.md`, because `spec:62` requires the README to describe the strategy.

---

## Open decisions — settle these before writing `merge_short`

Two contradictions survive from the original blueprint. Both change what the code does.

### D1 · Sub-500 residuals are structurally unavoidable *(affects the 15-point chunking row)*

The blueprint claimed `min_chunk: 500` "keeps every non-terminal chunk inside the spec band" and
that backward-merging a document's final piece "eliminates sub-500 residuals entirely." It cannot
hold. `merge_short` merges undersized pieces **forward**, and reserves backward merging for a
document's **final** piece only. Work an ordinary case:

- A 900-char section packs to one 800-char piece plus a ~250-char tail (100 net + the 150-char overlap carry).
- Forward merge: 250 + the next section's 800 = 1050, which exceeds the prefix-aware cap (~914 after an 86-char breadcrumb). **Fails.**
- Backward merge: strip the 150 carry → 100 net; 800 + 100 = 900; + 86 breadcrumb = 986 ≤ 1000. **Would fit — but is forbidden**, because this isn't the document's final piece.

So the tail is emitted at ~250 chars. Any section between roughly 800 and 1300 characters produces
one — the common case, not the exception.

**Recommended:** allow backward merge for **any** within-section terminal residual, not just the
document's last piece, under the same prefix-aware ≤1000 cap. Two lines in `merge_short`'s
eligibility test; eliminates the bulk of residuals without weakening any cap.

**If you decline:** keep current behaviour, delete the "eliminates sub-500 residuals entirely"
phrasing, and report the residual count honestly in the README Conclusions — `spec:29` constrains
the `chunk_size` *parameter*, not every emitted chunk, and the spec's own sample chunk is 154
characters.

### D1b · Forward-merge scope is stated at two different granularities

The merge-rules table below says a short **section** merges forward into the next sibling section.
`merge_short`'s contract says it merges undersized **fragments** forward. A within-section terminal
residual is a short *piece* but not a short *section* — exactly the case D1 argues about. Decide
which granularity `merge_short` operates on and make both statements match before implementing.

### D2 · The overlap assertion contradicts the merge rule

A proposed test and a grader-facing README note both assert that consecutive same-section chunks
share 100–200 characters. But the merge rule **strips** the overlap carry before concatenating,
producing same-section pairs that share **zero**.

**Recommended:** treat merge-produced pairs as a fourth legitimate zero-overlap case — already
applied to the zero-overlap list below. The alternative (keeping the carry inside merged chunks)
duplicates ~150 characters in the retrieval index.

### D3 · Heading casing

Headings are copied verbatim into `metadata.section` and into the breadcrumb, so whatever case you
write in `data/raw/` is what lands in the output. The reference samples use Title Case; the outlines
in [`corpus-plan.md`](corpus-plan.md) use sentence case. Pick one when authoring and stay
consistent. Both are graded on readability, not casing.

---

## Chunking strategy

### Method

**Header-aware section splitting with a recursive character-splitting fallback.** Stdlib Python; no
LangChain.

1. **Parse into sections** by ATX headings (`#`, `##`, `###`). Heading-like lines inside ``` code
   fences are ignored.
2. **Split oversized sections** recursively on `["\n\n", "\n", ". ", " "]` — paragraph, then line,
   then sentence, then word boundary. Never mid-word. A raw character cut happens only for a single
   token longer than the target.
3. **Prefix every chunk** with its breadcrumb, `"<Doc Title> > <Section>. "`, so the chunk reads
   standalone. This directly targets the 15-point "chunks make sense on their own" criterion.

### Section derivation

| Input | Becomes |
|---|---|
| YAML front-matter (`---` … `---`) | `metadata.document_type`; stripped before splitting |
| The first `#` (H1) | `metadata.title` |
| Body text before the first `##` | a section named `"Introduction"` |
| Each `##` / `###` heading | `metadata.section`, verbatim |

`metadata.section` is therefore **never** the document title.

### Parameters

| Parameter | Value | Measured on | Rationale |
|---|---|---|---|
| `chunk_size` | **800 chars** (target) | the **body**, before the breadcrumb | Upper-middle of the spec's 500–1000 band. Dense technical prose needs room for a complete thought — pattern, why, trade-off — and 800 leaves ~200 chars of headroom for the prefix. ~150–200 tokens: inside any embedding window, still precise for retrieval. **800, not 900:** early drafts disagreed; 900 leaves too little headroom once a long breadcrumb is prepended. |
| `chunk_overlap` | **150 chars** | the body | ≈19% of `chunk_size`, the top of the standard 10–20% band. Carries a full sentence across boundaries so boundary-crossing facts are retrievable from either side, without inflating the index. |
| `min_chunk` | **500 chars** | the body | Floor for merging. |
| **hard ceiling** | **1000 chars** | the **final `text`, breadcrumb included** | The spec's upper bound. `validate()` fails the run if any emitted chunk exceeds it. |

#### The 800/1000 distinction — read this once

Two different limits on two different strings:

- **800 bounds the body** the splitter packs. It is a target, and merges are allowed to exceed it.
- **1000 bounds the emitted `text`**, breadcrumb included. It is hard; nothing may exceed it.

This is why the reference samples in [`assets/chunks.sample.jsonl`](assets/chunks.sample.jsonl)
measure 777 / 860 / 823 / 784 chars of `text` while their bodies are 691 / 778 / 748 / 713 — all
under 800, all under 1000. An automated check asserting `len(text) <= 800` would wrongly flag them.
Use this exact phrasing wherever the boundary is restated.

### Overlap scope

Overlap applies **between consecutive chunks within a section only**. Heading boundaries reset the
window by design: a section that fits in one chunk carries no overlap, and chunks on opposite sides
of a heading share none. Overlapping across a topic boundary would repeat unrelated context.

Like the 500–1000 band, the spec's "overlap 100–200" constrains the overlap **parameter** (= 150),
not every emitted pair. Legitimately zero-overlap pairs:

- the first chunk of any section relative to the previous section's last chunk
- any pair spanning a heading
- any pair where a merge stripped the overlap carry (D2)

**Any automated overlap check must compare same-section neighbours only.** State this in the README
for a grader running a naive per-pair check — `spec:29` is otherwise easy to misread.

### Merge rules

All merge caps are measured on the **final prefixed length**, so the ≤1000 invariant holds on the
merge paths, not only on the split path.

| Rule | Behaviour |
|---|---|
| **Short section** | A section under `min_chunk` merges **forward** into the next sibling section, while the merged text — breadcrumb included — stays ≤1000. Metadata records the **first** section's name. |
| **Terminal residual** | A document's final short piece merges **backward** into the previous chunk, under the same prefix-aware ≤1000 cap. *(D1 proposes widening this to any within-section terminal residual.)* |
| **Cap measurement** | The caller passes `cap = 1000 − len(breadcrumb)` to `merge_short`, so the cap is prefix-aware. |
| **Overlap-carry strip** | A *within-section* merge strips the later piece's leading overlap carry (~150 chars repeating its predecessor's tail) before concatenating, so a merged chunk never contains the overlap region twice. A *cross-section* merge has no carry, so nothing is stripped. |

**When no merge fits under the cap, allow the short residual rather than pad**, and flag it in the
validation report.

### Other edge cases

**Tables.** A table is a blank-line-free block, so any table ≤ `chunk_size` survives the paragraph
split atomically. An oversized table would split at row boundaries via the `\n` fallback with **no
header row repeated** — so author documents with no single table over ~800 characters, and prefer
prose for vocabulary and checklist sections. If a larger table ever becomes unavoidable, add header
+ separator-row repetition to `split_section` then.

**Normalization, before any splitting.** Front-matter is stripped first, by `strip_front_matter`,
which also captures `document_type`. `normalize_text` then handles the body: NFC-normalize · strip
HTML comments · collapse 3+ blank lines to 2 · strip trailing spaces · normalize line endings to
`\n`. This keeps character counts stable and stops the overlap budget being spent on whitespace.

---

## Chunk contract

One line of `data/processed/chunks.jsonl` = one chunk. Machine-readable contract:
[`assets/chunk.schema.json`](assets/chunk.schema.json).

### Why the fields are nested

The spec's prose (`spec:32-40`) lists `chunk_id`, `document_id`, `source_file`, `chunk_index` and
`text` as a flat list of "required metadata". But the spec's **own sample chunk** (`spec:84-99`)
nests everything except `chunk_id` and `text` under a `metadata` object.

**This schema follows the sample**, which is the canonical shape — the key set and even the key
*order* match `spec:88-98` exactly. The submission README calls this out explicitly, so a grader
keyed to either reading finds every required field.

### Shape

```json
{
  "chunk_id": "freight_exchange_domain_primer_chunk_004",
  "text": "Freight Exchange Fundamentals: Actors, Loads, and Matching > Load Matching Mechanics. <chunk body…>",
  "metadata": {
    "document_id": "freight_exchange_domain_primer",
    "source_file": "data/raw/freight-exchange-domain-primer.md",
    "source_type": "markdown",
    "title": "Freight Exchange Fundamentals: Actors, Loads, and Matching",
    "section": "Load Matching Mechanics",
    "chunk_index": 4,
    "language": "en",
    "domain": "logistics-engineering",
    "document_type": "concept-guide"
  }
}
```

### Fields

| Field | Required by spec? | Type | Generation rule |
|---|---|---|---|
| `chunk_id` | ✅ required | str | `f"{document_id}_chunk_{chunk_index:03d}"` |
| `text` | ✅ required | str | Breadcrumb prefix + body. **≤1000 chars including prefix** |
| `metadata.document_id` | ✅ required | str | Filename stem, lowercased: `re.sub(r"[^a-z0-9]+", "_", stem).strip("_")` |
| `metadata.source_file` | ✅ required | str | Repo-relative path, e.g. `data/raw/freight-exchange-domain-primer.md` |
| `metadata.chunk_index` | ✅ required | int | **1-based** position within the document — matches the spec sample (index 1 ↔ `_chunk_001`) |
| `metadata.title` | recommended | str | The document's H1 (fallback: filename stem, title-cased) |
| `metadata.section` | recommended | str | Nearest H2/H3 heading; `"Introduction"` for pre-first-H2 body; never the title; **first** section's name for merged chunks |
| `metadata.language` | recommended | str | Constant `"en"` |
| `metadata.domain` | recommended | str | Constant `"logistics-engineering"` |
| `metadata.document_type` | recommended | str | **From the document's YAML front-matter.** Vocabulary owned by the enum in [`assets/chunk.schema.json`](assets/chunk.schema.json): `concept-guide` · `architecture-guide` · `case-study` · `playbook`. A file with no front-matter is a hard error, never a silent default. |
| `metadata.source_type` | bonus | str | Constant `"markdown"`. Kept because it appears in the spec's sample |

### Invariants

Enforced by `validate()`.

1. Every line parses as JSON.
2. All five spec-required fields present and non-empty.
3. `chunk_id` unique across the whole file.
4. Within each `document_id` group, `chunk_index` is contiguous `1..N`.
5. No `text` exceeds 1000 chars, breadcrumb included.
6. *(soft)* Sub-500 bodies are counted and reported, not failed.

**On `chunk_id` uniqueness.** `chunk_id` is unique because `document_id` is — but `document_id`
derivation is **not injective**: `a-b.md` and `a_b.md` both normalize to `a_b`. Rule 3 is what
actually guarantees uniqueness; treat the derivation as a convenience, not a proof. Keep filenames
distinct after lowercasing and punctuation-collapsing.

### Validating your output

```bash
# every line parses, required fields present, sizes in band
python3 -c "
import json,sys
rows=[json.loads(l) for l in open('data/processed/chunks.jsonl')]
ids=[r['chunk_id'] for r in rows]
assert len(ids)==len(set(ids)), 'duplicate chunk_id'
assert all(len(r['text'])<=1000 for r in rows), 'chunk over 1000 chars'
print(len(rows),'chunks OK')"
```

Against the real contract (`jsonschema` is a validator-only dependency — it is **not** part of the
graded dependency set, which stays stdlib-only):

```bash
python3 -m venv .venv && .venv/bin/pip install jsonschema
.venv/bin/python -c "
import json,jsonschema
s=json.load(open('docs/homework1/assets/chunk.schema.json'))
for l in open('data/processed/chunks.jsonl'): jsonschema.validate(json.loads(l),s)
print('schema OK')"
```

---

## Implementation brief — `scripts/prepare_knowledge_base.py`

Not written yet. Realistically 200–300 lines of stdlib Python. It carries **no rubric row of its
own**, yet it produces every artifact worth 35 points.

### Dependencies

Standard library only: `argparse`, `json`, `os`, `pathlib`, `re`, `unicodedata`, `dataclasses`,
`sys`. Requires Python ≥ 3.9. `requirements.txt` stays empty.

The corpus is 100% self-authored Markdown by design, so the loader is markdown-only — no HTML/PDF/
plaintext readers for inputs that cannot occur.

### Data model

```python
from dataclasses import dataclass
from pathlib import Path

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
    document_type: str         # from YAML front-matter
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

### Functions, in pipeline order

**`discover_raw_files(raw_dir: Path) -> list[Path]`**
Glob `data/raw/*.md`, sorted by name for determinism.
*Errors:* fewer than 3 files → exit non-zero with a clear message (the spec requires ≥3).

**`strip_front_matter(text: str) -> tuple[str, dict]`**
Strip a leading `---` … `---` block and parse its simple `key: value` lines (no external YAML
parser needed for a flat block).
*Errors:* missing front-matter, or a `document_type` outside the schema enum → exit non-zero.

**`normalize_text(text: str) -> str`**
NFC-normalize · strip HTML comments · collapse 3+ blank lines to 2 · strip trailing spaces ·
line endings → `\n`.

**`read_markdown(text: str) -> tuple[str, list[tuple[str, str]]]`**
Split on ATX headers H1–H3 (`^#{1,3}\s`), skipping heading-like lines inside ``` code fences.
*Returns* `(title, sections)`. The first H1 is the title; body before the first H2 is emitted as a
section named `"Introduction"`; H2/H3 headings name their own sections.

**`load_document(path: Path) -> Doc`**
Read → `strip_front_matter` → `normalize_text` → `read_markdown` → assemble the `Doc`.
`document_id = re.sub(r"[^a-z0-9]+", "_", path.stem.lower()).strip("_")`;
`document_type` comes from the front-matter.
*Errors:* empty file → diagnostic error, never a silent zero-chunk pass.

**`split_section(body: str, max_chars: int = 800, overlap: int = 150) -> list[str]`**
Recursive fallback splitter on `["\n\n", "\n", ". ", " "]` — paragraph → line → sentence → word
boundary, never mid-word. A raw character cut only for a single token longer than `max_chars`.
Greedy-packs up to `max_chars`, carrying `overlap` tail characters into the next piece. Overlap is
within-section only.

**`merge_short(pieces: list[str], min_chars: int = 500, cap: int = 1000) -> list[str]`**
Merges undersized pieces forward, and terminal short pieces backward, only while the merged piece
stays ≤ `cap`. The caller passes `cap = 1000 − len(breadcrumb)`, so the cap is prefix-aware. On a
within-section merge, strips the later piece's leading overlap carry — only when it actually repeats
the predecessor's tail. A cross-section merge has no carry, so nothing is stripped.
**Implement this against the D1 / D1b decisions above.**

**`chunk_document(doc: Doc, cfg: Config) -> list[dict]`**
Header-aware pass: split per section (section name → `metadata.section`), run `merge_short` over the
document's piece stream with the prefix-aware cap (merged chunks keep the **first** section's name),
prepend the breadcrumb, assign 1-based `chunk_index` and
`chunk_id = f"{document_id}_chunk_{i:03d}"`.

**`write_jsonl(chunks: list[dict], out_path: Path) -> None`**
Atomic write — temp file + `os.replace`. One `json.dumps(ensure_ascii=False)` per line.

**`validate(out_path: Path, cfg: Config) -> ValidationReport`**
Re-reads the written file line by line:

| # | Rule | Severity | Exit | Message |
|---|---|---|---|---|
| 1 | Line parses as JSON | hard | ≠0 | `line {n}: invalid JSON` |
| 2 | All 5 required fields present and non-empty | hard | ≠0 | `line {n}: missing field {name}` |
| 3 | `chunk_id` unique | hard | ≠0 | `duplicate chunk_id: {id}` |
| 4 | `chunk_index` contiguous 1..N within its `document_id` | hard | ≠0 | `{doc}: chunk_index gap at {i}` |
| 5 | `len(text) <= 1000` (breadcrumb included) | hard | ≠0 | `{id}: text {n} chars exceeds 1000` |
| 6 | Body ≥ 500 chars | **soft** | 0 | `{id}: {n}-char residual (merge policy)` |

Returns stats: document count, chunk count, length min/avg/max, per-document counts, warnings.

**`main(argv: list[str]) -> int`**
`argparse` → discover → load → normalize → chunk → write → validate → print summary. Non-zero exit
on hard validation failure; soft warnings are reported with exit 0.

### CLI

```bash
python scripts/prepare_knowledge_base.py \
  --raw-dir data/raw --out data/processed/chunks.jsonl \
  --chunk-size 800 --overlap 150 --min-chunk 500 [--dry-run] [--verbose]
```

### Idempotency

Output is a pure function of (raw files, config): deterministic file ordering, IDs derived from
filename stem + index — no UUIDs, no timestamps — and a full atomic overwrite. Rerunning on
unchanged input yields a **byte-identical** file. No append mode, no partial state.

### Error-handling stance

Surface real errors; never mask them with an empty result. Fewer than 3 source files, an empty
document, missing front-matter, or a hard validation failure must each exit non-zero with a
diagnostic message. A zero-chunk run is never a silent success.

---

## Optional tests

**Above rubric — zero points** (`spec:70-78` awards none for tests). Cheap credibility, and a
genuine safety net when you re-tune `chunk_size` for the retrieval homework.

If you write `tests/`, assert the invariants already stated above — the Parameters and Merge-rules
tables, the overlap-scope rules, the `validate()` rule table, and the schema — plus the four error
paths (<3 source files · empty file · missing front-matter · `document_id` collision between
`a-b.md` and `a_b.md`, which must be *detected*, not silently merged) and determinism (two runs,
byte-identical output).

Two traps worth naming because a naive assertion gets them wrong:

- **Overlap.** "Consecutive chunks share 100–200 chars" holds only for same-section pairs that a
  merge did not produce. Cross-heading pairs and merge-produced pairs legitimately share 0 (D2).
- **Size.** Assert `len(text) <= 1000`, never `<= 800` — 800 bounds the body, 1000 bounds the
  emitted text.

Keep fixtures inline or in `tests/fixtures/*.md`. Do **not** test against `data/raw/`, which will
change as you author it. [`assets/chunks.sample.jsonl`](assets/chunks.sample.jsonl) is a useful
expected-*shape* fixture for the metadata-completeness and schema-conformance tests, but it is
hand-written and is not the pipeline's output.
