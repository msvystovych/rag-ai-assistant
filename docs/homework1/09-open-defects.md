# Open defects and resolved contradictions

Found by an adversarial review of the original blueprint (every finding below survived an
independent refutation attempt). Two are **open** and change what the code does — decide them
before writing `merge_short`. The rest were fixed while splitting this folder and are recorded so
the reasoning isn't lost.

---

## OPEN — decide before coding

### D1 · Sub-500 residuals are structurally unavoidable *(affects the 15-point chunking row)*

**The claim that broke.** The original blueprint said `min_chunk: 500` "keeps every non-terminal
chunk inside the spec band," and that backward-merging a document's final piece "eliminates
sub-500 residuals entirely."

**Why it can't hold.** `merge_short` merges undersized pieces **forward**, and reserves backward
merging for a document's **final** piece only. Work an ordinary case:

- A 900-char section packs to one 800-char piece plus a ~250-char tail (100 net + the 150-char overlap carry).
- Forward merge: 250 + the next section's 800 = 1050, which exceeds the prefix-aware cap (~914 after an 86-char breadcrumb). **Fails.**
- Backward merge: strip the 150 carry → 100 net; 800 + 100 = 900; + 86 breadcrumb = 986 ≤ 1000. **Would fit — but is forbidden**, because this isn't the document's final piece.

So the tail is emitted at ~250 chars. Any section between roughly 800 and 1300 characters
produces one. Across the planned corpus that's a large fraction of sections — the common case, not
the exception.

**Recommended resolution.** Allow backward merge for **any** within-section terminal residual, not
just the document's last piece, under the same prefix-aware ≤1000 cap. This is a two-line change
to `merge_short`'s eligibility test and eliminates the bulk of residuals without weakening any cap.

**Then update:** the merge-rules table in [`05-chunking-strategy.md`](05-chunking-strategy.md),
`merge_short`'s contract in [`07-pipeline-brief.md`](07-pipeline-brief.md), and test 3 in
[`08-test-plan.md`](08-test-plan.md).

**If you decline**, keep the current behaviour but delete the "eliminates sub-500 residuals
entirely" phrasing everywhere, and report the residual count honestly in the README Conclusions —
the spec constrains the `chunk_size` *parameter*, not every emitted chunk, and its own sample
chunk is 154 characters.

### D2 · The overlap assertion contradicts the merge rule

The blueprint asserts — in a proposed pytest **and** in a grader-facing README note — that
consecutive same-section chunks share 100–200 characters. But the merge rule **strips** the
overlap carry before concatenating, producing same-section pairs that share **zero**. The
enumerated list of legitimate zero-overlap cases never included this one.

**Recommended resolution.** Treat merge-produced pairs as a fourth legitimate zero-overlap case.
Already applied to the zero-overlap list in [`05-chunking-strategy.md`](05-chunking-strategy.md)
and to test 4 in [`08-test-plan.md`](08-test-plan.md). Confirm you agree — the alternative
(keeping the carry inside merged chunks) duplicates ~150 characters in the retrieval index.

---

## Resolved while restructuring

| # | Defect | Resolution |
|---|---|---|
| **D3** | Floor and cap were measured on different strings — the 1000 cap on the *prefixed* text, the 500 floor on the *unprefixed* body. A 460-char body → 546-char `text`: inside the spec band, yet reported as a residual. | Both `chunk_size` and `min_chunk` are now explicitly measured **on the body**; only the 1000 ceiling is measured on the final `text`. Stated in the parameters table. |
| **D4** | Cross-section merged chunks get a breadcrumb naming only the first of the two sections — while the README asserted flatly that every chunk's prefix names its section. | Disclosed in the merge-rules table and in `metadata.section`'s generation rule. |
| **D5** | The blueprint's only provenance pointer referenced `~/Desktop/rag-training/raw/…` — a directory that exists but is **empty**. | Corrected to `docs/raw/` in [`README.md`](README.md). |
| **D6** | The repo tree named the root `rag-knowledge-base/`; the real root is `rag-ai-assistant`. It also omitted `docs/` and presented `data/`, `scripts/`, `tests/`, `README.md` as existing. | Tree rewritten with the real root, a `docs/` entry, and `(to create)` on every unbuilt path. |
| **D7** | The reference sample at 860 chars exceeded the declared `chunk_size` of 800, with no stated convention reconciling them. | Resolved: **800 bounds the body; 1000 bounds the emitted text.** All four samples' bodies measure 691/778/748/713 — consistent. Phrasing fixed identically in every file that restates it. |
| **D8** | Chunk-count estimates didn't follow the blueprint's own sizing rule and didn't sum (core 55–75 + extension 37–47 ≠ 86–119). | Recomputed from the stated rule (words ÷ 10): **56–72** core, **93–119** all seven. Word budgets were already correct. |
| **D11** | `os` was missing from the "exhaustive" stdlib import list though `os.replace` is required; `Config` and `ValidationReport` were used but never defined. | `os` added; both types now defined in the data model. |
| **D12** | The `Doc`/`Chunk` sketch was not valid Python — a dict literal mixing bare set elements with a `key: value` pair. It raised `SyntaxError` on `ast.parse`. | Rewritten as real dataclasses. |
| **D13** | "~40 lines of stdlib Python" described the whole method; the specified design is 10 functions, realistically 200–300 lines. It was also the stated justification for rejecting LangChain. | Scoped honestly: the *splitter* is small; the script is 200–300 lines. The LangChain rationale now rests on dependency count and explainability. |
| **D14** | `chunk_id` uniqueness was asserted to follow from `document_id` uniqueness, but the derivation isn't injective (`a-b.md` and `a_b.md` collide). | Uniqueness now attributed to the validator's explicit check, with the collision noted. |
| **D15** | The "delete the extension rows if you only wrote four documents" instruction sat *outside* the README skeleton's code fence — lost on copy-paste. | The skeleton is now a real file with the instruction inside it as a TODO. |

## Noted, no action needed

- **D9** — The reference samples' `chunk_index` values imply roughly one chunk per section, while
  the sizing rule predicts ~9 per document section-set. The samples are illustrative, hand-written,
  and will be replaced by real output before submission.
- **D10** — Heading casing conflict: the outlines use sentence case, the samples Title Case.
  Headings are copied verbatim into `metadata.section`, so pick one when authoring and stay
  consistent. Both breadcrumb and `section` are graded on readability, not on casing.

## Verified correct — do not re-litigate

- Sample `text` lengths are exactly 777 / 860 / 823 / 784, as claimed; all four parse via `json.loads`.
- The metadata key set **and order** match the spec's sample exactly.
- Word budgets sum exactly.
- Overlap 150 is 18.75% of 800 — the claimed "≈19%" is right.
- All four samples respect the sanitization rules in [`02-approved-facts.md`](02-approved-facts.md).
- The "worth 10 points" warning on the README placeholders maps correctly to two 5-point rubric rows.
