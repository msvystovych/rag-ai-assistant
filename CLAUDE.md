# CLAUDE.md — rag-ai-assistant

This repo is a graded homework series. It builds a RAG system step by step:

- HW1: knowledge-base preparation.
- HW2: semantic retrieval.
- HW3: retrieval improvements — `document_type` metadata filtering + hybrid BM25/RRF.
- HW4: grounded answer generation — prompt versions, a relevance floor and cited answers.
- HW5: external tool integration — a model-routed tool-calling turn over a mock operations API,
  with a validation boundary and an operator confirmation gate.

Further homeworks will extend this repo. The assignment specs in `docs/tasks/` (Ukrainian) are the
**arbiter for every graded behavior**. On any conflict between code, tests, README, and spec, the
spec wins. The repo-root `README.md` is itself a graded deliverable. It carries a per-homework,
per-rubric verification checklist.

## Repository map

The layout repeats per homework — follow the same pattern when a new homework starts:

- `docs/tasks/` — assignment specs. The filenames have no extension and contain spaces. Links to
  them must percent-encode the spaces.
- `docs/homeworkN/` — that homework's design docs and analysis. Read the owning design doc before
  you change its code:
  - `docs/homework1/pipeline-spec.md` owns every chunking rule (`prepare_knowledge_base.py`).
  - `docs/homework2/retrieval-spec.md` records the retrieval-layer decisions (`rag_lib.py`).
  - `docs/homework3/retrieval-improvements-spec.md` owns the improved pipeline (`rag_lib.py`'s HW3
    section + `retrieval_improved.py`). The filter/BM25/RRF tuning values and their rationale live
    there.
  - `docs/homework4/generation-spec.md` owns the answer layer (`rag_answer.py` +
    `Settings.answer_model`). The prompt versions, the 0.35 relevance floor, the citation contract
    and their known limits live there.
  - `docs/homework5/tool-integration-spec.md` owns the tool layer (`external_tool.py` +
    `data/external/loads.json`). The tool contract, the validation boundary, the confirmation gate
    and the bounded orchestration loop live there.
- The pipeline chain: `data/raw/` → `scripts/prepare_knowledge_base.py` →
  `data/processed/chunks.jsonl` → `scripts/build_index.py` → `index/chroma/` (+ `manifest.json`) →
  one of the downstream scripts → `outputs/`. The downstream scripts:
  - `scripts/retrieval.py` and `scripts/run_test_queries.py`.
  - `scripts/retrieval_improved.py` — HW3: filtered + hybrid search. `--compare` runs
    baseline-vs-improved.
  - `scripts/rag_answer.py` — HW4: prompt + LLM over the HW3 pipeline. Flags: `--evaluate` /
    `--improvements`.
  - `scripts/external_tool.py` — HW5: tool calling over `data/external/loads.json`. It falls
    through to HW4 when the model asks for no tool. Flags: `--examples` / `--list-tools`.
- `scripts/rag_lib.py` — the shared library: typed settings, embeddings, index handle, and the HW3
  layer (`infer_document_type`, `Bm25Index`, `rrf_fuse`, `search_improved`). Scripts import it as a
  sibling (`from rag_lib import …`). `notebooks/retrieval.ipynb` is a thin front-end over it.
  - HW4 added exactly one field here (`Settings.answer_model`). All generation logic lives in
    `rag_answer.py`.
  - HW5 added nothing here and changed no HW1–HW4 file. `external_tool.py` is self-contained, and
    it imports `rag_answer.answer_question` read-only for its fallback branch.
- `tests/` — the offline pytest suite. `scripts/` is not a package (the tests insert it into
  `sys.path`).

## Commands

Run everything **from the repo root**. `rag_lib` paths are repo-anchored, but the
`prepare_knowledge_base.py` defaults are cwd-relative. The root is thus the only safe working
directory.

The project venv is `.venv/`. Activate it (`source .venv/bin/activate`) or call `.venv/bin/python`.
The system interpreter has neither pytest nor chromadb, so a "module not found" there means an
unactivated environment, not a broken suite.

```bash
python scripts/prepare_knowledge_base.py    # build KB — stdlib only, defaults are the tuned 800/150/500
python scripts/build_index.py               # embed + index — needs OPENAI_API_KEY (env or gitignored .env)
python scripts/retrieval.py --query "..." --k 3   # search; also --interactive / --json
python scripts/retrieval_improved.py --query "..." --k 3   # HW3 filtered+hybrid; --document-type / --no-filter / --no-hybrid / --json
python scripts/retrieval_improved.py --compare --k 3       # baseline-vs-improved → outputs/ (two-pass; baseline read-only)
python scripts/rag_answer.py --query "..." --k 3            # HW4 grounded answer; --json / --prompt-version / --min-score / --no-min-score
python scripts/rag_answer.py --evaluate --k 3               # 10 grounded answers → outputs/ (two-pass)
python scripts/rag_answer.py --improvements                 # 3 prompt before/after cases → outputs/ (two-pass)
python scripts/external_tool.py --list-tools                # HW5 tool contract — offline, no key
python scripts/external_tool.py --question "..."            # model routes: tool or HW4 fallback; --confirm / --json
python scripts/external_tool.py --examples                  # 5 tool scenarios → outputs/ (two-pass)
python scripts/run_test_queries.py --k 3    # evaluation → outputs/ (two-pass; see Pitfalls)
python scripts/chunk_size_experiment.py --k 3
python -m pytest -q                         # full suite — offline, no key, no network
```

## Hard invariants — never break these

1. **`scripts/prepare_knowledge_base.py` stays standard-library only** (it runs on bare
   Python ≥ 3.9). Never add a third-party import to it. The `requirements.txt` packages exist solely
   for the retrieval layer and the tests. Prefer a few stdlib lines over a new dependency anywhere.
   The hand-rolled `load_dotenv` exists to avoid python-dotenv.
2. **Protect every graded deliverable.** Never modify or regenerate a file that a past homework's
   spec grades, unless the user explicitly confirms it. Each spec's § 3 deliverables table is the
   authoritative list. README's "How to verify" checklist mirrors that list.
   Never gitignore `data/`, `index/`, or `outputs/`; `.env` and `.claude/settings.local.json` stay
   gitignored. `index/chroma_500/` and `chunks_500.jsonl` are experiment artifacts, not deliverables.
3. **The chunks ↔ index ↔ manifest coupling is load-bearing.** `search()` reads
   `index/<name>/manifest.json` before every query, and refuses on a chunks-file digest mismatch or
   an embedding-model mismatch. One model must encode both the chunks and the queries. Never
   weaken, bypass, or "fix" these checks; the remedy is always a rebuild
   (`python scripts/build_index.py`). The manifest lives **inside** its index directory. A
   parent-anchored manifest once let the experiment index silently overwrite the primary one.
4. **The test suite stays offline.** No test may need `OPENAI_API_KEY` or the network. Chroma always
   runs with telemetry disabled.
   - Never patch the SDK with `unittest.mock`. Duck-typing fakes the OpenAI client instead:
     `tests/test_retrieval.py` defines `FakeOpenAI`, and `test_retrieval_improved.py` imports it
     from there. The tests inject that fake through the production `client=` seam.
   - `.env` is the only key location. A real environment variable always beats it (`load_dotenv`
     uses `setdefault`). `Settings.openai_api_key` keeps `repr=False`, so the key cannot leak into
     tracebacks or `pytest --showlocals`.
5. **`outputs/retrieval_results.json` doubles as the HW3 comparison baseline.** Never weaken these
   guards to make a run succeed — same family as invariant #3. The remedy is a deliberate flag
   (`--model`, `--k`) or a `git checkout` restore. `retrieval_improved.py --compare` reads the
   baseline read-only. It refuses on a model/k/query-text mismatch, and on output paths that would
   overwrite it.

## Code style — binding, derived from this codebase

- **One env-read point.** Every `os.environ` read routes through `Settings.from_env` in
  `rag_lib.py`. New configuration becomes a `Settings` field with an env override — never a
  scattered read. The existing overrides: `RAG_EMBEDDING_MODEL`, `RAG_COLLECTION`,
  `RAG_CONNECT_TIMEOUT`, `RAG_READ_TIMEOUT`, `RAG_MAX_RETRIES`.
- **Frozen dataclasses for values** (`Settings`, `Chunk`, `SearchHit`, `Config`, `Doc`, `Piece`).
  Use a mutable dataclass only for accumulators and reports. Pure functions never mutate their
  inputs.
- **Diagnostic over graceful.** No bare `except`, no `except Exception`, no fallback returns. Every
  stop-the-run failure raises the module's domain error (`RetrievalError` / `PipelineError` —
  "never a silent empty result"). When the user can repair the state, the message names the exact
  remedial command. Catches name a specific exception type, and re-raise as the domain error with
  `from exc`.
- **Library code raises; entrypoints exit.** Each script: `def main(argv: list[str] | None = None) -> int`,
  one boundary catch printing `error: …` to stderr and returning 1, and
  `if __name__ == "__main__": sys.exit(main())`. Tests call `main([...])` and assert exit codes.
- **Full type hints** on every function (tests included), with `from __future__ import annotations`
  in every file. Use `pathlib.Path` everywhere (argparse `type=Path`); never use `os.path`.
  Keyword-only optionals (bare `*`). Put an explicit `encoding="utf-8"` on every text read/write.
- **Tuning values are UPPER_SNAKE module constants.** One source holds each value, so the dataclass,
  function, and argparse defaults cannot drift apart.
- **Comments explain why.** A comment typically names the concrete failure that the line prevents
  (leaked key, misaligned vectors, overwritten manifest). No what-comments. Script docstrings double
  as `ArgumentParser(description=__doc__)`. Open a new script's docstring with the invocation
  command line — the retrieval-layer scripts all do.
- **Chroma discipline.** Create and open every collection with `embedding_function=None` and
  explicit vectors — never Chroma's default embedder. Always pass `anonymized_telemetry=False`. The
  score unit is `1 - cosine_distance`, and the code converts it once at the search boundary. HW3's
  fused results keep the rank-based `rrf_score` in its own `HybridHit` field. Never mix or compare
  RRF and cosine units.
- **Keep suppressions narrow** (`# type: ignore[arg-type]`, `# noqa: E402`). In production code, a
  suppression carries an adjacent justification.
- These scripts are CLI tools. Progress goes to stdout, and diagnostics go to stderr with `print`.
  This repo does not use the `logging` module.

## Testing

- Use pytest with class-per-behavior grouping. A test name is a sentence that states the invariant
  (`test_missing_api_key_is_a_diagnostic_error`). Use a plain `assert`, with a message when the
  invariant is subtle. Use `pytest.raises(match=...)` on every error path — the tests pin the
  remedial-message text. Use `@pytest.mark.parametrize` for verdict matrices.
- Deterministic fake embeddings (bag-of-characters) make ranking meaningful offline.
- A validation failure must never destroy the existing output. An artifact that replaces a previous
  good file goes to a candidate path first. The script validates it, then promotes it atomically
  (`os.replace`).

## Verification gate — before claiming any work done

1. Full test suite green: `python -m pytest -q` (offline).
2. Spec check: the relevant `docs/tasks/` spec is the arbiter. Confirm that the change matches it.
   Update the tests and the code toward the spec, never the reverse.
3. If your change touched a graded deliverable, re-run the README "How to verify" checklist
   commands. Then confirm that the outputs still match what the README documents.

## Git

- Write descriptive imperative commit subjects ("Add …", "Fix …") — never a bare "changes".
  A direct commit to `main` is fine. Keep each homework a coherent set of commits.
- Never commit `.env` or incidental Chroma binary churn.

## Pitfalls

- **A homework's scope ends where its spec ends.** HW3's spec asked for metadata filtering and
  hybrid BM25/RRF, and HW3 built them. HW2 had deliberately excluded them, so that addition is the
  per-homework scoping rule working as intended. HW4's spec then claimed two of HW3's deferrals:
  answer generation and the score threshold. That is the same carve-out working as designed. These
  items stay deliberately absent after HW4:
  - LLM query rewriting/classification.
  - Cross-encoder reranking.
  - A persisted BM25 index.
  - Multi-turn chat history.
  - Streaming.
  - LLM-as-judge answer scoring.

  `docs/homework3/retrieval-improvements-spec.md` and `docs/homework4/generation-spec.md` list them
  in § "What is deliberately not built". Do not add them unprompted. A future homework's spec that
  asks for one wins.
- **Opening the index dirties git.** Never commit that churn as a real change. Any Chroma read can
  touch binary bookkeeping files under `index/` without a content change. `git checkout -- index/`
  restores a clean tree.
- **Editing `chunks.jsonl` breaks retrieval by design** (digest refusal). Retrieval stays broken
  until `python scripts/build_index.py` rebuilds the index. That rebuild costs an OpenAI
  re-embedding run, so confirm before you trigger it.
- **You write every evaluation comment by hand.** Never pre-write or placeholder a comment — the
  design doc calls this the one way to lose rubric points. `run_test_queries.py` is two-pass: run
  it, read the real output, write each relevance comment into `data/eval/test_queries.json`, then
  run it again. The same discipline covers HW3. Write the per-query `hw3_comment` and the top-level
  `hw3_conclusion` in `test_queries.json` after a real `retrieval_improved.py --compare` run.
  The script reports which entries are still empty instead of rendering placeholders.
- **The chunk-size experiment needs per-config chunks files.** A variant index that points at the
  baseline's chunks file always looks stale.
- The assignment recommends a `k` between 3 and 5. The committed evaluations use `--k 3`: HW2, the
  HW3 comparison and the HW4 answer run. `--compare` refuses a `k` that differs from the baseline's.
- **HW4's evaluation is two-pass like HW2's and HW3's.** Write the per-query `hw4_comment`, the
  top-level `hw4_conclusion` and `hw4_prompt_improvements` in `test_queries.json` by hand after a
  real run. Both `--evaluate` and `--improvements` report which entries are still empty, rather than
  rendering a placeholder. After you edit any of them, re-run to re-render the outputs. Otherwise
  the committed Markdown silently disagrees with its own source.
- **HW5's write tool commits in memory only.** Never "fix" this by persisting, or the committed
  examples stop being reproducible. `book_load` mutates the in-process copy of
  `data/external/loads.json`, and never writes it back. The fixture is a fixed input, so every
  `--examples` run starts from the same state. A test pins the file's digest across a booking.
- **HW5's examples are two-pass like HW2's, HW3's and HW4's.** Write `hw5_scenarios` (per-scenario
  `why_better_than_retrieval` + `comment`) and `hw5_conclusion` in `test_queries.json` by hand after
  a real `--examples` run. The script names every missing entry on stderr. It then refuses to render
  `outputs/tool_examples.md`, rather than emitting a placeholder.
- **A tool `description` is a routing instruction, not documentation.** HW5 measured this. One
  description told the model that the system refuses `book_load` without operator authorisation.
  That description made the model stop calling the tool, and the write path became unreachable and
  ungradeable.
  Tool text that reads as honest documentation can silently disable a code path. Change such text
  only with a real run, to confirm that the routing still happens.
- **Counts embedded in docs go stale silently.** The README states test counts (currently 326 =
  74 HW1-2 + 52 HW3 + 79 HW4 + 121 HW5) and headline metrics. On any change that adds tests or
  re-runs the evaluation, you must re-verify those numbers. Do it LAST, after the final code change.
  The README's own checklist commands are the arbiter.
- Versions: read `requirements.txt` directly (openai 2.x, chromadb 1.x, pytest 9.x). The exact pins
  live there, and comments explain their scope. This repo deliberately excludes `jsonschema`.
  Install it ad hoc only for schema re-validation.
