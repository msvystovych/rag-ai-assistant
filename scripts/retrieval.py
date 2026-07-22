#!/usr/bin/env python3
"""Top-k semantic search over the Chroma index built by scripts/build_index.py.

  python scripts/retrieval.py --query "Can a carrier find a return load?" --k 3
  python scripts/retrieval.py --interactive

Prints chunk_id, score, a text preview and the chunk's metadata for each hit.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from rag_lib import RetrievalError, SearchHit, Settings, open_collection, search


def format_hit(hit: SearchHit, *, preview_width: int = 220) -> str:
    metadata = hit.metadata
    lines = [
        f"Top-{hit.rank}: {hit.chunk_id} | score: {hit.score:.3f}",
        f"  Text: {hit.preview(preview_width)}",
        f"  Source: {metadata.get('source_file', '?')}",
        f"  Document: {metadata.get('document_id', '?')} | Section: {metadata.get('section', '?')}"
        f" | Type: {metadata.get('document_type', '?')}",
    ]
    return "\n".join(lines)


def render(query: str, hits: list[SearchHit], *, preview_width: int = 220) -> str:
    blocks = [f"Query: {query}", ""]
    if not hits:
        blocks.append("(no results)")
    for hit in hits:
        blocks.append(format_hit(hit, preview_width=preview_width))
        blocks.append("")
    return "\n".join(blocks).rstrip()


def run(
    settings: Settings, query: str, k: int, *, as_json: bool, preview_width: int
) -> int:
    collection = open_collection(settings)
    hits = search(query, settings, k=k, collection=collection)
    if as_json:
        print(
            json.dumps(
                {
                    "query": query,
                    "results": [
                        {
                            "rank": hit.rank,
                            "chunk_id": hit.chunk_id,
                            "score": round(hit.score, 4),
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
    else:
        print(render(query, hits, preview_width=preview_width))
    return 0


def interactive(settings: Settings, k: int, preview_width: int) -> int:
    collection = open_collection(settings)
    print("Semantic search — blank line, Ctrl-D or Ctrl-C to exit.")
    while True:
        try:
            query = input("\nquery> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if not query:
            return 0
        hits = search(query, settings, k=k, collection=collection)
        print()
        print(render(query, hits, preview_width=preview_width))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--query", "-q", type=str, default=None)
    parser.add_argument("--k", type=int, default=5, help="number of chunks to retrieve")
    parser.add_argument("--index-dir", type=Path, default=None)
    parser.add_argument("--collection", type=str, default=None)
    parser.add_argument("--model", type=str, default=None)
    parser.add_argument("--json", dest="as_json", action="store_true")
    parser.add_argument("--preview-width", type=int, default=220)
    parser.add_argument("--interactive", "-i", action="store_true")
    args = parser.parse_args(argv)

    if not args.interactive and not args.query:
        parser.error("provide --query TEXT or --interactive")

    try:
        settings = Settings.from_env(
            index_dir=args.index_dir,
            collection_name=args.collection,
            embedding_model=args.model,
        )
        if args.interactive:
            return interactive(settings, args.k, args.preview_width)
        return run(
            settings,
            args.query,
            args.k,
            as_json=args.as_json,
            preview_width=args.preview_width,
        )
    except RetrievalError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
