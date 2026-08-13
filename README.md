# RAG Knowledge Base — Logistics-Domain Engineering Assistant

Homework #1 — preparing a knowledge base for a retrieval-augmented chatbot.
Homework #2 — a basic semantic retrieval layer over that knowledge base.
Homework #3 — an improved retrieval pipeline: metadata filtering + hybrid BM25/RRF search.
Homework #4 — grounded answer generation: the model answers only from retrieved context, with citations.
Homework #5 — external tool integration: the model calls a live operations API, or falls back to the knowledge base.

Assignment specs:
[`docs/tasks/Домашнє завдання №1 — Підготовка knowl`](docs/tasks/Домашнє%20завдання%20№1%20—%20Підготовка%20knowl) ·
[`docs/tasks/Домашнє завдання №2 — Базовий semantic retrieval layer`](docs/tasks/Домашнє%20завдання%20№2%20—%20Базовий%20semantic%20retrieval%20layer) ·
[`docs/tasks/Домашнє завдання №3 — Покращення retrieval pipeline`](docs/tasks/Домашнє%20завдання%20№3%20—%20Покращення%20retrieval%20pipeline) ·
[`docs/tasks/Домашнє завдання №4 — Генерація відповіді поверх retrieval`](docs/tasks/Домашнє%20завдання%20№4%20—%20Генерація%20відповіді%20поверх%20retrieval) ·
[`docs/tasks/Домашнє завдання №5 — Інтеграція зовнішнього tool або джерела`](docs/tasks/Домашнє%20завдання%20№5%20—%20Інтеграція%20зовнішнього%20tool%20або%20джерела)

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
```

## Subject area

A chatbot that answers freight-exchange / logistics-platform engineering questions: domain concepts
(loads, carriers, matching), architecture (CQRS + Event Sourcing), a monolith-to-microservices
migration case study, and operating a platform at 5,000 requests per second. All documents are
self-authored from general logistics-engineering knowledge — no proprietary material.

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

Each JSONL line carries top-level `chunk_id` and `text`, plus a `metadata` object with
`document_id`, `source_file`, `source_type`, `title`, `section`, `chunk_index` (1-based),
`language`, `domain`, and `document_type`. `chunk_id = <document_id>_chunk_<index:03d>`.
All 77 lines validate against
[`docs/homework1/assets/chunk.schema.json`](docs/homework1/assets/chunk.schema.json).

## Chunking strategy

- Header-aware section splitting, with a paragraph → line → sentence → word-boundary fallback
  inside long sections (never mid-word). Stdlib-only.
- `chunk_size` 800 characters, `overlap` 150, `min_chunk` 500; every chunk is capped at
  1000 characters including the `"Document Title > Section. "` breadcrumb prefix it carries.
- Chunks under 500 characters are merged backward into their predecessor when the result fits
  the cap.
- Overlap applies between consecutive chunks *within a section only*; heading boundaries reset
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
```

Step 1 needs only Python ≥ 3.9. Steps 2–8 need the packages in `requirements.txt`; verified on
Python 3.14.6. `notebooks/retrieval.ipynb` is the same pipeline interactively — it imports
`scripts/rag_lib.py` rather than reimplementing anything.

## Example chunks

Three real lines from `data/processed/chunks.jsonl`, reformatted for readability.

**1 — a document's opening chunk: stands alone and opens on a complete definition; the breadcrumb
makes every retrieval hit self-locating.**

```json
{"chunk_id": "freight_exchange_domain_primer_chunk_001",
 "text": "Freight Exchange Fundamentals: Actors, Loads, and Matching > What A Freight Exchange Is. A freight exchange is a two-sided digital marketplace in which one side publishes transport demand and the other offers vehicle capacity, while the platform supplies discovery, matching, and the commercial rails that let strangers transact safely. Demand arrives as loads: shipments described by origin, destination, weight, dimensions, equipment requirement, and a loading date window. …",
 "metadata": {"document_id": "freight_exchange_domain_primer", "source_file": "data/raw/freight-exchange-domain-primer.md", "source_type": "markdown", "title": "Freight Exchange Fundamentals: Actors, Loads, and Matching", "section": "What A Freight Exchange Is", "chunk_index": 1, "language": "en", "domain": "logistics-engineering", "document_type": "concept-guide"}}
```

**2 — one topic end to end: defines its term ("projection") before using it, which is what makes
it embed well.**

```json
{"chunk_id": "cqrs_event_sourcing_for_logistics_chunk_013",
 "text": "CQRS and Event Sourcing in a Freight Platform > Projections And Read Models. A projection is a consumer that folds the event stream into a shape optimized for one kind of query. A lane-search index is the natural example: fed by posting, repricing, and booking events, it stores each open load flat and pre-joined, with the filters carriers actually use — corridor, equipment type, weight band, date window — as first-class indexed attributes. …",
 "metadata": {"document_id": "cqrs_event_sourcing_for_logistics", "section": "Projections And Read Models", "chunk_index": 13, "document_type": "architecture-guide", "…": "…"}}
```

**3 — answers a "how do I" question directly: top-1 for query `q06` even though the query shares
almost no vocabulary with it.**

```json
{"chunk_id": "scaling_and_zero_downtime_operations_chunk_010",
 "text": "Operating a Freight Platform at 5,000 Requests per Second > Zero-Downtime Deployments. Zero-downtime deployment is usually attributed to the rollout mechanism, but the mechanism is the smaller half. Rolling updates replace instances gradually and are the cheapest option; blue-green and canary rollouts hold a full second environment or a small traffic slice … What actually makes any of them safe is that consecutive versions can run side by side. …",
 "metadata": {"document_id": "scaling_and_zero_downtime_operations", "section": "Zero-Downtime Deployments", "chunk_index": 10, "document_type": "playbook", "…": "…"}}
```

---

# Homework #2 — semantic retrieval layer

## How to verify this homework (grading checklist)

Each rubric row of the assignment (§ 4) maps to committed evidence and a copy-paste check.
Everything except V2's live query runs **offline — no API key required**. Run from the repo root
with the dependencies installed. All § 3 deliverables are tracked in git: `scripts/retrieval.py` +
`notebooks/retrieval.ipynb` · `index/chroma/` (Chroma is a spec-listed alternative to FAISS) ·
`outputs/retrieval_examples.md` · this README.

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

# The full test suite — 324 tests (74 HW1-2 + 52 HW3 + 77 HW4 + 121 HW5), offline, no key or network.
python -m pytest -q
```

Opening the Chroma index (V1, V2) may touch its binary bookkeeping files without changing any
content; `git checkout -- index/` restores a clean tree afterwards.

## Embeddings and vector storage

| | |
|---|---|
| **Embedding model** | OpenAI `text-embedding-3-small`, 1,536 dimensions |
| **What is embedded** | each chunk's full `text`, breadcrumb prefix included |
| **Query encoding** | the **same** model — enforced, not assumed |
| **Vector store** | Chroma `PersistentClient`, `index/chroma/`, HNSW, cosine space |
| **Vectors indexed** | 77 — equal to the line count of `chunks.jsonl` |
| **Score** | `1 - cosine_distance`, so 1.000 is identical and 0.000 orthogonal |

`index/chroma/manifest.json` records the model, dimension, chunk count and a SHA-256 of the input
file; `retrieval.py` reads it before every search and **refuses to run** against an index built
with a different model or from a since-edited `chunks.jsonl`.

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

**Top-1 hit rate on the nine in-corpus queries: 9/9**, including all three paraphrases.

## Conclusions — Homework #2

**Where retrieval works well.** Semantic matching genuinely works: `q06` asks how to "release new
code without users noticing any interruption", never uses the corpus's vocabulary, and still gets
the Zero-Downtime Deployments section for all three hits. Results cluster tightly — a top-3 spans
2.00 distinct sections and 1.33 distinct documents on average.

**Where it breaks down.**

1. **Paraphrasing costs 30% of the similarity score** (0.601 direct vs 0.423 paraphrase). Ranking
   survives; the margin does not.
2. **There is no "I don't know."** The out-of-corpus query still returns three confidently
   formatted results; only the score betrays it (0.266 vs an in-corpus floor of 0.413), and no
   threshold is enforced. A floor near 0.35 is the obvious next control.
3. **One high score is partly lexical:** `q08` repeats a phrase the breadcrumb prepends to every
   chunk of one document, so keyword overlap inflates a semantic-looking score.
4. **Chunks that open mid-sentence rank well and read badly** — an artifact of the overlap carry.

**Chunk-size experiment** ([`outputs/chunk_size_experiment.md`](outputs/chunk_size_experiment.md)):
re-chunking at 500/100 slightly raises mean top-1 but drops the hit rate from 100% to 89% and
narrows the out-of-corpus separation margin from 0.147 to 0.101. **800/150 is retained**, on
evidence rather than a best-practice guess.

**Limitations.** The corpus and the queries share an author, which makes retrieval easier than in
the wild; ten queries over 77 chunks is an anecdote, not a benchmark. Full analysis:
[`docs/homework2/analysis.md`](docs/homework2/analysis.md).

## Conclusions — Homework #1 chunk quality

Measured on the committed run: 4 documents → **77 chunks**, `text` length min 390 / mean 707 /
max 930, **90.9%** inside the 500–1000 band. All figures are printed by
`scripts/prepare_knowledge_base.py` itself.

**What worked well:**

- The breadcrumb prefix makes every chunk understandable in isolation, at a mean cost of
  79 characters per chunk.
- Overlap behaves as specified for 48 of 52 same-section pairs; the other 4 carry less because the
  carry is capped so a piece can never exceed `chunk_size` — by design, not a bug.
- No chunk is truncated mid-word, none exceeds the 1000-character ceiling, none is under
  250 characters, and reruns on unchanged input are byte-identical.

**What to improve:**

- **The backward-merge rule is nearly inert at 800/150** — 14 candidates, 1 merged, 13 refused by
  the 1000-character cap, because a predecessor packed to ~800 characters leaves no headroom.
  Either lower `chunk_size` to ~650 or drop the rule.
- **Overlap should snap to a sentence boundary** — chunks routinely open mid-sentence, which reads
  badly in retrieval output even though ranking is unaffected.
- Sections of ~1,600 characters (a clean 2× the target) would split with less waste.

---

# Homework #3 — improved retrieval pipeline

Two additions on top of the Homework #2 layer, measured against it on the same 10 queries:

1. **Metadata filtering** — a rule-based keyword map infers a `document_type` filter from the
   query (zero matches or a tie → unfiltered); the filter narrows **both** the semantic branch
   (Chroma `where=`) and the lexical branch. `--document-type` overrides, `--no-filter` disables.
2. **Hybrid search** — the semantic ranking is fused with a standard-library BM25 ranking via
   Reciprocal Rank Fusion (no new dependencies).

The baseline is the committed Homework #2 result file, read-only — the compare run refuses to
proceed on a model or k mismatch rather than compare apples to oranges. Design decisions and
known limits: [`docs/homework3/retrieval-improvements-spec.md`](docs/homework3/retrieval-improvements-spec.md).

## How to verify this homework (grading checklist)

All § 3 deliverables are tracked in git: `scripts/retrieval_improved.py` ·
`outputs/retrieval_comparison.md` · this README — plus `outputs/retrieval_results_improved.json`,
the machine-readable backing for the comparison (the HW3 counterpart of HW2's
`retrieval_results.json`; not §3-listed, kept because the checks below verify against it).
Everything except V2's live query runs **offline — no API key required**.

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

Every hit names which branch surfaced it (`semantic` rank, `bm25` rank) and the fused `rrf`
score — the units are deliberately separate, because RRF scores and cosine similarities are not
comparable.

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

8 of 10 queries were filtered (q05's vocabulary is ambiguous and q10 is out-of-corpus — both
correctly fall through unfiltered); 6 of 10 changed their top-1 chunk.

## Conclusions — Homework #3

**What gave the biggest effect: metadata filtering — but not for the obvious reason.** Its own
precision gain is modest (0.889 → 0.926, from evicting q09's foreign-document chunk). Its real
value is constraining hybrid search's failure mode: run alone, hybrid REGRESSED q09's top-1 to a
CQRS chunk (lexical strength of the word "event") and leaked a migration chunk into q06's top-3,
dropping the top-1 hit rate to 0.89. Combined, the filter caps the lexical leakage while BM25
re-ranks within the right document — 0.963 precision with the hit rate intact.

**The largest single-query win belongs to hybrid search**, on exactly the query filtering cannot
touch: q05 stays unfiltered (ambiguous vocabulary), and BM25 promoted two genuinely better
event-sourcing chunks from semantic ranks 4–5 into the top-2, shrinking HW2's three-document leak
to one foreign chunk.

**Honest caveats.** (1) With four `document_type` values mapping 1:1 to four documents, a correct
filter is equivalent to picking the right document — the measured effect is an upper bound that a
corpus with many documents per type would not reproduce as strongly. (2) Hybrid is a net win in
aggregate, not per query: q08's top-1 got qualitatively worse because the breadcrumb repeats the
document title's "5,000 Requests per Second" in every chunk, and BM25 amplifies exactly that
title-token inflation (flagged in HW2, inherited here). (3) The keyword rules encode corpus
vocabulary, not query wording, but a production system would replace them with a learned query
classifier — recorded, with the other limits, in
[`docs/homework3/retrieval-improvements-spec.md`](docs/homework3/retrieval-improvements-spec.md).

---

# Homework #4 — grounded answer generation

The first layer that answers rather than retrieves: `question → retrieve top-k → build prompt →
call the LLM → grounded answer with citations`. Retrieval is the Homework #3 combined pipeline, so
this homework adds only the generation half.

Two independent gates produce the "I don't know" behaviour, and they answer different questions:

1. **A relevance floor** (`--min-score`, default 0.35) reads the best cosine score in the retrieved
   set. Below it the context is passed to the model **empty** — the floor decides whether anything
   retrieved is close enough to be worth showing at all.
2. **The prompt's own refusal rule** decides whether the context it did receive actually contains
   the answer. A floor cannot tell that three on-topic chunks all miss the specific fact asked for;
   a prompt rule never sees an empty context.

0.35 is not a fresh guess — it is the number [Homework #2's analysis](docs/homework2/analysis.md)
derived from measurement (out-of-corpus top 0.266 vs in-corpus floor 0.413) and then deferred, as
did Homework #3. Design decisions and known limits:
[`docs/homework4/generation-spec.md`](docs/homework4/generation-spec.md).

## How to verify this homework (grading checklist)

All § 3 deliverables are tracked in git: [`scripts/rag_answer.py`](scripts/rag_answer.py) ·
[`outputs/rag_answers_examples.md`](outputs/rag_answers_examples.md) ·
[`outputs/prompt_improvements.md`](outputs/prompt_improvements.md) · the prompt template (below and
in the script) · this README — plus `outputs/rag_answers_results.json`, the machine-readable backing
for the examples (the HW4 counterpart of HW2's `retrieval_results.json`; not §3-listed, kept because
the checks below verify against it). Everything except V2's live run works **offline — no API key
required**.

| Rubric criterion (§ 4) | Pts | Evidence | Check |
|---|---|---|---|
| Prompt template with a grounded-answering rule | 10 | [Prompt template](#prompt-template) · `PROMPT_VERSIONS["v3"]` in [`scripts/rag_answer.py`](scripts/rag_answer.py) — only-from-context rule, verbatim refusal sentence, citation requirement | V1 |
| QA pipeline implemented (retrieval → answer) | 15 | [`scripts/rag_answer.py`](scripts/rag_answer.py) — `--query` / `--evaluate` / `--improvements`; all **10** questions run end to end (9 answered, 1 correctly refused) | V2, V3 |
| Citation or source in every answer | 10 | [`outputs/rag_answers_examples.md`](outputs/rag_answers_examples.md): **9 of 9** answered questions carry inline `[chunk_id]` markers **and** a `Source:` line, **0** fabricated. q10 is the refusal and deliberately carries neither — see the note below the table | V4 |
| Fallback behaviour on empty/weak context | 5 | q10 in [`outputs/rag_answers_examples.md`](outputs/rag_answers_examples.md): top 0.266 < 0.35 → context empty → refusal, no citation, no source | V5 |
| 2–3 prompt improvements with explanation | 10 | [`outputs/prompt_improvements.md`](outputs/prompt_improvements.md): **3** cases, each a real before/after over identical retrieved chunks | V6 |

The spec's § 2 asks for four *kinds* of test question. The question set is inherited from Homework
#2, whose `category` values were chosen for a retrieval evaluation, so the two taxonomies do not
line up name-for-name. The mapping is:

| § 2 required kind | Questions | Evidence it is that kind |
|---|---|---|
| Simple question whose answer is definitely in context | q01, q02, q03 (`direct`) | top scores 0.536 / 0.582 / 0.685 — the three highest in the set |
| Reformulated question | q04, q05, q06 (`paraphrase`) | deliberately avoid the corpus's own wording; q04 drops the word "backhaul" entirely |
| Context insufficient → fallback | q10 (`out-of-corpus`) | top 0.266 < 0.35 floor → context passed empty → refusal, 0 citations, no source |
| Retrieval returns a **weak** chunk | q05, q06 | q05: the floor was cleared at 0.412 by a *foreign-document* chunk the answer then did not cite, while the two chunks that answered scored 0.354 and 0.361 (+0.004 / +0.011 over the floor). q06: `scaling_..._chunk_004` at 0.2658 — *below* the floor — rode into the context on a stronger sibling's score, and the answer correctly ignored it |

The weak-chunk row is the one the inherited `category` labels do not name, so it is spelled out
here rather than left to be reconstructed. Both cases are analysed in their `Comment:` blocks in
[`outputs/rag_answers_examples.md`](outputs/rag_answers_examples.md).

Within `--evaluate` the floor always fires first, so only the *empty* half of the fallback occurs
there. The *weak* half was measured separately with the floor disabled — three genuinely off-topic
chunks reached the model and it refused anyway, so the prompt rule stands on its own:

```bash
$ python scripts/rag_answer.py --query "What is the best way to fine-tune a large language model on a custom dataset?" --k 3 --no-min-score

Context: 3 chunk(s) (top semantic 0.266, floor disabled)
Retrieved chunks: monolith_..._chunk_013 (semantic 0.244), cqrs_..._chunk_002 (semantic 0.222), monolith_..._chunk_014 (semantic 0.266)
Answer: I do not have enough information in the available documents to answer this question.
Citations: (none)
```

That run is deliberately outside the committed evaluation — including it would change the graded
aggregates. It also surfaced a real defect, since fixed and pinned by tests: a refusal over a
*non-empty* context was still naming its retrieved documents as sources. Details in
[`docs/homework4/generation-spec.md`](docs/homework4/generation-spec.md) § Known limits.

**On rubric row 3 and the refusal.** The spec asks for a citation in *every* answer (§ 4) and also
requires the model to refuse rather than invent when context is insufficient (§ 4) — and its own
example refusal (§ 5) carries no source. A refusal therefore cannot satisfy the citation row
literally. This implementation reports the citation rate over *answered* questions (9 of 9) and
deliberately emits no source for a withheld context, on the grounds that a chunk the model never
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

# The full test suite — 324 tests (74 HW1-2 + 52 HW3 + 77 HW4 + 121 HW5), offline, no key or network.
python -m pytest -q
```

## Prompt template

The shipped template is `v3`. All three versions stay runnable (`--prompt-version v1|v2|v3`) so
every before/after in `outputs/prompt_improvements.md` can be reproduced rather than taken on trust.

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

Each context entry is headed by the id the model must cite, so the citation format is shown rather
than only described:

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

This is the query Homework #2 could not resolve cleanly — its recorded judgement was that "the
POD-to-settlement link is retrievable but not cleanly isolated in one chunk". The answer layer
assembled it from three.

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

**The prompt is what produces the refusal, and that is measured rather than asserted.** Case-1 of
[`outputs/prompt_improvements.md`](outputs/prompt_improvements.md) runs the out-of-corpus question
through the assignment's own starting prompt over the *identical* retrieved chunks and gets a
confident eight-step tutorial on LoRA, Hugging Face and gradient clipping — not one word of it from
a logistics corpus. The same question under `v2` returns the refusal sentence. Retrieval was held
constant, so the hallucination was entirely the prompt's doing.

**Case-3 is the honest counterweight.** It was designed to catch the naive prompt drifting on q05,
the hardest in-corpus question — and the naive prompt did not drift. Its answer was substantively
grounded; what it lacked was any citation, so a reader could not verify a correct answer. A naive
prompt is not reliably wrong, it is *unreliably right*, which is worse: one well-behaved sample
would have predicted the opposite of case-1. That is the argument for keeping all three prompts
runnable instead of quoting them in a document.

**The floor is thinner than the aggregate suggests.** It fired exactly once, on q10 (0.266 against
0.35), and no in-corpus question was refused. But three of the nine answered questions sit within
0.07 of refusal, and q05 is the instructive one: it cleared the floor at 0.412 on a
*foreign-document* chunk the answer then did not cite, while the two chunks that actually answered
scored 0.354 and 0.361 — 0.004 and 0.011 above the line. The gate was opened by a chunk that
contributed nothing.

Two of the nine answered questions sit within 0.07 of refusal (q05 at +0.062, q04 at +0.063) and a
third, q06, within 0.09 (+0.081). q05 is also where a second, independent weakness shows up, and the
two compound on the same query.
The floor is calibrated on the *semantic top-1* but reads the *RRF-fused top-k*, which are not the
same statistic — under fusion a chunk found by both branches outranks a chunk the semantic branch
ranked first but BM25 never surfaced. The committed `semantic_rank` field makes this auditable, and
exactly one of the ten questions shows it: q05's returned chunks are semantic ranks **5, 4 and 2** —
the semantic rank-1 chunk never reached the context at all. So the query with the narrowest margin
is also the only one where the gate judged a displaced statistic. The floor earned its place on the
single query it was built for, and it is one recalibration away from costing a correct answer
([`docs/homework4/generation-spec.md`](docs/homework4/generation-spec.md) § Known limits).

**Several Homework #2 defects stopped being defects.** HW2 faulted q01's top-1 for opening
mid-sentence so the definition landed at top-3; generation reads all of top-k, so the chunk boundary
no longer matters. HW2 and HW3 both worried at q02's 0.582-vs-0.581 tie — HW3 spent BM25 on breaking
it — and both chunks are in context anyway, so the ordering was irrelevant. What does survive is
everything about *which* chunks arrive rather than in what order: q08's breadcrumb-inflated score
still decides its context, and no prompt rule repairs a chunk that was never retrieved.

---

# Homework #5 — external tool integration

The first layer that can consult something other than the corpus, and the first that can *act*:
`question → model chooses → validate → operations API → answer`. Both tool schemas are handed to
the model on every turn and it decides; when it asks for no tool the question falls through to the
Homework #4 pipeline unchanged, so "when NOT to call the tool" is an observed behaviour rather than
a claim about our dispatch code.

Two tools ship, because a read-only integration can only demonstrate half of what § 2 asks about
validation:

1. **`get_load_status(load_id)`** — read. One load's live lifecycle status, carrier, ETA and last
   known position with its age. The corpus defines what `in_transit` *means*; only the tool knows
   which load is in it.
2. **`book_load(load_id, carrier_id)`** — write, and irreversible. Booking is the first
   irreversible commercial transition in the load lifecycle, so the tool refuses unless the human
   operator authorised it through `--confirm`. The model cannot supply that authorisation: a
   `confirmed: true` it sets for itself is refused and recorded as `model_self_confirmed`.

Every argument reaching the tool layer was written by the model and is treated as untrusted —
required fields, declared `pattern`, no unknown properties, and no free-text parameter anywhere in
the contract for a query or a statement to be injected into. Design decisions and known limits:
[`docs/homework5/tool-integration-spec.md`](docs/homework5/tool-integration-spec.md).

## How to verify this homework (grading checklist)

All § 3 deliverables are tracked in git: [`scripts/external_tool.py`](scripts/external_tool.py) ·
[`outputs/tool_examples.md`](outputs/tool_examples.md) · the validation logic (in the script, and
described below) — plus `data/external/loads.json`, the external source itself, and
`outputs/tool_results.json`, the machine-readable backing for the examples (the HW5 counterpart of
HW4's `rag_answers_results.json`; not § 3-listed, kept because the checks below verify against it).
Everything except V4's live run works **offline — no API key required**.

| Rubric criterion (§ 4) | Pts | Evidence | Check |
|---|---|---|---|
| Tool described (name, type, purpose, when to call) | 5 | `python scripts/external_tool.py --list-tools` — name, type, purpose, source and the description the model actually reads, for both tools; each states its `Do NOT call this` case | V1 |
| Input / output contract defined | 10 | `GET_LOAD_STATUS_SCHEMA` / `BOOK_LOAD_SCHEMA` in [`scripts/external_tool.py`](scripts/external_tool.py) — JSON Schema literals that **are** the `tools=` payload, so contract and wire format cannot drift; output shape in [`outputs/tool_results.json`](outputs/tool_results.json) | V2 |
| Validation implemented | 10 | All four § 2 clauses: required fields, id `pattern`, `additionalProperties: false`, and operator confirmation on the write. **121** offline tests, incl. 6 parametrized malformed identifiers and a test proving validation runs *before* the data layer | V3 |
| Tool implemented and runs | 10 | [`scripts/external_tool.py`](scripts/external_tool.py) — `--question` / `--examples` / `--list-tools`; **4** of 6 committed runs reached a tool, 2 correctly did not | V4, V6 |
| 3–5 examples explaining the advantage over retrieval | 10 | [`outputs/tool_examples.md`](outputs/tool_examples.md): **5** scenarios, each with a hand-authored `Why tool is better than retrieval:` — including s5, where the tool is the *worse* instrument | V5 |
| Call through an orchestration layer or the model shown | 5 | Native OpenAI tool calling: `orchestrate()` in [`scripts/external_tool.py`](scripts/external_tool.py). No hand-written router — `route` in [`outputs/tool_results.json`](outputs/tool_results.json) records what the model chose per run | V6 |

**Two results worth reading before the checks.** Neither is a success, and both are in the design
doc's § Known limits with their reproduction commands.

- The write gate was initially **unreachable**. `book_load`'s first description told the model the
  call would be refused without operator authorisation, so it reasonably stopped calling — no tool
  call, no refusal, nothing to grade. A gate the model declines to approach has not been tested.
  The description now tells it to always call and let the tool decide, which is also the correct
  division of responsibility.
- **Format validation cannot detect fabrication.** Asked to book a load "for carrier 817" the model
  emitted `CAR-00817` — well formed, real, and probably not what the user meant. Every validation
  rule here passes it, because every one of them is syntactic. Only the confirmation gate stopped
  it, and a read tool has no such gate.

Scenario s3 also did not go as designed: given the malformed `FX-26-42` the model declined to emit
it at all, because the contract it is shown declares the pattern. So `invalid_load_id_format` never
fired live and is covered by the offline suite only — the contract is the outer filter, validation
the inner one.

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

# The full test suite — 324 tests (74 HW1-2 + 52 HW3 + 77 HW4 + 121 HW5), offline, no key or network.
python -m pytest -q
```

## Tool contract

Both schemas are module constants and are passed verbatim as the `tools=` payload, so what is
printed below is what the model receives:

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

Reproduced verbatim from the committed run in
[`outputs/tool_results.json`](outputs/tool_results.json) (scenario s1). The `Result:` line is
abridged where marked; nothing else is edited.

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

The model turned `last_position_age_s: 214` into "about 3.5 minutes ago" on its own. That
conversion is unchecked — see [`docs/homework5/tool-integration-spec.md`](docs/homework5/tool-integration-spec.md)
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

**The routing is what this homework actually demonstrates, and the model got it right four times
out of four decisions that mattered.** It reached for a tool on both live-state questions and both
booking attempts, and declined on both questions that were about documented knowledge — with the
tools sitting on the table each time. Nothing had to inspect the question before the model saw it.
The two declines are the more interesting half: s5 is the case the assignment's own § 2 asks about
("коли НЕ викликати"), and s3 was a decline nobody designed for.

**The tool description turned out to be the load-bearing piece of the design, and getting it wrong
made the gate untestable rather than merely worse.** The first version told the model that
`book_load` would be refused without operator authorisation. That is true, and it is exactly the
kind of honest documentation that reads well in a spec — and a well-aligned model responded by not
calling a tool it expected to fail. The write path silently became unreachable: no tool call, no
refusal, an empty result to grade. The lesson generalises past this homework. A schema
`description` is not documentation for a reader, it is a routing instruction for the model, and any
permission the model can decline to *request* is a permission the system has not actually retained.
Moving the decision into the tool made the gate both testable and correctly located.

**Validation is necessary and demonstrably not sufficient.** All four clauses the spec names are
implemented and refuse under test, and one of them — `additionalProperties: false` plus the absence
of any free-text parameter — is what makes "the tool never takes a raw query from the model" a
property of the contract instead of a promise. But two measured results bound what that buys. The
model padded "carrier 817" into `CAR-00817`, a fabrication every syntactic rule accepts, and the
only thing that caught it was a human being asked to confirm. And the malformed identifier never
reached the validator at all, because the schema's `pattern` filtered it a layer earlier. Both cut
the same way: shape checking tells you an argument is *well formed*, never that it is *right*, and
the confirmation gate is doing more of the safety work than the validators are.

**The static/dynamic split held up, including in the direction that flatters the corpus.** The
knowledge base states the rule — a load is booked exactly once, confirmation is idempotent — and
`book_load` enforces that same rule in code against live state; s4 and s5 are one design seen from
either side. Where the tool is absent the loss is concrete rather than theoretical: s3 fell through
to retrieval and the user was told the documents were insufficient, which was true, unhelpful, and
said nothing about the typo that caused it.

---

## Repository layout

```
├── data/raw/                     4 authored Markdown source documents
├── data/processed/
│   ├── chunks.jsonl              77 chunks — the Homework #1 deliverable
│   └── chunks_500.jsonl          116 chunks at 500/100 — chunk-size experiment only
├── data/eval/test_queries.json   10 evaluation queries + relevance comments (HW2 + HW3 + HW4 + HW5)
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
│   └── chunk_size_experiment.py  800/150 vs 500/100 comparison
├── notebooks/retrieval.ipynb     the same pipeline, interactively
├── outputs/                      retrieval examples, comparison, grounded answers, tool examples
├── tests/                        324 tests; no API key or network required
└── docs/homework1|homework2|homework3|homework4|homework5|tasks
```

Design notes and the full pipeline specification live in
[`docs/homework1/`](docs/homework1/README.md) and [`docs/homework2/`](docs/homework2/analysis.md);
the per-homework design decisions continue in
[`docs/homework3/retrieval-improvements-spec.md`](docs/homework3/retrieval-improvements-spec.md),
[`docs/homework4/generation-spec.md`](docs/homework4/generation-spec.md) and
[`docs/homework5/tool-integration-spec.md`](docs/homework5/tool-integration-spec.md).
