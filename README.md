# RAG Knowledge Base — Logistics-Domain Engineering Assistant

Homework #1 — preparing a knowledge base for a retrieval-augmented chatbot.
Homework #2 — a basic semantic retrieval layer over that knowledge base.
Homework #3 — an improved retrieval pipeline: metadata filtering + hybrid BM25/RRF search.
Homework #4 — grounded answer generation: the model answers only from retrieved context, with citations.
Homework #5 — external tool integration: the model calls a live operations API, or falls back to the knowledge base.
Homework #6 — first agentic structure: a rule-based router picks a route, commits to a plan, and runs it step by step.

Assignment specs:
[`docs/tasks/Домашнє завдання №1 — Підготовка knowl`](docs/tasks/Домашнє%20завдання%20№1%20—%20Підготовка%20knowl) ·
[`docs/tasks/Домашнє завдання №2 — Базовий semantic retrieval layer`](docs/tasks/Домашнє%20завдання%20№2%20—%20Базовий%20semantic%20retrieval%20layer) ·
[`docs/tasks/Домашнє завдання №3 — Покращення retrieval pipeline`](docs/tasks/Домашнє%20завдання%20№3%20—%20Покращення%20retrieval%20pipeline) ·
[`docs/tasks/Домашнє завдання №4 — Генерація відповіді поверх retrieval`](docs/tasks/Домашнє%20завдання%20№4%20—%20Генерація%20відповіді%20поверх%20retrieval) ·
[`docs/tasks/Домашнє завдання №5 — Інтеграція зовнішнього tool або джерела`](docs/tasks/Домашнє%20завдання%20№5%20—%20Інтеграція%20зовнішнього%20tool%20або%20джерела) ·
[`docs/tasks/Домашнє завдання №6 — Перша agentic-структура`](docs/tasks/Домашнє%20завдання%20№6%20—%20Перша%20agentic-структура)

```
data/raw/*.md → prepare_knowledge_base.py → chunks.jsonl → build_index.py → Chroma index
                                                                                  ↓
                    retrieved chunks ← top-k cosine search ← retrieval.py ← user query
                                                                                  ↓
      fused chunks ← document_type filter + BM25 ‖ semantic, RRF ← retrieval_improved.py
                                                                                  ↓
  grounded answer + [chunk_id] citations ← LLM ← prompt + relevance floor ← rag_answer.py
                                                                                  ↑
        no tool call ── model chooses ── tool call → validate → operations API → external_tool.py
                                                                                  ↓
   final answer + state ← step → observation → next step ← rule-based route ← agent_flow.py
```

## Subject area

The chatbot answers freight-exchange and logistics-platform engineering questions. The corpus
covers four areas:

- domain concepts (loads, carriers, matching)
- architecture (CQRS + Event Sourcing)
- a monolith-to-microservices migration case study
- operation of a platform at 5,000 requests per second

The author wrote all four documents from general logistics-engineering knowledge. No document
carries proprietary material.

## Sources

Four self-authored Markdown documents in `data/raw/`, one per `document_type`.

| File | Type | Words | Chunks |
|---|---|---|---|
| `freight-exchange-domain-primer.md` | concept-guide | 1,604 | 18 |
| `cqrs-event-sourcing-for-logistics.md` | architecture-guide | 1,670 | 18 |
| `monolith-to-microservices-migration.md` | case-study | 1,834 | 23 |
| `scaling-and-zero-downtime-operations.md` | playbook | 1,491 | 18 |
| **Total** | | **6,599** | **77** |

## Metadata structure

Each JSONL line carries the top-level fields `chunk_id` and `text`. Each line also carries a
`metadata` object. The object holds `document_id`, `source_file`, `source_type`, `title`,
`section`, `chunk_index` (1-based), `language`, `domain`, and `document_type`.
`chunk_id = <document_id>_chunk_<index:03d>`. All 77 lines validate against
[`docs/homework1/assets/chunk.schema.json`](docs/homework1/assets/chunk.schema.json).

## Chunking strategy

- The splitter is header-aware. Inside a long section it falls back to a paragraph, then a line,
  then a sentence, then a word boundary. It never splits mid-word, and it uses the standard
  library only.
- `chunk_size` is 800 characters, `overlap` is 150, and `min_chunk` is 500. The cap holds every
  chunk to 1000 characters. That count includes the `"Document Title > Section. "` breadcrumb
  prefix that the chunk carries.
- The pipeline merges a chunk under 500 characters backward into its predecessor. It merges only
  when the result fits the cap.
- Overlap applies between consecutive chunks *within a section only*. A heading boundary resets
  the window by design.

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

# 6. Homework #3 — improved search and the baseline-vs-improved comparison.
#    Query mode infers the document_type filter; --document-type overrides it, --no-filter and
#    --no-hybrid disable each technique. --compare reads the committed HW2 baseline read-only.
python scripts/retrieval_improved.py --query "How do we release code without interruption?" --k 3
python scripts/retrieval_improved.py --compare --k 3

# 7. Homework #4 — grounded answers over the retrieved context.
#    The relevance floor (--min-score, default 0.35) empties the context when nothing clears it;
#    --no-min-score leaves the refusal entirely to the prompt. --prompt-version v1|v2|v3 selects
#    the template, so any before/after in outputs/prompt_improvements.md is reproducible.
python scripts/rag_answer.py --query "What is a backhaul and why does it matter to a carrier?" --k 3
python scripts/rag_answer.py --evaluate --k 3
python scripts/rag_answer.py --improvements

# 8. Homework #5 — external tool integration. The model is offered both tools on every turn and
#    decides; no tool call falls through to the Homework #4 pipeline. --confirm is the operator's
#    authorisation for the write tool and the model can never set it. --list-tools needs no key.
python scripts/external_tool.py --list-tools
python scripts/external_tool.py --question "Where is load FX-2026-000042 right now?"
python scripts/external_tool.py --question "Book load FX-2026-000211 for carrier CAR-00817." --confirm
python scripts/external_tool.py --examples

# 9. Homework #6 — the deterministic agent workflow. No model and no key anywhere in this one:
#    a rule-based router picks one of four routes, the route commits to a plan, and each step's
#    observation is recorded in state that later steps read. --describe prints routes/tools/state.
python scripts/agent_flow.py --describe
python scripts/agent_flow.py --question "What does the status matched mean?"
python scripts/agent_flow.py --question "Book load FX-2026-000211 for carrier CAR-00817." --confirm
python scripts/agent_flow.py --examples
```

Step 1 needs only Python ≥ 3.9. Steps 2–9 need the packages in `requirements.txt`, and step 9
needs no API key. The recorded
verification ran on Python 3.14.6. `notebooks/retrieval.ipynb` runs the same pipeline
interactively. It imports `scripts/rag_lib.py`, and it reimplements nothing.

## Example chunks

Five real lines from `data/processed/chunks.jsonl` follow. Only the layout changed, to make them
easier to read. Every field stays verbatim, and this section elides nothing. All four source
documents appear.

**1 — a document's opening chunk.** It stands alone, and it opens on a complete definition.
The breadcrumb prefix makes every retrieval hit self-locating.

```json
{"chunk_id": "freight_exchange_domain_primer_chunk_001",
 "text": "Freight Exchange Fundamentals: Actors, Loads, and Matching > What A Freight Exchange Is. A freight exchange is a two-sided digital marketplace in which one side publishes transport demand and the other offers vehicle capacity, while the platform supplies discovery, matching, and the commercial rails that let strangers transact safely. Demand arrives as loads: shipments described by origin, destination, weight, dimensions, equipment requirement, and a loading date window. Supply arrives as capacity: vehicles with a known body type, a current or planned position, and a date on which they become free. The platform's core product is the reduction of search cost between the two.\n\nThe model is usually contrasted with traditional brokerage.",
 "metadata": {"document_id": "freight_exchange_domain_primer", "source_file": "data/raw/freight-exchange-domain-primer.md", "source_type": "markdown", "title": "Freight Exchange Fundamentals: Actors, Loads, and Matching", "section": "What A Freight Exchange Is", "chunk_index": 1, "language": "en", "domain": "logistics-engineering", "document_type": "concept-guide"}}
```

**2 — one topic, end to end.** It defines its term ("projection") before it uses the term,
which is what makes it embed well.

```json
{"chunk_id": "cqrs_event_sourcing_for_logistics_chunk_013",
 "text": "CQRS and Event Sourcing in a Freight Platform > Projections And Read Models. A projection is a consumer that folds the event stream into a shape optimized for one kind of query. A lane-search index is the natural example: fed by posting, repricing, and booking events, it stores each open load flat and pre-joined, with the filters carriers actually use — corridor, equipment type, weight band, date window — as first-class indexed attributes. A tracking view is fed by position events and holds only the latest known position per shipment plus a short trail. A settlement view is fed by delivery and invoicing events. None of these needs to agree with the others on structure, and none needs to be a relational store; a search index, a key-value store, and a relational table are all reasonable projection targets for different query shapes.",
 "metadata": {"document_id": "cqrs_event_sourcing_for_logistics", "source_file": "data/raw/cqrs-event-sourcing-for-logistics.md", "source_type": "markdown", "title": "CQRS and Event Sourcing in a Freight Platform", "section": "Projections And Read Models", "chunk_index": 13, "language": "en", "domain": "logistics-engineering", "document_type": "architecture-guide"}}
```

**3 — it answers a "how do I" question directly.** It is top-1 for query `q06`, although the
query shares almost no vocabulary with it.

```json
{"chunk_id": "scaling_and_zero_downtime_operations_chunk_010",
 "text": "Operating a Freight Platform at 5,000 Requests per Second > Zero-Downtime Deployments. Zero-downtime deployment is usually attributed to the rollout mechanism, but the mechanism is the smaller half. Rolling updates replace instances gradually and are the cheapest option; blue-green and canary rollouts hold a full second environment or a small traffic slice and buy a faster, cleaner rollback for riskier changes. What actually makes any of them safe is that consecutive versions can run side by side, because during every rollout both are serving live traffic. That requirement propagates into every contract the service exposes. API changes must be additive, readers must tolerate unknown fields, and event schemas must evolve without reordering or repurposing existing ones.",
 "metadata": {"document_id": "scaling_and_zero_downtime_operations", "source_file": "data/raw/scaling-and-zero-downtime-operations.md", "source_type": "markdown", "title": "Operating a Freight Platform at 5,000 Requests per Second", "section": "Zero-Downtime Deployments", "chunk_index": 10, "language": "en", "domain": "logistics-engineering", "document_type": "playbook"}}
```

**4 — the shortest chunk in the corpus, at 390 characters.** A short section produces it, and
`merge_short` cannot fold it into an ~800-character predecessor. It still reads on its own.
Its body is 315 characters, so it is one of the 13 sub-500 bodies that the pipeline reports
rather than pads.

```json
{"chunk_id": "monolith_to_microservices_migration_chunk_010",
 "text": "Migrating a Logistics Monolith to Microservices > Strangler-Fig Execution. The strangler-fig pattern replaces a system incrementally by intercepting calls at its edge and redirecting them, capability by capability, until nothing routes to the original. It is preferred over a rewrite because it keeps the product shippable throughout, and because each increment is independently reversible.",
 "metadata": {"document_id": "monolith_to_microservices_migration", "source_file": "data/raw/monolith-to-microservices-migration.md", "source_type": "markdown", "title": "Migrating a Logistics Monolith to Microservices", "section": "Strangler-Fig Execution", "chunk_index": 10, "language": "en", "domain": "logistics-engineering", "document_type": "case-study"}}
```

**5 — the disclosed weakness, shown and not described.** The body opens on "rules.", because the
overlap carry snaps back to a word boundary and not to a sentence boundary. 48 of 77 chunks open
this way. Ranking does not suffer — this chunk is top-1 for `q02` — but a human reader meets a
fragment of the previous chunk's sentence first.

```json
{"chunk_id": "cqrs_event_sourcing_for_logistics_chunk_002",
 "text": "CQRS and Event Sourcing in a Freight Platform > Why CQRS Fits Freight. rules. Reads are constant, tolerant of being a moment out of date, and want a flat shape that no normalized booking schema will produce cheaply.\n\nServing both from one model forces a permanent compromise. A schema normalized enough to enforce booking invariants needs multi-way joins to answer a search query, and the indexes added to rescue that search then slow the very writes the schema was designed to protect. Separating the two sides buys independent optimization: the write model keeps a small, strongly consistent core focused on correctness, while read models are denormalized, duplicated freely, and shaped per use case — one for lane search, another for a carrier's active shipments, another for settlement.",
 "metadata": {"document_id": "cqrs_event_sourcing_for_logistics", "source_file": "data/raw/cqrs-event-sourcing-for-logistics.md", "source_type": "markdown", "title": "CQRS and Event Sourcing in a Freight Platform", "section": "Why CQRS Fits Freight", "chunk_index": 2, "language": "en", "domain": "logistics-engineering", "document_type": "architecture-guide"}}
```
---

# Homework #2 — semantic retrieval layer

## How to verify this homework (grading checklist)

Each rubric row of the assignment (§ 4) maps to committed evidence and a copy-paste check.
Everything except V2's live query runs **offline — no API key required**. Install the dependencies
first, then run every command from the repo root. Git tracks all § 3 deliverables:

- `scripts/retrieval.py` + `notebooks/retrieval.ipynb`
- `index/chroma/` — Chroma is a spec-listed alternative to FAISS
- `outputs/retrieval_examples.md`
- this README

| Rubric criterion (§ 4) | Pts | Evidence | Check |
|---|---|---|---|
| Embeddings created & stored — index exists, model named | 10 | [`index/chroma/manifest.json`](index/chroma/manifest.json): `text-embedding-3-small`, 77 vectors — one per line of `chunks.jsonl` | V1 |
| Top-k semantic search — script runs, returns `chunk_id` + `score` | 15 | [`scripts/retrieval.py`](scripts/retrieval.py) · [`notebooks/retrieval.ipynb`](notebooks/retrieval.ipynb) | V2 |
| Minimum 5 queries tested, results recorded | 10 | [`outputs/retrieval_examples.md`](outputs/retrieval_examples.md): **10** queries, each `Query` / `Top-1..3` / `Comment` | V3 |
| Metadata present in results | 5 | a `Source:` line on all 30 recorded hits; `source_file` + `document_id` per hit in [`outputs/retrieval_results.json`](outputs/retrieval_results.json) | V4 |
| Conclusion — where retrieval works, where it fails | 10 | [Conclusions — Homework #2](#conclusions--homework-2) · [`docs/homework2/analysis.md`](docs/homework2/analysis.md) | V5 |

```bash
# V1 — index exists, model recorded, exactly one vector per chunk (offline).
python -c "import json, chromadb; from chromadb.config import Settings as S; \
m = json.load(open('index/chroma/manifest.json')); \
c = chromadb.PersistentClient(path='index/chroma', settings=S(anonymized_telemetry=False)).get_collection(m['collection']); \
n = sum(1 for l in open('data/processed/chunks.jsonl', encoding='utf-8') if l.strip()); \
print('model:', m['embedding_model'], '| vectors:', c.count(), '| chunks:', n); \
assert m['chunk_count'] == c.count() == n"

# V2 — the search script runs end to end (needs OPENAI_API_KEY; one embedding call).
python scripts/retrieval.py --query "How does load matching work?" --k 3

# V3 — 10 queries, each with Top-1..3 and a relevance comment (offline).
grep -c "^Query: " outputs/retrieval_examples.md                                     # 10
grep -cE "^Top-[123]: [a-z0-9_]+ \| score: 0\.[0-9]+" outputs/retrieval_examples.md  # 30
grep -c "^Comment: " outputs/retrieval_examples.md                                   # 10

# V4 — metadata on every recorded hit (offline).
grep -c "  Source: data/raw/" outputs/retrieval_examples.md                          # 30
grep -c '"source_file"' outputs/retrieval_results.json                               # 30

# V5 — the conclusions' headline numbers reproduce from the committed results (offline).
python -c "import json; r = json.load(open('outputs/retrieval_results.json'))['records']; \
top = lambda cat: [x['hits'][0]['score'] for x in r if x['category'] == cat]; \
ic = [x['hits'][0]['score'] for x in r if x['category'] != 'out-of-corpus']; \
print('direct', round(sum(top('direct'))/3, 3), '| paraphrase', round(sum(top('paraphrase'))/3, 3), \
'| in-corpus floor', round(min(ic), 3), '| out-of-corpus', round(top('out-of-corpus')[0], 3))"
#   direct 0.601 | paraphrase 0.423 | in-corpus floor 0.413 | out-of-corpus 0.266

# The full test suite — 521 tests (74 HW1-2 + 52 HW3 + 79 HW4 + 121 HW5 + 195 HW6), offline, no key or network.
python -m pytest -q
```

A read of the Chroma index (V1, V2) may touch its binary bookkeeping files. The content does not
change. `git checkout -- index/` restores a clean tree afterwards.

## Embeddings and vector storage

| | |
|---|---|
| **Embedding model** | OpenAI `text-embedding-3-small`, 1,536 dimensions |
| **What the pipeline embeds** | each chunk's full `text`, breadcrumb prefix included |
| **Query encoding** | the **same** model — enforced, not assumed |
| **Vector store** | Chroma `PersistentClient`, `index/chroma/`, HNSW, cosine space |
| **Vectors indexed** | 77 — equal to the line count of `chunks.jsonl` |
| **Score** | `1 - cosine_distance`, so 1.000 is identical and 0.000 orthogonal |

`index/chroma/manifest.json` records the model, the dimension, the chunk count and a SHA-256 of
the input file. `retrieval.py` reads that manifest before every search. It **refuses to run**
against an index that a different model built, or against one from a since-edited `chunks.jsonl`.

## Retrieval

```bash
$ python scripts/retrieval.py --query "How does load matching work?" --k 3

Query: How does load matching work?

Top-1: freight_exchange_domain_primer_chunk_012 | score: 0.657
  Text: Freight Exchange Fundamentals: Actors, Loads, and Matching > Load Matching Mechanics. …
  Source: data/raw/freight-exchange-domain-primer.md
  Document: freight_exchange_domain_primer | Section: Load Matching Mechanics | Type: concept-guide
```

`--json` emits the same results as structured JSON. `--interactive` opens a query loop.

## Test queries and results

Ten queries mix the categories deliberately, so the evaluation cannot flatter itself. The full
results live in [`outputs/retrieval_examples.md`](outputs/retrieval_examples.md), with a relevance
comment per query.

| Category | n | Mean top-1 | What it tests |
|---|---|---|---|
| direct | 3 | 0.601 | queries reusing the corpus's own vocabulary |
| paraphrase | 3 | 0.423 | queries deliberately avoiding corpus wording |
| cross-document | 3 | 0.577 | answers spanning more than one document |
| out-of-corpus | 1 | 0.266 | a question the corpus cannot answer |

**Top-1 hit rate on the nine in-corpus queries: 9/9**, including all three paraphrases.

## Conclusions — Homework #2

**Where retrieval works well.** Semantic matching genuinely works. `q06` asks how to
"release new code without users noticing any interruption".
The query never uses the corpus's vocabulary. It still gets the Zero-Downtime Deployments section
for all three hits. Results cluster tightly: a top-3 spans 2.00 distinct sections and 1.33
distinct documents on average.

**Where it breaks down.**

1. **Paraphrasing costs 30% of the similarity score** (0.601 direct vs 0.423 paraphrase).
   Ranking survives. The margin does not.
2. **There is no "I don't know."**
   The out-of-corpus query still returns three confidently formatted results. Only the score
   betrays it: 0.266, against an in-corpus floor of 0.413. The pipeline enforces no threshold.
   A floor near 0.35 is the obvious next control.
3. **One high score is partly lexical.** `q08` repeats a phrase that the breadcrumb prepends to
   every chunk of one document. Keyword overlap then inflates a semantic-looking score.
4. **Chunks that open mid-sentence rank well and read badly** — an artifact of the overlap carry.

**Chunk-size experiment** ([`outputs/chunk_size_experiment.md`](outputs/chunk_size_experiment.md)):
re-chunking at 500/100 raises mean top-1 a little. It also drops the hit rate from 100% to 89%.
It narrows the out-of-corpus separation margin from 0.147 to 0.101. **The pipeline keeps
800/150**, on evidence rather than a best-practice guess.

**Limitations.** The corpus and the queries share an author, which makes retrieval easier than in
the wild. Ten queries over 77 chunks is an anecdote, not a benchmark. Full analysis:
[`docs/homework2/analysis.md`](docs/homework2/analysis.md).

## Conclusions — Homework #1 chunk quality

On the committed run, 4 documents produced **77 chunks**. `text` length is min 390 / mean 707 /
max 930, and **90.9%** of the chunks fall inside the 500–1000 band.
`scripts/prepare_knowledge_base.py` itself prints the document, chunk and length figures.

**What worked well:**

- The breadcrumb prefix makes every chunk understandable in isolation.
  It costs 79 characters per chunk on average.
- Overlap behaves as the spec says for 48 of 52 same-section pairs.
  The other 4 carry less, because the pipeline caps the carry, so a piece can never exceed
  `chunk_size`. That is a design decision, not a bug.
- No chunk breaks mid-word. None exceeds the 1000-character ceiling.
  None is under 250 characters. A rerun on unchanged input gives a byte-identical result.

**What to improve:**

- **The backward-merge rule is nearly inert at 800/150.** The rule found 14 candidates and
  merged 1. The 1000-character cap refused the other 13, because a predecessor packed to ~800
  characters leaves no headroom. Lower `chunk_size` to ~650, or drop the rule.
- **Overlap should snap to a sentence boundary.** Chunks routinely open mid-sentence.
  That reads badly in retrieval output, although the ranking does not change.
- Sections of ~1,600 characters (a clean 2× the target) would split with less waste.

---

# Homework #3 — improved retrieval pipeline

Homework #3 adds two techniques on top of the Homework #2 layer. The same 10 queries measure both
against that layer:

1. **Metadata filtering.**
   A rule-based keyword map infers a `document_type` filter from the query. Zero matches or a tie
   leave the query unfiltered. The filter narrows **both** the semantic branch (Chroma `where=`)
   and the lexical branch. `--document-type` overrides the filter, and `--no-filter` disables it.
2. **Hybrid search.**
   Reciprocal Rank Fusion fuses the semantic ranking with a standard-library BM25 ranking. It adds
   no new dependencies.

The baseline is the committed Homework #2 result file, and the compare run reads it read-only.
That run refuses to proceed on a model or k mismatch, rather than compare apples to oranges.
Design decisions and known limits:
[`docs/homework3/retrieval-improvements-spec.md`](docs/homework3/retrieval-improvements-spec.md).

## How to verify this homework (grading checklist)

Git tracks all § 3 deliverables:

- `scripts/retrieval_improved.py`
- `outputs/retrieval_comparison.md`
- this README

Git also tracks `outputs/retrieval_results_improved.json`, the machine-readable backing for the
comparison. That file is the HW3 counterpart of HW2's `retrieval_results.json`. The § 3 list does
not name it, and the repo keeps it because the checks below verify against it. Everything except
V2's live query runs **offline — no API key required**.

| Rubric criterion (§ 4) | Pts | Evidence | Check |
|---|---|---|---|
| Metadata filtering implemented — works, narrows results | 15 | [`scripts/rag_lib.py`](scripts/rag_lib.py) (`infer_document_type`, `search(..., where=)`) · per-query `Filter` lines in [`outputs/retrieval_comparison.md`](outputs/retrieval_comparison.md) | V1, V2 |
| One improvement implemented correctly (hybrid search) | 15 | [`scripts/rag_lib.py`](scripts/rag_lib.py) (`Bm25Index`, `rrf_fuse`, `search_improved`) + offline tests | V3 |
| Baseline vs improved comparison for 5+ queries | 10 | [`outputs/retrieval_comparison.md`](outputs/retrieval_comparison.md): **10** queries, per-query table + side-by-side detail | V4 |
| Conclusion — what gave the biggest effect | 10 | [Conclusions — Homework #3](#conclusions--homework-3) · the Conclusion section of [`outputs/retrieval_comparison.md`](outputs/retrieval_comparison.md) | V5 |

```bash
# V1 — the filter narrows results: every hit of every filtered query comes from the document
# of the inferred document_type (offline, checked against the committed machine-readable results;
# FAILS loudly — non-empty mismatch list is an assertion error naming the leaked chunks).
python -c "import json; rs = json.load(open('outputs/retrieval_results_improved.json'))['records']; \
f = [r for r in rs if r['inferred_document_type']]; \
mismatch = [(r['id'], h['chunk_id']) for r in f \
for h in r['configs']['filter-only']['hits'] + r['configs']['combined']['hits'] \
if not h['chunk_id'].startswith({'concept-guide': 'freight', 'architecture-guide': 'cqrs', \
'case-study': 'monolith', 'playbook': 'scaling'}[r['inferred_document_type']])]; \
assert f and not mismatch, f'cross-type leaks under filter: {mismatch}'; \
print('filtered queries:', len(f), 'of', len(rs), '| cross-type leaks under filter: none')"

# V2 — the improved search runs end to end and prints its inferred filter
# (needs OPENAI_API_KEY; one embedding call).
python scripts/retrieval_improved.py --query "How do we release code without interruption?" --k 3

# V3 — the hybrid layer's behaviour is pinned by offline tests (no key, no network).
python -m pytest tests/test_retrieval_improved.py -q

# V4 — 10 comparison rows; the baseline top-1 column reproduces the committed HW2 top-1
# chunk ids verbatim (offline; full-hit-array byte-identity additionally holds in
# retrieval_results_improved.json's embedded baseline_hits).
grep -c "^| q[0-9]" outputs/retrieval_comparison.md                                  # 10
python -c "import json; base = {r['id']: r['hits'][0]['chunk_id'] \
for r in json.load(open('outputs/retrieval_results.json'))['records']}; \
imp = {r['id']: r['baseline_top1'] for r in json.load(open('outputs/retrieval_results_improved.json'))['records']}; \
assert base == imp, 'baseline drift'; print('baseline column matches committed HW2 results: 10/10')"

# V5 — the conclusions' headline numbers reproduce from the committed results (offline):
# the full precision progression, the hybrid-only top-1 regression, and the intact combined hit rate.
python -c "import json; a = json.load(open('outputs/retrieval_results_improved.json'))['aggregates']; \
[print(f\"{n}: top-1 {v['top1_hit_rate']:.2f} | top-3 precision {v['top3_precision']:.3f}\") for n, v in a.items()]; \
p = lambda n: round(a[n]['top3_precision'], 3); \
assert (p('baseline'), p('filter-only'), p('combined')) == (0.889, 0.926, 0.963), 'precision progression drifted'; \
assert round(a['hybrid-only']['top1_hit_rate'], 2) == 0.89, 'hybrid-only regression figure drifted'; \
assert a['combined']['top1_hit_rate'] == 1.0 and a['baseline']['top1_hit_rate'] == 1.0"
#   baseline 0.889 → filter-only 0.926 → combined 0.963; hybrid-only top-1 0.89 (the regression the filter prevents)
```

## Improved retrieval example

```bash
$ python scripts/retrieval_improved.py --query "How do we release code without interruption?" --k 3

Query: How do we release code without interruption?
Filter: document_type=playbook (inferred)

Top-1: scaling_and_zero_downtime_operations_chunk_011 | rrf: 0.0325 | semantic: 0.431 (#2) | bm25: #1
  Text: Operating a Freight Platform at 5,000 Requests per Second > Zero-Downtime Deployments. …
  Source: data/raw/scaling-and-zero-downtime-operations.md
  Document: scaling_and_zero_downtime_operations | Section: Zero-Downtime Deployments | Type: playbook
```

Every hit names the branch that surfaced it (`semantic` rank, `bm25` rank). It also names the
fused `rrf` score. The units stay deliberately separate, because RRF scores and cosine
similarities are not comparable.

## Baseline vs improved

Full table and per-query detail: [`outputs/retrieval_comparison.md`](outputs/retrieval_comparison.md).
Aggregates over the nine in-corpus queries (top-3 precision = share of top-3 slots from an
expected document):

| Configuration | Top-1 hit rate | Top-3 precision |
|---|---|---|
| baseline (HW2, semantic only) | 1.00 | 0.889 |
| filter-only | 1.00 | 0.926 |
| hybrid-only | **0.89** | 0.889 |
| **combined (filter + hybrid)** | **1.00** | **0.963** |

The filter fired on 8 of 10 queries. Query q05 has ambiguous vocabulary, and q10 is
out-of-corpus, so both correctly fall through unfiltered. 6 of 10 queries changed their top-1
chunk.

## Conclusions — Homework #3

**What gave the biggest effect: metadata filtering — but not for the obvious reason.** Its own
precision gain is modest: 0.889 → 0.926, from the eviction of q09's foreign-document chunk. Its
real value is a constraint on hybrid search's failure mode. Run alone, hybrid REGRESSED q09's
top-1 to a CQRS chunk, on the lexical strength of the word "event".
Hybrid also leaked a migration chunk into q06's top-3, and that dropped the top-1 hit rate to
0.89. Together, the filter caps the lexical leakage while BM25 re-ranks inside the right document.
The result is 0.963 precision with the hit rate intact.

**The largest single-query win belongs to hybrid search.** It lands on exactly the query that
filtering cannot touch. The query q05 stays unfiltered, because its vocabulary is ambiguous. BM25
promoted two genuinely better event-sourcing chunks from semantic ranks 4–5 into the top-2. That
shrank HW2's three-document leak to one foreign chunk.

**Honest caveats.**

1. Four `document_type` values map 1:1 to four documents.
   A correct filter is therefore equivalent to a choice of the right document. The measured effect
   is an upper bound, and a corpus with many documents per type would not reproduce it as
   strongly.
2. Hybrid is a net win in aggregate, not per query. The top-1 for q08 got qualitatively worse.
   The breadcrumb repeats the document title's "5,000 Requests per Second" in every chunk, and
   BM25 amplifies exactly that title-token inflation. HW2 flagged this problem, and HW3 inherits
   it.
3. The keyword rules encode corpus vocabulary, not query wording.
   A production system would replace them with a learned query classifier.
   [`docs/homework3/retrieval-improvements-spec.md`](docs/homework3/retrieval-improvements-spec.md)
   records that limit with the others.

---

# Homework #4 — grounded answer generation

This is the first layer that answers rather than retrieves: `question → retrieve top-k → build
prompt → call the LLM → grounded answer with citations`. Retrieval is the Homework #3 combined
pipeline, so this homework adds only the generation half.

Two independent gates produce the "I don't know" behaviour, and they answer different questions:

1. **A relevance floor** (`--min-score`, default 0.35) reads the best cosine score in the
   retrieved set. Below the floor, the pipeline hands the model an **empty** context. The floor
   decides if anything retrieved is close enough to be worth showing at all.
2. **The prompt's own refusal rule** decides if the context that did arrive actually contains the
   answer. A floor cannot tell that three on-topic chunks all miss the specific fact that the
   question asks for. A prompt rule never sees an empty context.

0.35 is not a fresh guess. [Homework #2's analysis](docs/homework2/analysis.md) derived the number
from measurement: out-of-corpus top 0.266 against in-corpus floor 0.413. Homework #2 then deferred
the floor, and Homework #3 deferred it too. Design decisions and known limits:
[`docs/homework4/generation-spec.md`](docs/homework4/generation-spec.md).

## How to verify this homework (grading checklist)

Git tracks all § 3 deliverables:

- [`scripts/rag_answer.py`](scripts/rag_answer.py)
- [`outputs/rag_answers_examples.md`](outputs/rag_answers_examples.md)
- [`outputs/prompt_improvements.md`](outputs/prompt_improvements.md)
- the prompt template, below and in the script
- this README

Git also tracks `outputs/rag_answers_results.json`, the machine-readable backing for the examples.
That file is the HW4 counterpart of HW2's `retrieval_results.json`. The § 3 list does not name it,
and the repo keeps it because the checks below verify against it. Everything except V2's live run
works **offline — no API key required**.

| Rubric criterion (§ 4) | Pts | Evidence | Check |
|---|---|---|---|
| Prompt template with a grounded-answering rule | 10 | [Prompt template](#prompt-template) · `PROMPT_VERSIONS["v3"]` in [`scripts/rag_answer.py`](scripts/rag_answer.py) — only-from-context rule, verbatim refusal sentence, citation requirement | V1 |
| QA pipeline implemented (retrieval → answer) | 15 | [`scripts/rag_answer.py`](scripts/rag_answer.py) — `--query` / `--evaluate` / `--improvements`; all **10** questions run end to end (9 answered, 1 correctly refused) | V2, V3 |
| Citation or source in every answer | 10 | [`outputs/rag_answers_examples.md`](outputs/rag_answers_examples.md): **9 of 9** answered questions carry inline `[chunk_id]` markers **and** a `Source:` line, **0** fabricated. q10 is the refusal: it cites nothing, and its `Source:` line names no file — see the note below the table | V4 |
| Fallback behaviour on empty/weak context | 5 | q10 in [`outputs/rag_answers_examples.md`](outputs/rag_answers_examples.md): top 0.266 < 0.35 → context empty → refusal, no citation, no source | V5 |
| 2–3 prompt improvements with explanation | 10 | [`outputs/prompt_improvements.md`](outputs/prompt_improvements.md): **3** cases, each a real before/after over identical retrieved chunks | V6 |

The spec's § 2 asks for four *kinds* of test question. This homework inherits the question set
from Homework #2. That homework chose its `category` values for a retrieval evaluation, so the two
taxonomies do not line up name-for-name. The mapping is:

| § 2 required kind | Questions | Evidence it is that kind |
|---|---|---|
| Simple question whose answer is definitely in context | q01, q02, q03 (`direct`) | top scores 0.536 / 0.582 / 0.685 — each at least 0.18 clear of the 0.35 floor |
| Reformulated question | q04, q05, q06 (`paraphrase`) | deliberately avoid the corpus's own wording; q04 drops the word "backhaul" entirely |
| Context insufficient → fallback | q10 (`out-of-corpus`) | top 0.266 < 0.35 floor → empty context → refusal, 0 citations, no source |
| Retrieval returns a **weak** chunk | q05, q06 | q05: a *foreign-document* chunk cleared the floor at 0.412, and the answer then did not cite it. The two chunks that did answer scored 0.354 and 0.361 — +0.004 and +0.011 over the floor. For q06, `scaling_..._chunk_004` scored 0.2658, *below* the floor. It rode into the context on a stronger sibling's score, and the answer correctly ignored it |

The inherited `category` labels do not name the weak-chunk row. This table spells it out, instead
of leaving the reader to reconstruct it. Both `Comment:` blocks in
[`outputs/rag_answers_examples.md`](outputs/rag_answers_examples.md)
analyse the two cases.

Within `--evaluate` the floor always fires first, so only the *empty* half of the fallback occurs
there. A separate run measured the *weak* half with the floor disabled. Three genuinely off-topic
chunks reached the model, and it refused anyway, so the prompt rule stands on its own. The block
below keeps the four lines that carry the result. `format_answer` also prints a `Question:`, a
`Prompt:` and a `Source:` line:

```bash
$ python scripts/rag_answer.py --query "What is the best way to fine-tune a large language model on a custom dataset?" --k 3 --no-min-score

Context: 3 chunk(s) (top semantic 0.266, floor disabled)
Retrieved chunks: monolith_..._chunk_013 (semantic 0.245), cqrs_..._chunk_002 (semantic 0.222), monolith_..._chunk_014 (semantic 0.266)
Answer: I do not have enough information in the available documents to answer this question.
Citations: (none)
```

That run stays deliberately outside the committed evaluation, because it would change the graded
aggregates. It also surfaced a real defect: a refusal over a *non-empty* context still named its
retrieved documents as sources. A fix landed, and tests now pin the behaviour. Details in
[`docs/homework4/generation-spec.md`](docs/homework4/generation-spec.md) § Known limits.

**On rubric row 3 and the refusal.** The spec asks for a citation in *every* answer (§ 4). The
same § 4 also requires the model to refuse rather than invent when context is insufficient. The
spec's own example refusal (§ 5) carries no source. A refusal therefore cannot satisfy the
citation row literally. This implementation reports the citation rate over *answered* questions
(9 of 9). It deliberately emits no source for a withheld context, because a chunk the model never
saw is not a source. Read strictly, that is 9 of 10.

```bash
# V1 — the shipped prompt carries all four required rules (offline, no key).
python -c "import sys; sys.path.insert(0,'scripts'); from rag_answer import PROMPT_VERSIONS as P, \
INSUFFICIENT_CONTEXT_ANSWER as R; v = P['v3'].user_template; \
assert 'ONLY the context below' in v and 'Do not add facts from general knowledge' in v; \
assert R in v and 'square brackets' in v and P['v3'].system; \
print('v3 carries: only-from-context, no-outside-knowledge, refusal sentence, citation rule')"

# V2 — the pipeline answers a single question end to end, with a citation and a source
# (needs OPENAI_API_KEY; one embedding + one chat call).
python scripts/rag_answer.py --query "What is a backhaul and why does it matter to a carrier?" --k 3

# V3 — 10 questions recorded, each with the spec's mandated block keys (offline).
grep -c "^Question: " outputs/rag_answers_examples.md              # 10
for key in "Retrieved chunks: " "Answer: " "Source: " "Comment: "; do \
  printf '%s%s\n' "$key" "$(grep -c "^$key" outputs/rag_answers_examples.md)"; done   # 10 each

# V4 — every answered question carries a real citation and none invents one (offline, self-asserting).
python -c "import json; d = json.load(open('outputs/rag_answers_results.json')); a = d['aggregates']; \
r = d['records']; \
assert a['answers_with_citation'] == a['answered'] == 9, a; \
assert a['fabricated_citations'] == 0, 'a cited id was never in the context'; \
assert a['answered_without_context'] == 0, 'an answer was produced from an empty context'; \
supplied = lambda x: {c['chunk_id'] for c in x['retrieved_chunks']}; \
assert all(set(x['cited_chunk_ids']) <= supplied(x) for x in r), 'citation outside the context'; \
print(f\"citation rate {a['citation_rate']:.2f} ({a['answers_with_citation']}/{a['answered']}) | \
fabricated {a['fabricated_citations']} | answered from empty context {a['answered_without_context']}\")"

# V5 — the fallback fires on the out-of-corpus question and ONLY there (offline).
python -c "import json; r = json.load(open('outputs/rag_answers_results.json'))['records']; \
ref = [x for x in r if x['refused']]; \
assert [x['id'] for x in ref] == ['q10'], f'unexpected refusals: {[x[\"id\"] for x in ref]}'; \
q = ref[0]; \
assert not q['context_used'] and q['top_semantic_score'] < 0.35 and not q['cited_chunk_ids']; \
assert not q['source_files'], 'a refusal must name no source'; \
print(f\"q10 refused: top {q['top_semantic_score']:.3f} < floor 0.35, context empty, 0 citations\")"

# V6 — 3 before/after cases, each showing a real answer from both prompt versions (offline).
grep -c "^## case-" outputs/prompt_improvements.md                 # 3
grep -c "^### Result" outputs/prompt_improvements.md               # 3

# The full test suite — 521 tests (74 HW1-2 + 52 HW3 + 79 HW4 + 121 HW5 + 195 HW6), offline, no key or network.
python -m pytest -q
```

## Prompt template

The shipped template is `v3`. All three versions stay runnable (`--prompt-version v1|v2|v3`), so
anyone can reproduce every before/after in `outputs/prompt_improvements.md` rather than take it on
trust.

```
System: You are a documentation assistant for a freight-exchange engineering knowledge base.
        You answer strictly from the source material you are given, and you never fall back
        on general knowledge.

Answer the engineer's question using ONLY the context below.

Rules:
1. Use only the provided context. Do not add facts from general knowledge, even when you are
   confident they are correct.
2. If the context does not contain enough information to answer, reply with exactly this
   sentence and nothing else:
   "I do not have enough information in the available documents to answer this question."
3. Cite the chunk every claim came from, inline, in square brackets — for example
   [freight_exchange_domain_primer_chunk_018]. Use the ids exactly as they appear in the
   context headers. Never cite an id that is not in the context.
4. Answer in at most five sentences. Do not restate the question.

Context:
{context}

Question:
{question}

Answer:
```

Each context entry starts with the id that the model must cite. The example below shows the
citation format, and does not only describe it:

```
[freight_exchange_domain_primer_chunk_018]
source_file: data/raw/freight-exchange-domain-primer.md
section: Key Domain Vocabulary
<chunk text>
```

## Answer example

```bash
$ python scripts/rag_answer.py --query "Who confirms that a delivery actually happened, and what does that confirmation trigger?" --k 3

Question: Who confirms that a delivery actually happened, and what does that confirmation trigger?
Prompt: v3 | Model: gpt-4.1-mini
Context: 3 chunk(s) (top semantic 0.483, floor 0.35)

Retrieved chunks: freight_exchange_domain_primer_chunk_018 (semantic 0.405), freight_exchange_domain_primer_chunk_008 (semantic 0.396), freight_exchange_domain_primer_chunk_009 (semantic 0.483)

Answer: The consignee confirms that a delivery actually happened by providing proof of delivery (POD), which is typically a photograph or signature capture from the driver's application. This confirmation triggers invoicing and settlement processes [freight_exchange_domain_primer_chunk_018][freight_exchange_domain_primer_chunk_008][freight_exchange_domain_primer_chunk_009].

Source: data/raw/freight-exchange-domain-primer.md
Citations: freight_exchange_domain_primer_chunk_018, freight_exchange_domain_primer_chunk_008, freight_exchange_domain_primer_chunk_009
```

Homework #2 could not resolve this query cleanly. Its recorded judgement was
"the POD-to-settlement link is retrievable but not cleanly isolated in one chunk".
The answer layer assembled the answer from three chunks.

## Answers and prompt improvements

Full set: [`outputs/rag_answers_examples.md`](outputs/rag_answers_examples.md) (10 questions) and
[`outputs/prompt_improvements.md`](outputs/prompt_improvements.md) (3 before/after cases).

| Measure | Value |
|---|---|
| Questions | 10 |
| Answered from context | 9 |
| Refused ("not enough information") | 1 |
| Answered despite an empty context (hallucination) | **0** |
| Answers carrying at least one citation | **9 of 9** |
| Citations naming a chunk that was never supplied | **0** |

## Conclusions — Homework #4

**The prompt produces the refusal, and a measurement proves it rather than an assertion.**
Case-1 of [`outputs/prompt_improvements.md`](outputs/prompt_improvements.md) runs the
out-of-corpus question through the assignment's own starting prompt, over the *identical*
retrieved chunks. It gets a confident eight-step tutorial on LoRA, Hugging Face and gradient
clipping. Not one word of that answer comes from a logistics corpus. The same question under `v2`
returns the refusal sentence. Retrieval stayed constant, so the hallucination was entirely the
prompt's doing.

**Case-3 is the honest counterweight.** Its design aimed to catch the naive prompt drifting
on q05, the hardest in-corpus question. But the naive prompt did not drift. Its answer had
substantive grounding. What it lacked was any citation, so a reader could not verify a correct
answer. A naive prompt is not reliably wrong. It is *unreliably right*, and that is worse: one
well-behaved sample would have predicted the opposite of case-1. That is the argument for keeping
all three prompts runnable, instead of a quotation in a document.

**The floor is thinner than the aggregate suggests.** It fired exactly once, on q10 (0.266 against
0.35). Not one in-corpus question got a refusal. But two of the nine answered questions sit
within 0.07 of refusal, and q05 is the instructive one. A *foreign-document* chunk cleared the floor at 0.412,
and the answer then did not cite that chunk. The two chunks that actually answered scored 0.354
and 0.361 — 0.004 and 0.011 above the line. A chunk that contributed nothing opened the gate.

Two of the nine answered questions sit within 0.07 of refusal: q05 at +0.062, and q04 at +0.063.
A third, q06, sits within 0.09 (+0.081). Query q05 also shows a second, independent weakness, and
the two compound on the same query. The floor takes its calibration from the *semantic top-1*, but
it reads the *RRF-fused top-k*. Those two are not the same statistic. Under fusion, a chunk that
both branches find outranks a chunk that the semantic branch ranked first and BM25 never surfaced.
The committed `semantic_rank` field makes this auditable, and exactly one of the ten questions
shows it. The returned chunks for q05 are semantic ranks **5, 4 and 2**, and the semantic rank-1
chunk never reached the context at all. So the query with the narrowest margin is also the only one
where the gate judged a displaced statistic. The floor earned its place on the one query its design
targets. It is also one recalibration away from costing a correct answer
([`docs/homework4/generation-spec.md`](docs/homework4/generation-spec.md) § Known limits).

**Several Homework #2 defects are no longer defects.** HW2 faulted q01's top-1, because it opened
mid-sentence and the definition landed at top-3. Generation reads all of top-k, so the chunk
boundary no longer matters. HW2 and HW3 both worried at q02's 0.582-vs-0.581 tie, and HW3 spent
BM25 on the tie-break. Both chunks are in context anyway, so the ordering was irrelevant. What does
survive is everything about *which* chunks arrive, rather than in what order. The
breadcrumb-inflated score for q08 still decides its context, and no prompt rule repairs a chunk
that retrieval never returned.

---

# Homework #5 — external tool integration

This is the first layer that can consult something other than the corpus, and the first that can
*act*: `question → model chooses → validate → operations API → answer`. The script hands the model
both tool schemas on every turn, and the model decides. When it asks for no tool, the question
falls through to the Homework #4 pipeline unchanged. So "when NOT to call the tool" is an observed
behaviour, not a claim about our dispatch code.

Two tools ship, because a read-only integration can only demonstrate half of what § 2 asks about
validation:

1. **`get_load_status(load_id)`** — read.
   One load's live lifecycle status, carrier, ETA and last known position with its age. The corpus
   defines what `in_transit` *means*; only the tool knows which load is in it.
2. **`book_load(load_id, carrier_id)`** — write, and irreversible.
   Booking is the first irreversible commercial transition in the load lifecycle. The tool
   therefore refuses the call unless the human operator authorised it through `--confirm`.
   The model cannot supply that authorisation. The tool refuses a `confirmed: true` that the model
   sets for itself, and records it as `model_self_confirmed`.

The model writes every argument that reaches the tool layer, so the tool layer treats each one as
untrusted. The contract declares required fields and a `pattern`, and it permits no unknown
properties. It also holds no free-text parameter anywhere for a query or a statement to be
injected into. Design decisions and known limits:
[`docs/homework5/tool-integration-spec.md`](docs/homework5/tool-integration-spec.md).

## How to verify this homework (grading checklist)

Git tracks all § 3 deliverables:

- [`scripts/external_tool.py`](scripts/external_tool.py)
- [`outputs/tool_examples.md`](outputs/tool_examples.md)
- the validation logic, in the script and in the description below

Git also tracks `data/external/loads.json`, the external source itself. It tracks
`outputs/tool_results.json` too, the machine-readable backing for the examples. That file is the
HW5 counterpart of HW4's `rag_answers_results.json`. The § 3 list does not name it, and the repo
keeps it because the checks below verify against it. Everything except V4's live run works
**offline — no API key required**.

| Rubric criterion (§ 4) | Pts | Evidence | Check |
|---|---|---|---|
| Tool described (name, type, purpose, when to call) | 5 | `python scripts/external_tool.py --list-tools` — name, type, purpose, source and the description the model actually reads, for both tools; each states its `Do NOT call this` case | V1 |
| Input / output contract defined | 10 | `GET_LOAD_STATUS_SCHEMA` / `BOOK_LOAD_SCHEMA` in [`scripts/external_tool.py`](scripts/external_tool.py) — JSON Schema literals that **are** the `tools=` payload. Contract and wire format therefore cannot drift. Output shape: [`outputs/tool_results.json`](outputs/tool_results.json) | V2 |
| Validation implemented | 10 | All four § 2 clauses: required fields, id `pattern`, `additionalProperties: false`, and operator confirmation on the write. **121** offline tests, incl. 6 parametrized malformed identifiers and a test proving validation runs *before* the data layer | V3 |
| Tool implemented and runs | 10 | [`scripts/external_tool.py`](scripts/external_tool.py) — `--question` / `--examples` / `--list-tools`; **4** of 6 committed runs reached a tool, 2 correctly did not | V4, V6 |
| 3–5 examples explaining the advantage over retrieval | 10 | [`outputs/tool_examples.md`](outputs/tool_examples.md): **5** scenarios, each with a hand-authored `Why tool is better than retrieval:` — including s5, where the tool is the *worse* instrument | V5 |
| Call through an orchestration layer or the model shown | 5 | Native OpenAI tool calling: `orchestrate()` in [`scripts/external_tool.py`](scripts/external_tool.py). No hand-written router — `route` in [`outputs/tool_results.json`](outputs/tool_results.json) records what the model chose per run | V6 |

**Two results worth reading before the checks.** Neither is a success, and both are in the design
doc's § Known limits with their reproduction commands.

- The write gate was initially **unreachable**.
  The first description of `book_load` told the model that the tool would refuse the call without
  operator authorisation. The model then reasonably stopped calling: no tool call, no refusal,
  nothing to grade. A gate that the model declines to approach has not been tested.
  The description now tells the model to always call, and to let the tool decide. That division of
  responsibility is also the correct one.
- **Format validation cannot detect fabrication.**
  The question asked the model to book a load "for carrier 817", and the model emitted
  `CAR-00817`. That id is well formed and real, and probably not what the user meant. Every
  validation rule here passes it, because every one of them is syntactic. Only the confirmation
  gate stopped it, and a read tool has no such gate.

Scenario s3 also did not go as its design intended. Given the malformed `FX-26-42`, the model
declined to emit the id at all, because the contract it is shown declares the pattern. So
`invalid_load_id_format` never fired live, and only the offline suite covers it. The contract is
the outer filter, and validation is the inner one.

```bash
# V1 — both tools are described, with type, purpose and a when-NOT-to-call clause (offline, no key).
python scripts/external_tool.py --list-tools | grep -E "^(Tool|Type|Purpose):"
python -c "import sys; sys.path.insert(0,'scripts'); from external_tool import TOOL_SCHEMAS, TOOLS; \
assert {s['function']['name'] for s in TOOL_SCHEMAS} == set(TOOLS) == {'get_load_status','book_load'}; \
assert all('Do NOT call this' in s['function']['description'] for s in TOOL_SCHEMAS); \
assert TOOLS['book_load'].is_write and not TOOLS['get_load_status'].is_write; \
print('2 tools described; both carry an explicit when-NOT-to-call clause')"

# V2 — the contract is the wire format, and nothing in it is a free-text field (offline).
python -c "import sys; sys.path.insert(0,'scripts'); \
from external_tool import TOOL_SCHEMAS, LOAD_ID_PATTERN, CARRIER_ID_PATTERN; \
props = [p for s in TOOL_SCHEMAS for p in s['function']['parameters']['properties'].values()]; \
assert all(s['function']['parameters']['additionalProperties'] is False for s in TOOL_SCHEMAS); \
assert all('pattern' in p for p in props if p['type'] == 'string'), 'an unconstrained string is an injection surface'; \
assert LOAD_ID_PATTERN in str(TOOL_SCHEMAS) and CARRIER_ID_PATTERN in str(TOOL_SCHEMAS); \
print('additionalProperties=false on both; every string parameter is pattern-constrained')"

# V3 — all four validation clauses refuse, and the model cannot confirm its own write (offline).
python -c "import sys; sys.path.insert(0,'scripts'); import json; \
from external_tool import ToolCall, validate_get_load_status as vg, validate_book_load as vb, dispatch; \
c = lambda n, a: ToolCall(call_id='c', name=n, raw_arguments=json.dumps(a)); \
assert vg(c('get_load_status', {}))[1].error == 'missing_argument'; \
assert vg(c('get_load_status', {'load_id':'FX-26-42'}))[1].error == 'invalid_load_id_format'; \
assert vg(c('get_load_status', {'load_id':'FX-2026-000042','sql':'DROP TABLE loads'}))[1].error == 'unknown_argument'; \
w = {'load_id':'FX-2026-000211','carrier_id':'CAR-00817','confirmed':True}; \
r = vb(c('book_load', w), operator_confirmed=False)[1]; \
assert r.error == 'confirmation_required' and r.data['model_self_confirmed'] is True; \
assert dispatch(c('drop_database', {}), data={'loads':{},'carriers':{}}, operator_confirmed=False).result.error == 'unknown_tool'; \
assert dispatch(c('get_load_status', {'load_id':'FX-26-42'}), data={'loads':{},'carriers':{}}, operator_confirmed=False).result.error == 'invalid_load_id_format', 'validation must precede the lookup'; \
print('refused: missing field, bad format, unknown property, self-confirmed write, unknown tool')"

# V4 — the tool runs end to end, and the write gate refuses then permits
# (needs OPENAI_API_KEY; one chat call per turn, no embedding unless it falls through).
python scripts/external_tool.py --question "Where is load FX-2026-000042 right now?"
python scripts/external_tool.py --question "Book load FX-2026-000211 for carrier CAR-00817."            # refused
python scripts/external_tool.py --question "Book load FX-2026-000211 for carrier CAR-00817." --confirm  # booked

# V5 — 5 scenarios recorded, each with the spec's mandated block keys (offline).
grep -c "^## s" outputs/tool_examples.md                                   # 5
for key in "User question: " "Tool called: " "Input: " "Result: " "Final answer: "; do \
  printf '%s%s\n' "$key" "$(grep -c "^$key" outputs/tool_examples.md)"; done          # 6 each (s4 runs twice)
grep -c "^Why tool is better than retrieval: " outputs/tool_examples.md    # 5

# V6 — the MODEL did the routing, and the write never persisted to the committed fixture (offline).
python -c "import json; d = json.load(open('outputs/tool_results.json')); \
runs = [r for s in d['scenarios'] for r in s['runs']]; \
routed = [r['route'] for r in runs]; \
assert routed.count('tool') == 4 and routed.count('knowledge_base') == 2, routed; \
assert all(not r['rounds_exhausted'] for r in runs), 'a run hit the tool bound'; \
gate = [i for r in runs for i in r['invocations'] if i['tool'] == 'book_load']; \
assert [i['error'] for i in gate] == ['confirmation_required', None], [i['error'] for i in gate]; \
fixture = json.load(open('data/external/loads.json')); \
assert fixture['loads']['FX-2026-000211']['status'] == 'posted', 'the committed booking leaked to disk'; \
print(f'model-chosen routes: {routed.count(\"tool\")} tool, {routed.count(\"knowledge_base\")} knowledge base; fixture still pristine')"

# The full test suite — 521 tests (74 HW1-2 + 52 HW3 + 79 HW4 + 121 HW5 + 195 HW6), offline, no key or network.
python -m pytest -q
```

## Tool contract

Both schemas are module constants, and the script passes them verbatim as the `tools=` payload.
The block below is `get_load_status`. The model receives it together with `book_load` on every turn:

```json
{
  "type": "function",
  "function": {
    "name": "get_load_status",
    "description": "Read the current live state of ONE load ... Do NOT call this for general questions about what the load lifecycle is, what a status means, or how the exchange works — those are answered from the knowledge base, not from live data.",
    "parameters": {
      "type": "object",
      "properties": {
        "load_id": {"type": "string", "pattern": "^FX-[0-9]{4}-[0-9]{6}$", "description": "..."}
      },
      "required": ["load_id"],
      "additionalProperties": false
    }
  }
}
```

`python scripts/external_tool.py --list-tools` prints both in full, offline.

## Tool call example

The block below comes verbatim from the committed run in
[`outputs/tool_results.json`](outputs/tool_results.json)
(scenario s1). The `Result:` line keeps 7 of the 17 top-level keys of the key-sorted payload, for
width. The full payload appears in
[`outputs/tool_examples.md`](outputs/tool_examples.md).
This example changes nothing else.

```bash
$ python scripts/external_tool.py --question "Where is load FX-2026-000042 right now, and when is it due to arrive?"

Question: Where is load FX-2026-000042 right now, and when is it due to arrive?
Model: gpt-4.1-mini
Route: tool (1 round(s))

Tool called: get_load_status
Input: {"load_id": "FX-2026-000042"}
Result: {"booking_reference": "BKG-2026-004411", "carrier": {"carrier_id": "CAR-00817", "name": "Nordwind Transport", "status": "active"}, "eta": "2026-08-14T09:30:00+00:00", "last_position_age_s": 214, "ok": true, "position_is_stale": false, "status": "in_transit", ...}

Answer: Load FX-2026-000042 is currently in transit. Its last known position was on the A2 motorway near Konin, Poland, updated about 3.5 minutes ago. The load is due to arrive at its destination in Poznan, Poland, on August 14, 2026, at 09:30 UTC. This information comes from the freight-exchange operations API.

Source: data/external/loads.json (operations API mock)
```

The model turned `last_position_age_s: 214` into "about 3.5 minutes ago" on its own. Nothing
checks that conversion — see
[`docs/homework5/tool-integration-spec.md`](docs/homework5/tool-integration-spec.md)
§ Known limits.

## Scenarios and results

Six runs across five scenarios, all in [`outputs/tool_examples.md`](outputs/tool_examples.md):

| Scenario | Route the model chose | Outcome |
|---|---|---|
| s1 · live state of `FX-2026-000042` | `get_load_status` | in transit, ETA 14 Aug 09:30 UTC, position 214 s old |
| s2 · a load that does not exist | `get_load_status` | `unknown_load` — relayed honestly, no substituted id |
| s3 · a malformed identifier | **knowledge base** | the contract's `pattern` filtered it before validation could |
| s4 · irreversible write, twice | `book_load` ×2 | `confirmation_required`, then `BKG-2026-000211` under `--confirm` |
| s5 · what "booked" means | **knowledge base** | cited answer from the primer; the tool is the wrong instrument |

## Conclusions — Homework #5

**The routing is what this homework actually demonstrates, and across six runs the model decided
correctly every time.** It reached for a tool on two of the three live-state questions and on both
booking attempts. It declined twice, with the tools sitting on the table each time. One decline
was the question about documented knowledge. The other was a malformed identifier. The contract's
own `pattern` filtered it before validation ran. Nothing had to inspect the question before the
model saw it. The two declines are the more interesting half. Scenario s5 is the case that the
assignment's own § 2 asks about ("коли НЕ викликати"). Scenario s3 was a decline nobody
designed for.

**The tool description turned out to be the load-bearing piece of the design. A wrong description
made the gate untestable, not merely worse.** The first version told the model that `book_load`
would refuse the call without operator authorisation. That statement is true, and it is exactly
the kind of honest documentation that reads well in a spec. A well-aligned model then responded:
it stopped calling a tool it expected to fail. The write path silently became unreachable, with no
tool call, no refusal, and an empty result to grade. The lesson generalises past this homework. A
schema `description` is not documentation for a reader. It is a routing instruction for the model.
Any permission the model can decline to *request* is a permission the system has not actually
retained. The move of the decision into the tool made the gate both testable and correctly located.

**Validation is necessary and demonstrably not sufficient.** The code implements all four clauses
the spec names, and each one refuses under test. One clause — `additionalProperties: false`, plus
the absence of any free-text parameter — makes "the tool never takes a raw query from the model" a
property of the contract instead of a promise. But two measured results bound what that buys. The
model padded "carrier 817" into `CAR-00817`, a fabrication every syntactic rule accepts. Only a
human operator caught it, at the confirmation prompt. The malformed identifier also never reached
the validator at all, because the schema's `pattern` filtered it a layer earlier. Both cut the same
way. Shape checking tells you an argument is *well formed*, never that it is *right*. The
confirmation gate does more of the safety work than the validators do.

**The static/dynamic split held up, including in the direction that flatters the corpus.** The
knowledge base states the rule: exactly one booking per load, and idempotent confirmation.
`book_load` enforces that same rule in code against live state. Scenarios s4 and s5
show one design from either side. Where the tool is absent, the loss is concrete rather than
theoretical. Scenario s3 fell through to retrieval, and the answer told the user that the documents
were insufficient. That answer was true, unhelpful, and silent about the typo that caused the
problem.

---

# Homework #6 — first agentic structure

This layer is the first that **plans**. Homework #5 gave the model two tools and let it choose;
here a rule-based router chooses, commits to an ordered plan, and runs the plan one step at a time,
with each step's observation recorded in state that later steps read:
`user goal → route → plan → step → observation → state update → next step → final answer`.

**Nothing in it calls a model.** § 2 says deterministic rule-based routing is fine for this
homework; this layer extends that to the whole flow, so the router, the three tools *and* the answer
composition are all rules. Three things follow. The committed artifact reproduces **byte for byte** —
two consecutive runs produce identical files, which no earlier homework's artifact can claim. The
tests drive the shipped flow instead of a fake of it. And the whole homework runs with **no
`OPENAI_API_KEY` and no network**, so every check below is reproducible without a credential. What
that costs is in
[`docs/homework6/agent-flow-spec.md`](docs/homework6/agent-flow-spec.md) § Known limits, and it is
not small.

## Use case and scenario

**Domain:** the same freight-exchange logistics platform as Homework #1–#5.
**Use case:** a *dispatcher's console* — one assistant that answers platform questions from the
documentation, reports live load state from the operations API, and commits a load to a carrier.

**The scenario it is built around.** A dispatcher is working a load board on a Tuesday morning. She
does not know what `matched` means, so she asks, and gets the definition from the platform primer.
She then asks where `FX-2026-000042` is, and gets its live status, carrier, ETA and last known
position. Satisfied, she moves to the load she actually has to place and types
`Book load FX-2026-000211 for carrier CAR-00817.` The assistant looks the load up, confirms it is
still open — and refuses, because booking is irreversible and she has not authorised it. She
re-issues the same request with `--confirm`, and only then is the load committed. Along the way she
mistypes an identifier once, and is told so rather than quietly answered about something else.

Those are the four routes, in the order a real session hits them.

## Workflow schema

```
                                  user question
                                        │
                                        ▼
                          ┌───────────────────────────┐
                          │  Router — 9 ordered rules │   no model, no network
                          │  R1 … R9, first match wins│
                          └───────────────────────────┘
          ┌────────────────┬─────────────┴──────────────┬────────────────┐
          ▼                ▼                            ▼                ▼
   knowledge_base     load_status                    booking       clarification
          │                │                            │                │
          ▼                ▼                            ▼                ▼
 search_knowledge_   get_load_status              get_load_status     ask_user
    base  (tool)          (tool)                      (tool)          (gate)
          │                │                            │                │
          ▼                ▼                            ▼                ▼
     observation      observation                  observation      observation
          │                │                            │                │
          │                │              state ────────┘                │
          │                │                │                            │
          │                │                ▼                            │
          │                │      check_authorisation (gate)             │
          │                │      load open?   operator confirmed?       │
          │                │           │                  │              │
          │                │        no │ halt         yes │              │
          │                │           │                  ▼              │
          │                │           │            book_load (tool)     │
          │                │           │                  │              │
          │                │           │                  ▼              │
          │                │           │             observation         │
          │                │           │                  │              │
          └────────────────┴───────────┴──────────────────┴──────────────┘
                                        │
                                        ▼
                             final answer  +  final state
```

Routing is by rules only. Identifiers are found by regex — the *same* patterns
`scripts/external_tool.py` validates with, unanchored so they match mid-sentence — intent by small
word sets, and corpus vocabulary by Homework #3's `infer_document_type`. The full nine-rule table,
and the reason for their order, is in
[`docs/homework6/agent-flow-spec.md`](docs/homework6/agent-flow-spec.md) § The router's rules.

## Routes and steps

Four routes, five step types. § 2 asks for *at least two routes **or** three steps*; the booking
route alone meets the step threshold and the four routes meet the other, so neither reading is left
to interpretation.

| Route | Plan | Steps | When the router picks it |
|---|---|---|---|
| `knowledge_base` | `search_knowledge_base` | 1 | the question asks what something *means*, or uses the corpus's own vocabulary |
| `load_status` | `get_load_status` | 1 | a well-formed load identifier appears in the question |
| `booking` | `get_load_status` → `check_authorisation` → `book_load` | 3 | a booking verb **and** one load id **and** one carrier id |
| `clarification` | `ask_user` | 1 | an identifier is missing, mistyped or ambiguous, or nothing matched |

A **tool step** consults a source outside the workflow. A **gate step** reads only what the state
already holds — `check_authorisation` and `ask_user` are gates, and the rendered trace says so
rather than counting them as tool calls.

**The booking route is where state stops being decorative.** Step 3 is reachable only through step
2, and step 2 is a verdict on step 1's *recorded observation*: it refuses unless the status it read
is one of the open lifecycle states **and** the human passed `--confirm`. A refused observation
halts the plan, so `book_load` is never called speculatively.

## Tools

Three mock tools, all offline, all over committed fixtures. Each is imported read-only from an
earlier homework — **no Homework #1–#5 file changed** — which is what keeps one contract for the
operations data instead of two that can drift.

| Tool | Type | Source | Returns |
|---|---|---|---|
| `search_knowledge_base` | read | `data/processed/chunks.jsonl` (77 chunks) | top-k chunks with `bm25_score`, `title`, `section`, `document_type`, excerpt |
| `get_load_status` | read | `data/external/loads.json` | status, carrier, ETA, last position with its age and staleness |
| `book_load` | **write** | `data/external/loads.json` (in-process copy only) | booking reference, or a refusal with its reason |

`search_knowledge_base` is Homework #3's improved pipeline **with the semantic half removed**:
`infer_document_type` picks the `document_type` filter and BM25 ranks inside it. Embedding a query
needs the key this homework refuses to require. The filter still earns its place — on the committed
`e1` example it cut the candidate set from 77 chunks to the 23 of one document before ranking
anything. `python scripts/agent_flow.py --describe` prints all three in full, offline.

## State

`AgentState` accumulates; the `StepRecord`s inside it are frozen, so a step's observation cannot be
rewritten by whatever runs next. The five fields § 2 names are all here, under those names.

| Field | What it holds |
|---|---|
| `user_goal` | the question verbatim, never rewritten |
| `selected_route` | one of the four routes |
| `routing_rule` | which rule fired (R1–R9), so a trace can be audited rather than trusted |
| `plan` | the ordered step list the route committed to **before** acting |
| `steps` | one frozen record per executed step: index, name, kind, arguments, observation |
| `tool_calls` | names of the tool steps that ran, in order (gate steps excluded) |
| `observations` | each step's result — read by later steps through `observation_of()` |
| `clarification_reason` | why the workflow asked instead of acted, or `null` |
| `halted_at` | the step whose observation ended the plan early, or `null` |
| `final_answer` | composed from the observations once the plan finishes or halts |

Every rendered trace carries a `State after step:` line per step, and an intermediate snapshot
deliberately does **not** know the future: `halted_at` and `final_answer` stay `null` until the step
that produced them.

## How to verify this homework (grading checklist)

Git tracks all § 3 deliverables:

- [`scripts/agent_flow.py`](scripts/agent_flow.py) — the custom flow
- [`outputs/agent_flow_examples.md`](outputs/agent_flow_examples.md) — 5 examples with full tracing
- the workflow schema, routes, tools and state — the five sections above

Git also tracks [`outputs/agent_flow_results.json`](outputs/agent_flow_results.json), the
machine-readable backing the Markdown renders from, on the same footing as HW4's
`rag_answers_results.json` and HW5's `tool_results.json`. **Everything below runs offline — no API
key, no network, not even for the live run.**

| Rubric criterion (§ 4) | Pts | Evidence | Check |
|---|---|---|---|
| Use case and domain described | 5 | § Use case and scenario above — one dispatcher, one Tuesday-morning session, the four routes in the order she hits them | V1 |
| Workflow schema present | 10 | § Workflow schema above — routes, steps and transitions, including the two that halt a plan. Full rule table in [`docs/homework6/agent-flow-spec.md`](docs/homework6/agent-flow-spec.md) | V1 |
| ≥2 routes or ≥3 steps implemented | 15 | **4** routes and a **3**-step booking plan; 9 ordered router rules, **195** offline tests including a 41-case routing matrix that pins the rule id of every case and whose questions are deliberately *not* the committed examples | V2 |
| ≥2 mock tools implemented | 10 | **3** tools, each returning a structured result: `search_knowledge_base`, `get_load_status`, `book_load` | V3 |
| State described and used | 5 | § State above; and the booking route's step 3 is unreachable except through a gate that reads step 1's observation | V4 |
| 3–5 examples with tracing | 5 | [`outputs/agent_flow_examples.md`](outputs/agent_flow_examples.md): **5** examples, **8** traced steps, all 4 routes, all 3 tools | V5, V6 |

**Three results worth reading before the checks.** An adversarial review of this router found three
real defects. All three were the same shape — **the router choosing an operand the user never
offered** — and none of them was catchable downstream, because `check_authorisation` verifies
whatever the router already chose. That is the general lesson: *a confirmation gate is not a
defence against a router that picked the wrong operand.*

1. **A booking borrowed its load from another clause.** *"Where is load FX-2026-000633 right now?
   Also, book a truck from carrier CAR-00817."* committed `FX-2026-000633`, an identifier that
   appears only in the read clause, with the gate reporting `ok: true`. Booking operands are now
   resolved from the span that asks for the booking, not from the whole sentence.
2. **Ambiguity was measured over well-formed identifiers only.** *"Book FX-2026-000211 or FX-26-42
   for CAR-00817."* found one valid candidate and booked it, discarding the user's own visible
   uncertainty. The check now counts mistyped candidates too.
3. **A well-formed carrier id was reported as malformed.** No rule consumed a bare `carrier_id`, so
   all four fixture carriers fell into the near-miss branch and the workflow told the user a real
   identifier was a typo.

Every fix is mutation-tested: reverting any one of them turns the suite red. V2 and V6 pin the
first two.

```bash
# V1 — the contract prints itself: 4 routes with their plans, 3 tools, 10 state fields (offline).
python scripts/agent_flow.py --describe

# V2 — 4 routes, a 3-step booking plan, and the routing rules land 8 hand-picked questions
# correctly, including three that two rules could plausibly claim (offline).
python -c "import sys; sys.path.insert(0,'scripts'); from agent_flow import ROUTES, PLANS, route; \
assert set(ROUTES) == {'knowledge_base','load_status','booking','clarification'}, ROUTES; \
assert len(PLANS['booking']) == 3, PLANS['booking']; \
cases = {'Explain why the migration used the strangler pattern instead of a rewrite.':'knowledge_base', \
'Where is load FX-2026-000042?':'load_status', \
'Book load FX-2026-000211 for carrier CAR-00817.':'booking', \
'Give me the status of load FX-26-42.':'clarification', \
'How do I book a load on the exchange?':'knowledge_base', \
'What does the status matched mean?':'knowledge_base', \
'Where is my load?':'clarification', \
'Where is FX-2026-000042 and should I book FX-2026-000318 for CAR-00817?':'clarification'}; \
bad = {q: route(q).route for q, want in cases.items() if route(q).route != want}; \
assert not bad, bad; \
print(str(len(ROUTES)) + ' routes; booking plan = ' + str(len(PLANS['booking'])) + ' steps; ' + str(len(cases)) + ' routing cases correct')"

# V3 — all three mock tools run and return a result (offline).
python -c "import sys; sys.path.insert(0,'scripts'); import agent_flow as af; \
from external_tool import load_operations_data; \
ops = load_operations_data(); kb = af.build_knowledge_index(af.Settings.from_env(require_key=False)); \
assert len(af.TOOLS) >= 2, af.TOOLS; \
a = af.search_knowledge_base('what is a backhaul', knowledge=kb, k=3); \
b = af.get_load_status('FX-2026-000042', operations=ops); \
c = af.book_load('FX-2026-000211', 'CAR-00817', operations=ops); \
assert a['ok'] and b['ok'] and c['ok'], (a['ok'], b['ok'], c['ok']); \
print(str(len(af.TOOLS)) + ' mock tools, each returning a result: ' + ', '.join(sorted(af.TOOLS)))"

# V4 — state is USED: the same question stops at a different step depending on the operator's
# decision, and the gate's verdict comes from the first step's recorded observation (offline).
python -c "import sys; sys.path.insert(0,'scripts'); import agent_flow as af; \
from external_tool import load_operations_data; \
kb = af.build_knowledge_index(af.Settings.from_env(require_key=False)); \
q = 'Book load FX-2026-000211 for carrier CAR-00817.'; \
refused = af.run_agent(q, operations=load_operations_data(), knowledge=kb, operator_confirmed=False); \
booked = af.run_agent(q, operations=load_operations_data(), knowledge=kb, operator_confirmed=True); \
assert refused.halted_at == 'check_authorisation' and 'book_load' not in refused.tool_calls; \
assert len(booked.steps) == 3 and booked.tool_calls == ['get_load_status', 'book_load']; \
gate = booked.observation_of('check_authorisation'); seen = booked.observation_of('get_load_status'); \
assert gate['status'] == seen['status'] == 'posted', (gate['status'], seen['status']); \
print('same question, same first observation: the plan stops after ' + str(len(refused.steps)) + \
' steps without --confirm and runs all ' + str(len(booked.steps)) + ' with it')"

# V5 — 5 examples, each with the spec's mandated block keys (offline).
grep -c "^## e" outputs/agent_flow_examples.md                                  # 5
for key in "Question: " "Route: " "Final answer: " "Comment: "; do \
  printf '%s%s\n' "$key" "$(grep -c "^$key" outputs/agent_flow_examples.md)"; done          # 5 each
for key in "Tool called: " "Observation: " "State after step: "; do \
  printf '%s%s\n' "$key" "$(grep -c "^$key" outputs/agent_flow_examples.md)"; done          # 8 each — one per EXECUTED step
python -c "import json; d = json.load(open('outputs/agent_flow_results.json')); \
routes = [e['route'] for e in d['examples']]; \
tools = sorted({t for e in d['examples'] for t in e['tool_calls']}); \
steps = [len(e['steps']) for e in d['examples']]; \
assert set(routes) == set(d['routes']), routes; assert len(tools) >= 2, tools; assert max(steps) >= 3, steps; \
print(str(len(routes)) + ' examples covering all ' + str(len(set(routes))) + ' routes; tools used: ' \
+ ', '.join(tools) + '; deepest plan ' + str(max(steps)) + ' steps')"

# V6 — the flow reaches no model, reproduces byte for byte, refuses an ambiguous write, and never
# persists a booking (offline; the first line must print nothing).
grep -nE "chat\.completions|responses\.create|embed_texts|embed_query|OpenAI\(" scripts/agent_flow.py
python scripts/agent_flow.py --examples --output /tmp/hw6.md --results /tmp/hw6.json > /dev/null
diff outputs/agent_flow_examples.md /tmp/hw6.md && diff outputs/agent_flow_results.json /tmp/hw6.json \
  && echo "two runs byte-identical — no model, no sampling"
python -c "import sys, json; sys.path.insert(0,'scripts'); from agent_flow import route; \
d = route('Where is FX-2026-000042 and should I book FX-2026-000318 for CAR-00817?'); \
assert d.route == 'clarification' and d.reason == 'ambiguous_load_id', d; \
f = json.load(open('data/external/loads.json')); \
assert f['loads']['FX-2026-000211']['status'] == 'posted', 'a committed booking leaked to disk'; \
print('two load ids in one booking request -> refused, not guessed; operations fixture still pristine')"

# The full test suite — 521 tests (74 HW1-2 + 52 HW3 + 79 HW4 + 121 HW5 + 195 HW6), offline.
python -m pytest -q
```

## Example trace

The block below is `e3`, the refused half of the booking pair — the run that proves the gate is
real. Every line is verbatim from the committed run except the four JSON payloads, which keep a
subset of the keys of the key-sorted original for width: 6 of 17 and 4 of 10 on step 1, 6 of 8 and
3 of 10 on step 2. The full payloads are in
[`outputs/agent_flow_examples.md`](outputs/agent_flow_examples.md).

```bash
$ python scripts/agent_flow.py --question "Book load FX-2026-000211 for carrier CAR-00817."

Question: Book load FX-2026-000211 for carrier CAR-00817.
Route: booking (rule R2)
Plan: get_load_status → check_authorisation → book_load

Step 1/3 — get_load_status (tool)
Input: {"load_id": "FX-2026-000211"}
Tool called: get_load_status
Observation: {"booking_reference": null, "carrier": null, "destination": "Milan, IT", "origin": "Antwerp, BE", "ok": true, "status": "posted", ...}
State after step: {"halted_at": null, "steps_executed": "1 of 3", "tool_calls": ["get_load_status"], "final_answer": null, ...}

Step 2/3 — check_authorisation (gate)
Input: {"carrier_id": "CAR-00817", "load_id": "FX-2026-000211", "operator_confirmed": false}
Tool called: (none — `check_authorisation` is a gate step, it reads state, not a source)
Observation: {"carrier_id": "CAR-00817", "error": "confirmation_required", "load_is_open": true, "ok": false, "operator_confirmed": false, "status": "posted", ...}
State after step: {"halted_at": "check_authorisation", "steps_executed": "2 of 3", "tool_calls": ["get_load_status"], ...}

Halted at: check_authorisation — the remaining plan steps lost their justification.

Final answer: Load FX-2026-000211 is posted and open, and the request would commit it to
CAR-00817. Booking is irreversible and no human operator authorised it. Check that both identifiers
are the ones you meant, then re-run the same request with --confirm; that decision is the
operator's.

Source: freight-exchange operations API (mock)
```

The error is `confirmation_required` and **not** `load_not_open`, and `load_is_open` is `true`. The
load was bookable and the workflow declined anyway. `book_load` never appears in `tool_calls`, so
nothing was called and nothing changed. Adding `--confirm` re-runs the identical first two steps and
reaches step 3, which commits `BKG-2026-000211`.

The refusal names **both** operands deliberately. The router selects the load and the carrier out
of the question, and this line is the last point at which a human can notice it selected the wrong
one — see the three defects above.

## Examples and results

| Example | Route (rule) | Steps run | Outcome |
|---|---|---|---|
| e1 · why the strangler pattern | `knowledge_base` (R6) | 1 of 1 | quoted from the case study, filtered to `case-study` before ranking |
| e2 · live state of `FX-2026-000042` | `load_status` (R4) | 1 of 1 | in transit, ETA 14 Aug 09:30 UTC, position 214 s old and fresh |
| e3 · book `FX-2026-000211` | `booking` (R2) | **2 of 3** | `confirmation_required` — open, but nobody authorised it |
| e4 · the same booking, authorised | `booking` (R2) | 3 of 3 | `BKG-2026-000211`, committed in memory only |
| e5 · `FX-26-42` | `clarification` (R5) | 1 of 1 | `malformed_load_id` — the typo is named, not answered around |

All five run against **one** shared in-memory copy of the operations data, in that order, so e3 and
e4 are a sequence rather than two independent simulations.

## Conclusions — Homework #6

**State is load-bearing rather than decorative, and the booking pair is the proof.** e3 and e4 put
the same question with the same first observation and stop at different steps. The third step is
unreachable except through the second, and the second is a verdict on what the first recorded. A
test pins this from the other side: with a stale recorded observation the gate follows the record,
not the live dictionary it was never handed. That is the difference between a workflow that
remembers and a workflow that re-derives.

**The interesting result is what a rule-based router cannot be talked into.** Homework #5 measured
its model padding "carrier 817" into `CAR-00817` — well formed, real, and probably not the carrier
the user meant. Every syntactic validator accepted it, and only the human at the confirmation prompt
caught it. This router has no capacity to invent an operand: the same phrasing yields
`missing_carrier_id`, and the mistyped `FX-26-42` that Homework #5's model silently declined to emit
is named here as a malformed identifier — the exact gain that homework's design doc predicted a
pre-router would buy. Determinism buys refusals that a helpful model will not make.

**The mirror-image failure was real, and a gate did not stop it.** Binding to the first identifier
in a sentence let a read-then-book question commit the load the user only asked about, with
`check_authorisation` confirming the wrong load was open. The lesson generalises past this homework
and past the confused-deputy case Homework #5 already documented: a confirmation gate validates the
operand it is given, so it can only ever be as correct as whatever chose that operand. Two further
defects surfaced in the same review — well-formed carrier identifiers reported as malformed, and any
sentence containing the word "book" swallowed into the booking route, including *"How do I book a
load on the exchange?"*. All three were found by tracing rules against adversarial questions, never
by running the flow. **Rules do not test themselves.**

**The cost is on the other side and it is not small.** The router reads vocabulary and word
position, never intent, so negation is invisible and a question naming a load is answered as a live
lookup even when its verb phrase is definitional. The knowledge route is BM25 over a rule-inferred
filter — Homework #3's pipeline with the semantic half removed — and its answers are extracted
quotations with a `[chunk_id]`, not the synthesised, grounded paragraphs Homework #4 writes. On a
documentation question Homework #4 is simply better, and it cannot run without a key. Every one of
these is enumerated with its failing question in
[`docs/homework6/agent-flow-spec.md`](docs/homework6/agent-flow-spec.md) § Known limits. The trade
this homework makes is fluency for reproducibility, and the assignment's own § 2 is what invites it:
routing without an LLM is normal here, and this is what normal costs.

---

## Repository layout

```
├── data/raw/                     4 authored Markdown source documents
├── data/processed/
│   ├── chunks.jsonl              77 chunks — the Homework #1 deliverable
│   └── chunks_500.jsonl          116 chunks at 500/100 — chunk-size experiment only
├── data/eval/test_queries.json   10 evaluation queries + relevance comments (HW2 + HW3 + HW4 + HW5 + HW6)
├── data/external/loads.json      mock freight operations API — the Homework #5 external source
├── index/
│   ├── chroma/                   the graded index (77 vectors) + manifest.json
│   └── chroma_500/               experiment index (116 vectors) — not a deliverable
├── scripts/
│   ├── prepare_knowledge_base.py Homework #1 — stdlib only
│   ├── rag_lib.py                settings, embeddings, index handle + HW3 filter/BM25/RRF
│   ├── build_index.py            embed chunks → Chroma
│   ├── retrieval.py              top-k semantic search (CLI)
│   ├── retrieval_improved.py     Homework #3 — filtered + hybrid search, --compare
│   ├── run_test_queries.py       evaluation → outputs/retrieval_examples.md
│   ├── rag_answer.py             Homework #4 — grounded QA, --evaluate / --improvements
│   ├── external_tool.py          Homework #5 — tool contract, validation, orchestration
│   ├── agent_flow.py             Homework #6 — rule-based router, plans, steps, state
│   └── chunk_size_experiment.py  800/150 vs 500/100 comparison
├── notebooks/retrieval.ipynb     the same pipeline, interactively
├── outputs/                      retrieval examples, comparison, grounded answers, tool and agent examples
├── tests/                        521 tests; no API key or network required
└── docs/homework1|homework2|homework3|homework4|homework5|homework6|tasks
```

Design notes and the full pipeline specification live in [`docs/`](docs/README.md) — start there.
The per-homework detail is in
[`docs/homework1/`](docs/homework1/README.md) and [`docs/homework2/`](docs/homework2/analysis.md).
The per-homework design decisions continue in
[`docs/homework3/retrieval-improvements-spec.md`](docs/homework3/retrieval-improvements-spec.md),
[`docs/homework4/generation-spec.md`](docs/homework4/generation-spec.md),
[`docs/homework5/tool-integration-spec.md`](docs/homework5/tool-integration-spec.md) and
[`docs/homework6/agent-flow-spec.md`](docs/homework6/agent-flow-spec.md).
