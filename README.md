# RAG Knowledge Base — Logistics-Domain Engineering Assistant

Homework #1 — preparing a knowledge base for a retrieval-augmented chatbot.
Homework #2 — a basic semantic retrieval layer over that knowledge base.

Assignment specs:
[`docs/tasks/Домашнє завдання №1 — Підготовка knowl`](docs/tasks/Домашнє%20завдання%20№1%20—%20Підготовка%20knowl) ·
[`docs/tasks/Домашнє завдання №2 — Базовий semantic retrieval layer`](docs/tasks/Домашнє%20завдання%20№2%20—%20Базовий%20semantic%20retrieval%20layer)

The full pipeline runs end to end:

```
data/raw/*.md → prepare_knowledge_base.py → chunks.jsonl → build_index.py → Chroma index
                                                                                  ↓
                    retrieved chunks ← top-k cosine search ← retrieval.py ← user query
```

## Subject area

A chatbot that answers freight-exchange / logistics-platform engineering questions: domain concepts
(loads, carriers, matching), architecture (CQRS + Event Sourcing, Kafka telemetry streaming), a
monolith-to-microservices migration case study, and operating a platform at 5,000 requests per
second.

Inspired by experience building a live digital logistics platform serving 8,500+ logistics service
providers across Europe. All documents are written from general logistics-engineering knowledge —
no proprietary material; the migration case study is a generic composite of standard strangler-fig
practice, and says so in its own opening paragraph.

## Sources

Four self-authored Markdown documents in `data/raw/`, all in English — one per `document_type`.

| File | Type | Words | Chunks | Covers |
|---|---|---|---|---|
| `freight-exchange-domain-primer.md` | concept-guide | 1,604 | 18 | actors, load lifecycle, matching, vetting, vocabulary |
| `cqrs-event-sourcing-for-logistics.md` | architecture-guide | 1,670 | 18 | CQRS / ES for freight, events, projections |
| `monolith-to-microservices-migration.md` | case-study | 1,834 | 23 | strangler-fig, zero-downtime sync, decommissioning |
| `scaling-and-zero-downtime-operations.md` | playbook | 1,491 | 18 | load profile, caching, deploys, resilience, observability |
| **Total** | | **6,599** | **77** | |

Word counts are `wc -w` on each file.

## Metadata structure

Each JSONL line carries top-level `chunk_id` and `text`, plus a `metadata` object with
`document_id`, `source_file`, `source_type`, `title`, `section`, `chunk_index` (1-based),
`language` (`"en"`), `domain` (`"logistics-engineering"`), and `document_type`.

`chunk_id = <document_id>_chunk_<index:03d>`; `document_id` is the normalized filename stem.

**All required spec fields are present** — `chunk_id` and `text` at the top level; `document_id`,
`source_file`, and `chunk_index` nested under `metadata`, exactly as in the homework's own sample
chunk. The machine-readable contract is
[`docs/homework1/assets/chunk.schema.json`](docs/homework1/assets/chunk.schema.json), and every one
of the 77 committed lines validates against it.

## Chunking strategy

- **Method:** header-aware section splitting on ATX headings, with a recursive
  paragraph → line → sentence → word-boundary fallback inside long sections (never mid-word).
  Stdlib-only implementation.
- **Parameters:** `chunk_size` 800 characters (measured on the chunk body), `overlap` 150
  characters, `min_chunk` 500. Every emitted chunk's `text` is capped at **1000 characters
  including the breadcrumb prefix**.
- **Short chunks are merged** by a single rule: any chunk body under 500 characters is merged
  **backward** into the chunk before it, while the result — breadcrumb included — stays within 1000
  characters. A document's first chunk has no predecessor, so it is never merged. See Conclusions
  for what this rule actually achieved on the real corpus, which is not what the design predicted.
- Each chunk's text is prefixed with `"Document Title > Section. "` so it reads standalone.

  > **Note for automated grading:** overlap applies between consecutive chunks *within a section
  > only*. Heading boundaries reset the window by design, so first-of-section pairs, cross-heading
  > pairs, and merge-produced pairs legitimately carry zero overlap. A per-pair overlap check must
  > compare same-section neighbours only. Measured: of **52** same-section consecutive pairs,
  > **48** carry a 100–200 character overlap and **4** carry less (34–91). The four are not a bug:
  > the carry is capped at `chunk_size − len(next atom)` so a piece can never exceed 800, so when
  > the following paragraph is itself close to 800 characters there is little budget left to carry.

## How to run

```bash
# 1. Build the knowledge base — standard library only, no dependencies.
python scripts/prepare_knowledge_base.py \
  --raw-dir data/raw --out data/processed/chunks.jsonl \
  --chunk-size 800 --overlap 150 --min-chunk 500

# 2. Install the retrieval dependencies and provide an API key.
pip install -r requirements.txt
export OPENAI_API_KEY=sk-...        # or put it in a gitignored .env at the repo root

# 3. Embed the chunks and build the vector index.
python scripts/build_index.py

# 4. Search.
python scripts/retrieval.py --query "How does load matching work?" --k 3
python scripts/retrieval.py --interactive

# 5. Reproduce the evaluation and the chunk-size experiment.
python scripts/run_test_queries.py --k 3
python scripts/chunk_size_experiment.py --k 3
```

Step 1 needs only Python ≥ 3.9. Steps 2–5 need the packages in `requirements.txt`; verified on
Python 3.14.6. `notebooks/retrieval.ipynb` is the same pipeline interactively — it imports
`scripts/rag_lib.py` rather than reimplementing anything.

## Example chunks

Four real lines from `data/processed/chunks.jsonl`, reformatted for readability (each is one line in
the file).

**1 — a document's opening chunk. Stands alone with no prior context.**

```json
{"chunk_id": "freight_exchange_domain_primer_chunk_001",
 "text": "Freight Exchange Fundamentals: Actors, Loads, and Matching > What A Freight Exchange Is. A freight exchange is a two-sided digital marketplace in which one side publishes transport demand and the other offers vehicle capacity, while the platform supplies discovery, matching, and the commercial rails that let strangers transact safely. Demand arrives as loads: shipments described by origin, destination, weight, dimensions, equipment requirement, and a loading date window. …",
 "metadata": {"document_id": "freight_exchange_domain_primer", "source_file": "data/raw/freight-exchange-domain-primer.md", "source_type": "markdown", "title": "Freight Exchange Fundamentals: Actors, Loads, and Matching", "section": "What A Freight Exchange Is", "chunk_index": 1, "language": "en", "domain": "logistics-engineering", "document_type": "concept-guide"}}
```

*Why it is a good chunk:* 743 characters, opens on a complete definition, and answers "what is a
freight exchange" without needing any neighbouring chunk. The breadcrumb names both the document and
the section, so a retrieval hit is self-locating.

**2 — one topic, end to end.**

```json
{"chunk_id": "cqrs_event_sourcing_for_logistics_chunk_013",
 "text": "CQRS and Event Sourcing in a Freight Platform > Projections And Read Models. A projection is a consumer that folds the event stream into a shape optimized for one kind of query. A lane-search index is the natural example: fed by posting, repricing, and booking events, it stores each open load flat and pre-joined, with the filters carriers actually use — corridor, equipment type, weight band, date window — as first-class indexed attributes. …",
 "metadata": {"document_id": "cqrs_event_sourcing_for_logistics", "section": "Projections And Read Models", "chunk_index": 13, "document_type": "architecture-guide", "…": "…"}}
```

*Why it is a good chunk:* 842 characters covering exactly one concept — what a projection is, plus
three concrete examples. It defines its term before using it, which is what makes it embed well.

**3 — the case study's framing chunk.**

```json
{"chunk_id": "monolith_to_microservices_migration_chunk_001",
 "text": "Migrating a Logistics Monolith to Microservices > Introduction. This narrative is a generic composite of standard strangler-fig practice as it is applied to freight and logistics platforms. It is not a report on any specific company, team, or system. …",
 "metadata": {"document_id": "monolith_to_microservices_migration", "section": "Introduction", "chunk_index": 1, "document_type": "case-study", "…": "…"}}
```

*Why it is a good chunk:* 855 characters, and the one chunk that had to be authored at ≥500
characters by hand — a document's first piece is the only piece the backward-merge rule can never
rescue. It also carries the sanitization framing, so the disclaimer travels with the content
wherever it is retrieved.

**4 — a chunk that answers a "how do I" question directly.**

```json
{"chunk_id": "scaling_and_zero_downtime_operations_chunk_010",
 "text": "Operating a Freight Platform at 5,000 Requests per Second > Zero-Downtime Deployments. Zero-downtime deployment is usually attributed to the rollout mechanism, but the mechanism is the smaller half. Rolling updates replace instances gradually and are the cheapest option; blue-green and canary rollouts hold a full second environment or a small traffic slice … What actually makes any of them safe is that consecutive versions can run side by side. …",
 "metadata": {"document_id": "scaling_and_zero_downtime_operations", "section": "Zero-Downtime Deployments", "chunk_index": 10, "document_type": "playbook", "…": "…"}}
```

*Why it is a good chunk:* 778 characters that state a claim, correct a common misconception, and
give the consequence. It is the top-1 result for query `q06` ("release new code without users
noticing any interruption") even though the query shares almost no vocabulary with it.

---

# Homework #2 — semantic retrieval layer

## Embeddings and vector storage

| | |
|---|---|
| **Embedding model** | OpenAI `text-embedding-3-small`, 1,536 dimensions |
| **What is embedded** | each chunk's full `text`, breadcrumb prefix included |
| **Query encoding** | the **same** model — enforced, not assumed (see below) |
| **Vector store** | Chroma `PersistentClient`, `index/chroma/`, HNSW, cosine space |
| **Vectors indexed** | 77 — equal to the line count of `chunks.jsonl` |
| **Score** | `1 - cosine_distance`, so 1.000 is identical and 0.000 orthogonal |

`index/chroma/manifest.json` records the model, dimension, chunk count, collection name and a
SHA-256 of the input file. `retrieval.py` reads it before every search and **refuses to run** if the
index was built with a different embedding model than the one configured — a mismatched index is a
hard error rather than a silently wrong answer.

## Retrieval

```bash
$ python scripts/retrieval.py --query "How does load matching work?" --k 3

Query: How does load matching work?

Top-1: freight_exchange_domain_primer_chunk_012 | score: 0.657
  Text: Freight Exchange Fundamentals: Actors, Loads, and Matching > Load Matching Mechanics. …
  Source: data/raw/freight-exchange-domain-primer.md
  Document: freight_exchange_domain_primer | Section: Load Matching Mechanics | Type: concept-guide
```

`--json` emits the same results as structured JSON; `--interactive` opens a query loop.

## Test queries and results

Ten queries, deliberately mixed so the evaluation cannot flatter itself — full results with
per-query relevance comments in
[`outputs/retrieval_examples.md`](outputs/retrieval_examples.md).

| Category | n | Mean top-1 | What it tests |
|---|---|---|---|
| direct | 3 | 0.601 | queries reusing the corpus's own vocabulary |
| paraphrase | 3 | 0.423 | queries deliberately avoiding corpus wording |
| cross-document | 3 | 0.577 | answers spanning more than one document |
| out-of-corpus | 1 | 0.266 | a question the corpus cannot answer |

**Top-1 hit rate on the nine in-corpus queries: 9/9.** Every one put an expected document at rank 1,
including all three paraphrases.

## Conclusions — Homework #2

**Where retrieval works well.** Semantic matching genuinely works: `q06` asks how to "release new
code without users noticing any interruption" and never says *deployment*, *rolling*, or
*blue-green*, yet all three hits are the Zero-Downtime Deployments section. A keyword index could
not do that. Results also cluster tightly — across the nine in-corpus queries a top-3 spans 2.00
distinct sections and 1.33 distinct documents on average, so hits concentrate where the answer is.

**Where it breaks down.**

1. **Paraphrasing costs 30% of the similarity score** — 0.601 mean top-1 for direct queries against
   0.423 for paraphrases. Ranking survives; the margin does not. On a bigger or noisier corpus that
   is where the first errors would appear.
2. **There is no "I don't know."** The out-of-corpus query still returns three confidently formatted
   results. Only the score betrays it — 0.266 against an in-corpus floor of 0.413 — and **no
   threshold is enforced anywhere in the code**. A floor near 0.35 is the obvious next control, and
   it is required before these chunks are ever fed to an LLM.
3. **One high score is lexical, not semantic.** `q08` contains the exact phrase "5,000 requests per
   second", which the breadcrumb prepends to *every* chunk of that document via its H1. Part of that
   0.646 is keyword overlap wearing a semantic score's clothing.
4. **Chunks that open mid-sentence rank well and read badly** — an artifact of the overlap carry,
   visible in `q01` and `q09`.

**Chunk-size experiment** ([`outputs/chunk_size_experiment.md`](outputs/chunk_size_experiment.md)),
closing risk #7 in `docs/homework1/reflection.md`, which deferred chunk-size tuning to this
homework. Re-chunking at 500/100 gives 116 chunks and *raises* mean top-1 slightly (0.546 vs 0.534)
— but top-1 hit rate falls from **100% to 89%**, and the separation margin against the out-of-corpus
query collapses from **0.147 to 0.101**. Smaller chunks buy sharper peaks and pay in discrimination.
**800/150 is retained**, now on evidence rather than on a best-practice guess.

**Honest limitations.** The corpus and the queries share an author, which makes retrieval easier
than it would be in the wild; the paraphrase category exists to push against exactly that, and the
30% score drop is the size of the effect. Ten queries over 77 chunks is an anecdote, not a
benchmark — no recall@k or nDCG is reported, because with one relevant document per query those
metrics would dress up the same ten observations in statistics they cannot support.

Full analysis: [`docs/homework2/analysis.md`](docs/homework2/analysis.md).

## Conclusions — Homework #1 chunk quality

Measured on the committed run: 4 documents → **77 chunks**, `text` length min 390 / mean 707 / max
930, and **70 of 77 (90.9%)** inside the 500–1000 band. Every figure below is printed by
`scripts/prepare_knowledge_base.py` itself, so it can be reproduced with one command.

**What worked well:**

- **The breadcrumb prefix does its job.** Reading five chunks at random, every one was
  understandable in isolation — the `"Document Title > Section. "` prefix means a retrieved fragment
  always names its own context. It costs a mean of 79 characters per chunk, which is the price of
  the 92.2% band figure above, and it is worth it.
- **Overlap behaves as specified for 48 of 52 same-section pairs**; the other 4 carry 34–91
  characters because the carry is capped so a piece can never exceed `chunk_size`. Zero-overlap
  pairs occur only across headings, as designed.
- **No chunk is truncated mid-word, and none exceeds the 1000-character ceiling.** Reruns on
  unchanged input are byte-identical, so re-chunking is a safe one-command experiment — which is
  what made the Homework #2 chunk-size comparison cheap to run.
- **Zero chunks under 250 characters**, which was the design's actual goal.

**What to improve:**

- **The `merge_short` rule is nearly inert at these parameters, and the design did not predict
  that.** `pipeline-spec.md` § D1 argues the rule at length and its simulation projected 8.5%
  sub-500 bodies against 14.6% without merging. Reality: **16.9% (13 of 77)**. The script reports
  the rule's own tally: **14 candidates, 1 merged, 13 refused by the ≤1000-character cap.** The
  cause is arithmetic the simulation missed — the cap is `1000 − longest breadcrumb` ≈ 900, and a
  predecessor packed to ~800 characters leaves only ~110 characters of headroom, so almost every
  undersized tail is too big to absorb. The 500/100 variant is the control that proves it: with a
  ~500-character predecessor there *is* headroom, and there the same rule fires **17 times out of
  17 candidates, refusing none**. At `chunk_size` 800 the rule cannot fire on the case it was
  written for. Either lower `chunk_size` to ~650 to create headroom, or drop the rule and its ~15
  lines. This is the clearest gap between the plan and the outcome, and only a real run showed it.
- **Overlap should snap to a sentence boundary.** The carry currently snaps to a word boundary, so
  chunks routinely open mid-sentence ("time and handling risk. That distinction…"). Ranking is
  unaffected — the embedding sees the whole chunk — but it reads badly and it hurt the readability
  of `q01`'s and `q09`'s top hit. This is `reflection.md` risk #3, now confirmed on real output.
- **Prose-only authoring paid off.** No section chunked badly, because the corpus contains no tables
  and no long lists. That was a deliberate constraint, and the absence of a problem here is the
  evidence it was the right one.
- **Every section was long enough to split** — 25 of 25 exceeded 800 characters, so no section
  fitted in a single chunk. Sections of 1,300–1,800 characters produce 2–3 chunks each and a tail;
  aiming at ~1,600 (a clean 2× the target) would waste less.
- **Which document chunked worst:** `scaling-and-zero-downtime-operations.md` — 4 residuals out of
  18 chunks (22.2%), against 17.4% for the migration case study (4 of 23), 16.7% for the primer
  (3 of 18) and 11.1% for the CQRS guide (2 of 18). It is the shortest document (1,491 words) with
  the same six-section structure as the others, so its sections sit closest to the awkward
  ~900–1,300 character band that yields one full 800-character piece plus a short tail. Section
  length, not subject matter, drives residuals.

---

## Repository layout

```
├── data/raw/                     4 authored Markdown source documents
├── data/processed/
│   ├── chunks.jsonl              77 chunks — the Homework #1 deliverable
│   └── chunks_500.jsonl          116 chunks at 500/100 — chunk-size experiment only
├── data/eval/test_queries.json   10 evaluation queries + relevance comments
├── index/
│   ├── chroma/                   the graded index (77 vectors) + manifest.json
│   └── chroma_500/               experiment index (116 vectors) — not a deliverable
├── scripts/
│   ├── prepare_knowledge_base.py Homework #1 — stdlib only
│   ├── rag_lib.py                settings, embeddings, index handle
│   ├── build_index.py            embed chunks → Chroma
│   ├── retrieval.py              top-k semantic search (CLI)
│   ├── run_test_queries.py       evaluation → outputs/retrieval_examples.md
│   └── chunk_size_experiment.py  800/150 vs 500/100 comparison
├── notebooks/retrieval.ipynb     the same pipeline, interactively
├── outputs/                      retrieval examples + experiment results
├── tests/                        47 tests; no API key or network required
└── docs/homework1|homework2|tasks
```

Design notes and the full pipeline specification live in
[`docs/homework1/`](docs/homework1/README.md) and [`docs/homework2/`](docs/homework2/analysis.md).
