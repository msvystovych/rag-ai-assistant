# Risk register and quality reflection

Seeds the submission README's **Conclusions** section, worth 5 points (`spec:77`).

> ✅ **Filled from the first real run** (4 documents, 77 chunks). The condensed version of these
> rows is in the repo-root `README.md` § Conclusions — Homework #1 chunk quality.

## Chunk quality

| # | Risk | Mitigation in the design | Observed after run | Verdict |
|---|---|---|---|---|
| 1 | **Residual short chunks.** Some chunk bodies fall under 500 chars — most often a section's trailing piece, a whole short section, or a document's opening piece. | `merge_short` merges any undersized piece backward; the validation report counts what survives. Simulation says single-digit percent, and zero bodies under 250 chars. Report the real number honestly rather than padding text to hit it. See § Settled decisions **D1** in [`pipeline-spec.md`](pipeline-spec.md). | **13 of 77 (16.9%)** — nearly double the simulated 8.5%, and barely better than the 14.6% no-merge baseline. The rule fired **once**: 14 candidates, 1 merged, 13 refused by the ≤1000 cap. Zero bodies under 250 chars, as predicted. | **Mitigation ineffective at chunk_size 800.** A ~800-char predecessor plus a ~79-char breadcrumb leaves ~110 chars of headroom, so almost no merge fits. The 500/100 variant merged 17 of 17 — the rule works, the parameters starve it. |
| 2 | **Breadcrumb overhead.** The prefix consumes 40–90 chars of every chunk's budget and repeats across a section's chunks. | Accepted trade for standalone readability. Improvement: shorten long H1 titles, or drop the title from the breadcrumb when the section name already disambiguates. | Mean overhead **79 chars/chunk** (~11% of mean chunk length), inside the predicted 40–90 band. | **Trade accepted, with a caveat found in HW2.** Readability held; but because the H1 is prepended to every chunk, a query repeating title wording gets a document-wide lexical boost (see `q08`, `docs/homework2/analysis.md`). |
| 3 | **Overlap quality.** A naive 150-char tail can start mid-sentence. | Improvement: snap the overlap window back to the previous sentence boundary so repeated context reads cleanly. | **Confirmed.** The carry snaps to a *word* boundary only, so chunks routinely open mid-sentence ("time and handling risk. That distinction…"). Visible in the top-1 hit for `q01` and `q09`. | **Still open.** Ranking is unaffected (the embedding sees the whole chunk); readability is not. Sentence-boundary snapping remains the right fix. |
| 4 | **List- and table-heavy sections chunk worse than prose.** Vocabulary and checklist sections fragment badly and embed poorly. | Author those sections as full sentences ("A lane is…"). Guidance is in [`corpus-plan.md`](corpus-plan.md). | **Avoided by construction** — the authored corpus contains no tables and no multi-item lists, so the failure mode never materialised. | **Mitigation worked.** The Key Domain Vocabulary section, the most list-prone by subject, chunked normally as prose. |

## Project limitations

| # | Limitation | Note |
|---|---|---|
| 5 | **Homogeneous style.** A corpus written by one author in one voice makes retrieval artificially easy — no vocabulary mismatch between query and document. | Declare it as a limitation. Homework #2 can add paraphrased queries to stress-test retrieval honestly. |
| 6 | **Sanitization drift.** Risk of a platform-specific detail slipping in while writing. | The authoring voice rule plus the pre-submission grep pass in [`corpus-plan.md`](corpus-plan.md). The knowledge base contains no personal data by construction. |
| 7 | **Chunk-size tuning is unvalidated until the retrieval homework.** 800/150 is a best-practice guess; retrieval experiments may show 600-char chunks retrieve more precisely. | The deterministic pipeline makes re-chunking a one-command experiment. Revisit after Homework #2. |

## Statistics to collect on the first run

The script's summary output should give you all of these. They are what turns this file from
hypothesis into the graded conclusion:

- documents processed, chunks produced, chunks per document
- `text` length: min / mean / max, and a rough histogram
- count and percentage of sub-500 bodies, and how many are unmergeable first pieces (D1's real magnitude — the simulation predicted single-digit percent)
- count of chunks produced by a merge, and by which merge rule
- number of sections that fitted in a single chunk (zero-overlap by construction)
- whether a rerun produced a byte-identical file

## Questions to answer in the README Conclusions

1. Did the breadcrumb prefix actually make sampled chunks understandable in isolation? Read five at random and say so honestly.
2. What percentage of chunks landed inside 500–1000 chars?
3. Which document chunked worst, and why?
4. What would you change about `chunk_size` / `overlap` if you re-ran it?
