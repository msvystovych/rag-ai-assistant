# Homework #1 — RAG Knowledge Base (Logistics-Domain Engineering Assistant)

**Status: DESIGNED, NOT BUILT.** Submitted as it stands today this scores **0 / 50** — every
rubric row grades a physical artifact, and none exist yet. See
[`docs/homework1/00-gap-analysis.md`](docs/homework1/00-gap-analysis.md) for the row-by-row breakdown and the work remaining.

Assignment spec: [`docs/raw/# Домашнє завдання №1 — Підготовка knowl`](docs/tasks/%23%20Домашнє%20завдання%20№1%20—%20Підготовка%20knowl)
— read the spec itself; this folder never paraphrases it. (The file has no extension and begins
with `#`, so the link is percent-encoded. Renaming it to `homework1-spec.md` would be an
improvement.)

**Subject area:** a chatbot answering freight-exchange / logistics-platform engineering questions
— domain concepts, CQRS + Event Sourcing, a monolith-to-microservices case study, Kafka
telemetry, payments automation, and operating at 5,000 requests per second.

---

## Start here

1. [`docs/homework1/00-gap-analysis.md`](docs/homework1/00-gap-analysis.md) — what's done, what's missing, what it scores.
2. [`docs/homework1/01-decisions.md`](docs/homework1/01-decisions.md) — the fixed decisions you must not re-litigate.
3. [`docs/homework1/04-corpus-plan.md`](docs/homework1/04-corpus-plan.md) — the seven documents to write. **This is the actual work.**
4. Then, when the corpus exists: [`docs/homework1/07-pipeline-brief.md`](docs/homework1/07-pipeline-brief.md) → run → [`docs/homework1/templates/README-submission.md`](docs/homework1/templates/README-submission.md).

## Files

| File | What it is |
|---|---|
| [`docs/homework1/00-gap-analysis.md`](docs/homework1/00-gap-analysis.md) | Spec-vs-reality compliance, ranked gaps, pre-submission checklist |
| [`docs/homework1/01-decisions.md`](docs/homework1/01-decisions.md) | User-confirmed decisions + decisions resolved during planning |
| [`docs/homework1/02-approved-facts.md`](docs/homework1/02-approved-facts.md) | Sanitization allowlist — the only real-world figures permitted, plus what is forbidden |
| [`docs/homework1/03-glossary.md`](docs/homework1/03-glossary.md) | Domain and architecture vocabulary |
| [`docs/homework1/04-corpus-plan.md`](docs/homework1/04-corpus-plan.md) | The seven source documents: outlines, tiering, word budgets, status |
| [`docs/homework1/05-chunking-strategy.md`](docs/homework1/05-chunking-strategy.md) | **Sole owner of every splitting rule** — size, overlap, merges, edge cases |
| [`docs/homework1/06-chunk-schema.md`](docs/homework1/06-chunk-schema.md) | Per-field contract for a chunk, and why fields are nested |
| [`docs/homework1/07-pipeline-brief.md`](docs/homework1/07-pipeline-brief.md) | Implementation brief for `scripts/prepare_knowledge_base.py` |
| [`docs/homework1/08-test-plan.md`](docs/homework1/08-test-plan.md) | Optional pytest suite (above rubric) |
| [`docs/homework1/09-open-defects.md`](docs/homework1/09-open-defects.md) | Design contradictions found in review — **two need your decision before coding** |
| [`docs/homework1/10-reflection.md`](docs/homework1/10-reflection.md) | Risk register; becomes the submission README's Conclusions |

## Reusable artifacts

| File | Format | Use |
|---|---|---|
| [`docs/homework1/assets/chunk.schema.json`](docs/homework1/assets/chunk.schema.json) | JSON Schema 2020-12 | Validate every line of `chunks.jsonl`; owns the `document_type` enum |
| [`docs/homework1/assets/chunks.sample.jsonl`](docs/homework1/assets/chunks.sample.jsonl) | JSONL | 4 hand-written reference chunks — test fixture today, **replace with real output before submitting** |
| [`docs/homework1/assets/chunk.example.json`](docs/homework1/assets/chunk.example.json) | JSON | One pretty-printed chunk, for reading |
| [`docs/homework1/assets/document-set.json`](docs/homework1/assets/document-set.json) | JSON | Corpus manifest — generates `data/raw/` stubs and the README Sources table |
| [`docs/homework1/templates/README-submission.md`](docs/homework1/templates/README-submission.md) | Markdown | Draft of the repo-root `README.md`. **Not** the real README — it has placeholders worth 10 points |

## Target repository layout

Only `docs` exists today. Everything marked *(to create)* is outstanding work.

```
rag-ai-assistant/
├── docs/
│   ├── homework1/                  # this folder — planning artifacts
│   └── raw/                        # assignment specs
├── data/
│   ├── raw/                        # (to create) the 7 authored .md documents
│   └── processed/
│       └── chunks.jsonl            # (to create) generated; commit it — it is graded
├── scripts/
│   └── prepare_knowledge_base.py   # (to create)
├── tests/
│   └── test_prepare_knowledge_base.py   # (to create, optional — above rubric)
├── requirements.txt                # (to create) empty; stdlib only, Python >= 3.9
└── README.md                       # (to create) from templates/README-submission.md
```
