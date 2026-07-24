"""Shared building blocks for the Homework #2 semantic retrieval layer.

Owns three things so nothing downstream re-derives them: the typed settings object (the single
place any environment variable is read), the OpenAI embedding call, and the Chroma index handle.
See docs/homework2/retrieval-spec.md.

Homework #3 extends this module with the improved retrieval pipeline: metadata filtering
(`search(..., where=...)`), a standard-library BM25 index, Reciprocal Rank Fusion, and the
rule-based document-type inference behind `search_improved`. See
docs/homework3/retrieval-improvements-spec.md.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TypeVar

import chromadb
import httpx
from chromadb.api.models.Collection import Collection
from chromadb.config import Settings as ChromaSettings
from chromadb.errors import NotFoundError
from openai import OpenAI, OpenAIError

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MODEL = "text-embedding-3-small"
DEFAULT_COLLECTION = "logistics_chunks"
MANIFEST_NAME = "manifest.json"
EMBED_BATCH_SIZE = 96

# Homework #3 tuning values — single-sourced here so the library, the CLI defaults, and the
# design doc cannot drift apart. Rationale for each: docs/homework3/retrieval-improvements-spec.md.
BM25_K1 = 1.5
BM25_B = 0.75
RRF_K = 60
RRF_POOL = 10

# Query tokens that appear in nearly every sentence carry no ranking signal; dropping them keeps
# BM25 scores driven by domain vocabulary instead of sentence glue.
STOPWORDS = frozenset(
    "a an and are as at be but by can do does for from how i in is it my of on or that the "
    "this to was we what when where which who why will with you your".split()
)

# Maps each document_type (the four values owned by docs/homework1/assets/chunk.schema.json)
# to corpus vocabulary that signals a query is about that document. Keywords are drawn from the
# source documents' own terminology — never from the evaluation queries' wording — so the
# inference is not tuned to the test set. A query matching no type (or tying) stays unfiltered:
# a wrong filter is worse than none, and out-of-corpus queries must not be funnelled into a
# document they cannot be answered by.
DOCUMENT_TYPE_KEYWORDS: dict[str, frozenset[str]] = {
    "concept-guide": frozenset(
        "backhaul carrier carriers shipper shippers freight broker brokers load loads truck "
        "trucks delivery deliveries exchange pod settlement".split()
    ),
    "architecture-guide": frozenset(
        "cqrs sourcing command commands projection projections aggregate aggregates event "
        "events".split()
    ),
    "case-study": frozenset(
        "migration migrations migrate migrating monolith monoliths microservice microservices "
        "strangler".split()
    ),
    "playbook": frozenset(
        "scaling scale deploy deployment deployments downtime release releases rollout caching "
        "cache observability rps throughput latency requests".split()
    ),
}


class RetrievalError(Exception):
    """A condition that must stop the run with a diagnostic, never a silent empty result."""


_Number = TypeVar("_Number", int, float)


def _env_number(name: str, default: _Number, cast: Callable[[str], _Number]) -> _Number:
    """Parse a numeric environment variable, turning a malformed value into a clear diagnostic."""
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return cast(raw)
    except ValueError as exc:
        raise RetrievalError(
            f"environment variable {name}={raw!r} is not a valid number"
        ) from exc


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

    # repr=False so printing Settings — in a traceback, a debug print, or pytest --showlocals —
    # can never dump the plaintext key.
    openai_api_key: str = field(repr=False)
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
            chunks_path=chunks_path
            or REPO_ROOT / "data" / "processed" / "chunks.jsonl",
            index_dir=index_dir or REPO_ROOT / "index" / "chroma",
            collection_name=collection_name
            or os.environ.get("RAG_COLLECTION", DEFAULT_COLLECTION),
            connect_timeout=_env_number("RAG_CONNECT_TIMEOUT", 10.0, float),
            read_timeout=_env_number("RAG_READ_TIMEOUT", 60.0, float),
            max_retries=_env_number("RAG_MAX_RETRIES", 3, int),
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
        return (
            collapsed
            if len(collapsed) <= width
            else collapsed[: width - 1].rstrip() + "…"
        )


def load_chunks(chunks_path: Path) -> list[Chunk]:
    if not chunks_path.is_file():
        raise RetrievalError(
            f"{chunks_path} not found. Build the knowledge base first:\n"
            "  python scripts/prepare_knowledge_base.py"
        )
    chunks: list[Chunk] = []
    for line_number, line in enumerate(
        chunks_path.read_text(encoding="utf-8").splitlines(), 1
    ):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise RetrievalError(
                f"{chunks_path}:{line_number}: invalid JSON ({exc.msg})"
            ) from exc
        if not isinstance(row, dict):
            raise RetrievalError(
                f"{chunks_path}:{line_number}: expected a JSON object, got {type(row).__name__}"
            )
        for required in ("chunk_id", "text"):
            if required not in row:
                raise RetrievalError(
                    f"{chunks_path}:{line_number}: missing field {required!r}"
                )
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
        try:
            response = api.embeddings.create(
                model=settings.embedding_model, input=batch
            )
        except OpenAIError as exc:
            # A rejected key or an exhausted quota is the likeliest real failure here; without
            # this the carefully worded diagnostics elsewhere are bypassed by a raw traceback.
            raise RetrievalError(
                f"embedding request failed for model {settings.embedding_model!r}: {exc}"
            ) from exc
        ordered = sorted(response.data, key=lambda item: item.index)
        vectors.extend(list(item.embedding) for item in ordered)
        if progress:
            print(f"  embedded {min(start + len(batch), len(texts))}/{len(texts)}")
    if len(vectors) != len(texts):
        raise RetrievalError(
            f"embedding API returned {len(vectors)} vectors for {len(texts)} inputs"
        )
    return vectors


def embed_query(
    query: str, settings: Settings, *, client: OpenAI | None = None
) -> list[float]:
    """Embed a user query with the SAME model used for the chunks."""
    return embed_texts([query], settings, client=client)[0]


def manifest_path(index_dir: Path) -> Path:
    """The manifest lives INSIDE its index directory.

    Anchoring it to the parent made two indexes under the same parent (index/chroma and
    index/chroma_500 in the chunk-size experiment) share — and silently overwrite — one manifest.
    """
    return index_dir / MANIFEST_NAME


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
    try:
        manifest: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RetrievalError(
            f"{path} is corrupt ({exc.msg}). Rebuild the index:\n  python scripts/build_index.py"
        ) from exc
    indexed_model = manifest.get("embedding_model")
    if indexed_model != settings.embedding_model:
        raise RetrievalError(
            f"index was built with {indexed_model!r} but the query would be embedded with "
            f"{settings.embedding_model!r}. Chunks and queries must use the same model — "
            "rebuild the index or set RAG_EMBEDDING_MODEL to match."
        )
    # Recording the digest without checking it is a safety net that never fires. An index built
    # from a since-edited chunks.jsonl returns neighbours for text that is no longer in the repo.
    indexed_digest = manifest.get("chunks_sha256")
    if indexed_digest and settings.chunks_path.is_file():
        current_digest = file_digest(settings.chunks_path)
        if current_digest != indexed_digest:
            raise RetrievalError(
                f"{settings.chunks_path} has changed since the index was built "
                f"(indexed {indexed_digest[:12]}…, current {current_digest[:12]}…). "
                "The index would return chunks that no longer match the corpus — rebuild it:\n"
                "  python scripts/build_index.py"
            )
    return manifest


def open_collection(settings: Settings, *, create: bool = False) -> Collection:
    settings.index_dir.mkdir(parents=True, exist_ok=True)
    # Telemetry defaults to on and would make an unmanaged network call outside this project's
    # own timeout policy. Nothing here needs to phone home.
    client = chromadb.PersistentClient(
        path=str(settings.index_dir),
        settings=ChromaSettings(anonymized_telemetry=False),
    )
    if create:
        if settings.collection_name in {c.name for c in client.list_collections()}:
            client.delete_collection(settings.collection_name)
        return client.create_collection(
            name=settings.collection_name,
            embedding_function=None,
            configuration={"hnsw": {"space": "cosine"}},
        )
    try:
        return client.get_collection(
            name=settings.collection_name, embedding_function=None
        )
    except NotFoundError as exc:
        # Translate the store's own error so a never-built index gives the same clear instruction
        # as a missing manifest, rather than a raw binding traceback.
        raise RetrievalError(
            f"no collection {settings.collection_name!r} in {settings.index_dir}. "
            "Build the index first:\n  python scripts/build_index.py"
        ) from exc


def search(
    query: str,
    settings: Settings,
    *,
    k: int = 5,
    client: OpenAI | None = None,
    collection: Collection | None = None,
    where: dict[str, Any] | None = None,
) -> list[SearchHit]:
    """Embed `query` with the indexed model and return the top-k nearest chunks.

    `where` is a Chroma metadata filter (e.g. ``{"document_type": "playbook"}``); it narrows the
    search space before nearest-neighbour ranking, so a filtered query can return fewer than `k`
    hits when the matching subset is small.
    """
    if not query.strip():
        raise RetrievalError("query is empty")
    read_manifest(settings)
    target = collection if collection is not None else open_collection(settings)
    vector = embed_query(query, settings, client=client)
    result = target.query(
        query_embeddings=[vector],
        n_results=k,
        where=where,
        include=["documents", "metadatas", "distances"],
    )
    hits: list[SearchHit] = []
    ids = result["ids"][0]
    # Name a missing field explicitly. Defaulting to [[]] and letting zip(strict=True) fail turns
    # a structured absence into "argument 2 is shorter than argument 1", which names nothing.
    columns: dict[str, list[Any]] = {}
    for key in ("documents", "metadatas", "distances"):
        column = result.get(key)
        if column is None:
            raise RetrievalError(f"the vector store returned no {key!r} for this query")
        columns[key] = column[0]
    documents, metadatas, distances = (
        columns["documents"],
        columns["metadatas"],
        columns["distances"],
    )
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


# --- Homework #3: improved retrieval (metadata filtering + hybrid BM25/RRF) -------------------
# Design decisions and tuning rationale: docs/homework3/retrieval-improvements-spec.md.


def _tokenize(text: str) -> list[str]:
    """Lowercased alphanumeric tokens with stopwords removed, duplicates preserved for BM25 tf."""
    return [
        token
        for token in re.findall(r"[a-z0-9]+", text.lower())
        if token not in STOPWORDS
    ]


def infer_document_type(query: str) -> str | None:
    """Infer a document_type filter from the query's vocabulary, or None to stay unfiltered.

    Counts distinct keyword matches per type; the unique best-scoring type wins. Zero matches or
    a tie yields None — ambiguity means filtering would be a guess, and a wrong filter excludes
    the right document entirely.
    """
    tokens = set(_tokenize(query))
    counts = {
        doc_type: len(tokens & keywords)
        for doc_type, keywords in DOCUMENT_TYPE_KEYWORDS.items()
    }
    best = max(counts.values())
    if best == 0:
        return None
    winners = [doc_type for doc_type, count in counts.items() if count == best]
    if len(winners) > 1:
        return None
    return winners[0]


class Bm25Index:
    """In-memory BM25 (Okapi) over the chunk corpus — standard library only.

    77 chunks fit comfortably in memory, so the index is rebuilt from chunks.jsonl on demand
    rather than persisted; IDF is always computed over the FULL corpus so that a metadata filter
    (via `allowed_ids`) narrows the candidate set without distorting term statistics.
    """

    def __init__(self, chunks: list[Chunk]) -> None:
        if not chunks:
            raise RetrievalError("cannot build a BM25 index from an empty chunk list")
        self._by_id: dict[str, Chunk] = {chunk.chunk_id: chunk for chunk in chunks}
        self._tokens: dict[str, list[str]] = {
            chunk.chunk_id: _tokenize(chunk.text) for chunk in chunks
        }
        self._doc_length = {
            chunk_id: len(tokens) for chunk_id, tokens in self._tokens.items()
        }
        total_length = sum(self._doc_length.values())
        self._avg_length = total_length / len(chunks) if total_length else 1.0
        document_frequency: dict[str, int] = {}
        for tokens in self._tokens.values():
            for term in set(tokens):
                document_frequency[term] = document_frequency.get(term, 0) + 1
        corpus_size = len(chunks)
        # The +0.5 / +1 smoothing keeps IDF positive even for terms present in most chunks.
        self._idf = {
            term: math.log(1.0 + (corpus_size - freq + 0.5) / (freq + 0.5))
            for term, freq in document_frequency.items()
        }

    def chunk(self, chunk_id: str) -> Chunk:
        return self._by_id[chunk_id]

    def matching_ids(self, metadata_key: str, value: Any) -> frozenset[str]:
        """Chunk ids whose metadata carries `metadata_key == value` — the BM25-side filter."""
        return frozenset(
            chunk_id
            for chunk_id, chunk in self._by_id.items()
            if chunk.metadata.get(metadata_key) == value
        )

    def top(
        self, query: str, *, k: int, allowed_ids: frozenset[str] | None = None
    ) -> list[tuple[str, float]]:
        """Top-k (chunk_id, bm25_score) for `query`, restricted to `allowed_ids` when given.

        Only positive-scoring chunks are returned, so the list may be shorter than `k`.
        Ties break on chunk_id to keep the ranking deterministic run-to-run.
        """
        terms = sorted(set(_tokenize(query)))
        if not terms:
            return []
        scores: dict[str, float] = {}
        for chunk_id, tokens in self._tokens.items():
            if allowed_ids is not None and chunk_id not in allowed_ids:
                continue
            length_norm = (
                1.0 - BM25_B + BM25_B * (self._doc_length[chunk_id] / self._avg_length)
            )
            score = 0.0
            for term in terms:
                frequency = tokens.count(term)
                if frequency == 0:
                    continue
                idf = self._idf.get(term, 0.0)
                score += (
                    idf
                    * (frequency * (BM25_K1 + 1))
                    / (frequency + BM25_K1 * length_norm)
                )
            if score > 0.0:
                scores[chunk_id] = score
        ranked = sorted(scores.items(), key=lambda item: (-item[1], item[0]))
        return ranked[:k]


def rrf_fuse(
    rankings: list[list[str]], *, rrf_k: int = RRF_K
) -> list[tuple[str, float]]:
    """Reciprocal Rank Fusion: score(id) = Σ 1/(rrf_k + rank) across the given rankings.

    Rank-based fusion sidesteps the unit mismatch between cosine similarity and BM25 scores.
    Ties break on chunk_id so the fused order is deterministic.
    """
    scores: dict[str, float] = {}
    for ranking in rankings:
        for position, chunk_id in enumerate(ranking, start=1):
            scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (rrf_k + position)
    return sorted(scores.items(), key=lambda item: (-item[1], item[0]))


@dataclass(frozen=True)
class HybridHit:
    """One improved-pipeline result.

    `rrf_score` is rank-based and NOT comparable to the cosine `score` of SearchHit — that unit
    mismatch is exactly why fusion happens on ranks. `semantic_score`/`semantic_rank` are None
    for a chunk surfaced only by BM25; `bm25_rank` is None for a chunk surfaced only
    semantically; `rrf_score` is None when the hit came from a non-hybrid (filter-only) run.
    """

    rank: int
    chunk_id: str
    rrf_score: float | None
    semantic_score: float | None
    semantic_rank: int | None
    bm25_rank: int | None
    text: str
    metadata: dict[str, Any]

    def preview(self, width: int = 220) -> str:
        collapsed = " ".join(self.text.split())
        return (
            collapsed
            if len(collapsed) <= width
            else collapsed[: width - 1].rstrip() + "…"
        )


def search_improved(
    query: str,
    settings: Settings,
    *,
    k: int = 5,
    client: OpenAI | None = None,
    collection: Collection | None = None,
    bm25: Bm25Index | None = None,
    document_type: str | None = None,
    hybrid: bool = True,
) -> list[HybridHit]:
    """The Homework #3 pipeline: optional document_type filter + optional hybrid BM25/RRF.

    The filter narrows BOTH branches — the semantic branch via the Chroma `where=` clause and
    the BM25 branch via `allowed_ids` — so they rank the same candidate space. Callers decide
    the filter (pass `infer_document_type(query)` for the rule-based behaviour); passing None
    searches unfiltered. Hybrid runs fetch RRF_POOL candidates per branch before fusing down
    to k — fusion needs more candidates than the final k or promotion is impossible.
    """
    if document_type is not None and document_type not in DOCUMENT_TYPE_KEYWORDS:
        valid = ", ".join(sorted(DOCUMENT_TYPE_KEYWORDS))
        raise RetrievalError(
            f"unknown document_type {document_type!r}. Valid values: {valid}"
        )
    where = {"document_type": document_type} if document_type is not None else None
    fetch = max(k, RRF_POOL) if hybrid else k
    semantic = search(
        query, settings, k=fetch, client=client, collection=collection, where=where
    )
    if not hybrid:
        return [
            HybridHit(
                rank=hit.rank,
                chunk_id=hit.chunk_id,
                rrf_score=None,
                semantic_score=hit.score,
                semantic_rank=hit.rank,
                bm25_rank=None,
                text=hit.text,
                metadata=hit.metadata,
            )
            for hit in semantic[:k]
        ]
    # search() has already verified the manifest digest, so chunks.jsonl is exactly the corpus
    # the vector index was built from — the BM25 branch cannot silently rank different text.
    index = bm25 if bm25 is not None else Bm25Index(load_chunks(settings.chunks_path))
    allowed = (
        index.matching_ids("document_type", document_type)
        if document_type is not None
        else None
    )
    lexical = index.top(query, k=fetch, allowed_ids=allowed)
    semantic_by_id = {hit.chunk_id: hit for hit in semantic}
    bm25_rank_by_id = {
        chunk_id: position for position, (chunk_id, _) in enumerate(lexical, start=1)
    }
    fused = rrf_fuse(
        [[hit.chunk_id for hit in semantic], [chunk_id for chunk_id, _ in lexical]]
    )
    hits: list[HybridHit] = []
    for rank, (chunk_id, rrf_score) in enumerate(fused[:k], start=1):
        semantic_hit = semantic_by_id.get(chunk_id)
        source = semantic_hit if semantic_hit is not None else index.chunk(chunk_id)
        hits.append(
            HybridHit(
                rank=rank,
                chunk_id=chunk_id,
                rrf_score=rrf_score,
                semantic_score=semantic_hit.score if semantic_hit else None,
                semantic_rank=semantic_hit.rank if semantic_hit else None,
                bm25_rank=bm25_rank_by_id.get(chunk_id),
                text=source.text,
                metadata=dict(source.metadata),
            )
        )
    return hits
