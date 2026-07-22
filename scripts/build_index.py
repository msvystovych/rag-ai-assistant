#!/usr/bin/env python3
"""Embed data/processed/chunks.jsonl and persist the vectors to a Chroma collection.

  python scripts/build_index.py [--chunks ...] [--index-dir ...] [--model ...]

Requires OPENAI_API_KEY in the environment. Writes a manifest.json inside the index directory so
retrieval can detect a stale or model-mismatched index instead of silently returning bad results.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from rag_lib import (
    RetrievalError,
    Settings,
    embed_texts,
    load_chunks,
    open_collection,
    write_manifest,
)


def build(settings: Settings, *, progress: bool = True) -> int:
    chunks = load_chunks(settings.chunks_path)
    print(f"loaded {len(chunks)} chunks from {settings.chunks_path}")
    print(f"embedding with {settings.embedding_model} …")

    vectors = embed_texts([chunk.text for chunk in chunks], settings, progress=progress)
    dimension = len(vectors[0])

    collection = open_collection(settings, create=True)
    collection.add(
        ids=[chunk.chunk_id for chunk in chunks],
        # chromadb's stub over-narrows embeddings to ndarray/invariant-List; a plain
        # list[list[float]] is valid at runtime and is what embed_texts returns.
        embeddings=vectors,  # type: ignore[arg-type]
        documents=[chunk.text for chunk in chunks],
        metadatas=[chunk.metadata for chunk in chunks],
    )

    indexed = collection.count()
    if indexed != len(chunks):
        raise RetrievalError(
            f"collection holds {indexed} vectors but {len(chunks)} were supplied"
        )

    manifest = write_manifest(settings, dimension=dimension, chunk_count=indexed)
    print(
        f"indexed {indexed} vectors of dimension {dimension} into {settings.index_dir}"
    )
    print(f"wrote {manifest}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chunks", type=Path, default=None)
    parser.add_argument("--index-dir", type=Path, default=None)
    parser.add_argument("--collection", type=str, default=None)
    parser.add_argument("--model", type=str, default=None)
    args = parser.parse_args(argv)

    try:
        settings = Settings.from_env(
            chunks_path=args.chunks,
            index_dir=args.index_dir,
            collection_name=args.collection,
            embedding_model=args.model,
        )
        return build(settings)
    except RetrievalError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
