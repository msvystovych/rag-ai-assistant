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

## The manifest exists because of a real failure mode

A vector index is a lookup table of numbers with no memory of how it was produced. Query it with a
vector from a different model and it returns nearest neighbours in a space where "nearest" means
nothing — silently, with plausible-looking scores. The manifest turns that into an exception.

It also caught a genuine bug during development: the manifest path was originally
`index_dir.parent / manifest.json`, so building the chunk-size experiment's second index at
`index/chroma_500/` **overwrote the primary index's manifest**. The manifest now lives inside its own
index directory.

## Timeouts and retries

`NEVER-PY-003` requires an explicit timeout on every network call, with connect and read budgets set
independently. `rag_lib._openai_client` builds an `httpx.Timeout` with `connect=10s` and
`read=60s` — a connect budget sized for a read holds the process through a black-holed connection,
and a read budget sized for a connect fails on a healthy-but-slow embedding batch. `max_retries=3`
covers rate-limit responses; the OpenAI SDK backs off between attempts.

## Batching

`text-embedding-3-small` accepts many inputs per request. Chunks are embedded in batches of 96 and
reordered by the API's returned `index` field before use — the response order is not contractually
the request order, and a silent misalignment would attach every chunk's vector to the wrong text.
`tests/test_retrieval.py::TestEmbedding::test_preserves_input_order_across_batches` pins this.

## What is deliberately not built

- **No score threshold.** The out-of-corpus query demonstrates why one is needed
  ([`analysis.md`](analysis.md)), but the assignment asks for top-k retrieval and adding an
  unrequested filter would hide the very behaviour worth showing.
- **No re-ranking, no hybrid BM25, no query expansion.** All are the obvious next steps; none is in
  scope for a "basic retrieval layer".
- **No LLM answer generation.** This homework ends at retrieved chunks.
