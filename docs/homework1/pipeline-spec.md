# Pipeline spec — chunking rules, chunk contract, and `scripts/prepare_knowledge_base.py`

**This file is the sole owner of every splitting rule and every chunk field.** If a rule about size,
overlap, merging, section derivation, or metadata appears anywhere else in this repository, it is a
copy. Change it here first. One sanctioned copy exists: the *Chunking strategy* section of the
repo-root `README.md`, because `spec:62` requires the README to describe the strategy.

---

## Settled decisions — `merge_short` is one rule *(settled 2026-07-21)*

Three contradictions survived the original blueprint. This section settles all three. It keeps the
reasoning for two reasons. Two of the rejected options look cheaper than they are. The residual
numbers are the honest answer to the 15-point chunking row. D3 is an authoring note, not a code
decision.

**The rule, stated once.** `merge_short` operates on **pieces**, never on sections. Any piece under
`min_chunk` merges **backward** into its predecessor, while the merged text — breadcrumb included —
stays ≤1000. A within-section merge strips the later piece's overlap carry; a cross-section merge
has no carry. There is no forward merge, no whole-short-section branch, and no final-piece special
case. One direction, one granularity, one pass — `split_section` stays unchanged.

### D1 · Sub-500 residuals — reduced, not eliminated

**Settled: the rule allows a backward merge for *any* undersized piece, not only a document's final
one.** *Rationale:* the blueprint's forward branch cannot fire on the common case — it is
arithmetically dead. To widen the backward branch and delete the forward branch is therefore both
strictly better and strictly less code.

The blueprint claimed `min_chunk: 500` "keeps every non-terminal chunk inside the spec band" and
that backward-merging a document's final piece "eliminates sub-500 residuals entirely." Work an
ordinary case:

- A 900-char section packs to one 800-char piece plus a ~250-char tail (100 net + the 150-char overlap carry).
- Forward merge: 250 + the next section's 800 = 1050, which exceeds the prefix-aware cap (~914 after an 86-char breadcrumb). **Fails.**
- Backward merge: strip the 150 carry → 100 net; 800 + 100 = 900; + 86 breadcrumb = 986 ≤ 1000. **Fits.**

Any section between roughly 800 and 1300 characters produces such a tail — the common case, not the
exception. The backward path fits it; the forward path never does.

**How many residuals actually remain.** The simulation ran over `corpus-plan.md`'s word budgets for
the core four: 400 trials, a fixed seed, and sections that a separator-snapping splitter packs. It
counts bodies.

| Merge policy | sub-500 bodies | median residual | bodies under 250 chars |
|---|---|---|---|
| no merging at all | 14.6% | 368 | 2.8% |
| the blueprint (short-section forward + final-piece backward) | 13.7% | 373 | 2.4% |
| **this rule** (any undersized piece, backward) | **8.5%** | **413** | **0.0%** |

At half the section length (12–14 sections per document) no-merge becomes 25.6% and this rule 14.2%.
The gain that matters is the last column. The rule does not remove short chunks. It removes *tiny*
ones. A 413-char chunk ends on a paragraph boundary and carries its breadcrumb. Such a chunk is
neither truncated nor context-free.

**These figures are simulations, not measurements.** The corpus did not exist when the simulation
ran, so read the table and the percentages around it as estimates. The measured distribution
follows.

**The measured distribution.** The first real run over the finished corpus produced 77 chunks. The
measurement:

- `text` length: minimum 390 · mean 706.9 · maximum 930.
- 70 of the 77 chunks (90.9%) sit inside the 500–1000 band.
- 13 bodies fall under 500 characters (16.9%). No body falls under 250.
- The merge rule saw 14 candidates, merged 1, and refused 13 at the 1000-character cap.

No body fell under 250 characters, which the simulation predicted. The merge rule did not produce
that outcome: a run with merging disabled reaches the same floor of 315 characters. The rule moved
one body only, from 14 sub-500 bodies to 13. It left 16.9% of bodies under 500, against the 8.5%
that the same simulation predicted. The README Conclusions carry
the chunk count, the 390 / 930 bounds and the 90.9%, but not the sub-500 count.

**Never write "eliminates sub-500 residuals."** `spec:29` constrains the `chunk_size` *parameter*,
not every emitted chunk, and the assignment's own sample chunk is 154 characters. Report the count.

**What this rule does not fix — two named cases.**

1. **A whole section under `min_chunk` that will not fit under the cap.** A 300-char section behind
   an 800-char predecessor needs 1100 + breadcrumb; the cap rejects it. Every policy considered,
   including the blueprint's, emits it short. The rule solves within-section tails, not
   short sections.
2. **A document's first piece.** It has no predecessor, so a backward-only rule can never merge it.
   With a leading `"Introduction"` of 200–600 chars the simulation measures 12.6% sub-500 overall,
   of which 4.1 points are unmergeable first pieces. At ≥500 chars it disappears — 8.7%, zero
   first-piece residuals. **This makes `corpus-plan.md`'s "aim sections at 800–1,600 characters"
   load-bearing for the `"Introduction"` specifically**, the one piece the merge rule cannot rescue.
   The fix is authoring, not a forward-merge branch. A forward merge would stamp the short section's
   name onto a chunk that is mostly the *next* section — see D1b.

`validate()` rule 6 counts and reports both cases (soft, exit 0).

**Rejected — rebalancing the last two pieces at split time.** The idea: when a section's final piece
would fall under `min_chunk`, redistribute the last two pieces across their combined span. Then
neither piece is a residual. This spec rejects the idea on measurement *and* on risk.

**Measurement.** Under the same separator-snapping simulation it buys 8.5% → 7.3% at the planned
section length. That gain is under one chunk per corpus. At half the section length it is *worse*
than this rule (18.4% vs 14.2%). That is because two locally-legal rebalanced pieces no longer
merge, so a later residual survives. An earlier arithmetic model produced "0.0%" only because it
assumed a cut at every character. The real splitter cuts only on `["\n\n", "\n", ". ", " "]`.

**Risk.** Rebalancing needs three things:

- `split_section` must track which atoms landed in the last two pieces.
- A guard must confirm that both halves clear `min_chunk` *after* snapping. Without that guard, one
  residual becomes two in 10–20% of simulated firings.
- `min_chunk` — a merge-only concept — must become a splitter input.

A descent to the word separator makes the rule fire more often. In the simulation that descent ends
7–11% of non-final chunks mid-sentence, where greedy packing ends 0%. It therefore attacks the same
15-point row that rebalancing set out to protect.

**Rejected — deleting `merge_short` and `min_chunk` entirely.** The honest minimum: no merge code at
all, with the 154-char sample precedent as its defence. In the simulation it costs ~6 percentage
points of sub-500 rate (14.6% vs 8.5%). Decisively, it is also the only *live* option that emits
sub-250-char chunks — 2.8% of them. A 413-char chunk passes the rubric's "makes sense on its own" reading; a
200-char one is where a grader's eye stops. A dozen lines is the cheapest insurance on the board.

### D1b · Merge granularity — settled: **pieces**

**Settled: `merge_short` operates on pieces. This spec deletes the merge-rules table's "short
section" row.** *Rationale:* one granularity removes the contradiction outright. A whole short
section simply *is* a single piece. The same rule covers it with no separate branch.

Backward is also the direction that keeps the metadata honest, independent of any residual count.
The blueprint forward-merged a short section into its next sibling. It recorded "the first section's
name". Under forward merge the first section is the *short* one. A 300-char section A therefore
merged into a 700-char section B, and the output carried `metadata.section = "A"` plus a breadcrumb
reading `… > A. `. That body is mostly B. The breadcrumb exists to make a chunk read standalone, and
this result degrades it.

Under backward merge the predecessor is both the first section and the majority of the text. The
§ Fields rule "**first** section's name for merged chunks" therefore needs no change. It becomes
correct rather than merely stipulated.

### D2 · The overlap assertion contradicts the merge rule — settled: carve-out

**Settled: merge-produced pairs are a fourth legitimate zero-overlap case** — § Overlap scope lists
it, and the README grader note repeats it. *Rationale:* the alternative keeps the carry inside
merged chunks. That alternative duplicates ~150 characters in the retrieval index for no retrieval
gain.

D1's settlement does not change this. Nothing in D1 makes the case rare enough to stop stating it.
The simulation puts the merge at about one piece in fifteen at the planned section length (≈5 merges
per corpus). At half that length it puts the merge at one piece in eight. The first real run merged
only 1 piece of 14 candidates, so the real rate is lower than the simulation predicted. It is not
zero, so the carve-out stays. `spec:29`'s "overlap 100–200" constrains the overlap *parameter*
(= 150), not every emitted pair — the same argument § Overlap scope already makes.

### D3 · Heading casing *(authoring note — no code impact)*

The pipeline copies headings verbatim into `metadata.section` and into the breadcrumb, so whatever
case you write in `data/raw/` lands in the output. The reference samples use Title Case; the
outlines in [`corpus-plan.md`](corpus-plan.md) use sentence case. Pick one when you author and stay
consistent. The grading rewards readability, not casing.

---

## Chunking strategy

### Method

**Header-aware section splitting with a recursive character-splitting fallback.** Stdlib Python; no
LangChain.

1. **Parse into sections** by ATX headings (`#`, `##`, `###`). The parser ignores heading-like lines
   inside fenced code blocks.
2. **Split oversized sections** recursively on `["\n\n", "\n", ". ", " "]` — paragraph, then line,
   then sentence, then word boundary. Never mid-word. A raw character cut happens only for a single
   token longer than the target.
3. **Prefix every chunk** with its breadcrumb, `"<Doc Title> > <Section>. "`, so the chunk reads
   standalone. This directly targets the 15-point "chunks make sense on their own" criterion.

### Section derivation

| Input | Becomes |
|---|---|
| YAML front-matter (`---` … `---`) | `metadata.document_type`; the pipeline strips it before splitting |
| The first `#` (H1) | `metadata.title` |
| Body text before the first `##` | a section named `"Introduction"` |
| Each `##` / `###` heading | `metadata.section`, verbatim |

`metadata.section` is therefore **never** the document title.

### Parameters

| Parameter | Value | Measured on | Rationale |
|---|---|---|---|
| `chunk_size` | **800 chars** (target) | the **body**: breadcrumb excluded, inbound overlap carry **included** | Upper-middle of the spec's 500–1000 band. Dense technical prose needs room for a complete thought — pattern, why, trade-off. 800 leaves ~200 chars of headroom for the prefix. ~150–200 tokens: inside any embedding window, still precise for retrieval. **800, not 900:** early drafts disagreed; 900 leaves too little headroom once the pipeline prepends a long breadcrumb. |
| `chunk_overlap` | **150 chars** | the body | ≈19% of `chunk_size`, the top of the standard 10–20% band. It carries a full sentence across boundaries — so a boundary-crossing fact stays retrievable from either side — without inflating the index. |
| `min_chunk` | **500 chars** | the same string `chunk_size` is measured on | Floor for merging (§ Merge rules). The pipeline counts and reports every body below it. It never pads such a body and never fails the run. |
| **hard ceiling** | **1000 chars** | the **final `text`, breadcrumb included** | The spec's upper bound. `validate()` fails the run if any emitted chunk exceeds it. |

#### The 800/1000 distinction — read this once

Two different limits on two different strings:

- **800 bounds the body** the splitter packs. It is a target, and a merge may exceed it.
- **1000 bounds the emitted `text`**, breadcrumb included. It is hard; nothing may exceed it.

The reference samples in [`assets/chunks.sample.jsonl`](assets/chunks.sample.jsonl) show this. Their
bodies measure 691 / 778 / 748 / 713 chars — all four under 800. Their `text` values measure
777 / 860 / 823 / 784 chars — all four under 1000. An automated check asserting `len(text) <= 800`
would wrongly flag them. Use this exact phrasing at every restatement of the boundary.

#### What the 800 includes

A piece's body is ≤800 characters, **including its 150-character inbound overlap carry**. Net new
content per piece is therefore ~650. That is the number `corpus-plan.md`'s sizing rule derives
from. The pipeline measures `min_chunk` on that same string.

Read the other way, the arithmetic breaks: 800 of *new* content plus a 150-char carry plus an
86-char breadcrumb. A mid-section chunk then reaches 1036 and breaches the hard ceiling. That
happens on the pure split path, where no cap and no fallback would catch it.

**The 500–1000 band constrains the `chunk_size` parameter, not every emitted chunk.** The
assignment's own sample chunk is 154 characters. This is why invariant 6 and `validate()` rule 6
*count and report* sub-500 bodies instead of failing the run. Nothing hides the residual count. This document
reports it, and the README Conclusions carry the chunk count, the length bounds and the band share.

### Overlap scope

Overlap applies **between consecutive chunks within a section only**. Heading boundaries reset the
window by design. A section that fits in one chunk therefore carries no overlap, and chunks on
opposite sides of a heading share none. An overlap across a topic boundary would repeat unrelated
context.

Like the 500–1000 band, the spec's "overlap 100–200" constrains the overlap **parameter** (= 150),
not every emitted pair. Legitimately zero-overlap pairs:

- the first chunk of any section relative to the previous section's last chunk
- any pair spanning a heading
- any pair a merge produced, because the merge stripped the later piece's overlap carry

**Any automated overlap check must compare same-section neighbours only.** State this in the README
for a grader running a naive per-pair check — `spec:29` is otherwise easy to misread.

### Merge rules

The pipeline measures all merge caps on the **final prefixed length**. The ≤1000 invariant therefore
holds on the merge paths, not only on the split path. That measurement uses the document's
**longest** breadcrumb, not the current chunk's. Three facts force that choice:

- A merged chunk carries its predecessor's breadcrumb.
- Breadcrumbs differ in length by section name.
- `merge_short` takes a single scalar cap.

The longest breadcrumb is the conservative choice. It rejects a handful of merges that would fit. It
also makes the ceiling hold by construction rather than on average.

`merge_short` operates on the document's **piece** stream. One rule, one direction:

| Rule | Behaviour |
|---|---|
| **Undersized piece** | Any piece under `min_chunk` merges **backward** into its predecessor, while the merged text — breadcrumb included — stays ≤1000. This covers a within-section tail, a whole short section, and a document's final piece identically. There is no forward merge and no final-piece special case. The merged chunk keeps the **predecessor's** section name, which is both the first section and the majority of the text. |
| **First piece** | A document's first piece has no predecessor, so it is never a merge target. Author the leading `"Introduction"` at ≥ `min_chunk` — it is the only piece this rule cannot rescue (D1). |
| **Overlap-carry strip** | A *within-section* merge strips the later piece's leading overlap carry before it concatenates. That carry is ~150 chars repeating its predecessor's tail. A merged chunk therefore never contains the overlap region twice. The strip happens only when the carry actually repeats that tail. A *cross-section* merge has no carry, so it strips nothing. |

**When no merge fits under the cap, allow the short residual rather than pad**, and flag it in the
validation report. The simulation expected single-digit-percent residuals, not zero; the first real
run measured 16.9% (D1).

The ≤1000 ceiling then holds by construction on both paths. The split path emits at most 800 of body
plus a breadcrumb. The merge path emits at most `cap` plus the longest breadcrumb. This assumes every
breadcrumb stays under 200 characters — `"<Doc Title> > <Section>. "`, so title + section ≤ ~196.
The planned titles measure 60–90. If a document ever needs a longer one, shorten the H1.

### Other edge cases

**Tables.** A table is a blank-line-free block, so any table ≤ `chunk_size` survives the paragraph
split atomically. An oversized table would split at row boundaries through the `\n` fallback, with
**no header row repeated**. So author documents with no single table over ~800 characters. Prefer
prose for vocabulary and checklist sections. If a larger table ever becomes unavoidable, add header
+ separator-row repetition to `split_section` then.

**Normalization, before any splitting.** `strip_front_matter` strips the front-matter first, and it
also captures `document_type`. `normalize_text` then handles the body. It normalizes to NFC, strips
HTML comments, and collapses 3+ blank lines to 2. It also strips trailing spaces and normalizes line
endings to `\n`. This keeps character counts stable, and it stops whitespace from consuming the
overlap budget.

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
| `metadata.document_type` | recommended | str | **From the document's YAML front-matter.** The enum in [`assets/chunk.schema.json`](assets/chunk.schema.json) owns the vocabulary: `concept-guide` · `architecture-guide` · `case-study` · `playbook`. A file with no front-matter is a hard error, never a silent default. |
| `metadata.source_type` | bonus | str | Constant `"markdown"`. It appears in the spec's sample, so the schema keeps it |

### Invariants

`validate()` enforces these.

1. Every line parses as JSON.
2. All five spec-required fields present and non-empty.
3. `chunk_id` unique across the whole file.
4. Within each `document_id` group, `chunk_index` is contiguous `1..N`.
5. No `text` exceeds 1000 chars, breadcrumb included.
6. *(soft)* `validate()` counts and reports sub-500 bodies; the run does not fail.

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

The script exists. It measures 590 lines of stdlib Python, against an original estimate of 200–300.
It carries **no rubric row of its own**, yet it produces every artifact worth 35 points.

### Dependencies

Standard library only: `argparse`, `json`, `os`, `pathlib`, `re`, `unicodedata`, `dataclasses`,
`sys`. Requires Python ≥ 3.9. **This script** needs nothing from `requirements.txt` — it runs on a
bare interpreter. (`requirements.txt` is no longer empty: Homework #2's retrieval layer added
`openai` and `chromadb`. That does not relax this script's stdlib-only constraint.)

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

@dataclass(frozen=True)
class Piece:
    section: str
    text: str
    first_in_section: bool
    carry_len: int = 0         # leading chars of `text` copied from the previous piece
    merged: bool = False

@dataclass
class MergeStats:
    candidates: int = 0
    merged: int = 0

    @property
    def refused(self) -> int:
        return self.candidates - self.merged

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

A chunk goes out as a plain dict that matches [`assets/chunk.schema.json`](assets/chunk.schema.json)
exactly. Do not wrap it in a dataclass, because the writer serializes it verbatim.

### Functions, in pipeline order

**`discover_raw_files(raw_dir: Path) -> list[Path]`**
Glob `data/raw/*.md` and sort by name for determinism.
*Errors:* fewer than 3 files → exit non-zero with a clear message (the spec requires ≥3).

**`strip_front_matter(text: str) -> tuple[str, dict]`**
Strip a leading `---` … `---` block and parse its simple `key: value` lines (no external YAML
parser needed for a flat block).
*Errors:* missing front-matter, or a `document_type` outside the schema enum → exit non-zero.

**`normalize_text(text: str) -> str`**
NFC-normalize · strip HTML comments · collapse 3+ blank lines to 2 · strip trailing spaces ·
line endings → `\n`.

**`read_markdown(text: str) -> tuple[str, list[tuple[str, str]]]`**
Split on ATX headers H1–H3 (`^#{1,3}\s`), and skip heading-like lines inside fenced code blocks.
*Returns* `(title, sections)`. The first H1 is the title. The body before the first H2 becomes a
section named `"Introduction"`. H2/H3 headings name their own sections.

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

**`merge_short(pieces: list[Piece], min_chars: int, cap: int, stats: MergeStats | None = None) -> list[Piece]`**
Single pass over the document's piece stream. Any piece shorter than `min_chars` merges **backward**
into its predecessor. The merge happens only while the merged piece stays ≤ `cap`. Otherwise the
pass emits the piece short. There is no forward merge, so the first piece of the stream is never a
merge target.

The caller passes `cap = 1000 − max(len(breadcrumb))` across the document's sections. The cap is
therefore prefix-aware, and it holds for whichever breadcrumb the merged chunk carries. On a
within-section merge the pass strips the later piece's leading overlap carry. It strips only when
that carry actually repeats the predecessor's tail. A cross-section merge has no carry, so the pass
strips nothing.

**`chunk_document(doc: Doc, cfg: Config, stats: MergeStats | None = None) -> list[dict]`**
Header-aware pass, in four steps:

- Split per section. The section name becomes `metadata.section`.
- Run `merge_short` over the document's piece stream with the prefix-aware cap. A merged chunk keeps
  the **first** section's name.
- Prepend the breadcrumb.
- Assign a 1-based `chunk_index` and `chunk_id = f"{document_id}_chunk_{i:03d}"`.

**`write_jsonl(chunks: list[dict], out_path: Path) -> None`**
Atomic write — temp file + `os.replace`. One `json.dumps(ensure_ascii=False)` per line.

**`validate(out_path: Path, cfg: Config) -> ValidationReport`**
Re-reads the file it just wrote, line by line:

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
on hard validation failure. The run reports soft warnings and exits 0.

### CLI

```bash
python scripts/prepare_knowledge_base.py \
  --raw-dir data/raw --out data/processed/chunks.jsonl \
  --chunk-size 800 --overlap 150 --min-chunk 500 [--dry-run] [--verbose]
```

### Idempotency

Output is a pure function of (raw files, config): deterministic file ordering, IDs from the filename
stem + index, and a full atomic overwrite. No UUIDs, no timestamps. A rerun on unchanged input
yields a **byte-identical** file. No append mode, no partial state.

### Error-handling stance

Surface real errors. Never mask them with an empty result. Each of these four conditions must exit
non-zero with a diagnostic message:

- fewer than 3 source files
- an empty document
- missing front-matter
- a hard validation failure

A zero-chunk run is never a silent success.

---

## Optional tests

**Above rubric — zero points** (`spec:70-78` awards none for tests). Cheap credibility, and a
genuine safety net when you re-tune `chunk_size` for the retrieval homework.

These tests exist. `tests/test_prepare_knowledge_base.py` holds 40 of them. They assert the
invariants this file states above:

- the Parameters and Merge-rules tables
- the overlap-scope rules
- the `validate()` rule table
- the loader's front-matter and `document_type` enum guards

No test loads [`assets/chunk.schema.json`](assets/chunk.schema.json), so schema conformance stays a
manual check — § Validating your output holds the command.

They also cover the four error paths and determinism. The four error paths are <3 source files, an
empty file, missing front-matter, and a `document_id` collision between `a-b.md` and `a_b.md`. The
pipeline must *detect* that collision, never merge it silently. The determinism test runs the
pipeline twice and compares the two files byte for byte.

Two traps worth naming because a naive assertion gets them wrong:

- **Overlap.** "Consecutive chunks share 100–200 chars" holds only for same-section pairs that a
  merge did not produce. Cross-heading pairs and merge-produced pairs legitimately share 0.
- **Size.** Assert `len(text) <= 1000`, never `<= 800` — 800 bounds the body, 1000 bounds the
  emitted text.

Keep fixtures inline or in `tests/fixtures/*.md`. Do **not** test against `data/raw/`, which will
change as you author it. [`assets/chunks.sample.jsonl`](assets/chunks.sample.jsonl) is a useful
expected-*shape* fixture for the metadata-completeness and schema-conformance tests. An author wrote
that file by hand, and it is not the pipeline's output.

---

## Known limits — stated, not hidden

The first real run measured three costs. [`reflection.md`](reflection.md) records the sub-500 and
breadcrumb figures, and the repo-root `README.md` records the mid-sentence count.
[`../homework2/analysis.md`](../homework2/analysis.md) describes what a mid-sentence opening costs
a reader.

- **Chunk bodies open in mid-sentence.** 48 of the 77 bodies start part-way through a sentence. The
  overlap carry snaps to a word boundary, not to a sentence boundary.
- **13 bodies stay under 500 characters.** `merge_short` cannot fold a piece into an ~800-character
  predecessor. That predecessor plus a ~79-char breadcrumb leaves ~110 characters of headroom under
  the ≤1000 cap, so almost no merge fits.
- **The breadcrumb prefix costs a mean 79 characters per chunk.** It also repeats the document title
  into every chunk of that document.

## What is deliberately not built

Three absences are deliberate. Do not close one without a spec that asks for it.

- **No third-party import.** `scripts/prepare_knowledge_base.py` imports the standard library only.
  `CLAUDE.md` hard invariant 1 states this rule, and the script runs on a bare Python ≥ 3.9
  interpreter.
- **No `jsonschema` in `requirements.txt`.** That file excludes the package on purpose. Install it
  ad hoc in a throwaway venv when you want to re-run the schema check.
- **No reader for any format but Markdown.** `discover_raw_files` globs `data/raw/*.md`, and the
  corpus is 100% self-authored Markdown by design.
