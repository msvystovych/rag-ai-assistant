#!/usr/bin/env python3
"""Compare retrieval quality between two chunkings of the same corpus.

Closes risk #7 in docs/homework1/reflection.md, which deferred chunk-size tuning to Homework #2:
"800/150 is a best-practice guess; retrieval experiments may show 600-char chunks retrieve more
precisely."

  python scripts/chunk_size_experiment.py --k 3
"""

from __future__ import annotations

import argparse
import statistics
import sys
from pathlib import Path
from typing import Any

from rag_lib import REPO_ROOT, RetrievalError, Settings, open_collection, search
from run_test_queries import load_queries, verdict

DEFAULT_OUTPUT = REPO_ROOT / "outputs" / "chunk_size_experiment.md"


def evaluate(
    settings: Settings, queries: list[dict[str, Any]], k: int
) -> list[dict[str, Any]]:
    collection = open_collection(settings)
    rows: list[dict[str, Any]] = []
    for entry in queries:
        hits = search(entry["query"], settings, k=k, collection=collection)
        expected = entry.get("expected_documents", [])
        rows.append(
            {
                "id": entry["id"],
                "category": entry["category"],
                "top1": hits[0].score if hits else float("nan"),
                "top1_document": hits[0].metadata.get("document_id", "")
                if hits
                else "",
                "top1_section": hits[0].metadata.get("section", "") if hits else "",
                "documents_in_topk": len(
                    {hit.metadata.get("document_id", "") for hit in hits}
                ),
                "sections_in_topk": len(
                    {hit.metadata.get("section", "") for hit in hits}
                ),
                "verdict": verdict(hits, expected),
                "hit": bool(
                    expected
                    and hits
                    and hits[0].metadata.get("document_id", "") in expected
                ),
            }
        )
    return rows


def _count_lines(path: Path) -> int:
    if not path.is_file():
        raise RetrievalError(f"{path} not found")
    return sum(
        1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    )


def summarize(rows: list[dict[str, Any]]) -> dict[str, float]:
    in_corpus = [row for row in rows if row["category"] != "out-of-corpus"]
    out_of_corpus = [row for row in rows if row["category"] == "out-of-corpus"]
    if not in_corpus:
        raise RetrievalError("the query set has no in-corpus queries to summarize")
    return {
        "top1_hit_rate": sum(1 for row in in_corpus if row["hit"]) / len(in_corpus),
        "mean_top1": statistics.mean(row["top1"] for row in in_corpus),
        "min_top1": min(row["top1"] for row in in_corpus),
        "mean_sections": statistics.mean(row["sections_in_topk"] for row in in_corpus),
        "mean_documents": statistics.mean(
            row["documents_in_topk"] for row in in_corpus
        ),
        "out_of_corpus_top1": out_of_corpus[0]["top1"]
        if out_of_corpus
        else float("nan"),
    }


def render(
    baseline: list[dict[str, Any]],
    variant: list[dict[str, Any]],
    *,
    k: int,
    baseline_label: str,
    variant_label: str,
    baseline_chunks: int,
    variant_chunks: int,
) -> str:
    base_summary, variant_summary = summarize(baseline), summarize(variant)
    margin_base = base_summary["min_top1"] - base_summary["out_of_corpus_top1"]
    margin_variant = variant_summary["min_top1"] - variant_summary["out_of_corpus_top1"]

    lines = [
        "# Chunk-size experiment",
        "",
        "`docs/homework1/reflection.md` risk #7 deferred chunk-size tuning to this homework:",
        '*"800/150 is a best-practice guess; retrieval experiments may show 600-char chunks',
        'retrieve more precisely."* This is that experiment.',
        "",
        "The same corpus, the same embedding model, and the same query set — only the chunking",
        f"parameters differ. Both runs use k={k}.",
        "",
        "| | Baseline | Variant |",
        "|---|---|---|",
        f"| Parameters | {baseline_label} | {variant_label} |",
        f"| Chunks produced | {baseline_chunks} | {variant_chunks} |",
        f"| Top-1 hit rate (in-corpus) | {base_summary['top1_hit_rate']:.0%} "
        f"| {variant_summary['top1_hit_rate']:.0%} |",
        f"| Mean top-1 score | {base_summary['mean_top1']:.3f} "
        f"| {variant_summary['mean_top1']:.3f} |",
        f"| Lowest in-corpus top-1 | {base_summary['min_top1']:.3f} "
        f"| {variant_summary['min_top1']:.3f} |",
        f"| Out-of-corpus top-1 | {base_summary['out_of_corpus_top1']:.3f} "
        f"| {variant_summary['out_of_corpus_top1']:.3f} |",
        f"| Separation margin | {margin_base:.3f} | {margin_variant:.3f} |",
        f"| Distinct sections in top-{k} | {base_summary['mean_sections']:.2f} "
        f"| {variant_summary['mean_sections']:.2f} |",
        f"| Distinct documents in top-{k} | {base_summary['mean_documents']:.2f} "
        f"| {variant_summary['mean_documents']:.2f} |",
        "",
        "## Per-query top-1 score",
        "",
        "| Query | Category | Baseline | Variant | Delta |",
        "|---|---|---|---|---|",
    ]
    for base_row, variant_row in zip(baseline, variant, strict=True):
        delta = variant_row["top1"] - base_row["top1"]
        lines.append(
            f"| {base_row['id']} | {base_row['category']} | {base_row['top1']:.3f} "
            f"| {variant_row['top1']:.3f} | {delta:+.3f} |"
        )
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--k", type=int, default=3)
    parser.add_argument(
        "--queries", type=Path, default=REPO_ROOT / "data/eval/test_queries.json"
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--baseline-index", type=Path, default=REPO_ROOT / "index/chroma"
    )
    parser.add_argument("--baseline-collection", type=str, default="logistics_chunks")
    parser.add_argument(
        "--baseline-label", type=str, default="chunk_size 800 / overlap 150"
    )
    parser.add_argument(
        "--variant-index", type=Path, default=REPO_ROOT / "index/chroma_500"
    )
    parser.add_argument(
        "--variant-collection", type=str, default="logistics_chunks_500"
    )
    parser.add_argument(
        "--variant-label", type=str, default="chunk_size 500 / overlap 100"
    )
    parser.add_argument(
        "--baseline-chunks",
        type=Path,
        default=REPO_ROOT / "data/processed/chunks.jsonl",
    )
    parser.add_argument(
        "--variant-chunks",
        type=Path,
        default=REPO_ROOT / "data/processed/chunks_500.jsonl",
    )
    args = parser.parse_args(argv)

    try:
        queries = load_queries(args.queries)
        # Each configuration must carry its own chunks file: the manifest's staleness check
        # compares against settings.chunks_path, so the variant would otherwise be checked
        # against the baseline's chunks.jsonl and always look stale.
        baseline = evaluate(
            Settings.from_env(
                chunks_path=args.baseline_chunks,
                index_dir=args.baseline_index,
                collection_name=args.baseline_collection,
            ),
            queries,
            args.k,
        )
        variant = evaluate(
            Settings.from_env(
                chunks_path=args.variant_chunks,
                index_dir=args.variant_index,
                collection_name=args.variant_collection,
            ),
            queries,
            args.k,
        )
        report = render(
            baseline,
            variant,
            k=args.k,
            baseline_label=args.baseline_label,
            variant_label=args.variant_label,
            baseline_chunks=_count_lines(args.baseline_chunks),
            variant_chunks=_count_lines(args.variant_chunks),
        )
    except RetrievalError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(report, encoding="utf-8")
    print(report)
    print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
