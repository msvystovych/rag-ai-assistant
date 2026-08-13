# Retrieval layer — design decisions

The Homework #2 counterpart to [`../homework1/pipeline-spec.md`](../homework1/pipeline-spec.md).
That file owns every chunking rule; this one owns everything downstream of `chunks.jsonl`.

Assignment spec:
[`../tasks/Домашнє завдання №2 — Базовий semantic retrieval layer`](../tasks/Домашнє%20завдання%20№2%20—%20Базовий%20semantic%20retrieval%20layer).

## Decisions

| # | Decision | Rationale |
|---|---|---|
| 1 | **Embedding model: OpenAI `text-embedding-3-small`** (1,536-dim) | User's choice from the two the spec recommends. No local model weights, no torch. |
| 2 | **Vector store: Chroma**, `PersistentClient`, HNSW, cosine space | User's choice. `index/` is what the spec grades; FAISS was the alternative. |
| 3 | **Embeddings are supplied explicitly** — `embedding_function=None` on the collection | Chroma would otherwise construct its default ONNX embedder and encode text itself, silently using a *different* model than the one that embedded the query. Passing vectors makes the model choice explicit and auditable. |
| 4 | **Score = `1 - cosine_distance`** | Chroma returns a distance; the spec's example output shows similarities (0.91). Converting once, at the boundary, keeps every downstream artifact in one unit. |
| 5 | **`index/chroma/manifest.json` is written on every build** | Records model, dimension, chunk count, collection, and a SHA-256 of `chunks.jsonl`. |
| 6 | **A model mismatch is a hard error** | `read_manifest` compares the index's model against the configured one and raises. The spec's "chunks and queries must use the same model" is otherwise an unenforced comment. |
| 7 | **One typed settings object** (`Settings.from_env`) | Every `os.environ` read in the project happens in that one classmethod. |
| 8 | **`.env` support, gitignored** | Keeps the key out of shell history and out of git. `load_dotenv` uses `setdefault`, so a real environment variable always wins over the file. |
| 9 | **Relevance comments are authored after a real run** | `run_test_queries.py` reports which queries still have an empty comment instead of rendering a placeholder — the failure mode `docs/homework1/README.md` calls "the one way to lose 10 points after doing all the work". |
| 10 | **The notebook imports `rag_lib`** | A notebook that reimplements retrieval drifts from the script it is supposed to demonstrate. |

### The manifest exists because of a real failure mode

A vector index is a lookup table of numbers. It keeps no memory of how it came to exist. It cannot
tell you which model, which dimension, or which chunks file produced it. Query it with a vector
from a different model, and it returns nearest neighbours in a space where "nearest" means nothing.
It does this silently, and the scores still look plausible. The manifest turns that into an
exception.

The manifest also caught a genuine bug during development. The manifest path first pointed at
`index_dir.parent / manifest.json`. That parent anchor made two indexes under the same parent share
one manifest. The chunk-size experiment then built its second index at `index/chroma_500/`, so that
build **overwrote the primary index's manifest**. The manifest now lives inside its own index
directory.

## Timeouts and retries

`NEVER-PY-003` requires an explicit timeout on every network call. It also requires independent
connect and read budgets, and it forbids one identical value for both. `rag_lib._openai_client`
builds an `httpx.Timeout` with `connect=10s` and `read=60s`. A connect budget as large as the read
budget holds the process through a black-holed connection. A read budget as small as the connect
budget fails on a healthy-but-slow embedding batch. `max_retries=3` covers rate-limit responses,
and the OpenAI SDK backs off between attempts.

## Batching

`text-embedding-3-small` accepts many inputs per request. `embed_texts` embeds chunks in batches of
96. It then reorders each batch by the API's returned `index` field before use. It does that
because the response order is not contractually the request order. A silent misalignment would
attach every chunk's vector to the wrong text.
`tests/test_retrieval.py::TestEmbedding::test_preserves_input_order_across_batches` pins this.

## Known limits — stated, not hidden

Every limit below comes from a real run over the committed index. The numbers and the per-query
detail live in [`analysis.md`](analysis.md).

- **Paraphrasing costs 30% of the similarity score.** Mean top-1 falls from 0.601 on direct queries
  to 0.423 on paraphrases. The ranking still holds, but the margin narrows sharply.
- **Chunks that open in mid-sentence rank well and read badly.** The embedding covers the whole
  chunk, so the ranking holds. But a human reader gets a fragment whose first clause belongs to the
  previous chunk. An LLM asked to quote a source gets that same fragment.
- **One high score rests partly on keyword overlap.** `q08` contains the exact string
  "5,000 requests per second", and that string appears in the document's H1. The breadcrumb
  prepends that H1 to *every* chunk of that document. The 0.646 is therefore partly keyword
  overlap, not semantic similarity.
- **The layer has no way to decline an out-of-corpus question.** `q10` asks about a topic the
  corpus does not cover, and the layer still returns three cleanly formatted results. `q10`'s top-1
  scores 0.266 against an in-corpus floor of 0.413.

## What is deliberately not built

- **No score threshold.** The out-of-corpus query shows why the layer needs one
  ([`analysis.md`](analysis.md)). But the assignment asks for top-k retrieval, and adding an
  unrequested filter would hide the very behaviour worth showing.
  **Since then:** Homework #4 (2026-08-12) built the threshold. `scripts/rag_answer.py:59` sets the
  floor, and `scripts/rag_answer.py:431` applies it.
- **No re-ranking, no hybrid BM25, no query expansion.** All are the obvious next steps; none is in
  scope for a "basic retrieval layer".
  **Since then:** Homework #3 (2026-07-24) built hybrid BM25 and RRF. `scripts/rag_lib.py` gained
  `Bm25Index`, `rrf_fuse` and `search_improved`, and `scripts/retrieval_improved.py` drives them.
  The repo still has no re-ranking and no query expansion.
- **No LLM answer generation.** This homework ends at retrieved chunks.
  **Since then:** Homework #4 (2026-08-12) built it in `scripts/rag_answer.py`.
