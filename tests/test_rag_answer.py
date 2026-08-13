"""Tests for the Homework #4 grounded answer layer.

Every OpenAI call is mocked — embeddings and chat alike: the suite runs with no network and no
OPENAI_API_KEY. The chat fake extends the Homework #2 fake through the same duck-typed `client=`
seam the production code uses, so nothing here patches the SDK.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from openai import OpenAIError

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import rag_answer  # noqa: E402
from rag_answer import (  # noqa: E402
    DEFAULT_MIN_SCORE,
    INSUFFICIENT_CONTEXT_ANSWER,
    PROMPT_VERSIONS,
    PROTECTED_OUTPUTS,
    answer_question,
    extract_citations,
    generate,
    get_template,
    guard_outputs,
    main,
    render_context,
    run_evaluate,
    run_query,
    run_improvements,
    top_semantic_score,
)
from rag_lib import (  # noqa: E402
    HybridHit,
    RetrievalError,
    Settings,
    embed_texts,
    load_chunks,
    open_collection,
    write_manifest,
)

# The deterministic fake-embedding client is shared with the Homework #2 suite — same seam, same
# bag-of-characters projection, so retrieval rankings stay meaningful offline.
from test_retrieval import DIMENSION, FakeOpenAI  # noqa: E402


@dataclass
class FakeMessage:
    content: str | None


@dataclass
class FakeChoice:
    message: FakeMessage


@dataclass
class FakeChatResponse:
    choices: list[FakeChoice]


class FakeCompletions:
    def __init__(self, owner: FakeAnswerClient) -> None:
        self._owner = owner

    def create(
        self, *, model: str, messages: list[dict[str, str]], temperature: float
    ) -> FakeChatResponse:
        if self._owner.fails_with is not None:
            raise self._owner.fails_with
        position = len(self._owner.chat_calls)
        self._owner.chat_calls.append((model, messages, temperature))
        # The last reply repeats, so a test making one call needs to supply only one.
        reply = self._owner.replies[min(position, len(self._owner.replies) - 1)]
        return FakeChatResponse([FakeChoice(FakeMessage(reply))])


class FakeChat:
    def __init__(self, owner: FakeAnswerClient) -> None:
        self.completions = FakeCompletions(owner)


class _NoChoices:
    """A completions surface returning an empty choices array — the SDK shape that would
    otherwise surface as a bare IndexError past the entrypoint's boundary catch."""

    def create(
        self, *, model: str, messages: list[dict[str, str]], temperature: float
    ) -> FakeChatResponse:
        return FakeChatResponse([])


class FakeAnswerClient(FakeOpenAI):
    """FakeOpenAI plus a chat surface.

    Chat calls record into `chat_calls`, never into the inherited `calls`: four Homework #2/#3
    tests assert on len(calls) to prove embedding batching, and retrieval_improved.CachingClient
    copies only `.embeddings`. Mixing the two logs would break both.
    """

    def __init__(
        self, *replies: str | None, fails_with: OpenAIError | None = None
    ) -> None:
        super().__init__()
        self.chat_calls: list[tuple[str, list[dict[str, str]], float]] = []
        self.replies: list[str | None] = list(replies) or ["A grounded answer."]
        self.fails_with = fails_with
        self.chat = FakeChat(self)

    def last_prompt(self) -> str:
        return "\n".join(part["content"] for part in self.chat_calls[-1][1])


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        openai_api_key="test-key",
        embedding_model="text-embedding-3-small",
        answer_model="gpt-4.1-mini",
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


@pytest.fixture
def queries_file(tmp_path: Path) -> Path:
    # q01/q05/q10 are the ids IMPROVEMENT_CASES compares prompts on; the other two exist because
    # load_queries requires at least five entries.
    payload = {
        "description": "offline fixture",
        "hw4_conclusion": "",
        "queries": [
            {
                "id": "q01",
                "category": "direct",
                "query": "What is a backhaul?",
                "expected_documents": ["primer"],
                "hw4_comment": "Grounded and cited.",
            },
            {
                "id": "q05",
                "category": "paraphrase",
                "query": "Why keep every change as a permanent record?",
                "expected_documents": ["cqrs"],
                "hw4_comment": "Mixed context, answer stayed inside it.",
            },
            {
                "id": "q07",
                "category": "cross-document",
                "query": "How is data kept consistent during a migration?",
                "expected_documents": ["migration"],
                "hw4_comment": "Right document.",
            },
            {
                "id": "q09",
                "category": "direct",
                "query": "What triggers settlement?",
                "expected_documents": ["primer"],
                "hw4_comment": "Correct section.",
            },
            {
                "id": "q10",
                "category": "out-of-corpus",
                "query": "How do I fine-tune a large language model?",
                "expected_documents": [],
                "hw4_comment": "Refused, as designed.",
            },
        ],
    }
    path = tmp_path / "test_queries.json"
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def make_hit(
    chunk_id: str,
    *,
    semantic_score: float | None = 0.50,
    rank: int = 1,
    text: str = "A backhaul is a return leg load.",
    source_file: str = "data/raw/primer.md",
    section: str = "Backhaul",
) -> HybridHit:
    return HybridHit(
        rank=rank,
        chunk_id=chunk_id,
        rrf_score=0.03,
        semantic_score=semantic_score,
        semantic_rank=rank if semantic_score is not None else None,
        bm25_rank=rank,
        text=text,
        metadata={
            "source_file": source_file,
            "section": section,
            "document_id": chunk_id.split("_chunk_")[0],
        },
    )


class TestPromptVersions:
    def test_v1_is_the_unimproved_baseline(self) -> None:
        template = get_template("v1")

        assert template.system == "", "v1 deliberately has no role instruction"
        assert "only" not in template.user_template.lower()
        assert "cite" not in template.user_template.lower()

    def test_v2_adds_grounding_and_refusal(self) -> None:
        template = get_template("v2")

        assert template.system
        assert "using only the provided context" in template.user_template
        assert INSUFFICIENT_CONTEXT_ANSWER in template.user_template

    def test_v3_adds_the_citation_requirement(self) -> None:
        template = get_template("v3")

        assert "square brackets" in template.user_template
        assert "Never cite an id that is not in the context." in template.user_template
        assert "general knowledge" in template.user_template
        assert INSUFFICIENT_CONTEXT_ANSWER in template.user_template

    @pytest.mark.parametrize("version", sorted(PROMPT_VERSIONS))
    def test_every_version_carries_both_placeholders(self, version: str) -> None:
        template = get_template(version)

        assert "{context}" in template.user_template
        assert "{question}" in template.user_template

    @pytest.mark.parametrize("bad_version", ["v4", "", "V3"])
    def test_unknown_version_is_a_diagnostic_error(self, bad_version: str) -> None:
        with pytest.raises(RetrievalError, match="unknown prompt version"):
            get_template(bad_version)


class TestRenderContext:
    def test_each_chunk_is_headed_by_the_id_the_model_must_cite(self) -> None:
        block = render_context([make_hit("primer_chunk_001")])

        assert block.startswith("[primer_chunk_001]")

    def test_context_carries_source_file_and_section(self) -> None:
        block = render_context([make_hit("primer_chunk_001")])

        assert "source_file: data/raw/primer.md" in block
        assert "section: Backhaul" in block


class TestScoreFloor:
    def test_top_score_ignores_bm25_only_hits(self) -> None:
        hits = [
            make_hit("primer_chunk_001", semantic_score=None, rank=1),
            make_hit("cqrs_chunk_001", semantic_score=0.41, rank=2),
        ]

        assert top_semantic_score(hits) == pytest.approx(0.41)

    def test_a_wholly_bm25_set_carries_no_semantic_evidence(self) -> None:
        hits = [make_hit("primer_chunk_001", semantic_score=None)]

        assert top_semantic_score(hits) is None

    def test_score_above_the_floor_passes_the_context(self, settings: Settings) -> None:
        client = FakeAnswerClient("Grounded [primer_chunk_001].")

        result = generate(
            "What is a backhaul?",
            [make_hit("primer_chunk_001", semantic_score=0.42)],
            settings,
            client=client,
            min_score=DEFAULT_MIN_SCORE,
        )

        assert result.context_used
        assert "[primer_chunk_001]" in client.last_prompt()

    def test_score_below_the_floor_empties_the_context(
        self, settings: Settings
    ) -> None:
        client = FakeAnswerClient(INSUFFICIENT_CONTEXT_ANSWER)

        result = generate(
            "How do I fine-tune a language model?",
            [make_hit("primer_chunk_001", semantic_score=0.266)],
            settings,
            client=client,
            min_score=DEFAULT_MIN_SCORE,
        )

        assert not result.context_used
        assert result.top_semantic_score == pytest.approx(0.266)
        assert rag_answer.EMPTY_CONTEXT in client.last_prompt()
        assert "A backhaul is a return leg load." not in client.last_prompt(), (
            "a chunk below the floor must not reach the model"
        )

    def test_a_bm25_only_set_empties_the_context(self, settings: Settings) -> None:
        client = FakeAnswerClient(INSUFFICIENT_CONTEXT_ANSWER)

        result = generate(
            "anything",
            [make_hit("primer_chunk_001", semantic_score=None)],
            settings,
            client=client,
            min_score=DEFAULT_MIN_SCORE,
        )

        assert not result.context_used

    def test_disabled_floor_always_passes_the_context(
        self, settings: Settings
    ) -> None:
        client = FakeAnswerClient("Answer.")

        result = generate(
            "anything",
            [make_hit("primer_chunk_001", semantic_score=0.01)],
            settings,
            client=client,
            min_score=None,
        )

        assert result.context_used
        assert "[primer_chunk_001]" in client.last_prompt()


class TestCitations:
    def test_only_supplied_ids_count_as_citations(self) -> None:
        hits = [make_hit("primer_chunk_001")]

        cited, fabricated = extract_citations(
            "The definition is here [primer_chunk_001].", hits
        )

        assert cited == ("primer_chunk_001",)
        assert fabricated == ()

    def test_an_invented_id_is_reported_separately(self) -> None:
        hits = [make_hit("primer_chunk_001")]

        cited, fabricated = extract_citations(
            "See [primer_chunk_001] and [vacation_policy_chunk_009].", hits
        )

        assert cited == ("primer_chunk_001",)
        assert fabricated == ("vacation_policy_chunk_009",), (
            "an id that was never supplied is a hallucination, not a citation"
        )

    def test_a_repeated_citation_is_reported_once(self) -> None:
        hits = [make_hit("primer_chunk_001")]

        cited, _ = extract_citations(
            "[primer_chunk_001] says X, and [primer_chunk_001] adds Y.", hits
        )

        assert cited == ("primer_chunk_001",)

    @pytest.mark.parametrize(
        "answer",
        [
            "See [primer_chunk_001, cqrs_chunk_001] for both halves.",
            "See [primer_chunk_001; cqrs_chunk_001].",
            "See [`primer_chunk_001`] and [`cqrs_chunk_001`].",
            "See [primer_chunk_001] and [cqrs_chunk_001].",
        ],
    )
    def test_multi_id_and_backticked_citations_are_all_found(
        self, answer: str
    ) -> None:
        # A one-id-per-bracket regex dropped BOTH ids of a comma list and every backticked id.
        # Silent undercounting is worst in the fabricated direction, where a missed id is a
        # hallucination going unreported in the graded aggregate.
        hits = [make_hit("primer_chunk_001"), make_hit("cqrs_chunk_001", rank=2)]

        cited, fabricated = extract_citations(answer, hits)

        assert set(cited) == {"primer_chunk_001", "cqrs_chunk_001"}
        assert fabricated == ()

    def test_an_invented_id_inside_a_multi_id_citation_is_still_caught(self) -> None:
        hits = [make_hit("primer_chunk_001")]

        cited, fabricated = extract_citations(
            "See [primer_chunk_001, vacation_policy_chunk_009].", hits
        )

        assert cited == ("primer_chunk_001",)
        assert fabricated == ("vacation_policy_chunk_009",)

    def test_bracketed_prose_is_not_mistaken_for_a_citation(self) -> None:
        cited, fabricated = extract_citations(
            "The load [see the settlement section] expires.", [make_hit("a_chunk_001")]
        )

        assert cited == ()
        assert fabricated == (), "only ids matching the chunk_id schema count"

    def test_prose_without_markers_yields_no_citation(self) -> None:
        cited, fabricated = extract_citations(
            "A backhaul is a return load.", [make_hit("primer_chunk_001")]
        )

        assert cited == ()
        assert fabricated == ()

    def test_a_refusal_over_empty_context_carries_no_citation(
        self, settings: Settings
    ) -> None:
        # Below the floor the chunk never reaches the model, so any id in the answer would be
        # invented — crediting it as a citation would make the citation rate meaningless.
        client = FakeAnswerClient(f"{INSUFFICIENT_CONTEXT_ANSWER} [primer_chunk_001]")

        result = generate(
            "unanswerable",
            [make_hit("primer_chunk_001", semantic_score=0.1)],
            settings,
            client=client,
            min_score=DEFAULT_MIN_SCORE,
        )

        assert result.cited_chunk_ids == ()
        assert result.fabricated_citations == ("primer_chunk_001",)
        assert result.source_files() == (), (
            "a chunk the model never saw is not a source of its refusal"
        )


class TestGenerate:
    def test_answer_records_the_model_and_prompt_version(
        self, settings: Settings
    ) -> None:
        client = FakeAnswerClient("Answer [primer_chunk_001].")

        result = generate(
            "q", [make_hit("primer_chunk_001")], settings, client=client, min_score=None
        )

        assert result.answer_model == "gpt-4.1-mini"
        assert result.prompt_version == "v3"
        assert client.chat_calls[0][0] == "gpt-4.1-mini"

    def test_temperature_is_pinned_to_zero(self, settings: Settings) -> None:
        client = FakeAnswerClient("Answer.")

        generate("q", [make_hit("a_chunk_001")], settings, client=client, min_score=None)

        assert client.chat_calls[0][2] == 0.0, (
            "committed answers must be reproducible, so decoding stays greedy"
        )

    def test_refusal_is_detected_from_the_answer_text(
        self, settings: Settings
    ) -> None:
        client = FakeAnswerClient(INSUFFICIENT_CONTEXT_ANSWER)

        result = generate(
            "q", [make_hit("a_chunk_001")], settings, client=client, min_score=None
        )

        assert result.refused

    def test_a_grounded_answer_is_not_marked_refused(self, settings: Settings) -> None:
        client = FakeAnswerClient("A backhaul is a return leg load [a_chunk_001].")

        result = generate(
            "q", [make_hit("a_chunk_001")], settings, client=client, min_score=None
        )

        assert not result.refused

    def test_v1_prompt_reaches_the_model_unchanged(self, settings: Settings) -> None:
        client = FakeAnswerClient("Answer.")

        generate(
            "What is a backhaul?",
            [make_hit("primer_chunk_001")],
            settings,
            client=client,
            prompt_version="v1",
            min_score=None,
        )

        model, messages, _ = client.chat_calls[0]
        assert len(messages) == 1, "v1 has no system message"
        assert messages[0]["content"].startswith("Answer the question using the context.")

    def test_braces_in_chunk_text_do_not_break_prompt_building(
        self, settings: Settings
    ) -> None:
        # Corpus prose can contain braces (a JSON snippet, a code sample). str.format would raise
        # KeyError on it; the production code uses str.replace for exactly this reason.
        client = FakeAnswerClient("Answer.")

        generate(
            "q",
            [make_hit("a_chunk_001", text='A payload like {"id": 1} is stored verbatim.')],
            settings,
            client=client,
            min_score=None,
        )

        assert '{"id": 1}' in client.last_prompt()

    def test_a_chunk_containing_the_question_placeholder_is_not_rewritten(
        self, settings: Settings
    ) -> None:
        # Two chained str.replace calls would substitute this, because the second pass scans the
        # corpus text the first pass just inserted. One pass over the template cannot.
        client = FakeAnswerClient("Answer.")

        generate(
            "What is a backhaul?",
            [make_hit("a_chunk_001", text="A template uses {question} as its slot.")],
            settings,
            client=client,
            min_score=None,
        )

        prompt = client.last_prompt()
        assert "A template uses {question} as its slot." in prompt
        assert prompt.count("What is a backhaul?") == 1, (
            "the question must appear only where the template put it"
        )

    def test_a_response_without_choices_is_a_diagnostic_error(
        self, settings: Settings
    ) -> None:
        client = FakeAnswerClient()
        client.chat.completions = _NoChoices()  # type: ignore[assignment]

        with pytest.raises(RetrievalError, match="returned no choices"):
            generate(
                "q", [make_hit("a_chunk_001")], settings, client=client, min_score=None
            )

    def test_api_failure_becomes_a_diagnostic_naming_the_remedy(
        self, settings: Settings
    ) -> None:
        client = FakeAnswerClient(fails_with=OpenAIError("model_not_found"))

        with pytest.raises(RetrievalError, match="RAG_ANSWER_MODEL"):
            generate(
                "q", [make_hit("a_chunk_001")], settings, client=client, min_score=None
            )

    def test_an_empty_completion_is_a_diagnostic_error(
        self, settings: Settings
    ) -> None:
        client = FakeAnswerClient(None)

        with pytest.raises(RetrievalError, match="returned an empty answer"):
            generate(
                "q", [make_hit("a_chunk_001")], settings, client=client, min_score=None
            )


class TestSourceFiles:
    def test_sources_come_from_the_cited_chunks(self, settings: Settings) -> None:
        hits = [
            make_hit("primer_chunk_001", rank=1, source_file="data/raw/primer.md"),
            make_hit("cqrs_chunk_001", rank=2, source_file="data/raw/cqrs.md"),
        ]
        client = FakeAnswerClient("Only this one matters [cqrs_chunk_001].")

        result = generate("q", hits, settings, client=client, min_score=None)

        assert result.source_files() == ("data/raw/cqrs.md",)

    def test_sources_fall_back_to_every_retrieved_chunk_when_nothing_was_cited(
        self, settings: Settings
    ) -> None:
        hits = [
            make_hit("primer_chunk_001", rank=1, source_file="data/raw/primer.md"),
            make_hit("cqrs_chunk_001", rank=2, source_file="data/raw/cqrs.md"),
            make_hit("primer_chunk_002", rank=3, source_file="data/raw/primer.md"),
        ]
        client = FakeAnswerClient("No markers at all.")

        result = generate("q", hits, settings, client=client, min_score=None)

        assert result.source_files() == ("data/raw/primer.md", "data/raw/cqrs.md"), (
            "every retrieved source is reported, in rank order, with duplicates collapsed"
        )

    def test_a_refusal_over_a_NON_empty_context_still_names_no_source(
        self, settings: Settings
    ) -> None:
        # Found by running --no-min-score against the out-of-corpus question: the floor was off, so
        # the model DID receive three off-topic chunks and refused anyway. The uncited fallback then
        # credited both source documents for an answer that explicitly declined to use them.
        client = FakeAnswerClient(INSUFFICIENT_CONTEXT_ANSWER)

        result = generate(
            "unanswerable",
            [
                make_hit("migration_chunk_013", semantic_score=0.244, rank=1),
                make_hit("cqrs_chunk_002", semantic_score=0.222, rank=2, source_file="data/raw/cqrs.md"),
            ],
            settings,
            client=client,
            min_score=None,
        )

        assert result.context_used, "the floor is disabled, so the chunks did reach the model"
        assert result.refused
        assert result.cited_chunk_ids == ()
        assert result.source_files() == (), (
            "a refusal names no source even when it was shown a context"
        )

    def test_an_uncited_answer_still_falls_back_to_every_retrieved_source(
        self, settings: Settings
    ) -> None:
        # The counterpart to the test above: the fallback must survive for real answers, otherwise
        # suppressing it for refusals would silently strip sources from uncited good answers too.
        client = FakeAnswerClient("A backhaul is a return leg load.")

        result = generate(
            "q",
            [make_hit("primer_chunk_001"), make_hit("cqrs_chunk_001", rank=2, source_file="data/raw/cqrs.md")],
            settings,
            client=client,
            min_score=None,
        )

        assert not result.refused
        assert result.source_files() == ("data/raw/primer.md", "data/raw/cqrs.md")

    def test_a_withheld_context_reports_no_source_anywhere(
        self, settings: Settings
    ) -> None:
        # The gate lives inside source_files() rather than at each call site: the JSON payloads
        # and the Markdown renderers must not disagree about what sourced a refusal.
        client = FakeAnswerClient(INSUFFICIENT_CONTEXT_ANSWER)

        result = generate(
            "unanswerable",
            [make_hit("primer_chunk_001", semantic_score=0.2)],
            settings,
            client=client,
            min_score=DEFAULT_MIN_SCORE,
        )

        assert not result.context_used
        assert result.hits, "the hits are still recorded for diagnostics"
        assert result.source_files() == ()


class TestAnswerQuestion:
    def test_the_pipeline_answers_from_the_index(self, index: Settings) -> None:
        client = FakeAnswerClient("A backhaul is a return leg load [primer_chunk_001].")

        result = answer_question("backhaul return load", index, k=3, client=client)

        assert result.hits, "retrieval must reach the index"
        assert result.answer.endswith("[primer_chunk_001].")
        assert len(client.chat_calls) == 1, "one question means one chat call"



class TestRunQuery:
    def test_text_mode_prints_the_spec_mandated_lines(
        self, index: Settings, capsys: pytest.CaptureFixture[str]
    ) -> None:
        exit_code = run_query(
            index,
            "backhaul return load",
            3,
            prompt_version="v3",
            min_score=None,
            as_json=False,
            client=FakeAnswerClient("A return leg load [primer_chunk_001]."),
        )

        printed = capsys.readouterr().out
        assert exit_code == 0
        for key in ("Question: ", "Retrieved chunks: ", "Answer: ", "Source: "):
            assert key in printed
        assert "[primer_chunk_001]" in printed

    def test_json_mode_emits_the_full_payload(
        self, index: Settings, capsys: pytest.CaptureFixture[str]
    ) -> None:
        run_query(
            index,
            "backhaul return load",
            3,
            prompt_version="v3",
            min_score=None,
            as_json=True,
            client=FakeAnswerClient("A return leg load [primer_chunk_001]."),
        )

        payload = json.loads(capsys.readouterr().out)
        assert payload["answer_model"] == "gpt-4.1-mini"
        assert payload["prompt_version"] == "v3"
        assert payload["cited_chunk_ids"] == ["primer_chunk_001"]
        assert payload["retrieved_chunks"]

    def test_json_mode_reports_no_source_for_a_withheld_context(
        self, index: Settings, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # The machine-readable surface must agree with the human-readable one: a refusal produced
        # from an empty context has no sources. A floor of 1.0 is unreachable, so nothing passes.
        run_query(
            index,
            "backhaul return load",
            3,
            prompt_version="v3",
            min_score=1.0,
            as_json=True,
            client=FakeAnswerClient(INSUFFICIENT_CONTEXT_ANSWER),
        )

        payload = json.loads(capsys.readouterr().out)
        assert payload["context_used"] is False
        assert payload["refused"] is True
        assert payload["source_files"] == []


class TestGuardOutputs:
    def test_every_graded_artifact_is_on_the_protected_list(self) -> None:
        # Parametrizing over PROTECTED_OUTPUTS alone would pass even if an entry were deleted —
        # the parametrization would just shrink. This pins the membership, which is the asset.
        assert {
            "test_queries.json",
            "retrieval_results.json",
            "retrieval_results_improved.json",
            "retrieval_examples.md",
            "retrieval_comparison.md",
            "chunk_size_experiment.md",
        } <= {path.name for path in PROTECTED_OUTPUTS}

    @pytest.mark.parametrize("protected", PROTECTED_OUTPUTS, ids=lambda p: p.name)
    def test_a_graded_deliverable_is_never_overwritten(self, protected: Path) -> None:
        with pytest.raises(RetrievalError, match="refusing to overwrite"):
            guard_outputs({"--output": protected})

    def test_writing_over_the_input_question_file_is_refused(
        self, tmp_path: Path
    ) -> None:
        # The graded question file is what this run READS, which is exactly why an --output typo
        # aimed at it would destroy the source of the run producing the output.
        questions = tmp_path / "my_queries.json"

        with pytest.raises(RetrievalError, match="the question file this run reads"):
            guard_outputs({"--output": questions}, reads=questions)

    def test_two_outputs_at_the_same_path_are_rejected(self, tmp_path: Path) -> None:
        collision = tmp_path / "same.md"

        with pytest.raises(RetrievalError, match="point at the same file"):
            guard_outputs({"--output": collision, "--results": collision})

    def test_distinct_unprotected_paths_are_accepted(self, tmp_path: Path) -> None:
        guard_outputs(
            {"--output": tmp_path / "a.md", "--results": tmp_path / "b.json"}
        )


class TestEvaluate:
    def test_writes_both_artifacts_with_the_spec_mandated_keys(
        self, index: Settings, queries_file: Path, tmp_path: Path
    ) -> None:
        output = tmp_path / "answers.md"
        results = tmp_path / "answers.json"

        exit_code = run_evaluate(
            index,
            queries_file,
            output,
            results,
            3,
            prompt_version="v3",
            min_score=None,
            client=FakeAnswerClient("Grounded [primer_chunk_001]."),
        )

        assert exit_code == 0
        rendered = output.read_text(encoding="utf-8")
        for key in ("Question: ", "Retrieved chunks: ", "Answer: ", "Source: ", "Comment: "):
            assert rendered.count(f"\n{key}") >= 5, f"missing {key!r} for some question"
        payload = json.loads(results.read_text(encoding="utf-8"))
        assert payload["answer_model"] == "gpt-4.1-mini"
        assert payload["aggregates"]["questions"] == 5
        assert len(payload["records"]) == 5
        # semantic_rank is what makes the floor's calibration mismatch auditable after the run;
        # the design doc's known-limits section points a reader at this field by name.
        assert all(
            "semantic_rank" in chunk
            for record in payload["records"]
            for chunk in record["retrieved_chunks"]
        )

    def test_missing_comments_are_reported_not_rendered_as_placeholders(
        self,
        index: Settings,
        queries_file: Path,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        payload = json.loads(queries_file.read_text(encoding="utf-8"))
        payload["queries"][0]["hw4_comment"] = ""
        queries_file.write_text(json.dumps(payload), encoding="utf-8")

        run_evaluate(
            index,
            queries_file,
            tmp_path / "answers.md",
            tmp_path / "answers.json",
            3,
            prompt_version="v3",
            min_score=None,
            client=FakeAnswerClient("Answer."),
        )

        captured = capsys.readouterr()
        assert "empty hw4_comment" in captured.err
        assert "q01" in captured.err
        rendered = (tmp_path / "answers.md").read_text(encoding="utf-8")
        for placeholder in ("TBD", "TODO", "n/a"):
            assert placeholder not in rendered

    def test_the_conclusion_is_reported_when_still_empty(
        self,
        index: Settings,
        queries_file: Path,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        run_evaluate(
            index,
            queries_file,
            tmp_path / "answers.md",
            tmp_path / "answers.json",
            3,
            prompt_version="v3",
            min_score=None,
            client=FakeAnswerClient("Answer."),
        )

        assert "hw4_conclusion is still empty" in capsys.readouterr().err

    def test_refuses_to_overwrite_a_graded_deliverable(
        self, index: Settings, queries_file: Path, tmp_path: Path
    ) -> None:
        with pytest.raises(RetrievalError, match="refusing to overwrite"):
            run_evaluate(
                index,
                queries_file,
                PROTECTED_OUTPUTS[2],
                tmp_path / "answers.json",
                3,
                prompt_version="v3",
                min_score=None,
                client=FakeAnswerClient("Answer."),
            )


class TestImprovements:
    def test_each_case_generates_twice_over_one_retrieval(
        self, index: Settings, queries_file: Path, tmp_path: Path
    ) -> None:
        client = FakeAnswerClient("Answer.")

        exit_code = run_improvements(
            index,
            queries_file,
            tmp_path / "improvements.md",
            3,
            min_score=None,
            client=client,
        )

        assert exit_code == 0
        assert len(client.chat_calls) == 2 * len(rag_answer.IMPROVEMENT_CASES)
        assert len(client.calls) == len(rag_answer.IMPROVEMENT_CASES), (
            "each case embeds its question once, so both prompt versions see identical context"
        )

    def test_renders_before_and_after_answers_per_case(
        self, index: Settings, queries_file: Path, tmp_path: Path
    ) -> None:
        output = tmp_path / "improvements.md"

        run_improvements(
            index,
            queries_file,
            output,
            3,
            min_score=None,
            client=FakeAnswerClient("first answer", "second answer"),
        )

        rendered = output.read_text(encoding="utf-8")
        for case in rag_answer.IMPROVEMENT_CASES:
            assert case.case_id in rendered
            assert case.tests in rendered
        assert "first answer" in rendered
        assert "second answer" in rendered

    def test_a_case_whose_query_is_absent_is_a_diagnostic_error(
        self, index: Settings, queries_file: Path, tmp_path: Path
    ) -> None:
        payload = json.loads(queries_file.read_text(encoding="utf-8"))
        payload["queries"] = [
            entry for entry in payload["queries"] if entry["id"] != "q10"
        ]
        payload["queries"].append(
            {"id": "q11", "category": "direct", "query": "filler", "hw4_comment": "x"}
        )
        queries_file.write_text(json.dumps(payload), encoding="utf-8")

        with pytest.raises(RetrievalError, match="has no query 'q10'"):
            run_improvements(
                index,
                queries_file,
                tmp_path / "improvements.md",
                3,
                min_score=None,
                client=FakeAnswerClient("Answer."),
            )


class TestCliValidation:
    @pytest.mark.parametrize(
        "argv",
        [
            [],
            ["--query", "x", "--evaluate"],
            ["--evaluate", "--improvements"],
            ["--query", "x", "--improvements"],
        ],
    )
    def test_exactly_one_mode_is_required(self, argv: list[str]) -> None:
        with pytest.raises(SystemExit) as excinfo:
            main(argv)

        assert excinfo.value.code == 2

    @pytest.mark.parametrize("bad_k", ["0", "-1"])
    def test_non_positive_k_is_an_error(self, bad_k: str) -> None:
        with pytest.raises(SystemExit) as excinfo:
            main(["--query", "x", "--k", bad_k])

        assert excinfo.value.code == 2

    def test_min_score_conflicts_with_no_min_score(self) -> None:
        with pytest.raises(SystemExit) as excinfo:
            main(["--query", "x", "--min-score", "0.4", "--no-min-score"])

        assert excinfo.value.code == 2

    def test_json_is_rejected_outside_query_mode(self) -> None:
        with pytest.raises(SystemExit) as excinfo:
            main(["--evaluate", "--json"])

        assert excinfo.value.code == 2

    def test_an_unknown_prompt_version_is_rejected_by_argparse(self) -> None:
        # argparse `choices` rather than a boundary raise, so this exits 2 like every other
        # input-validation failure instead of 1.
        with pytest.raises(SystemExit) as excinfo:
            main(["--query", "x", "--prompt-version", "v9"])

        assert excinfo.value.code == 2

    @pytest.mark.parametrize("bad_score", ["nan", "1.5", "-0.1"])
    def test_an_out_of_range_min_score_is_an_error(self, bad_score: str) -> None:
        # nan is the dangerous one: every comparison against it is False, so the floor would
        # silently refuse every question across a whole graded run.
        with pytest.raises(SystemExit) as excinfo:
            main(["--query", "x", "--min-score", bad_score])

        assert excinfo.value.code == 2

    def test_prompt_version_is_rejected_in_improvements_mode(self) -> None:
        with pytest.raises(SystemExit) as excinfo:
            main(["--improvements", "--prompt-version", "v1"])

        assert excinfo.value.code == 2
