"""Shared building blocks for the Homework #2 semantic retrieval layer.

Owns three things so nothing downstream re-derives them: the typed settings object (the single
place any environment variable is read), the OpenAI embedding call, and the Chroma index handle.
See docs/homework2/retrieval-spec.md.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import chromadb
import httpx
from chromadb.api.models.Collection import Collection
from openai import OpenAI

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MODEL = "text-embedding-3-small"
DEFAULT_COLLECTION = "logistics_chunks"
MANIFEST_NAME = "manifest.json"
EMBED_BATCH_SIZE = 96


class RetrievalError(Exception):
    """A condition that must stop the run with a diagnostic, never a silent empty result."""


def load_dotenv(path: Path | None = None) -> None:
    """Load KEY=VALUE lines from a gitignored .env, without overriding a real environment variable.

    Avoids a dependency on python-dotenv for a file this project reads once.
    """
    env_file = path or REPO_ROOT / ".env"
    if not env_file.is_file():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        key, separator, value = stripped.partition("=")
        if not separator:
            continue
        os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


@dataclass(frozen=True)
class Settings:
    """The single place this project reads environment variables."""

    openai_api_key: str
    embedding_model: str
    chunks_path: Path
    index_dir: Path
    collection_name: str
    connect_timeout: float
    read_timeout: float
    max_retries: int

    @classmethod
    def from_env(
        cls,
        *,
        chunks_path: Path | None = None,
        index_dir: Path | None = None,
        collection_name: str | None = None,
        embedding_model: str | None = None,
        require_key: bool = True,
    ) -> Settings:
        load_dotenv()
        api_key = os.environ.get("OPENAI_API_KEY", "").strip()
        if require_key and not api_key:
            raise RetrievalError(
                "OPENAI_API_KEY is not set. Export it before running:\n"
                "  export OPENAI_API_KEY=sk-...\n"
                "The key is read from the environment only — it is never written to any file."
            )
        return cls(
            openai_api_key=api_key,
            embedding_model=embedding_model
            or os.environ.get("RAG_EMBEDDING_MODEL", DEFAULT_MODEL),
            chunks_path=chunks_path or REPO_ROOT / "data" / "processed" / "chunks.jsonl",
            index_dir=index_dir or REPO_ROOT / "index" / "chroma",
            collection_name=collection_name
            or os.environ.get("RAG_COLLECTION", DEFAULT_COLLECTION),
            connect_timeout=float(os.environ.get("RAG_CONNECT_TIMEOUT", "10")),
            read_timeout=float(os.environ.get("RAG_READ_TIMEOUT", "60")),
            max_retries=int(os.environ.get("RAG_MAX_RETRIES", "3")),
        )


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    text: str
    metadata: dict[str, Any]


@dataclass(frozen=True)
class SearchHit:
    rank: int
    chunk_id: str
    score: float
    distance: float
    text: str
    metadata: dict[str, Any]

    def preview(self, width: int = 220) -> str:
        collapsed = " ".join(self.text.split())
        return collapsed if len(collapsed) <= width else collapsed[: width - 1].rstrip() + "…"


def load_chunks(chunks_path: Path) -> list[Chunk]:
    if not chunks_path.is_file():
        raise RetrievalError(
            f"{chunks_path} not found. Build the knowledge base first:\n"
            "  python scripts/prepare_knowledge_base.py"
        )
    chunks: list[Chunk] = []
    for line_number, line in enumerate(chunks_path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise RetrievalError(f"{chunks_path}:{line_number}: invalid JSON ({exc.msg})") from exc
        chunks.append(
            Chunk(
                chunk_id=row["chunk_id"],
                text=row["text"],
                metadata=dict(row.get("metadata", {})),
            )
        )
    if not chunks:
        raise RetrievalError(f"{chunks_path} contains no chunks")
    return chunks


def file_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _openai_client(settings: Settings) -> OpenAI:
    # Connect and read budgets are set independently: a connect budget sized for a read either
    # fails fast on a healthy slow response or holds the process through a black-holed connect.
    timeout = httpx.Timeout(
        connect=settings.connect_timeout,
        read=settings.read_timeout,
        write=settings.read_timeout,
        pool=settings.connect_timeout,
    )
    return OpenAI(
        api_key=settings.openai_api_key,
        timeout=timeout,
        max_retries=settings.max_retries,
    )


def embed_texts(
    texts: list[str],
    settings: Settings,
    *,
    client: OpenAI | None = None,
    progress: bool = False,
) -> list[list[float]]:
    """Embed `texts` with the configured model, preserving input order."""
    if not texts:
        return []
    api = client if client is not None else _openai_client(settings)
    vectors: list[list[float]] = []
    for start in range(0, len(texts), EMBED_BATCH_SIZE):
        batch = texts[start : start + EMBED_BATCH_SIZE]
        response = api.embeddings.create(model=settings.embedding_model, input=batch)
        ordered = sorted(response.data, key=lambda item: item.index)
        vectors.extend(list(item.embedding) for item in ordered)
        if progress:
            print(f"  embedded {min(start + len(batch), len(texts))}/{len(texts)}")
    if len(vectors) != len(texts):
        raise RetrievalError(
            f"embedding API returned {len(vectors)} vectors for {len(texts)} inputs"
        )
    return vectors


def embed_query(query: str, settings: Settings, *, client: OpenAI | None = None) -> list[float]:
    """Embed a user query with the SAME model used for the chunks."""
    return embed_texts([query], settings, client=client)[0]


def manifest_path(index_dir: Path) -> Path:
    return index_dir.parent / MANIFEST_NAME


def _display_path(path: Path) -> str:
    """Repo-relative when the path is inside the repo, absolute otherwise."""
    resolved = path.resolve()
    if resolved.is_relative_to(REPO_ROOT):
        return str(resolved.relative_to(REPO_ROOT))
    return str(resolved)


def write_manifest(settings: Settings, *, dimension: int, chunk_count: int) -> Path:
    path = manifest_path(settings.index_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "embedding_model": settings.embedding_model,
        "dimension": dimension,
        "chunk_count": chunk_count,
        "collection": settings.collection_name,
        "chunks_file": _display_path(settings.chunks_path),
        "chunks_sha256": file_digest(settings.chunks_path),
        "vector_store": f"chromadb {chromadb.__version__}",
        "distance": "cosine",
        "score": "1 - cosine_distance",
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def read_manifest(settings: Settings) -> dict[str, Any]:
    path = manifest_path(settings.index_dir)
    if not path.is_file():
        raise RetrievalError(
            f"{path} not found. Build the index first:\n  python scripts/build_index.py"
        )
    manifest: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    indexed_model = manifest.get("embedding_model")
    if indexed_model != settings.embedding_model:
        raise RetrievalError(
            f"index was built with {indexed_model!r} but the query would be embedded with "
            f"{settings.embedding_model!r}. Chunks and queries must use the same model — "
            "rebuild the index or set RAG_EMBEDDING_MODEL to match."
        )
    return manifest


def open_collection(settings: Settings, *, create: bool = False) -> Collection:
    settings.index_dir.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(settings.index_dir))
    if create:
        if settings.collection_name in {c.name for c in client.list_collections()}:
            client.delete_collection(settings.collection_name)
        return client.create_collection(
            name=settings.collection_name,
            embedding_function=None,
            configuration={"hnsw": {"space": "cosine"}},
        )
    return client.get_collection(name=settings.collection_name, embedding_function=None)


def search(
    query: str,
    settings: Settings,
    *,
    k: int = 5,
    client: OpenAI | None = None,
    collection: Collection | None = None,
) -> list[SearchHit]:
    """Embed `query` with the indexed model and return the top-k nearest chunks."""
    if not query.strip():
        raise RetrievalError("query is empty")
    read_manifest(settings)
    target = collection if collection is not None else open_collection(settings)
    vector = embed_query(query, settings, client=client)
    result = target.query(
        query_embeddings=[vector],
        n_results=k,
        include=["documents", "metadatas", "distances"],
    )
    hits: list[SearchHit] = []
    ids = result["ids"][0]
    documents = (result.get("documents") or [[]])[0]
    metadatas = (result.get("metadatas") or [[]])[0]
    distances = (result.get("distances") or [[]])[0]
    for rank, (chunk_id, document, metadata, distance) in enumerate(
        zip(ids, documents, metadatas, distances, strict=True), start=1
    ):
        hits.append(
            SearchHit(
                rank=rank,
                chunk_id=chunk_id,
                score=1.0 - float(distance),
                distance=float(distance),
                text=document or "",
                metadata=dict(metadata or {}),
            )
        )
    return hits
