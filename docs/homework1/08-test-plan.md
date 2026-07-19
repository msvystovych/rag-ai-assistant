# Test plan — `tests/test_prepare_knowledge_base.py`

**Above rubric.** No criterion in `spec:70-78` awards points for tests. This is cheap credibility
and a genuine safety net when you later re-tune `chunk_size` for the retrieval homework.

Not written yet. Depends on `scripts/prepare_knowledge_base.py` existing first.

| # | Test | Arrange | Assert | Source rule |
|---|---|---|---|---|
| 1 | Hard size ceiling | Run the pipeline over a fixture corpus | Every `text` ≤ 1000 chars, breadcrumb included | [`05`](05-chunking-strategy.md) parameters |
| 2 | Body target | Same | Every non-merged body ≤ 800 chars | [`05`](05-chunking-strategy.md) parameters |
| 3 | Residuals are sanctioned only | Same | Every sub-500 body is flagged in the report; none are silent | [`05`](05-chunking-strategy.md) merge rules |
| 4 | Same-section overlap | Fixture with one long section | Consecutive chunks **of the same section** share 100–200 chars — **except** pairs produced by a merge, which share 0 | [`05`](05-chunking-strategy.md) overlap scope |
| 5 | Cross-section overlap is zero | Fixture with two short sections | Chunks spanning a heading share no overlap | [`05`](05-chunking-strategy.md) overlap scope |
| 6 | Metadata completeness | Same | Every chunk carries all 5 required + 5 recommended fields | [`06`](06-chunk-schema.md) fields |
| 7 | `chunk_id` uniqueness | Corpus with similar filenames (`a-b.md`, `a_b.md`) | No duplicate `chunk_id`; the collision is *detected*, not silently merged | [`06`](06-chunk-schema.md) invariant 3 |
| 8 | Contiguous index | Same | Within each `document_id`, `chunk_index` is exactly `1..N` | [`06`](06-chunk-schema.md) invariant 4 |
| 9 | Determinism | Run twice into two paths | Files are byte-identical | [`07`](07-pipeline-brief.md) idempotency |
| 10 | Header awareness | Fixture with distinct sections | A chunk spans two `##` sections **only** when a short-section merge produced it; `metadata.section` matches its **first** section's header | [`05`](05-chunking-strategy.md) merge rules |
| 11 | No duplicated overlap in merges | Fixture forcing a within-section merge | The overlap region appears exactly once in the merged chunk | [`05`](05-chunking-strategy.md) overlap-carry strip |
| 12 | Too few sources | `data/raw/` with 2 files | Non-zero exit, message names the ≥3 requirement | [`07`](07-pipeline-brief.md) `discover_raw_files` |
| 13 | Empty document | One zero-byte `.md` | Diagnostic error; never a silent zero-chunk pass | [`07`](07-pipeline-brief.md) `load_document` |
| 14 | Schema conformance | Run the pipeline | Every line validates against [`assets/chunk.schema.json`](assets/chunk.schema.json) | [`06`](06-chunk-schema.md) |

## Before writing test 4

Test 4 is where [`09-open-defects.md`](09-open-defects.md) **D2** bites: the merge rule strips
the overlap carry, so a naive "every same-section pair shares 100–200 chars" assertion fails on
merged pairs. The exception clause in the table above is the resolution — do not drop it.

## Fixtures

Keep fixtures inline as strings, or in `tests/fixtures/*.md`. Do **not** test against
`data/raw/` — those documents will change as you author them, and the tests would drift.
[`assets/chunks.sample.jsonl`](assets/chunks.sample.jsonl) is a useful *expected-shape* fixture
for tests 6 and 14, but it is hand-written and is not the pipeline's output.
