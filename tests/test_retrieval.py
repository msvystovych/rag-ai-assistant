"""Tests for the Homework #2 retrieval layer.

Every OpenAI call is mocked: the suite runs with no network and no OPENAI_API_KEY.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import rag_lib  # noqa: E402
from rag_lib import (  # noqa: E402
    RetrievalError,
    Settings,
    embed_texts,
    load_chunks,
    open_collection,
    read_manifest,
    search,
    write_manifest,
)
from retrieval import format_hit, render  # noqa: E402
from run_test_queries import load_queries, verdict  # noqa: E402

DIMENSION = 8


@dataclass
class FakeEmbedding:
    index: int
    embedding: list[float]


@dataclass
class FakeResponse:
    data: list[FakeEmbedding]


class FakeEmbeddings:
    def __init__(self, owner: FakeOpenAI) -> None:
        self._owner = owner

    def create(self, *, model: str, input: list[str]) -> FakeResponse:  # noqa: A002
        self._owner.calls.append((model, list(input)))
        # Deterministic pseudo-embedding: a bag-of-characters projection, so texts sharing
        # vocabulary land near each other and the ranking is meaningful without a real model.
        data = []
        for position, text in enumerate(input):
            vector = [0.0] * DIMENSION
            for character in text.lower():
                if character.isalpha():
                    vector[ord(character) % DIMENSION] += 1.0
            norm = sum(value * value for value in vector) ** 0.5 or 1.0
            data.append(FakeEmbedding(position, [value / norm for value in vector]))
        return FakeResponse(data)


class FakeOpenAI:
    def __init__(self) -> None:
        self.calls: list[tuple[str, list[str]]] = []
        self.embeddings = FakeEmbeddings(self)


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        openai_api_key="test-key",
        embedding_model="text-embedding-3-small",
        chunks_path=tmp_path / "chunks.jsonl",
        index_dir=tmp_path / "index" / "chroma",
        collection_name="test_chunks",
        connect_timeout=10.0,
        read_timeout=60.0,
        max_retries=3,
    )


@pytest.fixture
def corpus(settings: Settings) -> list[dict[str, Any]]:
    rows = [
        {
            "chunk_id": "primer_chunk_001",
            "text": "Primer > Backhaul. A backhaul is a return-leg load that avoids running empty.",
            "metadata": {
                "document_id": "primer",
                "source_file": "data/raw/primer.md",
                "chunk_index": 1,
                "section": "Backhaul",
                "title": "Primer",
                "document_type": "concept-guide",
            },
        },
        {
            "chunk_id": "cqrs_chunk_001",
            "text": "CQRS > Projections. Projections rebuild denormalized read models from the event stream.",
            "metadata": {
                "document_id": "cqrs",
                "source_file": "data/raw/cqrs.md",
                "chunk_index": 1,
                "section": "Projections",
                "title": "CQRS",
                "document_type": "architecture-guide",
            },
        },
        {
            "chunk_id": "scaling_chunk_001",
            "text": "Scaling > Deploys. Blue-green deployment swaps traffic with zero downtime.",
            "metadata": {
                "document_id": "scaling",
                "source_file": "data/raw/scaling.md",
                "chunk_index": 1,
                "section": "Deploys",
                "title": "Scaling",
                "document_type": "playbook",
            },
        },
    ]
    settings.chunks_path.parent.mkdir(parents=True, exist_ok=True)
    settings.chunks_path.write_text(
        "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
    )
    return rows


@pytest.fixture
def index(settings: Settings, corpus: list[dict[str, Any]]) -> Settings:
    client = FakeOpenAI()
    chunks = load_chunks(settings.chunks_path)
    vectors = embed_texts([chunk.text for chunk in chunks], settings, client=client)
    collection = open_collection(settings, create=True)
    collection.add(
        ids=[chunk.chunk_id for chunk in chunks],
        embeddings=vectors,
        documents=[chunk.text for chunk in chunks],
        metadatas=[chunk.metadata for chunk in chunks],
    )
    write_manifest(settings, dimension=DIMENSION, chunk_count=len(chunks))
    return settings


class TestSettings:
    def test_missing_api_key_is_a_diagnostic_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(rag_lib, "load_dotenv", lambda path=None: None)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        with pytest.raises(RetrievalError, match="OPENAI_API_KEY is not set"):
            Settings.from_env()

    def test_dotenv_never_overrides_a_real_environment_variable(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("OPENAI_API_KEY", "from-environment")
        env_file = tmp_path / ".env"
        env_file.write_text("OPENAI_API_KEY=from-file\n", encoding="utf-8")
        rag_lib.load_dotenv(env_file)
        assert rag_lib.os.environ["OPENAI_API_KEY"] == "from-environment"

    def test_malformed_numeric_env_var_is_a_diagnostic_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("OPENAI_API_KEY", "k")
        monkeypatch.setenv("RAG_CONNECT_TIMEOUT", "soon")
        with pytest.raises(RetrievalError, match="RAG_CONNECT_TIMEOUT"):
            Settings.from_env()

    def test_blank_numeric_env_var_falls_back_to_the_default(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("OPENAI_API_KEY", "k")
        monkeypatch.setenv("RAG_MAX_RETRIES", "")
        assert Settings.from_env().max_retries == 3


class TestLoadChunks:
    def test_missing_file_is_a_diagnostic_error(self, tmp_path: Path) -> None:
        with pytest.raises(RetrievalError, match="Build the knowledge base first"):
            load_chunks(tmp_path / "absent.jsonl")

    def test_invalid_json_names_the_line(self, tmp_path: Path) -> None:
        path = tmp_path / "chunks.jsonl"
        path.write_text('{"chunk_id": "a"\n', encoding="utf-8")
        with pytest.raises(RetrievalError, match=":1: invalid JSON"):
            load_chunks(path)

    def test_missing_required_field_is_a_diagnostic_error(self, tmp_path: Path) -> None:
        path = tmp_path / "chunks.jsonl"
        path.write_text('{"text": "no id here"}\n', encoding="utf-8")
        with pytest.raises(RetrievalError, match="missing field 'chunk_id'"):
            load_chunks(path)

    def test_non_object_line_is_a_diagnostic_error(self, tmp_path: Path) -> None:
        path = tmp_path / "chunks.jsonl"
        path.write_text("42\n", encoding="utf-8")
        with pytest.raises(RetrievalError, match="expected a JSON object"):
            load_chunks(path)


class TestEmbedding:
    def test_preserves_input_order_across_batches(self, settings: Settings) -> None:
        client = FakeOpenAI()
        texts = [f"text number {i}" for i in range(rag_lib.EMBED_BATCH_SIZE + 20)]
        vectors = embed_texts(texts, settings, client=client)
        assert len(vectors) == len(texts)
        assert len(client.calls) == 2, (
            "should batch rather than issue one call per text"
        )
        assert vectors[5] == embed_texts([texts[5]], settings, client=FakeOpenAI())[0]

    def test_uses_the_configured_model(self, settings: Settings) -> None:
        client = FakeOpenAI()
        embed_texts(["anything"], settings, client=client)
        assert client.calls[0][0] == "text-embedding-3-small"

    def test_empty_input_makes_no_api_call(self, settings: Settings) -> None:
        client = FakeOpenAI()
        assert embed_texts([], settings, client=client) == []
        assert client.calls == []

    def test_api_failure_surfaces_as_a_diagnostic_error(
        self, settings: Settings
    ) -> None:
        from openai import OpenAIError

        class FailingEmbeddings:
            def create(self, *, model: str, input: list[str]) -> Any:  # noqa: A002
                raise OpenAIError("simulated auth failure")

        class FailingClient:
            embeddings = FailingEmbeddings()

        with pytest.raises(RetrievalError, match="embedding request failed"):
            embed_texts(["x"], settings, client=FailingClient())


class TestManifest:
    def test_records_model_and_chunk_count(self, index: Settings) -> None:
        manifest = read_manifest(index)
        assert manifest["embedding_model"] == "text-embedding-3-small"
        assert manifest["chunk_count"] == 3
        assert manifest["score"] == "1 - cosine_distance"

    def test_model_mismatch_is_refused(self, index: Settings) -> None:
        mismatched = Settings(
            **{**index.__dict__, "embedding_model": "text-embedding-3-large"}
        )
        with pytest.raises(RetrievalError, match="same model"):
            read_manifest(mismatched)

    def test_missing_manifest_is_a_diagnostic_error(self, settings: Settings) -> None:
        with pytest.raises(RetrievalError, match="Build the index first"):
            read_manifest(settings)

    def test_stale_chunks_file_is_refused(self, index: Settings) -> None:
        index.chunks_path.write_text(
            index.chunks_path.read_text() + "\n", encoding="utf-8"
        )
        with pytest.raises(
            RetrievalError, match="has changed since the index was built"
        ):
            read_manifest(index)

    def test_corrupt_manifest_is_a_diagnostic_error(self, index: Settings) -> None:
        rag_lib.manifest_path(index.index_dir).write_text("{not json", encoding="utf-8")
        with pytest.raises(RetrievalError, match="corrupt"):
            read_manifest(index)


class TestSearch:
    def test_returns_k_hits_ranked_by_descending_score(self, index: Settings) -> None:
        hits = search("backhaul return leg empty", index, k=3, client=FakeOpenAI())
        assert len(hits) == 3
        assert [hit.rank for hit in hits] == [1, 2, 3]
        assert hits == sorted(hits, key=lambda hit: hit.score, reverse=True)

    def test_k_caps_the_result_count(self, index: Settings) -> None:
        assert len(search("anything", index, k=1, client=FakeOpenAI())) == 1

    def test_scores_are_within_the_cosine_range(self, index: Settings) -> None:
        for hit in search("projections read models", index, k=3, client=FakeOpenAI()):
            assert -1.0001 <= hit.score <= 1.0001
            assert abs(hit.score - (1.0 - hit.distance)) < 1e-9

    def test_metadata_survives_the_round_trip(self, index: Settings) -> None:
        hit = search("backhaul", index, k=1, client=FakeOpenAI())[0]
        assert hit.metadata["source_file"].startswith("data/raw/")
        assert hit.metadata["document_id"]
        assert hit.metadata["chunk_index"] >= 1

    def test_empty_query_is_refused(self, index: Settings) -> None:
        with pytest.raises(RetrievalError, match="query is empty"):
            search("   ", index, k=3, client=FakeOpenAI())

    def test_query_is_embedded_with_the_same_model_as_the_chunks(
        self, index: Settings
    ) -> None:
        client = FakeOpenAI()
        search("backhaul", index, k=1, client=client)
        assert client.calls[0][0] == read_manifest(index)["embedding_model"]


class TestPresentation:
    def test_hit_line_carries_id_score_and_source(self, index: Settings) -> None:
        rendered = format_hit(search("backhaul", index, k=1, client=FakeOpenAI())[0])
        assert "score:" in rendered
        assert "Source: data/raw/" in rendered
        assert "Top-1:" in rendered

    def test_render_includes_the_query(self, index: Settings) -> None:
        hits = search("backhaul", index, k=2, client=FakeOpenAI())
        assert render("backhaul?", hits).startswith("Query: backhaul?")

    def test_preview_is_truncated_and_single_line(self, index: Settings) -> None:
        hit = search("backhaul", index, k=1, client=FakeOpenAI())[0]
        preview = hit.preview(40)
        assert len(preview) <= 40
        assert "\n" not in preview


class TestVerdict:
    @pytest.mark.parametrize(
        ("top_documents", "expected", "fragment"),
        [
            (["primer", "cqrs"], ["primer"], "hit"),
            (["cqrs", "primer"], ["primer"], "partial"),
            (["cqrs", "scaling"], ["primer"], "miss"),
            (["cqrs"], [], "out-of-corpus"),
        ],
    )
    def test_classification(
        self, top_documents: list[str], expected: list[str], fragment: str
    ) -> None:
        hits = [
            rag_lib.SearchHit(
                rank=position,
                chunk_id=f"{document}_chunk_001",
                score=0.9 - position * 0.1,
                distance=0.1,
                text="body",
                metadata={"document_id": document},
            )
            for position, document in enumerate(top_documents, start=1)
        ]
        assert fragment in verdict(hits, expected)


class TestLoadQueries:
    def test_invalid_json_is_a_diagnostic_error(self, tmp_path: Path) -> None:
        path = tmp_path / "q.json"
        path.write_text("{not json", encoding="utf-8")
        with pytest.raises(RetrievalError, match="invalid JSON"):
            load_queries(path)

    def test_missing_queries_key_is_a_diagnostic_error(self, tmp_path: Path) -> None:
        path = tmp_path / "q.json"
        path.write_text('{"items": []}', encoding="utf-8")
        with pytest.raises(RetrievalError, match="expected a top-level 'queries' list"):
            load_queries(path)

    def test_too_few_queries_is_a_diagnostic_error(self, tmp_path: Path) -> None:
        path = tmp_path / "q.json"
        path.write_text('{"queries": [1, 2]}', encoding="utf-8")
        with pytest.raises(RetrievalError, match="at least 5"):
            load_queries(path)

    def test_malformed_query_entry_is_a_diagnostic_error(self, tmp_path: Path) -> None:
        path = tmp_path / "q.json"
        entries = [{"id": "q1", "category": "direct", "query": "ok"}] * 4 + [
            {"oops": 1}
        ]
        path.write_text(json.dumps({"queries": entries}), encoding="utf-8")
        with pytest.raises(RetrievalError, match="query 4 must be an object"):
            load_queries(path)
