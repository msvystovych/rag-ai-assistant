# Gap Analysis — does the plan complete Homework #1?

**No.** The planning documents in this folder are a *design*. Every one of the spec's six rubric
rows (`spec:70-78`) grades a **physical artifact**, and none of them exist in the repository.

| | |
|---|---|
| **Score if submitted today** | **0 / 50** |
| Score once the plan is executed faithfully | 45–50 / 50 |
| Realistic downside if executed carelessly | 40 / 50 — see [D-README](#the-one-way-to-lose-10-points-after-doing-all-the-work) |

Verified repo state: `git ls-files` tracks only `.gitignore` and three Markdown files under
`docs/`. There is no `data/`, no `data/raw/`, no `data/processed/chunks.jsonl`, no `scripts/`,
no `notebooks/`, no `tests/`, no `requirements.txt`, and no root `../../README.md`.

---

## Rubric row by row

| # | Criterion (`spec:70-78`) | Pts | Designed? | Delivered? | Score today |
|---|---|---|---|---|---|
| 1 | ≥3 sources in `data/raw/`, readable | 5 | ✅ 7 documents outlined → [`04-corpus-plan.md`](04-corpus-plan.md) | ❌ 0 written | **0** |
| 2 | Correct chunking — size, overlap, readability | 15 | ✅ full strategy → [`05-chunking-strategy.md`](05-chunking-strategy.md) | ❌ nothing chunked | **0** |
| 3 | Full metadata structure | 15 | ✅ schema → [`06-chunk-schema.md`](06-chunk-schema.md) + [`assets/chunk.schema.json`](assets/chunk.schema.json) | ❌ no chunks to carry it | **0** |
| 4 | Valid JSONL output | 5 | ✅ writer + validator → [`07-pipeline-brief.md`](07-pipeline-brief.md) | ❌ file absent | **0** |
| 5 | 3–5 example chunks in README | 5 | ✅ 4 samples → [`assets/chunks.sample.jsonl`](assets/chunks.sample.jsonl) | ❌ no README; samples are synthetic | **0** |
| 6 | Conclusion — chunk-quality analysis | 5 | ✅ 7 risks → [`10-reflection.md`](10-reflection.md) | ❌ written pre-run; no real observations | **0** |
| | **Total** | **50** | | | **0** |

Rows 5 and 6 deserve emphasis: the samples and the reflection **exist as text but do not count**.
`spec:76` wants examples drawn from the submitted `chunks.jsonl`, and `spec:77` wants reflection
on what actually happened. Both are currently pre-run placeholders.

## Deliverables checklist (`spec:49-56`)

| Required | Path | State |
|---|---|---|
| Source documents | `data/raw/` | ❌ missing |
| Prep script or notebook | `scripts/prepare_knowledge_base.py` | ❌ missing |
| Processed chunks | `data/processed/chunks.jsonl` | ❌ missing |
| README | `../../README.md` | ❌ missing (draft only, in `templates/`) |

---

## Remaining work, ranked

| # | Task | Gates | Effort |
|---|---|---|---|
| 1 | **Author the corpus.** Write the core four documents (≈5,600–7,200 words). Nothing downstream can run until ≥3 exist. | 5 pts directly, 30 more indirectly | Large — this is the real work |
| 2 | **Write `scripts/prepare_knowledge_base.py`.** [`07-pipeline-brief.md`](07-pipeline-brief.md) specifies 10 functions; realistically 200–300 lines of stdlib Python. Carries **no rubric row of its own** yet produces every artifact worth 35 points. | gates 35 pts | Medium |
| 3 | **Run it** → `data/processed/chunks.jsonl`, and commit the output. | 5 pts | Small |
| 4 | **Write the real `../../README.md`** from [`templates/README-submission.md`](templates/README-submission.md), covering all six sections of `spec:58-64`. | 10 pts | Medium |
| 5 | **Regenerate the 3–5 example chunks** from the real corpus. The four in `assets/` are hand-written and will not match any produced line. | part of row 5 | Small |
| 6 | **Rewrite Conclusions with real stats** — length distribution, residual counts, actual failures — replacing the pre-run hypotheses. | part of row 6 | Small |
| 7 | **Check the real chunk-length distribution** and tune the merge threshold. The only self-acknowledged risk on the 15-point chunking row. | risk to 15 pts | Small |
| 8 | Optional: `tests/` — above rubric, zero points, cheap credibility. See [`08-test-plan.md`](08-test-plan.md). | 0 pts | Medium |

**Before writing any code**, resolve the two open design defects in
[`09-open-defects.md`](09-open-defects.md) — both change what the splitter does.

---

## The one way to lose 10 points after doing all the work

`templates/README-submission.md` contains two placeholder sections — *Example chunks* and
*Conclusions* — mapping to two 5-point rubric rows. Copying that file to `../../README.md` and
submitting it with the placeholders intact scores **zero on both rows**. This is the single
highest-probability failure mode in the whole plan, which is why the template lives in
`templates/` and not at the repo root.

## Pre-submission gate

Tick every box before submitting:

- [ ] ≥3 (ideally 4) documents exist in `data/raw/` and read cleanly
- [ ] No unapproved real-world specifics leaked — run the grep pass in [`02-approved-facts.md`](02-approved-facts.md)
- [ ] `python scripts/prepare_knowledge_base.py` exits 0 and prints its summary
- [ ] `data/processed/chunks.jsonl` exists, is committed, and every line parses
- [ ] Every line validates against `assets/chunk.schema.json`
- [ ] `chunk_index` is contiguous 1..N within each `document_id`; all `chunk_id`s unique
- [ ] No chunk `text` exceeds 1000 chars; sub-500 residuals counted and reported honestly
- [ ] `../../README.md` exists at the repo root with all six sections of `spec:58-64`
- [ ] Its *Example chunks* section holds 3–5 **real** lines from `chunks.jsonl`, each commented
- [ ] Its *Conclusions* section reports **real** run statistics, not the pre-run hypotheses
- [ ] Sources table lists exactly the documents that actually exist (delete unwritten extension rows)
