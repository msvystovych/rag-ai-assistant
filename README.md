<!--
  THIS IS THE GRADED SUBMISSION README (spec:56-64). Two sections below — "Example chunks" and
  "Conclusions" — are placeholders mapping to two 5-point rubric rows (spec:76-77). Submitting them
  unfilled scores ZERO on both: 10 points lost after all the work is done.

  TODO before submitting:
   [ ] Author data/raw/ and run scripts/prepare_knowledge_base.py (see docs/homework1/README.md).
   [ ] Replace "Example chunks" with 3-5 REAL lines from data/processed/chunks.jsonl, each with a
       one-line comment explaining what makes it a good chunk. NEVER paste the hand-written samples
       from docs/homework1/assets/chunks.sample.jsonl — they match no produced line.
   [ ] Rewrite "Conclusions" from the actual run's statistics (see docs/homework1/reflection.md).
   [ ] Prune the Sources table to the documents that actually exist, and drop its "None are
       written yet" caveat.
   [ ] Settle the open merge decisions in docs/homework1/pipeline-spec.md, then re-check the
       "Short chunks are merged" bullet under Chunking strategy still describes what the code does.
   [ ] Delete the "Work in progress" banner under the title, the "Planned" note under How to run,
       and this comment block — LAST, and only once all of the above is genuinely done. The banner
       is the only honest signal a GitHub reader sees; HTML comments do not render.
-->

# RAG Knowledge Base — Logistics-Domain Engineering Assistant

Homework #1 — preparing a knowledge base for a retrieval-augmented chatbot.
Assignment spec: [`docs/tasks/Домашнє завдання №1 — Підготовка knowl`](docs/tasks/Домашнє%20завдання%20№1%20—%20Підготовка%20knowl).

> ⚠️ **Work in progress — the design is complete, the corpus is not.** `data/raw/`, `scripts/`,
> and `data/processed/chunks.jsonl` **do not exist yet**. Everything below describes the intended
> pipeline; sections marked *planned* or *to be filled* are not yet real. Remaining work:
> [`docs/homework1/README.md`](docs/homework1/README.md).

## Subject area

A chatbot that answers freight-exchange / logistics-platform engineering questions: domain concepts
(loads, carriers, matching), architecture (CQRS + Event Sourcing, Kafka telemetry streaming), a
monolith-to-microservices migration case study, payments automation, and operating a platform at
5,000 requests per second.

Inspired by experience building a live digital logistics platform serving 8,500+ logistics service
providers across Europe. All documents are written from general logistics-engineering knowledge —
no proprietary material; the migration case study is a generic composite of standard strangler-fig
practice.

## Sources

Self-authored Markdown documents in `data/raw/`, all in English. **None are written yet** — this is
the planned corpus; prune this table to the documents that actually exist before submitting. The
core four alone satisfy the spec's ≥3 requirement with one document per `document_type`.

| File | Type | Covers |
|---|---|---|
| `freight-exchange-domain-primer.md` | concept-guide | actors, load lifecycle, matching |
| `cqrs-event-sourcing-for-logistics.md` | architecture-guide | CQRS / ES for freight |
| `monolith-to-microservices-migration.md` | case-study | strangler-fig, zero-downtime sync |
| `scaling-and-zero-downtime-operations.md` | playbook | scaling, deploys, observability |
| `real-time-freight-visibility.md` | concept-guide | telemetry, ETA, data quality *(extension)* |
| `kafka-vehicle-telemetry-streaming.md` | architecture-guide | topics, partitions, semantics *(extension)* |
| `freight-payments-automation.md` | concept-guide | settlement, idempotency, compliance *(extension)* |

## Metadata structure

Each JSONL line carries top-level `chunk_id` and `text`, plus a `metadata` object with
`document_id`, `source_file`, `source_type`, `title`, `section`, `chunk_index` (1-based),
`language` (`"en"`), `domain` (`"logistics-engineering"`), and `document_type`.

`chunk_id = <document_id>_chunk_<index:03d>`; `document_id` is the normalized filename stem.

**All required spec fields are present** — `chunk_id` and `text` at the top level; `document_id`,
`source_file`, and `chunk_index` nested under `metadata`, exactly as in the homework's own sample
chunk. The machine-readable contract is
[`docs/homework1/assets/chunk.schema.json`](docs/homework1/assets/chunk.schema.json).

## Chunking strategy

- **Method:** header-aware section splitting on ATX headings, with a recursive
  paragraph → line → sentence → word-boundary fallback inside long sections (never mid-word).
  Stdlib-only implementation.
- **Parameters:** `chunk_size` 800 characters (measured on the chunk body), `overlap` 150
  characters, `min_chunk` 500. Every emitted chunk's `text` is capped at **1000 characters
  including the breadcrumb prefix**.
- **Short chunks** are merged — short sections forward, a trailing piece backward — both capped at
  1000 characters including the breadcrumb. A within-section merge strips the duplicated overlap
  carry; a cross-section merge has no carry and strips nothing. Residual outliers are counted and
  reported by the script. *(Merge eligibility is still being finalised — see the open decisions in
  [`docs/homework1/pipeline-spec.md`](docs/homework1/pipeline-spec.md); re-check this bullet once
  they land.)*
- **Overlap parameter = 150 characters**, inside the required 100–200 band.

  > **Note for automated grading:** overlap applies between consecutive chunks *within a section
  > only*. Heading boundaries reset the window by design, so first-of-section pairs, cross-heading
  > pairs, and merge-produced pairs legitimately carry zero overlap. A per-pair overlap check must
  > compare same-section neighbours only.

- Each chunk's text is prefixed with `"Document Title > Section. "` so it reads standalone.

## How to run

*Planned — `scripts/prepare_knowledge_base.py` is specified in
[`docs/homework1/pipeline-spec.md`](docs/homework1/pipeline-spec.md) but not yet written.*

```bash
python scripts/prepare_knowledge_base.py \
  --raw-dir data/raw --out data/processed/chunks.jsonl \
  --chunk-size 800 --overlap 150 --min-chunk 500
```

Python ≥ 3.9, standard library only — no dependencies to install.

## Example chunks

<!-- PLACEHOLDER — worth 5 points (spec:76). Paste 3-5 real lines from data/processed/chunks.jsonl
     here, each followed by one comment line explaining what makes it a good chunk: it stands alone,
     it is inside the size band, it covers exactly one topic. -->

_To be filled from the first real pipeline run._

## Conclusions

<!-- PLACEHOLDER — worth 5 points (spec:77). Rewrite both lists from the actual run. Statistics to
     quote and questions to answer are listed in docs/homework1/reflection.md. -->

_To be filled from the first real pipeline run._

**What worked well:**

- <!-- e.g. breadcrumb prefixes made every sampled chunk understandable in isolation -->

**What to improve:**

- <!-- e.g. glossary-style sections chunk awkwardly; consider per-term chunks -->

---

Design notes, the corpus plan, and the full pipeline specification live in
[`docs/homework1/`](docs/homework1/README.md).
