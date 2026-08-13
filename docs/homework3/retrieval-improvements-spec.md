# Retrieval improvements — design decisions

The Homework #3 counterpart to [`../homework2/retrieval-spec.md`](../homework2/retrieval-spec.md).
That file owns the basic semantic layer. This one owns everything the improved pipeline adds on
top of it: metadata filtering, hybrid BM25/RRF search, and the baseline-vs-improved evaluation.

Assignment spec:
[`../tasks/Домашнє завдання №3 — Покращення retrieval pipeline`](../tasks/Домашнє%20завдання%20№3%20—%20Покращення%20retrieval%20pipeline).

## Decisions

| # | Decision | Rationale |
|---|---|---|
| 1 | **Filter field: `document_type`** (4 values, from the HW1 schema enum) | The only metadata field that is both categorical and *about content kind*. `domain`/`language`/`source_type` are single-valued constants, so a filter on them removes nothing. `section` has 25 values, which is too fine-grained to infer reliably from a query. |
| 2 | **Rule-based filter inference** — `infer_document_type` counts keyword matches per type; zero matches **or a tie → unfiltered** | A wrong filter is worse than none. With 4 types mapping 1:1 to 4 documents, a misinferred type excludes the correct document entirely. Keywords come from the corpus's own vocabulary, never from the evaluation queries' wording, so the rules are not tuned to the test set. The out-of-corpus query must fall through unfiltered — a filter would funnel it into a document that cannot answer it. |
| 3 | **The filter narrows BOTH branches** — Chroma `where=` on the semantic side, `allowed_ids` on the BM25 side | A filter on one branch only would leave RRF to fuse two different candidate spaces. The excluded-then-reintroduced chunks would then defeat the filter's purpose. |
| 4 | **Additional technique: hybrid search (BM25 + RRF)**, standard library only | Chosen over query rewriting (chat-API cost + nondeterminism), cross-encoder reranking (heavy new dependencies), and static query expansion (hand-tuned dictionary against a known test set). BM25 over 77 chunks is a page of stdlib code. The existing fake-embedding seam keeps it fully offline-testable. BM25 complements semantic retrieval: it anchors on exact term overlap where that overlap exists. A paraphrase that still shares rare terms with the right chunk gains a lexical foothold (q05's "record"/"row"/"table"). But a pure vocabulary miss (q04) remains the semantic branch's job. |
| 5 | **Fusion: Reciprocal Rank Fusion**, `RRF_K = 60` | Cosine similarity and BM25 scores live in incomparable units. Fusion on ranks sidesteps normalization entirely. 60 is the constant from the original RRF paper. Ties break on `chunk_id`, so runs are deterministic. |
| 6 | **BM25 parameters `k1=1.5`, `b=0.75`; IDF over the full corpus even when filtered** | These are the standard Okapi defaults. Nothing in a 77-chunk corpus justifies tuning them. Corpus-wide IDF keeps a term's rarity stable, with a filter active or without one. `allowed_ids` narrows candidates, not statistics. |
| 7 | **Candidate pool `RRF_POOL = 10` per branch** before fusing down to k | Fusion needs more candidates than the final k=3. Without a larger pool, promotion is impossible. 10 per branch on a 77-chunk corpus (18–23 after filtering) balances recall against ranking noise. |
| 8 | **Baseline = the committed HW2 `outputs/retrieval_results.json`, read-only** | It already *is* "saved baseline results for the same queries" (same 10 queries, k=3, full scores), and it is a graded HW2 artifact. A regeneration would risk the HW2 grade to produce data git already has. The compare run refuses on a model or k mismatch rather than comparing apples to oranges. |
| 9 | **Primary metric: top-3 expected-document precision** (+ ablation) | The baseline already resolves 100% of in-corpus queries to the right document at top-1. The top-1 hit rate therefore sits at its ceiling and cannot show improvement. One measure can still improve: how much of the top-3 comes from the right document. At baseline, q05 and q09 leak foreign chunks into top-3. |
| 10 | **Three measured configurations: filter-only, hybrid-only, combined** | The rubric asks *which* change had the biggest effect. Without ablations, that answer is a guess. All three reuse one embedding per query, through a memoizing client wrapper over the production `client=` seam. Ranking differences are therefore attributable to the techniques, never to embedding drift. |
| 11 | **`HybridHit` carries `rrf_score`, `semantic_score/rank`, `bm25_rank` as separate fields** | Reuse of `SearchHit.score` for an RRF value would silently mix units downstream. Explicit fields also let the comparison show *why* a chunk surfaced (which branch promoted it). |
| 12 | **`hw3_comment` / `hw3_conclusion` are authored by hand after a real run** | This repeats the two-pass discipline of HW2's relevance comments. The compare run reports which entries are still empty instead of rendering a placeholder. |

## Known limits — stated, not hidden

- **Type cardinality makes filtering ≈ document selection.** With 4 document types mapping 1:1 to
  4 documents, a correct `document_type` filter is equivalent to picking the right document. The
  filter's measured effect is therefore an upper bound. A larger corpus, with many documents per
  type, would not reproduce it as strongly. The comparison's conclusion accounts for this.
- **The keyword rules are still corpus-sized.** They generalize beyond the 10 evaluation queries
  (they encode document vocabulary, not query wording). But a production system would replace them
  with a learned or LLM-based query classifier.
- **Cross-document queries can be narrowed too far.** q07/q08 expect two documents, and a
  single-type filter can exclude one. The tie/zero → unfiltered rule is deliberately conservative
  for exactly this case. The per-query detail shows the outcome honestly.
- **The breadcrumb prefix (`Title > Section.`) inflates BM25 for title words.** Every chunk of a
  document repeats its title tokens. A query that shares title vocabulary thus gets a lexical boost
  on every chunk of that document. Query q08 shows this at baseline already (HW2 comment). Hybrid
  search inherits it.

## What is deliberately not built

- **No LLM query rewriting / classification.** The improvement must be measurable offline and
  deterministically. A chat-model dependency would make the comparison unreproducible run-to-run.
- **No cross-encoder reranking.** sentence-transformers + torch is a heavyweight dependency set
  for a 77-chunk corpus. The assignment requires one technique, with a good implementation.
- **No score threshold.** Same reasoning as HW2: the out-of-corpus query's low score is the
  behaviour worth showing, and the spec does not ask for a floor. Homework #4 built that floor on
  2026-08-12. It sets the value at 0.35 (`scripts/rag_answer.py:59`) and applies it at
  `scripts/rag_answer.py:431`. That floor rests on the very separation this homework re-measured —
  see [`../homework4/generation-spec.md`](../homework4/generation-spec.md).
- **No persisted BM25 index.** A rebuild from `chunks.jsonl` takes milliseconds at this corpus
  size. The manifest digest gate covers the vector index only, so persistence would add an
  invalidation problem for no measurable gain.
