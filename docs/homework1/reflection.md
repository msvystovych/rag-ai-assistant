# Risk register and quality reflection

Seeds the submission README's **Conclusions** section, worth 5 points (`spec:77`).

> ⚠️ Every "Observed after run" cell below is **empty on purpose**. `spec:77` grades reflection on
> what actually happened — pre-run hypotheses score nothing. Fill the last two columns after your
> first real run, then copy the filled rows into the repo-root `README.md`.

## Chunk quality

| # | Risk | Mitigation in the design | Observed after run | Verdict |
|---|---|---|---|---|
| 1 | **Residual short chunks.** Final chunks of documents and merged short sections fall under 500 chars. | `merge_short` with backward merge for terminal pieces; the validation report counts outliers. Report the number honestly rather than padding text to hit a number. See [`pipeline-spec.md`](pipeline-spec.md) **D1** — this risk is larger than the design assumed. | | |
| 2 | **Breadcrumb overhead.** The prefix consumes 40–90 chars of every chunk's budget and repeats across a section's chunks. | Accepted trade for standalone readability. Improvement: shorten long H1 titles, or drop the title from the breadcrumb when the section name already disambiguates. | | |
| 3 | **Overlap quality.** A naive 150-char tail can start mid-sentence. | Improvement: snap the overlap window back to the previous sentence boundary so repeated context reads cleanly. | | |
| 4 | **List- and table-heavy sections chunk worse than prose.** Vocabulary and checklist sections fragment badly and embed poorly. | Author those sections as full sentences ("A lane is…"). Guidance is in [`corpus-plan.md`](corpus-plan.md). | | |

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
- count and percentage of sub-500 bodies (D1's real magnitude)
- count of chunks produced by a merge, and by which merge rule
- number of sections that fitted in a single chunk (zero-overlap by construction)
- whether a rerun produced a byte-identical file

## Questions to answer in the README Conclusions

1. Did the breadcrumb prefix actually make sampled chunks understandable in isolation? Read five at random and say so honestly.
2. What percentage of chunks landed inside 500–1000 chars?
3. Which document chunked worst, and why?
4. What would you change about `chunk_size` / `overlap` if you re-ran it?
