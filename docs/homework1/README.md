# Homework #1 — planning

Design notes for the knowledge base. **The graded deliverable is the repo-root `README.md`** — this
folder is the reasoning behind it and is not itself submitted for marks.

Assignment spec: [`../tasks/Домашнє завдання №1 — Підготовка knowl`](../tasks/Домашнє%20завдання%20№1%20—%20Підготовка%20knowl).
Read the spec itself; these notes never paraphrase it. The file has no extension, so links to it
must percent-encode the spaces. A `git mv` to `homework1-spec.md` and `homework2-spec.md` would
improve that. Such a rename keeps the content, so `spec:NN` citations still hold.

**Subject area:** a chatbot that answers freight-exchange and logistics-platform engineering
questions. The subject area spans these topics:

- domain concepts
- CQRS + Event Sourcing
- a monolith-to-microservices case study
- Kafka telemetry
- payments automation
- operation at 5,000 requests per second

That list scopes the chatbot, not the delivered corpus. `data/raw/` holds four documents: the
freight-exchange domain primer, CQRS and event sourcing, the monolith-to-microservices migration,
and scaling and zero-downtime operations. Kafka telemetry and payments automation are two of the
three dropped documents, so the corpus covers neither.

## Status

**Homework #1 is complete.** Every rubric row (`spec:70-78`) grades a physical artifact, and every
artifact now exists.

| # | Criterion | Pts | Designed | Delivered |
|---|---|---|---|---|
| 1 | ≥3 sources in `data/raw/`, readable | 5 | ✅ 7 documents outlined | ✅ 4 documents, 1,491–1,834 words each |
| 2 | Correct chunking — size, overlap, readability | 15 | ✅ full strategy | ✅ 77 chunks, `text` 390–930 chars |
| 3 | Full metadata structure | 15 | ✅ schema + JSON Schema | ✅ all 77 chunks carry it |
| 4 | Valid JSONL output | 5 | ✅ writer + validator specced | ✅ 77 lines, all parse and validate |
| 5 | 3–5 example chunks in README | 5 | ✅ 4 hand-written samples | ✅ 5 real chunks in the root README |
| 6 | Conclusion — chunk-quality analysis | 5 | ✅ risk register | ✅ Conclusions from the real run |

The corpus plan scoped 7 documents. The author wrote 4 of them. The other 3 never reached a file,
and the plan dropped them.

Rows 5 and 6 now rest on real output. `spec:76` wants examples from the submitted `chunks.jsonl`,
and the root README carries 5 such lines. `spec:77` wants reflection on what actually happened, and
the root README's Conclusions section reports the measured run.

The plan predicted 45–50 for faithful execution, and 40 / 50 if the two README placeholders stayed
empty. The run filled both placeholders. The gap was execution, and the execution is complete.

## Start here

1. **This file** — status, decisions, and the record of the work below.
2. [`corpus-plan.md`](corpus-plan.md) — read § Sanitization, then the outlines. **This was the work.**
3. [`pipeline-spec.md`](pipeline-spec.md) — the splitting rules, the chunk contract, and the script brief. Nothing is left open, and `scripts/prepare_knowledge_base.py` implements it as written.
4. The corpus exists, the script ran, and the repo-root `README.md` carries the real numbers.

## Files

| File | What it is |
|---|---|
| [`corpus-plan.md`](corpus-plan.md) | The seven planned source documents — outlines, word budgets, **sanitization rules**, domain vocabulary. Four of them became files. **This was the actual work.** |
| [`pipeline-spec.md`](pipeline-spec.md) | Sole owner of every splitting rule, the chunk contract, and the script's function-by-function brief |
| [`reflection.md`](reflection.md) | Risk register; the source of the submission README's Conclusions |
| [`assets/chunk.schema.json`](assets/chunk.schema.json) | JSON Schema 2020-12 — validates every line of `chunks.jsonl`; owns the `document_type` enum |
| [`assets/chunks.sample.jsonl`](assets/chunks.sample.jsonl) | 4 hand-written reference chunks — a shape fixture, **not** pipeline output. Real output has existed since 2026-07-21, so retire this fixture |

> ⚠️ Never paste the samples into the submission README. They are illustrative only, and they match
> no line of the real `chunks.jsonl`. Their `chunk_index` values imply roughly one chunk per
> section, but the sizing rule predicted ~9 per document. The real run wrote 77 chunks from 4
> documents. That averages about 19 per document, so the run missed the prediction by more than
> double.

## Target repository layout

Every path in the tree below now exists. The *(to create)* markers and the note about unfilled
placeholders record the state before the run.

```
rag-ai-assistant/
├── README.md                           # the graded submission (placeholders unfilled)
├── .gitignore
├── requirements.txt                    # HW2 deps only; the HW1 script needs none of them
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
| 2 | **Session scope** | Ideas and blueprint only. The author wrote the source documents personally, after that session. |
| 3 | **Stack** | All-Python, minimal dependencies. For HW1 this resolves to **stdlib only**; LangChain / LlamaIndex remain acceptable in later homeworks. |
| 4 | **Language** | All output in English. |
| 10 | **`document_type` source** | YAML front-matter in each `data/raw/*.md`. Decided 2026-07-20. It closes a hole: the schema declared the field, and no rule filled it. |
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

## The work, in the order it ran

| # | Work | Gates | Effort | Outcome |
|---|---|---|---|---|
| 1 | **Author the corpus.** The plan budgeted the core four at ≈5,600–7,200 words. Nothing downstream runs until at least 3 exist, because `discover_raw_files` refuses a smaller set. The floor was 3 documents at ~900 words each, which still clears `spec:25` and exercises the whole pipeline | 5 pts directly, 30 indirectly | Large — this was the real work | 4 documents in `data/raw/`, 1,491–1,834 words each |
| 2 | **Run the sanitization grep pass** over `data/raw/` before chunking, not after | protects everything | Small | Unverified — the sweep leaves no artifact, and nothing in the tree records a run |
| 3 | **Write `scripts/prepare_knowledge_base.py`** — the plan estimated ~200–300 lines of stdlib Python. It carries no rubric row of its own, although it produces every artifact worth 35 points | gates 35 pts | Medium | 590 lines, and the standard library only. The estimate was roughly half the real size |
| 4 | **Run it** → `data/processed/chunks.jsonl`, and commit the output | 5 pts | Small | 77 chunks, committed and graded; Homework #2 reads them back |
| 5 | **Fill the two README placeholders** — 3–5 real example chunks, and Conclusions from real run statistics | 10 pts | Medium | 5 real example chunks, and Conclusions from the measured run |
| 6 | **Check the real chunk-length distribution** and tune the merge threshold if the residual fraction is embarrassing. Re-chunking is one command | risk to 15 pts | Small | min 390, mean 706.9, max 930; 70 of 77 (90.9%) in the 500–1000 band |
| 7 | Optional: `tests/` — above rubric, zero points, cheap credibility | 0 pts | Medium | 40 tests in `tests/test_prepare_knowledge_base.py`; the full suite holds 326 tests, all of them pass |

[`pipeline-spec.md`](pipeline-spec.md) § Settled decisions holds the merge decisions (2026-07-21).
`merge_short` is one rule: any piece under 500 chars merges backward into its predecessor while the
result stays ≤1000. The plan expected single-digit-percent sub-500 residuals, not zero. The run
matched that: 70 of 77 chunks land in the 500–1000 band, and the other 7 sit below 500. The script
counts those residuals and reports them.

## The one way to lose 10 points after doing all the work

The repo-root `README.md` carried two placeholder sections — *Example chunks* and *Conclusions* —
mapping to two 5-point rubric rows. Unfilled, they score **zero on both**. This was the single
highest-probability failure mode in the whole plan. The run closed it: that README now holds 5 real
example chunks and the real run statistics.

## Pre-submission gate

Most rows carry their evidence beside them. The audit read the working tree, not the committed tree,
and that working tree holds uncommitted changes. Three boxes stay open because nothing in the
repository records the work, and each one names what would tick it. The two grep sweeps leave no
artifact in the tree, so run them by hand before any later submission.

- [x] ≥3 (ideally 4) documents exist in `data/raw/` and read cleanly — 4 documents, 1,491–1,834 words each
- [ ] No unapproved real-world specifics leaked — nothing in the tree records that the grep pass in
      [`corpus-plan.md`](corpus-plan.md) ran, or when. Run it, then record the result here
- [ ] Employer-name sweep, **sweep 2 of 2** — whole-repo, run last (sweep 1 is `data/raw/`-scoped,
      in [`corpus-plan.md`](corpus-plan.md)): `grep -rniE '<your-brand-alternation>' README.md docs/ data/`
      The command still carries its `<your-brand-alternation>` placeholder, so nobody ran it as
      written. Fill the alternation in, run it, then tick this box
- [ ] `python scripts/prepare_knowledge_base.py` exits 0 and prints its summary — nobody ran the
      script in this session, so this box stays open. A run that exits 0 ticks it. What is verified:
      40 tests in `tests/test_prepare_knowledge_base.py` cover the script, and they pass
- [x] `data/processed/chunks.jsonl` exists, the repository commits it, and every line parses — 77 lines
- [x] Every line validates against [`assets/chunk.schema.json`](assets/chunk.schema.json)
- [x] `chunk_index` is contiguous 1..N within each `document_id`; all `chunk_id`s unique
- [x] No chunk `text` exceeds 1000 chars — the maximum measures 930; sub-500 residuals counted and reported honestly
- [x] The repo-root `README.md` has all six sections of `spec:58-64`
- [x] Its *Example chunks* section holds 3–5 **real** lines from `chunks.jsonl`, each commented — 5 lines
- [x] Its *Conclusions* section reports **real** run statistics, not the pre-run hypotheses
- [x] Its Sources table lists exactly the documents that actually exist — the 4 files in `data/raw/`
- [x] `git push origin main` — `git ls-remote origin main` returns the `HEAD` commit, so the push
      landed. The working tree holds uncommitted changes on top
- [ ] Open the GitHub URL and confirm the grader can reach it — nobody checked the repository's
      visibility, and no artifact records such a check. Open the URL as a signed-out user, then
      tick this box

> ⚠️ **The employer name is still in git history.** A redaction pass cleaned the working tree on
> 2026-07-20. Earlier commits of the planning notes still hold the name. The repository is private
> today. Keep it private, or rewrite the history with `git filter-repo` before you make it public or
> share it beyond the grader.
