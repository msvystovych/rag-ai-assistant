"""Tests for the Homework #3 improved retrieval layer.

Every OpenAI call is mocked: the suite runs with no network and no OPENAI_API_KEY.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from rag_lib import (  # noqa: E402
    DOCUMENT_TYPE_KEYWORDS,
    Bm25Index,
    Chunk,
    RetrievalError,
    Settings,
    embed_texts,
    infer_document_type,
    load_chunks,
    open_collection,
    rrf_fuse,
    search,
    search_improved,
    write_manifest,
)
from rag_lib import _tokenize  # noqa: E402
from retrieval_improved import (  # noqa: E402
    CachingClient,
    aggregate,
    load_baseline,
    main,
    run_compare,
    top1_hit,
    top3_precision,
)

# The deterministic fake-embedding client is shared with the Homework #2 suite — same seam,
# same bag-of-characters projection, so rankings stay meaningful offline.
from test_retrieval import DIMENSION, FakeOpenAI  # noqa: E402


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
    # One chunk per document_type plus a second concept-guide chunk, so a filter leaves more
    # than one candidate and BM25 has something to rank inside the narrowed set.
    rows = [
        {
            "chunk_id": "primer_chunk_001",
            "text": "Primer > Backhaul. A backhaul is a return leg load so the truck avoids running empty.",
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
            "chunk_id": "primer_chunk_002",
            "text": "Primer > Settlement. Proof of delivery triggers settlement and carrier payment.",
            "metadata": {
                "document_id": "primer",
                "source_file": "data/raw/primer.md",
                "chunk_index": 2,
                "section": "Settlement",
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
            "chunk_id": "migration_chunk_001",
            "text": "Migration > Strangler. The strangler fig migration carves the monolith into services.",
            "metadata": {
                "document_id": "migration",
                "source_file": "data/raw/migration.md",
                "chunk_index": 1,
                "section": "Strangler",
                "title": "Migration",
                "document_type": "case-study",
            },
        },
        {
            "chunk_id": "scaling_chunk_001",
            "text": "Scaling > Deploys. Blue green deployment swaps traffic with zero downtime.",
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


def make_chunk(chunk_id: str, text: str, document_type: str = "concept-guide") -> Chunk:
    return Chunk(
        chunk_id=chunk_id, text=text, metadata={"document_type": document_type}
    )


class TestTokenize:
    def test_lowercases_and_drops_stopwords_and_punctuation(self) -> None:
        assert _tokenize("The Backhaul, and the Carrier!") == ["backhaul", "carrier"]

    def test_preserves_duplicates_for_term_frequency(self) -> None:
        assert _tokenize("load load truck") == ["load", "load", "truck"]


class TestInferDocumentType:
    @pytest.mark.parametrize(
        ("query", "expected"),
        [
            (
                "What is a backhaul and why does it matter to a carrier?",
                "concept-guide",
            ),
            ("How does CQRS event sourcing work?", "architecture-guide"),
            ("Migrating the monolith with the strangler pattern", "case-study"),
            ("Zero downtime deployment and caching", "playbook"),
        ],
    )
    def test_corpus_vocabulary_selects_the_matching_type(
        self, query: str, expected: str
    ) -> None:
        assert infer_document_type(query) == expected

    def test_out_of_corpus_query_matches_no_rule(self) -> None:
        # The real q10 — a filter here would funnel an unanswerable question into a document.
        assert (
            infer_document_type(
                "What is the best way to fine-tune a large language model on a custom dataset?"
            )
            is None
        )

    def test_ambiguous_vocabulary_matches_no_rule(self) -> None:
        # The real q05 — its wording is deliberately generic, so inference must abstain.
        assert (
            infer_document_type(
                "Why would you keep every change as a permanent record instead of just "
                "updating a row in a table?"
            )
            is None
        )

    def test_a_tie_between_types_abstains(self) -> None:
        assert infer_document_type("backhaul migration") is None

    def test_keyword_sets_are_pairwise_disjoint(self) -> None:
        # A keyword in two sets would make the tie rule fire unpredictably as the maps evolve.
        types = list(DOCUMENT_TYPE_KEYWORDS)
        for position, first in enumerate(types):
            for second in types[position + 1 :]:
                overlap = DOCUMENT_TYPE_KEYWORDS[first] & DOCUMENT_TYPE_KEYWORDS[second]
                assert not overlap, f"{first} and {second} share {sorted(overlap)}"


class TestBm25Index:
    def test_keyword_match_ranks_first_with_positive_score(self) -> None:
        chunks = [
            make_chunk("a", "backhaul return leg load"),
            make_chunk("b", "projections rebuild read models"),
        ]
        ranked = Bm25Index(chunks).top("backhaul load", k=2)
        assert ranked and ranked[0][0] == "a"
        assert ranked[0][1] > 0.0

    def test_allowed_ids_restricts_candidates_without_reintroducing_others(
        self,
    ) -> None:
        chunks = [
            make_chunk("a", "backhaul return leg"),
            make_chunk("b", "backhaul also here"),
        ]
        ranked = Bm25Index(chunks).top("backhaul", k=5, allowed_ids=frozenset({"b"}))
        assert [chunk_id for chunk_id, _ in ranked] == ["b"]

    def test_query_sharing_no_vocabulary_returns_nothing(self) -> None:
        index = Bm25Index([make_chunk("a", "backhaul return leg")])
        assert index.top("quantum chromodynamics", k=3) == []

    def test_stopword_only_query_returns_nothing(self) -> None:
        index = Bm25Index([make_chunk("a", "backhaul return leg")])
        assert index.top("the and of", k=3) == []

    def test_identical_documents_tie_break_on_chunk_id(self) -> None:
        chunks = [
            make_chunk("z_chunk", "backhaul return"),
            make_chunk("a_chunk", "backhaul return"),
        ]
        ranked = Bm25Index(chunks).top("backhaul", k=2)
        assert [chunk_id for chunk_id, _ in ranked] == ["a_chunk", "z_chunk"]

    def test_empty_chunk_list_is_a_diagnostic_error(self) -> None:
        with pytest.raises(RetrievalError, match="empty chunk list"):
            Bm25Index([])

    def test_matching_ids_selects_exactly_the_metadata_matches(self) -> None:
        chunks = [
            make_chunk("a", "text", document_type="concept-guide"),
            make_chunk("b", "text", document_type="playbook"),
            make_chunk("c", "text", document_type="concept-guide"),
        ]
        matched = Bm25Index(chunks).matching_ids("document_type", "concept-guide")
        assert matched == frozenset({"a", "c"})


class TestRrfFuse:
    def test_scores_sum_reciprocal_ranks_across_rankings(self) -> None:
        fused = dict(rrf_fuse([["a", "b"], ["b", "a"]]))
        assert fused["a"] == pytest.approx(1 / 61 + 1 / 62)
        assert fused["b"] == pytest.approx(1 / 62 + 1 / 61)

    def test_equal_scores_tie_break_on_chunk_id(self) -> None:
        fused = rrf_fuse([["a", "b"], ["b", "a"]])
        assert [chunk_id for chunk_id, _ in fused] == ["a", "b"]

    def test_single_ranking_preserves_its_order(self) -> None:
        fused = rrf_fuse([["x", "y", "z"]])
        assert [chunk_id for chunk_id, _ in fused] == ["x", "y", "z"]

    def test_id_present_in_one_ranking_only_scores_once(self) -> None:
        fused = dict(rrf_fuse([["a"], ["b"]]))
        assert fused["a"] == pytest.approx(1 / 61)
        assert fused["b"] == pytest.approx(1 / 61)


class TestSearchWhereFilter:
    def test_where_narrows_hits_to_the_matching_metadata(self, index: Settings) -> None:
        hits = search(
            "backhaul deployment projections",
            index,
            k=5,
            client=FakeOpenAI(),
            where={"document_type": "concept-guide"},
        )
        assert hits, "the filtered subset should still match"
        assert {hit.metadata["document_type"] for hit in hits} == {"concept-guide"}

    def test_unfiltered_search_spans_documents(self, index: Settings) -> None:
        hits = search(
            "backhaul deployment projections", index, k=5, client=FakeOpenAI()
        )
        assert len({hit.metadata["document_id"] for hit in hits}) > 1


class TestSearchImproved:
    def test_filter_constrains_both_branches(self, index: Settings) -> None:
        # 'deployment' is strong lexical bait for the playbook chunk; the concept-guide filter
        # must keep it out of the fused result even though BM25 would rank it.
        hits = search_improved(
            "backhaul deployment",
            index,
            k=5,
            client=FakeOpenAI(),
            document_type="concept-guide",
            hybrid=True,
        )
        assert hits
        assert {hit.metadata["document_type"] for hit in hits} == {"concept-guide"}

    def test_hybrid_hits_carry_fused_and_per_branch_fields(
        self, index: Settings
    ) -> None:
        hits = search_improved("backhaul truck", index, k=3, client=FakeOpenAI())
        assert [hit.rank for hit in hits] == list(range(1, len(hits) + 1))
        for hit in hits:
            assert hit.rrf_score is not None and hit.rrf_score > 0.0
            assert hit.semantic_rank is not None or hit.bm25_rank is not None
            assert hit.text and hit.metadata

    def test_non_hybrid_wraps_the_plain_filtered_search(self, index: Settings) -> None:
        hits = search_improved(
            "backhaul truck",
            index,
            k=2,
            client=FakeOpenAI(),
            document_type="concept-guide",
            hybrid=False,
        )
        assert hits
        for hit in hits:
            assert hit.rrf_score is None
            assert hit.bm25_rank is None
            assert hit.semantic_score is not None and hit.semantic_rank == hit.rank

    def test_results_are_deterministic_across_calls(self, index: Settings) -> None:
        first = [
            hit.chunk_id
            for hit in search_improved(
                "backhaul truck", index, k=3, client=FakeOpenAI()
            )
        ]
        second = [
            hit.chunk_id
            for hit in search_improved(
                "backhaul truck", index, k=3, client=FakeOpenAI()
            )
        ]
        assert first == second

    @pytest.mark.parametrize("bad_type", ["policy", ""])
    def test_unknown_document_type_is_a_diagnostic_error(
        self, index: Settings, bad_type: str
    ) -> None:
        # "" included: an explicitly empty CLI override must hit this diagnostic, never
        # silently fall back to inference.
        with pytest.raises(RetrievalError, match="unknown document_type"):
            search_improved(
                "backhaul", index, k=3, client=FakeOpenAI(), document_type=bad_type
            )


class TestCachingClient:
    def test_identical_inputs_hit_the_inner_client_once(self) -> None:
        inner = FakeOpenAI()
        caching = CachingClient(inner)
        first = caching.embeddings.create(model="m", input=["same"])
        second = caching.embeddings.create(model="m", input=["same"])
        assert first is second
        assert len(inner.calls) == 1

    def test_different_inputs_pass_through(self) -> None:
        inner = FakeOpenAI()
        caching = CachingClient(inner)
        caching.embeddings.create(model="m", input=["one"])
        caching.embeddings.create(model="m", input=["two"])
        assert len(inner.calls) == 2


class TestMetrics:
    def test_top1_hit_is_none_for_out_of_corpus_and_false_without_hits(self) -> None:
        assert top1_hit([{"document_id": "a"}], []) is None
        assert top1_hit([], ["a"]) is False
        assert top1_hit([{"document_id": "a"}], ["a"]) is True
        assert top1_hit([{"document_id": "b"}], ["a"]) is False

    def test_top3_precision_counts_expected_document_slots(self) -> None:
        hits = [{"document_id": "a"}, {"document_id": "b"}, {"document_id": "a"}]
        assert top3_precision(hits, ["a"]) == pytest.approx(2 / 3)
        assert top3_precision(hits, []) is None
        assert top3_precision([], ["a"]) == 0.0

    def test_aggregate_excludes_out_of_corpus_rows(self) -> None:
        rows: list[tuple[bool | None, float | None]] = [
            (True, 1.0),
            (False, 0.5),
            (None, None),
        ]
        hit_rate, precision, count = aggregate(rows)
        assert hit_rate == pytest.approx(0.5)
        assert precision == pytest.approx(0.75)
        assert count == 2


class TestBaselineLoading:
    def test_missing_baseline_names_the_remedial_command(
        self, settings: Settings, tmp_path: Path
    ) -> None:
        with pytest.raises(RetrievalError, match="git checkout"):
            load_baseline(tmp_path / "absent.json", settings, 3)

    def test_model_mismatch_refuses_the_comparison(
        self, settings: Settings, tmp_path: Path
    ) -> None:
        path = tmp_path / "baseline.json"
        path.write_text(
            json.dumps(
                {"model": "other-model", "k": 3, "records": [{"id": "q01", "hits": []}]}
            ),
            encoding="utf-8",
        )
        with pytest.raises(RetrievalError, match="apples to oranges"):
            load_baseline(path, settings, 3)

    def test_k_mismatch_refuses_the_comparison(
        self, settings: Settings, tmp_path: Path
    ) -> None:
        path = tmp_path / "baseline.json"
        path.write_text(
            json.dumps(
                {
                    "model": settings.embedding_model,
                    "k": 5,
                    "records": [{"id": "q01", "hits": []}],
                }
            ),
            encoding="utf-8",
        )
        with pytest.raises(RetrievalError, match="rank the same depth"):
            load_baseline(path, settings, 3)

    def test_corrupt_baseline_is_a_diagnostic_error(
        self, settings: Settings, tmp_path: Path
    ) -> None:
        path = tmp_path / "baseline.json"
        path.write_text("{not json", encoding="utf-8")
        with pytest.raises(RetrievalError, match="invalid JSON"):
            load_baseline(path, settings, 3)

    def test_missing_records_list_is_a_diagnostic_error(
        self, settings: Settings, tmp_path: Path
    ) -> None:
        path = tmp_path / "baseline.json"
        path.write_text(
            json.dumps({"model": settings.embedding_model, "k": 3}), encoding="utf-8"
        )
        with pytest.raises(RetrievalError, match="records"):
            load_baseline(path, settings, 3)

    def test_non_object_baseline_is_a_diagnostic_error(
        self, settings: Settings, tmp_path: Path
    ) -> None:
        path = tmp_path / "baseline.json"
        path.write_text(json.dumps([1, 2, 3]), encoding="utf-8")
        with pytest.raises(RetrievalError, match="expected a JSON object"):
            load_baseline(path, settings, 3)


def write_eval_files(
    tmp_path: Path, model: str, *, with_comments: bool
) -> tuple[Path, Path]:
    """A five-query eval set (load_queries requires >= 5) plus a matching fake baseline."""
    queries = []
    baseline_records = []
    cases = [
        ("q01", "direct", "What is a backhaul for a truck?", ["primer"]),
        ("q02", "direct", "How do projections rebuild read models?", ["cqrs"]),
        ("q03", "direct", "Zero downtime blue green deployment", ["scaling"]),
        ("q04", "direct", "What triggers settlement after delivery?", ["primer"]),
        ("q05", "out-of-corpus", "How do I bake sourdough bread?", []),
    ]
    for query_id, category, query, expected in cases:
        entry: dict[str, Any] = {
            "id": query_id,
            "category": category,
            "query": query,
            "expected_documents": expected,
        }
        if with_comments:
            entry["hw3_comment"] = f"authored judgement for {query_id}"
        queries.append(entry)
        baseline_records.append(
            {
                "id": query_id,
                "hits": [
                    {
                        "rank": 1,
                        "chunk_id": f"{query_id}_baseline_top1",
                        "score": 0.5,
                        "document_id": expected[0] if expected else "primer",
                    }
                ],
            }
        )
    payload: dict[str, Any] = {"queries": queries}
    if with_comments:
        payload["hw3_conclusion"] = "authored conclusion"
    queries_path = tmp_path / "queries.json"
    queries_path.write_text(json.dumps(payload), encoding="utf-8")
    baseline_path = tmp_path / "baseline.json"
    baseline_path.write_text(
        json.dumps({"model": model, "k": 3, "records": baseline_records}),
        encoding="utf-8",
    )
    return queries_path, baseline_path


class TestCompare:
    def test_compare_writes_both_artifacts_from_the_fake_baseline(
        self, index: Settings, tmp_path: Path
    ) -> None:
        queries_path, baseline_path = write_eval_files(
            tmp_path, index.embedding_model, with_comments=True
        )
        output_path = tmp_path / "comparison.md"
        results_path = tmp_path / "results.json"
        exit_code = run_compare(
            index,
            queries_path,
            baseline_path,
            output_path,
            results_path,
            3,
            client=FakeOpenAI(),
        )
        assert exit_code == 0
        rendered = output_path.read_text(encoding="utf-8")
        assert rendered.count("| q0") == 5
        assert "authored judgement for q01" in rendered
        assert "authored conclusion" in rendered
        results = json.loads(results_path.read_text(encoding="utf-8"))
        assert set(results["aggregates"]) == {
            "baseline",
            "filter-only",
            "hybrid-only",
            "combined",
        }
        assert [record["baseline_top1"] for record in results["records"]] == [
            f"q0{position}_baseline_top1" for position in range(1, 6)
        ]

    def test_missing_comments_are_reported_not_rendered_as_placeholders(
        self, index: Settings, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        queries_path, baseline_path = write_eval_files(
            tmp_path, index.embedding_model, with_comments=False
        )
        exit_code = run_compare(
            index,
            queries_path,
            baseline_path,
            tmp_path / "c.md",
            tmp_path / "r.json",
            3,
            client=FakeOpenAI(),
        )
        assert exit_code == 0
        captured = capsys.readouterr()
        assert "empty hw3_comment" in captured.err
        assert "hw3_conclusion is still empty" in captured.err

    def test_baseline_missing_a_query_id_refuses(
        self, index: Settings, tmp_path: Path
    ) -> None:
        queries_path, baseline_path = write_eval_files(
            tmp_path, index.embedding_model, with_comments=True
        )
        payload = json.loads(baseline_path.read_text(encoding="utf-8"))
        payload["records"] = payload["records"][:-1]
        baseline_path.write_text(json.dumps(payload), encoding="utf-8")
        with pytest.raises(RetrievalError, match="has no record for: q05"):
            run_compare(
                index,
                queries_path,
                baseline_path,
                tmp_path / "c.md",
                tmp_path / "r.json",
                3,
                client=FakeOpenAI(),
            )

    def test_refuses_to_overwrite_the_baseline_file(
        self, index: Settings, tmp_path: Path
    ) -> None:
        queries_path, baseline_path = write_eval_files(
            tmp_path, index.embedding_model, with_comments=True
        )
        with pytest.raises(RetrievalError, match="refusing to overwrite"):
            run_compare(
                index,
                queries_path,
                baseline_path,
                tmp_path / "c.md",
                baseline_path,
                3,
                client=FakeOpenAI(),
            )
        assert json.loads(baseline_path.read_text(encoding="utf-8"))["records"], (
            "the baseline file must be untouched after the refusal"
        )

    def test_refuses_colliding_output_and_results_paths(
        self, index: Settings, tmp_path: Path
    ) -> None:
        queries_path, baseline_path = write_eval_files(
            tmp_path, index.embedding_model, with_comments=True
        )
        with pytest.raises(RetrievalError, match="same file"):
            run_compare(
                index,
                queries_path,
                baseline_path,
                tmp_path / "collide.md",
                tmp_path / "collide.md",
                3,
                client=FakeOpenAI(),
            )

    def test_query_text_diverging_from_baseline_refuses(
        self, index: Settings, tmp_path: Path
    ) -> None:
        queries_path, baseline_path = write_eval_files(
            tmp_path, index.embedding_model, with_comments=True
        )
        payload = json.loads(baseline_path.read_text(encoding="utf-8"))
        for record in payload["records"]:
            record["query"] = "a different question entirely"
        baseline_path.write_text(json.dumps(payload), encoding="utf-8")
        with pytest.raises(RetrievalError, match="must ask the same questions"):
            run_compare(
                index,
                queries_path,
                baseline_path,
                tmp_path / "c.md",
                tmp_path / "r.json",
                3,
                client=FakeOpenAI(),
            )


class TestCliValidation:
    def test_query_and_compare_are_mutually_exclusive(self) -> None:
        with pytest.raises(SystemExit) as excinfo:
            main(["--query", "x", "--compare"])
        assert excinfo.value.code == 2

    def test_neither_query_nor_compare_is_an_error(self) -> None:
        with pytest.raises(SystemExit) as excinfo:
            main([])
        assert excinfo.value.code == 2

    def test_query_mode_flags_are_rejected_in_compare_mode(self) -> None:
        with pytest.raises(SystemExit) as excinfo:
            main(["--compare", "--json"])
        assert excinfo.value.code == 2

    def test_document_type_conflicts_with_no_filter(self) -> None:
        with pytest.raises(SystemExit) as excinfo:
            main(["--query", "x", "--document-type", "playbook", "--no-filter"])
        assert excinfo.value.code == 2

    @pytest.mark.parametrize("bad_k", ["0", "-1"])
    def test_non_positive_k_is_an_error(self, bad_k: str) -> None:
        with pytest.raises(SystemExit) as excinfo:
            main(["--query", "x", "--k", bad_k])
        assert excinfo.value.code == 2
