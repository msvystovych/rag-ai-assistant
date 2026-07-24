#!/usr/bin/env python3
"""Improved retrieval (Homework #3): document_type metadata filter + hybrid BM25/RRF search.

  python scripts/retrieval_improved.py --query "How do we release code without interruption?" --k 3
  python scripts/retrieval_improved.py --query "..." --document-type playbook --no-hybrid
  python scripts/retrieval_improved.py --compare --k 3

Query mode prints the improved pipeline's hits (filter inferred from the query unless
--document-type or --no-filter says otherwise). Compare mode runs the committed evaluation
queries through three configurations (filter-only, hybrid-only, combined), reads the committed
Homework #2 baseline read-only, and renders outputs/retrieval_comparison.md plus
outputs/retrieval_results_improved.json.

Two-pass by design, like run_test_queries.py: the first pass writes mechanical results; the
per-query `hw3_comment` ("what changed") and the top-level `hw3_conclusion` are then authored by
hand into data/eval/test_queries.json from real output, and the second pass renders them. Missing
ones are reported, never rendered as placeholders.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from rag_lib import (
    REPO_ROOT,
    Bm25Index,
    HybridHit,
    RetrievalError,
    Settings,
    infer_document_type,
    load_chunks,
    open_collection,
    search_improved,
)
from run_test_queries import DEFAULT_QUERIES, load_queries, verdict

DEFAULT_BASELINE = REPO_ROOT / "outputs" / "retrieval_results.json"
DEFAULT_COMPARISON = REPO_ROOT / "outputs" / "retrieval_comparison.md"
DEFAULT_IMPROVED_RESULTS = REPO_ROOT / "outputs" / "retrieval_results_improved.json"
DESIGN_DOC = "docs/homework3/retrieval-improvements-spec.md"

# The three improved configurations measured against the Homework #2 baseline. Keeping the
# ablations (filter-only, hybrid-only) alongside the combined pipeline is what lets the
# conclusion say WHICH technique produced the effect instead of guessing.
CONFIGS: tuple[tuple[str, bool, bool], ...] = (
    ("filter-only", True, False),
    ("hybrid-only", False, True),
    ("combined", True, True),
)


class _CachingEmbeddings:
    def __init__(
        self, inner: Any, cache: dict[tuple[str, tuple[str, ...]], Any]
    ) -> None:
        self._inner = inner
        self._cache = cache

    def create(self, *, model: str, input: list[str]) -> Any:
        key = (model, tuple(input))
        if key not in self._cache:
            self._cache[key] = self._inner.create(model=model, input=input)
        return self._cache[key]


class CachingClient:
    """Memoizes embeddings.create so the three configurations share ONE embedding per query.

    Reusing the identical vector is what makes the ablations comparable: any ranking difference
    between configurations is then attributable to the filter or the fusion, never to embedding
    nondeterminism. Uses the same duck-typed seam the tests use (client=), so it wraps either a
    real OpenAI client or a fake.
    """

    def __init__(self, inner: Any) -> None:
        self._cache: dict[tuple[str, tuple[str, ...]], Any] = {}
        self.embeddings = _CachingEmbeddings(inner.embeddings, self._cache)


def format_hit(hit: HybridHit, *, preview_width: int = 220) -> str:
    if hit.rrf_score is None:
        scores = (
            f"score: {hit.semantic_score:.3f}" if hit.semantic_score is not None else ""
        )
    else:
        semantic = (
            f"semantic: {hit.semantic_score:.3f} (#{hit.semantic_rank})"
            if hit.semantic_score is not None
            else "semantic: —"
        )
        bm25 = f"bm25: #{hit.bm25_rank}" if hit.bm25_rank is not None else "bm25: —"
        scores = f"rrf: {hit.rrf_score:.4f} | {semantic} | {bm25}"
    metadata = hit.metadata
    lines = [
        f"Top-{hit.rank}: {hit.chunk_id} | {scores}",
        f"  Text: {hit.preview(preview_width)}",
        f"  Source: {metadata.get('source_file', '?')}",
        f"  Document: {metadata.get('document_id', '?')} | Section: {metadata.get('section', '?')}"
        f" | Type: {metadata.get('document_type', '?')}",
    ]
    return "\n".join(lines)


def describe_filter(document_type: str | None, *, source: str) -> str:
    if document_type is None:
        reason = "disabled" if source == "disabled" else "no rule matched"
        return f"Filter: none ({reason})"
    return f"Filter: document_type={document_type} ({source})"


def run_query(
    settings: Settings,
    query: str,
    k: int,
    *,
    document_type: str | None,
    filter_source: str,
    hybrid: bool,
    as_json: bool,
    preview_width: int,
) -> int:
    collection = open_collection(settings)
    hits = search_improved(
        query,
        settings,
        k=k,
        collection=collection,
        document_type=document_type,
        hybrid=hybrid,
    )
    if as_json:
        print(
            json.dumps(
                {
                    "query": query,
                    "document_type": document_type,
                    "filter_source": filter_source,
                    "hybrid": hybrid,
                    "results": [
                        {
                            "rank": hit.rank,
                            "chunk_id": hit.chunk_id,
                            "rrf_score": hit.rrf_score,
                            "semantic_score": hit.semantic_score,
                            "semantic_rank": hit.semantic_rank,
                            "bm25_rank": hit.bm25_rank,
                            "text": hit.text,
                            "metadata": hit.metadata,
                        }
                        for hit in hits
                    ],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    blocks = [
        f"Query: {query}",
        describe_filter(document_type, source=filter_source),
        "",
    ]
    if not hits:
        blocks.append("(no results)")
    for hit in hits:
        blocks.append(format_hit(hit, preview_width=preview_width))
        blocks.append("")
    print("\n".join(blocks).rstrip())
    return 0


def load_baseline(path: Path, settings: Settings, k: int) -> dict[str, dict[str, Any]]:
    """The committed Homework #2 results, read-only, keyed by query id."""
    if not path.is_file():
        raise RetrievalError(
            f"{path} not found — it is the committed Homework #2 baseline. Restore it:\n"
            "  git checkout -- outputs/retrieval_results.json"
        )
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RetrievalError(
            f"{path}: invalid JSON ({exc.msg}). Restore the committed baseline:\n"
            "  git checkout -- outputs/retrieval_results.json"
        ) from exc
    if not isinstance(payload, dict):
        raise RetrievalError(
            f"{path}: expected a JSON object, got {type(payload).__name__}"
        )
    records = payload.get("records")
    if not isinstance(records, list) or not records:
        raise RetrievalError(f"{path}: expected a non-empty top-level 'records' list")
    baseline_model = payload.get("model")
    if baseline_model != settings.embedding_model:
        raise RetrievalError(
            f"baseline {path} was produced with model {baseline_model!r} but this run would use "
            f"{settings.embedding_model!r} — the comparison would be apples to oranges. "
            "Pass --model to match the baseline."
        )
    baseline_k = payload.get("k")
    if baseline_k != k:
        raise RetrievalError(
            f"baseline {path} was produced with k={baseline_k!r} but this run uses k={k} — "
            f"re-run with --k {baseline_k} so both sides rank the same depth."
        )
    by_id: dict[str, dict[str, Any]] = {}
    for record in records:
        if not isinstance(record, dict) or "id" not in record or "hits" not in record:
            raise RetrievalError(f"{path}: every baseline record needs 'id' and 'hits'")
        by_id[record["id"]] = record
    return by_id


def _doc_ids(hits: list[Any]) -> list[str]:
    ids: list[str] = []
    for hit in hits:
        if isinstance(hit, dict):
            ids.append(hit.get("document_id", ""))
        else:
            ids.append(hit.metadata.get("document_id", ""))
    return ids


def top1_hit(hits: list[Any], expected: list[str]) -> bool | None:
    """True/False for in-corpus queries; None when the query has no expected documents."""
    if not expected:
        return None
    ids = _doc_ids(hits)
    return bool(ids) and ids[0] in expected


def top3_precision(hits: list[Any], expected: list[str]) -> float | None:
    """Fraction of the returned top-3 slots that come from an expected document."""
    if not expected:
        return None
    top = _doc_ids(hits)[:3]
    if not top:
        return 0.0
    return sum(1 for document_id in top if document_id in expected) / len(top)


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def aggregate(rows: list[tuple[bool | None, float | None]]) -> tuple[float, float, int]:
    """(top-1 hit rate, mean top-3 precision, n) over the in-corpus queries."""
    hit_flags = [flag for flag, _ in rows if flag is not None]
    precisions = [precision for _, precision in rows if precision is not None]
    hit_rate = _mean([1.0 if flag else 0.0 for flag in hit_flags])
    return hit_rate, _mean(precisions), len(hit_flags)


def render_comparison(
    records: list[dict[str, Any]],
    aggregates: dict[str, tuple[float, float, int]],
    *,
    k: int,
    model: str,
    conclusion: str,
) -> str:
    lines = [
        "# Retrieval comparison — Homework #3",
        "",
        f"Generated by `scripts/retrieval_improved.py --compare --k {k}`.",
        f"Embedding model: `{model}` — identical to the baseline; every configuration reuses the",
        "same query embedding, so ranking differences are attributable to the filter and the",
        "fusion, never to embedding drift.",
        "",
        "Baseline: the committed Homework #2 results (`outputs/retrieval_results.json`, semantic",
        "top-k only, no filter). Improved: rule-based `document_type` metadata filtering applied",
        "to both branches, plus hybrid search — semantic ranking fused with a standard-library",
        f"BM25 ranking via Reciprocal Rank Fusion. Method details: [`{DESIGN_DOC}`](../{DESIGN_DOC}).",
        "",
        "## Baseline vs improved (combined configuration), top-1 per query",
        "",
        "| # | Query | Filter (inferred) | Baseline top-1 | Improved top-1 | What changed |",
        "|---|---|---|---|---|---|",
    ]
    for record in records:
        inferred = record["inferred_document_type"] or "—"
        baseline_top = record["baseline_top1"] or "—"
        improved_hits = record["configs"]["combined"]["hits"]
        improved_top = improved_hits[0]["chunk_id"] if improved_hits else "—"
        comment = record["hw3_comment"]
        lines.append(
            f"| {record['id']} | {record['query']} | {inferred} | `{baseline_top}` "
            f"| `{improved_top}` | {comment} |"
        )
    lines.extend(
        [
            "",
            "## Aggregate metrics (in-corpus queries)",
            "",
            "Top-3 precision = fraction of returned top-3 slots that come from an expected",
            "document. The baseline already resolves every in-corpus query to the right document",
            "at top-1, so precision within the top-3 — not the top-1 hit rate — is where",
            "improvement is measurable.",
            "",
            "| Configuration | Top-1 hit rate | Top-3 expected-doc precision | n |",
            "|---|---|---|---|",
        ]
    )
    for name in ("baseline", "filter-only", "hybrid-only", "combined"):
        hit_rate, precision, count = aggregates[name]
        lines.append(f"| {name} | {hit_rate:.2f} | {precision:.3f} | {count} |")
    lines.extend(
        [
            "",
            "## Per-query detail (baseline vs combined)",
            "",
        ]
    )
    for record in records:
        lines.append(f"### {record['id']} · {record['category']}")
        lines.append("")
        lines.append(f"Query: {record['query']}")
        lines.append(
            describe_filter(
                record["inferred_document_type"],
                source="inferred" if record["inferred_document_type"] else "auto",
            )
        )
        lines.append("")
        lines.append("| Rank | Baseline | Improved (combined) |")
        lines.append("|---|---|---|")
        baseline_hits = record["baseline_hits"]
        improved_hits = record["configs"]["combined"]["hits"]
        for position in range(max(len(baseline_hits), len(improved_hits))):
            baseline_cell = "—"
            if position < len(baseline_hits):
                hit = baseline_hits[position]
                baseline_cell = f"`{hit['chunk_id']}` ({hit['score']:.3f})"
            improved_cell = "—"
            if position < len(improved_hits):
                hit = improved_hits[position]
                semantic = (
                    f"{hit['semantic_score']:.3f}"
                    if hit["semantic_score"] is not None
                    else "bm25-only"
                )
                improved_cell = f"`{hit['chunk_id']}` ({semantic})"
            lines.append(f"| {position + 1} | {baseline_cell} | {improved_cell} |")
        lines.append("")
        lines.append(f"Verdict (combined): {record['configs']['combined']['verdict']}")
        lines.append("")
    lines.extend(["## Conclusion — what gave the biggest effect", "", conclusion, ""])
    return "\n".join(lines)


def run_compare(
    settings: Settings,
    queries_path: Path,
    baseline_path: Path,
    output_path: Path,
    results_path: Path,
    k: int,
    *,
    client: Any | None = None,
) -> int:
    # The baseline is a graded, read-only Homework #2 artifact — refuse any output routing that
    # would overwrite it (or collapse the two generated artifacts into one file) before touching
    # anything on disk.
    resolved_baseline = baseline_path.resolve()
    for label, path in (("--output", output_path), ("--results", results_path)):
        if path.resolve() == resolved_baseline:
            raise RetrievalError(
                f"{label} points at the baseline file {baseline_path} — refusing to overwrite "
                "the committed Homework #2 baseline. Choose a different output path."
            )
    if output_path.resolve() == results_path.resolve():
        raise RetrievalError(
            "--output and --results point at the same file — the Markdown comparison would "
            "overwrite the JSON results. Choose distinct paths."
        )
    queries = load_queries(queries_path)
    payload = json.loads(queries_path.read_text(encoding="utf-8"))
    conclusion = str(payload.get("hw3_conclusion", "")).strip()
    baseline = load_baseline(baseline_path, settings, k)
    missing_baseline = [entry["id"] for entry in queries if entry["id"] not in baseline]
    if missing_baseline:
        raise RetrievalError(
            f"baseline {baseline_path} has no record for: {', '.join(missing_baseline)} — "
            "baseline and improved runs must cover the same queries."
        )
    # The assignment's premise is "the SAME queries as Homework #2" — a baseline record whose
    # recorded query text differs from the eval entry would silently compare different questions.
    mismatched = [
        entry["id"]
        for entry in queries
        if "query" in baseline[entry["id"]]
        and baseline[entry["id"]]["query"] != entry["query"]
    ]
    if mismatched:
        raise RetrievalError(
            f"query text differs from the baseline's recorded query for: {', '.join(mismatched)} "
            "— baseline and improved runs must ask the same questions. Restore the queries file "
            "or regenerate the baseline deliberately."
        )
    collection = open_collection(settings)
    bm25 = Bm25Index(load_chunks(settings.chunks_path))
    # `client=` is the same duck-typed injection seam as rag_lib.embed_texts — tests pass a fake.
    caching = CachingClient(client if client is not None else _real_client(settings))

    records: list[dict[str, Any]] = []
    per_config_rows: dict[str, list[tuple[bool | None, float | None]]] = {
        name: [] for name, _, _ in CONFIGS
    }
    baseline_rows: list[tuple[bool | None, float | None]] = []

    for entry in queries:
        expected = entry.get("expected_documents", [])
        inferred = infer_document_type(entry["query"])
        baseline_record = baseline[entry["id"]]
        baseline_hits = baseline_record["hits"]
        baseline_rows.append(
            (top1_hit(baseline_hits, expected), top3_precision(baseline_hits, expected))
        )
        record: dict[str, Any] = {
            "id": entry["id"],
            "category": entry["category"],
            "query": entry["query"],
            "expected_documents": expected,
            "inferred_document_type": inferred,
            "hw3_comment": entry.get("hw3_comment", "").strip(),
            "baseline_top1": baseline_hits[0]["chunk_id"] if baseline_hits else None,
            "baseline_hits": baseline_hits,
            "configs": {},
        }
        for name, filtered, hybrid in CONFIGS:
            document_type = inferred if filtered else None
            hits = search_improved(
                entry["query"],
                settings,
                k=k,
                client=caching,
                collection=collection,
                bm25=bm25,
                document_type=document_type,
                hybrid=hybrid,
            )
            per_config_rows[name].append(
                (top1_hit(hits, expected), top3_precision(hits, expected))
            )
            record["configs"][name] = {
                "document_type": document_type,
                "hybrid": hybrid,
                "verdict": verdict(hits, expected),
                "hits": [
                    {
                        "rank": hit.rank,
                        "chunk_id": hit.chunk_id,
                        "rrf_score": hit.rrf_score,
                        "semantic_score": hit.semantic_score,
                        "semantic_rank": hit.semantic_rank,
                        "bm25_rank": hit.bm25_rank,
                        "preview": hit.preview(),
                        "source_file": hit.metadata.get("source_file", "?"),
                        "document_id": hit.metadata.get("document_id", "?"),
                        "section": hit.metadata.get("section", "?"),
                    }
                    for hit in hits
                ],
            }
        records.append(record)
        combined_top = record["configs"]["combined"]["hits"]
        top_id = combined_top[0]["chunk_id"] if combined_top else "—"
        changed = "→" if top_id != record["baseline_top1"] else "="
        print(
            f"{entry['id']}  filter={inferred or '—'}  "
            f"baseline {record['baseline_top1']}  {changed}  combined {top_id}"
        )

    aggregates = {"baseline": aggregate(baseline_rows)}
    for name, _, _ in CONFIGS:
        aggregates[name] = aggregate(per_config_rows[name])

    results_path.parent.mkdir(parents=True, exist_ok=True)
    results_path.write_text(
        json.dumps(
            {
                "model": settings.embedding_model,
                "k": k,
                "baseline": str(baseline_path.relative_to(REPO_ROOT))
                if baseline_path.is_relative_to(REPO_ROOT)
                else str(baseline_path),
                "aggregates": {
                    name: {
                        "top1_hit_rate": hit_rate,
                        "top3_precision": precision,
                        "n": count,
                    }
                    for name, (hit_rate, precision, count) in aggregates.items()
                },
                "records": records,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        render_comparison(
            records,
            aggregates,
            k=k,
            model=settings.embedding_model,
            conclusion=conclusion,
        ),
        encoding="utf-8",
    )
    print(f"\nwrote {results_path}")
    print(f"wrote {output_path}")

    missing_comments = [record["id"] for record in records if not record["hw3_comment"]]
    notes = []
    if missing_comments:
        notes.append(
            f"{len(missing_comments)} quer(y/ies) still have an empty hw3_comment: "
            f"{', '.join(missing_comments)}"
        )
    if not conclusion:
        notes.append("hw3_conclusion is still empty")
    if notes:
        print(
            "\nNOTE: " + "; ".join(notes) + f"\n"
            f"Author them in {queries_path} from the real results above, then re-run.",
            file=sys.stderr,
        )
    return 0


def _real_client(settings: Settings) -> Any:
    # Imported lazily from rag_lib's own factory so compare mode builds exactly the client the
    # rest of the pipeline uses (same independent connect/read timeouts, same retry policy).
    from rag_lib import _openai_client

    return _openai_client(settings)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--query", "-q", type=str, default=None)
    parser.add_argument("--compare", action="store_true")
    parser.add_argument(
        "--k",
        type=int,
        default=3,
        help="committed evaluations use 3 (assignment recommends 3-5)",
    )
    parser.add_argument("--document-type", type=str, default=None)
    parser.add_argument("--no-filter", action="store_true")
    parser.add_argument("--no-hybrid", action="store_true")
    parser.add_argument("--queries", type=Path, default=DEFAULT_QUERIES)
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    parser.add_argument("--output", type=Path, default=DEFAULT_COMPARISON)
    parser.add_argument("--results", type=Path, default=DEFAULT_IMPROVED_RESULTS)
    parser.add_argument("--index-dir", type=Path, default=None)
    parser.add_argument("--collection", type=str, default=None)
    parser.add_argument("--model", type=str, default=None)
    parser.add_argument("--json", dest="as_json", action="store_true")
    parser.add_argument("--preview-width", type=int, default=220)
    args = parser.parse_args(argv)

    if bool(args.query) == args.compare:
        parser.error("provide exactly one of --query TEXT or --compare")
    if args.k < 1:
        parser.error(f"--k must be a positive integer, got {args.k}")
    if args.compare and (
        args.document_type is not None
        or args.no_filter
        or args.no_hybrid
        or args.as_json
    ):
        parser.error(
            "--compare always runs the filter-only/hybrid-only/combined configurations; "
            "--document-type/--no-filter/--no-hybrid/--json apply to --query mode only"
        )
    if args.document_type is not None and args.no_filter:
        parser.error("--document-type and --no-filter are mutually exclusive")

    try:
        settings = Settings.from_env(
            index_dir=args.index_dir,
            collection_name=args.collection,
            embedding_model=args.model,
        )
        if args.compare:
            return run_compare(
                settings, args.queries, args.baseline, args.output, args.results, args.k
            )
        if args.no_filter:
            document_type, filter_source = None, "disabled"
        elif args.document_type is not None:
            # `is not None`, not truthiness: an explicit empty string must reach
            # search_improved's unknown-type diagnostic, never silently re-enable inference.
            document_type, filter_source = args.document_type, "explicit"
        else:
            document_type, filter_source = infer_document_type(args.query), "inferred"
        return run_query(
            settings,
            args.query,
            args.k,
            document_type=document_type,
            filter_source=filter_source,
            hybrid=not args.no_hybrid,
            as_json=args.as_json,
            preview_width=args.preview_width,
        )
    except RetrievalError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
