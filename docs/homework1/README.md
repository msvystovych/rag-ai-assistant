# Homework #1 — planning

Design notes for the knowledge base. **The graded deliverable is the repo-root `README.md`** — this
folder is the reasoning behind it and is not itself submitted for marks.

Assignment spec: [`../tasks/Домашнє завдання №1 — Підготовка knowl`](../tasks/Домашнє%20завдання%20№1%20—%20Підготовка%20knowl).
Read the spec itself; these notes never paraphrase it. (The file has no extension, so links to it
must percent-encode the spaces. Renaming both specs to `homework1-spec.md` / `homework2-spec.md`
with `git mv` would be an improvement — the content is unchanged, so `spec:NN` citations still hold.)

**Subject area:** a chatbot answering freight-exchange / logistics-platform engineering questions —
domain concepts, CQRS + Event Sourcing, a monolith-to-microservices case study, Kafka telemetry,
payments automation, and operating at 5,000 requests per second.

## Status

**Nothing is built yet. Submitted as it stands, this scores 0 / 50.** Every rubric row
(`spec:70-78`) grades a physical artifact.

| # | Criterion | Pts | Designed | Delivered |
|---|---|---|---|---|
| 1 | ≥3 sources in `data/raw/`, readable | 5 | ✅ 7 documents outlined | ❌ none written |
| 2 | Correct chunking — size, overlap, readability | 15 | ✅ full strategy | ❌ nothing chunked |
| 3 | Full metadata structure | 15 | ✅ schema + JSON Schema | ❌ no chunks to carry it |
| 4 | Valid JSONL output | 5 | ✅ writer + validator specced | ❌ file absent |
| 5 | 3–5 example chunks in README | 5 | ✅ 4 hand-written samples | ❌ samples are synthetic |
| 6 | Conclusion — chunk-quality analysis | 5 | ✅ risk register | ❌ written pre-run |

Rows 5 and 6 deserve emphasis: the samples and the reflection **exist as text but do not count**.
`spec:76` wants examples drawn from the submitted `chunks.jsonl`, and `spec:77` wants reflection on
what actually happened. Both are pre-run placeholders today.

Executed faithfully the plan is worth 45–50. Executed carelessly — leaving the two README
placeholders unfilled — it lands at 40 / 50. The gap is execution, not design.

## Start here

1. **This file** — status, decisions, and the ranked backlog below.
2. [`corpus-plan.md`](corpus-plan.md) — read § Sanitization, then the outlines. **This is the work.**
3. [`pipeline-spec.md`](pipeline-spec.md) — settle the open decisions at the top, then implement.
4. When the corpus exists: run the script, then fill the repo-root `README.md`'s two placeholders.

## Files

| File | What it is |
|---|---|
| [`corpus-plan.md`](corpus-plan.md) | The seven source documents — outlines, word budgets, **sanitization rules**, domain vocabulary. **This is the actual work.** |
| [`pipeline-spec.md`](pipeline-spec.md) | Sole owner of every splitting rule, the chunk contract, and the script's function-by-function brief |
| [`reflection.md`](reflection.md) | Risk register; becomes the submission README's Conclusions |
| [`assets/chunk.schema.json`](assets/chunk.schema.json) | JSON Schema 2020-12 — validates every line of `chunks.jsonl`; owns the `document_type` enum |
| [`assets/chunks.sample.jsonl`](assets/chunks.sample.jsonl) | 4 hand-written reference chunks — a shape fixture, **not** pipeline output. Retire once real output exists. |

> ⚠️ The samples are illustrative only. Their `chunk_index` values imply roughly one chunk per
> section, while the sizing rule predicts ~9 per document. Never paste them into the submission
> README — they will match no line of the real `chunks.jsonl`.

## Target repository layout

Only `README.md`, `.gitignore` and `docs/` exist today. Everything marked *(to create)* is
outstanding work.

```
rag-ai-assistant/
├── README.md                           # the graded submission (placeholders unfilled)
├── .gitignore
├── requirements.txt                    # (to create) empty — stdlib only, Python >= 3.9
├── data/
│   ├── raw/                            # (to create) the authored .md documents
│   └── processed/
│       └── chunks.jsonl                # (to create) generated; commit it — it is graded
├── scripts/
│   └── prepare_knowledge_base.py       # (to create)
├── tests/                              # (optional, above rubric)
└── docs/
    ├── tasks/                          # assignment specs
    └── homework1/                      # this folder — planning artifacts
```

## Decisions

Settled with the user — do not revisit:

| # | Decision | Detail |
|---|---|---|
| 1 | **Subject area** | Logistics-Domain Engineering Assistant. **Not** a career or recruiter bot. |
| 2 | **Session scope** | Ideas and blueprint only. The source documents are authored personally, later. |
| 3 | **Stack** | All-Python, minimal dependencies. For HW1 this resolves to **stdlib only**; LangChain / LlamaIndex remain acceptable in later homeworks. |
| 4 | **Language** | All output in English. |
| 10 | **`document_type` source** | YAML front-matter in each `data/raw/*.md`. Decided 2026-07-20; closes a hole where the field was declared but never populated. |
| 11 | **Employer name** | Redacted from these notes going forward. It remains in git history — see the warning below. |

Resolved during planning — revisitable, but change them in **one** place:

| # | Decision | Rationale |
|---|---|---|
| 5 | Target `chunk_size` = **800**, not 900 | See [`pipeline-spec.md`](pipeline-spec.md) § Parameters — sole owner. |
| 6 | `chunk_index` is **1-based** | See [`pipeline-spec.md`](pipeline-spec.md) § Fields — sole owner. |
| 7 | `document_type` vocabulary | `concept-guide` · `architecture-guide` · `case-study` · `playbook`. The enum in [`assets/chunk.schema.json`](assets/chunk.schema.json) is the **single** source of truth. |
| 8 | Sample-chunk `document_id`s follow the real document filenames | Keeps the samples consistent with the corpus plan. |
| 9 | Corpus is **100% self-authored Markdown** | Therefore the loader is markdown-only by design — no HTML/PDF/TXT readers for inputs that cannot occur. |

**Why stdlib only.** LangChain would add roughly a hundred transitive dependencies to replicate a
splitter that fits in well under a hundred lines. For a graded script the author must be able to
explain line by line, that is a poor trade. If a non-Markdown source ever genuinely lands in
`data/raw/`, add the matching reader then — not speculatively.

## Remaining work, ranked

| # | Task | Gates | Effort |
|---|---|---|---|
| 1 | **Author the corpus.** Write the core four (≈5,600–7,200 words). Nothing downstream runs until ≥3 exist. Minimum viable: 3 documents at ~900 words each still clears `spec:25` and exercises the whole pipeline. | 5 pts directly, 30 indirectly | Large — this is the real work |
| 2 | **Run the sanitization grep pass** over `data/raw/` before chunking, not after. | protects everything | Small |
| 3 | **Write `scripts/prepare_knowledge_base.py`** — ~200–300 lines of stdlib Python. Carries no rubric row of its own yet produces every artifact worth 35 points. | gates 35 pts | Medium |
| 4 | **Run it** → `data/processed/chunks.jsonl`, and commit the output. It is graded, and Homework #2 reads it back. | 5 pts | Small |
| 5 | **Fill the two README placeholders** — 3–5 real example chunks, and Conclusions from real run statistics. | 10 pts | Medium |
| 6 | **Check the real chunk-length distribution** and tune the merge threshold if the residual fraction is embarrassing. Re-chunking is one command. | risk to 15 pts | Small |
| 7 | Optional: `tests/` — above rubric, zero points, cheap credibility. | 0 pts | Medium |

**Before writing the splitter**, resolve the two open decisions at the top of
[`pipeline-spec.md`](pipeline-spec.md) — both change what `merge_short` does.

## The one way to lose 10 points after doing all the work

The repo-root `README.md` carries two placeholder sections — *Example chunks* and *Conclusions* —
mapping to two 5-point rubric rows. Submitting them unfilled scores **zero on both**. This is the
single highest-probability failure mode in the whole plan.

## Pre-submission gate

Tick every box before submitting:

- [ ] ≥3 (ideally 4) documents exist in `data/raw/` and read cleanly
- [ ] No unapproved real-world specifics leaked — run the grep pass in [`corpus-plan.md`](corpus-plan.md)
- [ ] Employer-name sweep, **sweep 2 of 2** — whole-repo, run last (sweep 1 is `data/raw/`-scoped,
      in [`corpus-plan.md`](corpus-plan.md)): `grep -rniE '<your-brand-alternation>' README.md docs/ data/`
- [ ] `python scripts/prepare_knowledge_base.py` exits 0 and prints its summary
- [ ] `data/processed/chunks.jsonl` exists, is committed, and every line parses
- [ ] Every line validates against [`assets/chunk.schema.json`](assets/chunk.schema.json)
- [ ] `chunk_index` is contiguous 1..N within each `document_id`; all `chunk_id`s unique
- [ ] No chunk `text` exceeds 1000 chars; sub-500 residuals counted and reported honestly
- [ ] The repo-root `README.md` has all six sections of `spec:58-64`
- [ ] Its *Example chunks* section holds 3–5 **real** lines from `chunks.jsonl`, each commented
- [ ] Its *Conclusions* section reports **real** run statistics, not the pre-run hypotheses
- [ ] Its Sources table lists exactly the documents that actually exist
- [ ] `git push origin main`, then open the GitHub URL and confirm the grader can reach it

> ⚠️ **The employer name is still in git history.** It was redacted from the working tree on
> 2026-07-20, but earlier commits of the planning notes still contain it. The repository is private
> today. Before making it public or sharing it beyond the grader, either rewrite history
> (`git filter-repo`) or keep the repository private.
