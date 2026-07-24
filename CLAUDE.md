# CLAUDE.md — rag-ai-assistant

Graded homework series building a RAG system step by step (HW1: knowledge-base preparation,
HW2: semantic retrieval, HW3: retrieval improvements — `document_type` metadata filtering +
hybrid BM25/RRF; further homeworks will extend this repo). The assignment specs in
`docs/tasks/` (Ukrainian) are the **arbiter for every graded behavior** — on any conflict between
code, tests, README, and spec, the spec wins. The repo-root `README.md` is itself a graded
deliverable and carries a per-homework, per-rubric verification checklist.

## Repository map

The layout repeats per homework — follow the same pattern when a new homework starts:

- `docs/tasks/` — assignment specs. Filenames are extensionless and contain spaces: links to them
  must percent-encode the spaces.
- `docs/homeworkN/` — that homework's design docs and analysis. Read the owning design doc before
  changing its code: `docs/homework1/pipeline-spec.md` owns every chunking rule
  (`prepare_knowledge_base.py`); `docs/homework2/retrieval-spec.md` records the retrieval-layer
  decisions (`rag_lib.py`); `docs/homework3/retrieval-improvements-spec.md` owns the improved
  pipeline (`rag_lib.py`'s HW3 section + `retrieval_improved.py`) — filter/BM25/RRF tuning values
  and their rationale live there.
- `data/raw/` → `scripts/prepare_knowledge_base.py` → `data/processed/chunks.jsonl` →
  `scripts/build_index.py` → `index/chroma/` (+ `manifest.json`) → `scripts/retrieval.py` /
  `scripts/run_test_queries.py` / `scripts/retrieval_improved.py` (HW3: filtered + hybrid search,
  `--compare` baseline-vs-improved) → `outputs/`.
- `scripts/rag_lib.py` — shared library: typed settings, embeddings, index handle, plus the HW3
  layer (`infer_document_type`, `Bm25Index`, `rrf_fuse`, `search_improved`). Scripts import it
  as a sibling (`from rag_lib import …`); `notebooks/retrieval.ipynb` is a thin front-end over it.
- `tests/` — offline pytest suite; `scripts/` is not a package (tests insert it into `sys.path`).

## Commands

Run everything **from the repo root** — `rag_lib` paths are repo-anchored but
`prepare_knowledge_base.py` defaults are cwd-relative, so the root is the only safe working directory.
The project venv is `.venv/`: activate it (`source .venv/bin/activate`) or call `.venv/bin/python` —
the system interpreter has neither pytest nor chromadb, and a "module not found" there is an
unactivated environment, not a broken suite.

```bash
python scripts/prepare_knowledge_base.py    # build KB — stdlib only, defaults are the tuned 800/150/500
python scripts/build_index.py               # embed + index — needs OPENAI_API_KEY (env or gitignored .env)
python scripts/retrieval.py --query "..." --k 3   # search; also --interactive / --json
python scripts/retrieval_improved.py --query "..." --k 3   # HW3 filtered+hybrid; --document-type / --no-filter / --no-hybrid / --json
python scripts/retrieval_improved.py --compare --k 3       # baseline-vs-improved → outputs/ (two-pass; baseline read-only)
python scripts/run_test_queries.py --k 3    # evaluation → outputs/ (two-pass; see Pitfalls)
python scripts/chunk_size_experiment.py --k 3
python -m pytest -q                         # full suite — offline, no key, no network
```

## Hard invariants — never break these

1. **`scripts/prepare_knowledge_base.py` stays standard-library only** (runs on bare Python ≥ 3.9).
   Never add a third-party import to it; `requirements.txt` packages exist solely for the retrieval
   layer and tests. Prefer a few stdlib lines over a new dependency anywhere (the hand-rolled
   `load_dotenv` exists to avoid python-dotenv).
2. **Graded deliverables are protected.** Files graded by a past homework's spec — each spec's § 3
   deliverables table is the authoritative list, mirrored in README's "How to verify" checklist —
   are never modified or regenerated without explicit user confirmation.
   Never gitignore `data/`, `index/`, or `outputs/`; `.env` and `.claude/settings.local.json` stay
   gitignored. `index/chroma_500/` and `chunks_500.jsonl` are experiment artifacts, not deliverables.
3. **The chunks ↔ index ↔ manifest coupling is load-bearing.** `search()` reads
   `index/<name>/manifest.json` before every query and refuses on a chunks-file digest mismatch or
   an embedding-model mismatch — chunks and queries must be encoded by the same model. Never weaken,
   bypass, or "fix" these checks; the remedy is always a rebuild (`python scripts/build_index.py`).
   The manifest lives **inside** its index directory (a parent-anchored manifest once let the
   experiment index silently overwrite the primary one).
4. **The test suite stays offline.** No test may need `OPENAI_API_KEY` or the network. The OpenAI
   client is faked by duck-typing (`FakeOpenAI` in `tests/test_retrieval.py`, imported from there
   by `test_retrieval_improved.py`) injected through the production `client=` seam — never patch
   the SDK with `unittest.mock`. Chroma always runs with telemetry disabled. `.env` is the only
   key location; a real environment variable always beats it (`load_dotenv` uses `setdefault`),
   and `Settings.openai_api_key` keeps `repr=False` so the key cannot leak into tracebacks or
   `pytest --showlocals`.
5. **`outputs/retrieval_results.json` doubles as the HW3 comparison baseline.**
   `retrieval_improved.py --compare` reads it read-only and refuses on a model/k/query-text
   mismatch or on output paths that would overwrite it. Same family as invariant #3: never weaken
   these guards to make a run succeed — the remedy is a deliberate flag (`--model`, `--k`) or a
   `git checkout` restore.

## Code style — binding, derived from this codebase

- **One env-read point.** Every `os.environ` read routes through `Settings.from_env` in
  `rag_lib.py`. New configuration becomes a `Settings` field with an env override
  (`RAG_EMBEDDING_MODEL`, `RAG_COLLECTION`, `RAG_CONNECT_TIMEOUT`, `RAG_READ_TIMEOUT`,
  `RAG_MAX_RETRIES` are the existing ones) — never a scattered read.
- **Frozen dataclasses for values** (`Settings`, `Chunk`, `SearchHit`, `Config`, `Doc`, `Piece`);
  a mutable dataclass only for accumulators/reports. Pure functions never mutate their inputs.
- **Diagnostic over graceful.** Every stop-the-run failure raises the module's domain error
  (`RetrievalError` / `PipelineError` — "never a silent empty result"); when the user can repair the
  state, the message names the exact remedial command. Catches name a specific exception type and
  re-raise as the domain error with `from exc`. No bare `except`, no `except Exception`, no
  fallback returns.
- **Library code raises; entrypoints exit.** Each script: `def main(argv: list[str] | None = None) -> int`,
  one boundary catch printing `error: …` to stderr and returning 1, and
  `if __name__ == "__main__": sys.exit(main())`. Tests call `main([...])` and assert exit codes.
- **Full type hints** on every function (tests included) with `from __future__ import annotations`
  in every file. `pathlib.Path` everywhere (argparse `type=Path`); `os.path` is never used.
  Keyword-only optionals (bare `*`). Explicit `encoding="utf-8"` on every text read/write.
- **Tuning values are UPPER_SNAKE module constants**, single-sourced so dataclass, function, and
  argparse defaults cannot drift apart.
- **Comments explain why** — typically naming the concrete failure the line prevents (leaked key,
  misaligned vectors, overwritten manifest). No what-comments. Script docstrings double as
  `ArgumentParser(description=__doc__)`; open new scripts' docstrings with the invocation command
  line (the retrieval-layer scripts all do).
- **Chroma discipline:** collections are created and opened with `embedding_function=None` and
  explicit vectors (never Chroma's default embedder), `anonymized_telemetry=False` always, and the
  score unit is `1 - cosine_distance`, converted once at the search boundary. HW3's fused results
  keep the rank-based `rrf_score` in its own `HybridHit` field — RRF and cosine units are never
  mixed or compared.
- **Suppressions are narrow** (`# type: ignore[arg-type]`, `# noqa: E402`) and carry an adjacent
  justification when in production code.
- These scripts are CLI tools: progress to stdout, diagnostics to stderr via `print` — the
  `logging` module is not used in this repo.

## Testing

- pytest with class-per-behavior grouping and sentence-style names stating the invariant
  (`test_missing_api_key_is_a_diagnostic_error`). Plain `assert`, with a message when the invariant
  is subtle; `pytest.raises(match=...)` on every error path (tests pin the remedial-message text);
  `@pytest.mark.parametrize` for verdict matrices.
- Deterministic fake embeddings (bag-of-characters) make ranking meaningful offline.
- Artifacts that replace a previous good file are written to a candidate path, validated, then
  promoted atomically (`os.replace`) — a validation failure must never destroy the existing output.

## Verification gate — before claiming any work done

1. Full test suite green: `python -m pytest -q` (offline).
2. Spec check: the relevant `docs/tasks/` spec is the arbiter — confirm the change matches it, and
   update tests/code toward the spec, never the reverse.
3. If a graded deliverable was touched: re-run the README "How to verify" checklist commands and
   confirm the outputs still match what the README documents.

## Git

- Descriptive imperative commit subjects ("Add …", "Fix …") — never bare "changes".
  Committing directly to `main` is fine; keep each homework a coherent set of commits.
- Never commit `.env` or incidental Chroma binary churn.

## Pitfalls

- **A homework's scope ends where its spec ends.** HW3's spec asked for — and built — metadata
  filtering and hybrid BM25/RRF (the per-homework scoping rule working as intended: HW2 had
  deliberately excluded them). Still deliberately absent after HW3: score threshold, LLM query
  rewriting/classification, cross-encoder reranking, answer generation, and a persisted BM25 index
  (`docs/homework3/retrieval-improvements-spec.md` § "What is deliberately not built") — do not add
  them unprompted; a future homework's spec asking for one wins.
- **Opening the index dirties git.** Any Chroma read may touch binary bookkeeping files under
  `index/` without changing content — `git checkout -- index/` restores a clean tree; never commit
  that churn as a real change.
- **Editing `chunks.jsonl` breaks retrieval by design** (digest refusal) until
  `python scripts/build_index.py` rebuilds — and that costs an OpenAI re-embedding run; confirm
  before triggering it.
- **Evaluation comments are authored by hand.** `run_test_queries.py` is two-pass: run, read the
  real output, write each relevance comment into `data/eval/test_queries.json`, run again. Never
  pre-write or placeholder a comment — the design doc calls this the one way to lose rubric points.
  The same discipline covers HW3: `hw3_comment` per query and the top-level `hw3_conclusion` in
  `test_queries.json` are authored after a real `retrieval_improved.py --compare` run (the script
  reports which are still empty instead of rendering placeholders).
- **The chunk-size experiment needs per-config chunks files** — pointing a variant index at the
  baseline's chunks file always looks stale.
- The assignment recommends `k` between 3 and 5; committed evaluations (HW2 and the HW3
  comparison) use `--k 3` — `--compare` refuses a `k` that differs from the baseline's.
- **Counts embedded in docs go stale silently.** The README states test counts (currently 126 =
  74 HW1-2 + 52 HW3) and headline metrics; any change that adds tests or re-runs the evaluation
  must re-verify those numbers LAST, after the final code change — the README's own checklist
  commands are the arbiter.
- Versions: read `requirements.txt` directly (openai 2.x, chromadb 1.x, pytest 9.x — exact pins
  live there, comments explain scope). `jsonschema` is deliberately excluded — install ad hoc only
  for schema re-validation.
