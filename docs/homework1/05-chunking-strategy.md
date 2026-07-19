# Chunking strategy

**This file is the sole owner of every splitting rule.** If a rule about size, overlap, merging,
or section derivation appears anywhere else in this repository, it is a copy — change it here
first. (Two sanctioned copies exist: the chunking section of
[`templates/README-submission.md`](templates/README-submission.md), because `spec:62` requires
the README to describe the strategy, and the docstrings in
[`07-pipeline-brief.md`](07-pipeline-brief.md), because those ship inside the code.)

## Method

**Header-aware section splitting with a recursive character-splitting fallback.** Stdlib Python;
no LangChain.

1. **Parse into sections** by ATX headings (`#`, `##`, `###`). Heading-like lines inside ``` code
   fences are ignored.
2. **Split oversized sections** recursively on `["\n\n", "\n", ". ", " "]` — paragraph, then
   line, then sentence, then word boundary. Never mid-word. A raw character cut happens only for
   a single token longer than the target.
3. **Prefix every chunk** with its breadcrumb, `"<Doc Title> > <Section>. "`, so the chunk reads
   standalone. This directly targets the 15-point "chunks make sense on their own" criterion.

## Section derivation

| Input | Becomes |
|---|---|
| The first `#` (H1) | `metadata.title` |
| Body text before the first `##` | a section named `"Introduction"` |
| Each `##` / `###` heading | `metadata.section`, verbatim |

`metadata.section` is therefore **never** the document title.

**Heading casing:** headings are copied verbatim, so whatever case you write in `data/raw/`
is what lands in `metadata.section` and in the breadcrumb. The reference samples in
`assets/` use Title Case; the outlines in [`04-corpus-plan.md`](04-corpus-plan.md) use sentence
case. Pick one when authoring and stay consistent — see [`09-open-defects.md`](09-open-defects.md) D10.

## Parameters

| Parameter | Value | Measured on | Rationale |
|---|---|---|---|
| `chunk_size` | **800 chars** (target) | the **body**, before the breadcrumb | Upper-middle of the spec's 500–1000 band. Dense technical prose needs room for a complete thought — pattern, why, trade-off — and 800 leaves ~200 chars of headroom for the prefix. ~150–200 tokens: inside any embedding window, still precise for retrieval. |
| `chunk_overlap` | **150 chars** | the body | ≈19% of `chunk_size`, the top of the standard 10–20% band. Carries a full sentence across boundaries so boundary-crossing facts are retrievable from either side, without inflating the index. |
| `min_chunk` | **500 chars** | the body | Floor for merging. |
| **hard ceiling** | **1000 chars** | the **final `text`, breadcrumb included** | The spec's upper bound. `validate()` fails the run if any emitted chunk exceeds it. |

### The 800/1000 distinction — read this once

Two different limits on two different strings:

- **800 bounds the body** the splitter packs. It is a target, and merges are allowed to exceed it.
- **1000 bounds the emitted `text`**, breadcrumb included. It is hard; nothing may exceed it.

This is why the reference samples measure 777 / 860 / 823 / 784 chars of `text` while their
bodies are 691 / 778 / 748 / 713 — all under 800, all under 1000. An automated check asserting
`len(text) <= 800` would wrongly flag them. Use this exact phrasing wherever the boundary is
restated.

## Overlap scope

Overlap applies **between consecutive chunks within a section only**. Heading boundaries reset
the window by design: a section that fits in one chunk carries no overlap, and chunks on
opposite sides of a heading share none. Overlapping across a topic boundary would repeat
unrelated context.

Like the 500–1000 band, the spec's "overlap 100–200" constrains the overlap **parameter**
(= 150), not every emitted pair. Legitimately zero-overlap pairs:

- the first chunk of any section relative to the previous section's last chunk
- any pair spanning a heading
- any pair where a merge stripped the overlap carry (see below)

**Any automated overlap check must compare same-section neighbours only.** State this in the
README for a grader running a naive per-pair check — `spec:29` is otherwise easy to misread.

## Merge rules

Four sub-rules. All merge caps are measured on the **final prefixed length**, so the
≤1000 invariant holds on the merge paths, not only on the split path.

| Rule | Behaviour |
|---|---|
| **Short section** | A section under `min_chunk` merges **forward** into the next sibling section, while the merged text — breadcrumb included — stays ≤1000. Metadata records the **first** section's name. |
| **Terminal residual** | A document's final short piece merges **backward** into the previous chunk, under the same prefix-aware ≤1000 cap. |
| **Cap measurement** | The caller passes `cap = 1000 − len(breadcrumb)` to `merge_short`, so the cap is prefix-aware. |
| **Overlap-carry strip** | A *within-section* merge strips the later piece's leading overlap carry (~150 chars repeating its predecessor's tail) before concatenating, so a merged chunk never contains the overlap region twice. A *cross-section* merge has no carry, so nothing is stripped. |

**When no merge fits under the cap, allow the short residual rather than pad**, and flag it in
the validation report. The spec constrains the `chunk_size` parameter, not every residual chunk —
the spec's own sample chunk text is 154 characters.

> ⚠️ Sub-500 residuals are **not** rare, despite what an earlier draft claimed. See
> [`09-open-defects.md`](09-open-defects.md) **D1** — it is an open decision that changes
> `merge_short`'s behaviour. Resolve it before writing the function.

## Other edge cases

**Tables.** A table is a blank-line-free block, so any table ≤ `chunk_size` survives the
paragraph split atomically. An oversized table would split at row boundaries via the `\n`
fallback with **no header row repeated** — so author documents with no single table over ~800
characters, and prefer prose for vocabulary and checklist sections. If a larger table ever
becomes unavoidable, add header + separator-row repetition to `split_section` then.

**Normalization, before any splitting.** NFC-normalize · strip HTML comments · collapse 3+ blank
lines to 2 · strip trailing spaces · normalize line endings to `\n`. This keeps character counts
stable and stops the overlap budget being spent on whitespace.
