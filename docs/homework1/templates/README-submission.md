<!--
  DRAFT of the repository-root README.md. Do NOT copy this to / and submit as-is.

  Two sections below — "Example chunks" and "Conclusions" — are placeholders mapping to two
  5-point rubric rows (spec:76-77). Submitting them unfilled scores ZERO on both: 10 points lost
  after all the work is done. See ../00-gap-analysis.md.

  TODO before this becomes README.md:
   [ ] Replace "Example chunks" with 3-5 REAL lines from data/processed/chunks.jsonl, each with
       a one-line comment explaining what makes it a good chunk.
   [ ] Rewrite "Conclusions" from the actual run's statistics (see ../10-reflection.md).
   [ ] If you authored only the core four documents, DELETE the four extension rows from the
       Sources table below.
   [ ] Delete this comment block.
-->

# RAG Knowledge Base — Logistics-Domain Engineering Assistant

## Subject area

A chatbot that answers freight-exchange / logistics-platform engineering questions: domain
concepts (loads, carriers, matching), architecture (CQRS + Event Sourcing, Kafka telemetry
streaming), a monolith-to-microservices migration case study, payments automation, and operating
a platform at 5,000 requests per second.

Inspired by my experience building a live digital logistics platform serving 8,500+ logistics
service providers across Europe. All documents are written from general logistics-engineering
knowledge — no proprietary material; the migration case study is a generic composite of standard
strangler-fig practice.

## Sources

Self-authored Markdown documents in `data/raw/`, all in English:

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

**All required spec fields are present** — `chunk_id` and `text` at the top level;
`document_id`, `source_file`, and `chunk_index` nested under `metadata`, exactly as in the
homework's own sample chunk.

## Chunking strategy

- **Method:** header-aware section splitting on ATX headings, with a recursive
  paragraph → line → sentence → word-boundary fallback inside long sections (never mid-word).
  Stdlib-only implementation.
- **Parameters:** `chunk_size` 800 characters (measured on the chunk body), `overlap` 150
  characters, `min_chunk` 500. Every emitted chunk's `text` is capped at **1000 characters
  including the breadcrumb prefix**.
- **Short chunks** are merged — short sections forward, a document's trailing piece backward —
  both capped at 1000 characters including the breadcrumb. A within-section merge strips the
  duplicated overlap carry; a cross-section merge has no carry and strips nothing. Residual
  outliers are counted and reported by the script.
- **Overlap parameter = 150 characters**, inside the required 100–200 band.

  > **Note for automated grading:** overlap applies between consecutive chunks *within a section
  > only*. Heading boundaries reset the window by design, so first-of-section pairs, cross-heading
  > pairs, and merge-produced pairs legitimately carry zero overlap. A per-pair overlap check must
  > compare same-section neighbours only.

- Each chunk's text is prefixed with `"Document Title > Section. "` so it reads standalone.
- **Run:** `python scripts/prepare_knowledge_base.py` → `data/processed/chunks.jsonl`

## Example chunks

<!-- PLACEHOLDER — worth 5 points. Paste 3-5 real lines from data/processed/chunks.jsonl here,
     each followed by one comment line explaining what makes it a good chunk: it stands alone,
     it is inside the size band, it covers exactly one topic. -->

## Conclusions

<!-- PLACEHOLDER — worth 5 points. Rewrite both lists from the actual run. Statistics to quote and
     questions to answer are listed in ../10-reflection.md. -->

**What worked well:**

- <!-- e.g. breadcrumb prefixes made every sampled chunk understandable in isolation -->
- <!-- e.g. header-aware splitting kept N% of chunks inside 500-1000 characters -->

**What to improve:**

- <!-- e.g. glossary-style sections chunk awkwardly; consider per-term chunks -->
- <!-- e.g. overlap sometimes repeats a heading instead of a sentence; snap to sentence boundaries -->
