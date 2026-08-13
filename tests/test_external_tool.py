"""Tests for the Homework #5 external tool integration.

Offline like the rest of the suite: no network, no OPENAI_API_KEY. The tool-calling client is
faked through the same duck-typed `client=` seam the production code uses, extending the
Homework #4 chat fake with a scripted queue of replies so a full tool round trip — model asks,
validation runs, tool answers, model summarises — plays out deterministically.

The fake mirrors the wire shape rather than the SDK objects: `arguments` is a JSON *string*,
because that is what the API returns and it is exactly what makes the decode guard load-bearing.
"""

from __future__ import annotations

import hashlib
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from openai import OpenAIError

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import external_tool  # noqa: E402
from external_tool import (  # noqa: E402
    BOOK_LOAD_SCHEMA,
    CARRIER_ID_PATTERN,
    DEFAULT_LOADS,
    GET_LOAD_STATUS_SCHEMA,
    LOAD_ID_PATTERN,
    LOAD_STATES,
    MAX_TOOL_ROUNDS,
    OPEN_STATUSES,
    PROTECTED_OUTPUTS,
    SCENARIOS,
    STALE_POSITION_S,
    TOOL_SCHEMAS,
    TOOLS,
    ToolCall,
    assistant_echo,
    book_load,
    check_shape,
    complete_with_tools,
    dispatch,
    format_answer,
    get_load_status,
    guard_outputs,
    load_commentary,
    load_operations_data,
    main,
    orchestrate,
    parse_arguments,
    render_examples_markdown,
    render_tool_catalogue,
    result_record,
    run_examples,
    run_question,
    validate_book_load,
    validate_get_load_status,
)
from rag_lib import (  # noqa: E402
    RetrievalError,
    Settings,
    embed_texts,
    load_chunks,
    open_collection,
    write_manifest,
)

from test_retrieval import DIMENSION, FakeOpenAI  # noqa: E402


# --------------------------------------------------------------------------------------------
# The scripted tool-calling fake
# --------------------------------------------------------------------------------------------


@dataclass
class ScriptedCall:
    name: str
    arguments: str
    call_id: str = "call_1"


@dataclass
class FakeFunction:
    name: str
    arguments: str


@dataclass
class FakeToolCall:
    id: str
    function: FakeFunction
    type: str = "function"


@dataclass
class FakeToolMessage:
    content: str | None
    tool_calls: list[FakeToolCall] | None = None


@dataclass
class FakeChoice:
    message: FakeToolMessage


@dataclass
class FakeChatResponse:
    choices: list[FakeChoice]


@dataclass
class RecordedCall:
    model: str
    messages: list[dict[str, Any]]
    temperature: float
    tools: list[dict[str, Any]] | None
    tool_choice: str | None = None


class FakeToolCompletions:
    def __init__(self, owner: FakeToolClient) -> None:
        self._owner = owner

    def create(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        temperature: float,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | None = None,
    ) -> FakeChatResponse:
        if self._owner.fails_with is not None:
            raise self._owner.fails_with
        if self._owner.no_choices:
            return FakeChatResponse([])
        position = len(self._owner.chat_calls)
        self._owner.chat_calls.append(
            RecordedCall(
                model=model,
                messages=[dict(message) for message in messages],
                temperature=temperature,
                tools=tools,
                tool_choice=tool_choice,
            )
        )
        # The last reply repeats, so a test making one call needs to supply only one.
        reply = self._owner.replies[min(position, len(self._owner.replies) - 1)]
        if isinstance(reply, (list, tuple)):
            calls = [
                FakeToolCall(
                    id=item.call_id, function=FakeFunction(item.name, item.arguments)
                )
                for item in reply
            ]
            return FakeChatResponse(
                [FakeChoice(FakeToolMessage(content=None, tool_calls=calls))]
            )
        return FakeChatResponse([FakeChoice(FakeToolMessage(content=reply))])


class FakeToolChat:
    def __init__(self, owner: FakeToolClient) -> None:
        self.completions = FakeToolCompletions(owner)


class FakeToolClient(FakeOpenAI):
    """FakeOpenAI plus a chat surface that can answer with text or with tool calls."""

    def __init__(
        self,
        *replies: str | None | tuple[ScriptedCall, ...] | list[ScriptedCall],
        fails_with: OpenAIError | None = None,
        no_choices: bool = False,
    ) -> None:
        super().__init__()
        self.chat_calls: list[RecordedCall] = []
        self.replies: list[Any] = list(replies) or ["An answer."]
        self.fails_with = fails_with
        self.no_choices = no_choices
        self.chat = FakeToolChat(self)


def call_of(name: str, arguments: Any, *, call_id: str = "call_1") -> ToolCall:
    """Build a ToolCall the way the wire delivers one: arguments as a JSON string."""
    raw = arguments if isinstance(arguments, str) else json.dumps(arguments)
    return ToolCall(call_id=call_id, name=name, raw_arguments=raw)


# --------------------------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------------------------


def a_load(**overrides: Any) -> dict[str, Any]:
    """A complete load record. Tests override exactly the field under test, so a fixture-integrity
    test cannot pass for the wrong reason (tripping the required-keys check instead)."""
    record = {
        "load_id": "FX-2026-000001",
        "status": "posted",
        "origin": "Rotterdam, NL",
        "destination": "Poznan, PL",
        "equipment": "curtainsider",
        "weight_kg": 1000,
        "pickup_window": {
            "from": "2026-08-16T06:00:00+00:00",
            "to": "2026-08-16T18:00:00+00:00",
        },
        "updated_at": "2026-08-13T00:00:00+00:00",
    }
    record.update(overrides)
    return record


def a_carrier(**overrides: Any) -> dict[str, Any]:
    record = {"carrier_id": "CAR-00001", "name": "Test Haulage", "status": "active"}
    record.update(overrides)
    return record


@pytest.fixture
def operations() -> dict[str, Any]:
    """The committed operations fixture, freshly loaded so a write cannot leak between tests."""
    return load_operations_data(DEFAULT_LOADS)


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
            "text": (
                "Primer > Load Lifecycle. A load becomes booked when the demand side confirms one "
                "candidate, the first irreversible commercial transition."
            ),
            "metadata": {
                "document_id": "primer",
                "source_file": "data/raw/primer.md",
                "chunk_index": 1,
                "section": "Load Lifecycle",
                "title": "Primer",
                "document_type": "concept-guide",
            },
        },
        {
            "chunk_id": "cqrs_chunk_001",
            "text": (
                "CQRS > Command Side. A BookLoad command checks that the load is still open and "
                "not already committed elsewhere."
            ),
            "metadata": {
                "document_id": "cqrs",
                "source_file": "data/raw/cqrs.md",
                "chunk_index": 1,
                "section": "Command Side",
                "title": "CQRS",
                "document_type": "architecture-guide",
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
def commentary_file(tmp_path: Path) -> Path:
    """A complete hand-authored commentary file, so the renderer has nothing to report missing."""
    payload = {
        "description": "offline fixture",
        "hw5_scenarios": {
            scenario.id: {
                "why_better_than_retrieval": f"why {scenario.id}",
                "comment": f"comment {scenario.id}",
            }
            for scenario in SCENARIOS
        },
        "hw5_conclusion": "A conclusion authored by hand.",
    }
    path = tmp_path / "test_queries.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


# --------------------------------------------------------------------------------------------
# The contract
# --------------------------------------------------------------------------------------------


class TestToolContract:
    def test_every_schema_is_in_openai_tool_shape(self) -> None:
        for schema in TOOL_SCHEMAS:
            assert schema["type"] == "function"
            function = schema["function"]
            assert function["name"] in TOOLS
            assert function["description"].strip()
            assert function["parameters"]["type"] == "object"

    def test_no_tool_accepts_unknown_properties(self) -> None:
        # additionalProperties:false is what makes "the tool never takes a free-form query from
        # the model" a property of the contract rather than a claim about it.
        for schema in TOOL_SCHEMAS:
            assert schema["function"]["parameters"]["additionalProperties"] is False

    def test_no_tool_exposes_a_free_text_parameter(self) -> None:
        for schema in TOOL_SCHEMAS:
            for name, spec in schema["function"]["parameters"]["properties"].items():
                if spec["type"] == "string":
                    assert "pattern" in spec, (
                        f"{schema['function']['name']}.{name} is an unconstrained string — the "
                        "shape a raw query or an injected statement would arrive in"
                    )

    def test_the_id_patterns_are_single_sourced(self) -> None:
        # If these ever diverge, the model is shown one contract and validation enforces another.
        assert (
            GET_LOAD_STATUS_SCHEMA["function"]["parameters"]["properties"]["load_id"][
                "pattern"
            ]
            == LOAD_ID_PATTERN
        )
        assert (
            BOOK_LOAD_SCHEMA["function"]["parameters"]["properties"]["carrier_id"][
                "pattern"
            ]
            == CARRIER_ID_PATTERN
        )

    def test_every_description_states_when_not_to_call(self) -> None:
        for schema in TOOL_SCHEMAS:
            assert "Do NOT call this" in schema["function"]["description"]

    def test_only_book_load_is_a_write_tool(self) -> None:
        assert TOOLS["book_load"].is_write is True
        assert TOOLS["get_load_status"].is_write is False

    def test_the_catalogue_renders_offline(self) -> None:
        rendered = render_tool_catalogue()

        assert "Tool: get_load_status" in rendered
        assert "Type: write / active" in rendered
        assert LOAD_ID_PATTERN in rendered


# --------------------------------------------------------------------------------------------
# Validation
# --------------------------------------------------------------------------------------------


class TestArgumentParsing:
    def test_a_json_object_parses(self) -> None:
        args, rejection = parse_arguments(call_of("get_load_status", {"load_id": "x"}))

        assert rejection is None
        assert args == {"load_id": "x"}

    def test_absent_arguments_parse_as_an_empty_object(self) -> None:
        args, rejection = parse_arguments(call_of("get_load_status", ""))

        assert rejection is None
        assert args == {}

    def test_malformed_json_is_reported_to_the_model_with_the_decode_reason(
        self,
    ) -> None:
        _, rejection = parse_arguments(call_of("get_load_status", "{not json"))

        assert rejection is not None
        assert rejection.error == "malformed_arguments"
        assert "valid JSON" in (rejection.message or "")

    def test_a_json_scalar_is_not_an_argument_object(self) -> None:
        _, rejection = parse_arguments(call_of("get_load_status", "42"))

        assert rejection is not None
        assert rejection.error == "malformed_arguments"


class TestCheckShape:
    def test_an_unknown_property_is_refused(self) -> None:
        rejection = check_shape(
            GET_LOAD_STATUS_SCHEMA,
            {"load_id": "FX-2026-000042", "sql": "DROP TABLE loads"},
        )

        assert rejection is not None
        assert rejection.error == "unknown_argument"
        assert "sql" in (rejection.message or "")

    def test_a_missing_required_field_is_refused(self) -> None:
        rejection = check_shape(GET_LOAD_STATUS_SCHEMA, {})

        assert rejection is not None
        assert rejection.error == "missing_argument"

    def test_a_blank_required_field_is_refused(self) -> None:
        rejection = check_shape(GET_LOAD_STATUS_SCHEMA, {"load_id": "   "})

        assert rejection is not None
        assert rejection.error == "missing_argument"

    def test_a_non_string_required_field_is_refused(self) -> None:
        rejection = check_shape(GET_LOAD_STATUS_SCHEMA, {"load_id": 42})

        assert rejection is not None
        assert rejection.error == "missing_argument"

    def test_a_declared_optional_field_is_allowed(self) -> None:
        assert (
            check_shape(
                BOOK_LOAD_SCHEMA,
                {"load_id": "a", "carrier_id": "b", "confirmed": True},
            )
            is None
        )

    def test_the_allowed_field_set_is_read_from_the_contract(self) -> None:
        # Not restated in the validator: a property added to the schema must be accepted without
        # a second edit, or the model gets refused for sending what it was invited to send.
        for schema in TOOL_SCHEMAS:
            parameters = schema["function"]["parameters"]
            complete = {
                name: "x" if spec["type"] == "string" else True
                for name, spec in parameters["properties"].items()
            }

            assert check_shape(schema, complete) is None, schema["function"]["name"]


class TestGetLoadStatusValidation:
    def test_a_well_formed_call_validates(self) -> None:
        args, rejection = validate_get_load_status(
            call_of("get_load_status", {"load_id": "FX-2026-000042"})
        )

        assert rejection is None
        assert args == {"load_id": "FX-2026-000042"}

    def test_surrounding_whitespace_is_tolerated(self) -> None:
        args, rejection = validate_get_load_status(
            call_of("get_load_status", {"load_id": " FX-2026-000042 "})
        )

        assert rejection is None
        assert args == {"load_id": "FX-2026-000042"}

    @pytest.mark.parametrize(
        "load_id",
        [
            "42",
            "FX-26-42",
            "fx-2026-000042",
            "FX-2026-00042",
            "FX-2026-0000042",
            "FX2026000042",
        ],
    )
    def test_an_identifier_off_the_pattern_is_refused(self, load_id: str) -> None:
        _, rejection = validate_get_load_status(
            call_of("get_load_status", {"load_id": load_id})
        )

        assert rejection is not None
        assert rejection.error == "invalid_load_id_format"


class TestBookLoadValidation:
    def test_an_operator_confirmed_call_validates(self) -> None:
        args, rejection = validate_book_load(
            call_of(
                "book_load", {"load_id": "FX-2026-000211", "carrier_id": "CAR-00817"}
            ),
            operator_confirmed=True,
        )

        assert rejection is None
        assert args == {"load_id": "FX-2026-000211", "carrier_id": "CAR-00817"}

    def test_an_unconfirmed_write_is_refused(self) -> None:
        _, rejection = validate_book_load(
            call_of(
                "book_load", {"load_id": "FX-2026-000211", "carrier_id": "CAR-00817"}
            ),
            operator_confirmed=False,
        )

        assert rejection is not None
        assert rejection.error == "confirmation_required"

    def test_the_model_cannot_confirm_its_own_write(self) -> None:
        # The whole point of the confirmation rule: authorisation supplied by the thing being
        # authorised is not authorisation. The attempt is recorded rather than merely ignored.
        _, rejection = validate_book_load(
            call_of(
                "book_load",
                {
                    "load_id": "FX-2026-000211",
                    "carrier_id": "CAR-00817",
                    "confirmed": True,
                },
            ),
            operator_confirmed=False,
        )

        assert rejection is not None
        assert rejection.error == "confirmation_required"
        assert rejection.data is not None
        assert rejection.data["model_self_confirmed"] is True

    def test_a_malformed_carrier_id_is_refused(self) -> None:
        _, rejection = validate_book_load(
            call_of("book_load", {"load_id": "FX-2026-000211", "carrier_id": "817"}),
            operator_confirmed=True,
        )

        assert rejection is not None
        assert rejection.error == "invalid_carrier_id_format"

    def test_an_unknown_property_is_refused_before_the_confirmation_check(self) -> None:
        _, rejection = validate_book_load(
            call_of(
                "book_load",
                {"load_id": "FX-2026-000211", "carrier_id": "CAR-00817", "force": True},
            ),
            operator_confirmed=False,
        )

        assert rejection is not None
        assert rejection.error == "unknown_argument"


# --------------------------------------------------------------------------------------------
# The external source
# --------------------------------------------------------------------------------------------


class TestOperationsData:
    def test_the_committed_fixture_loads(self, operations: dict[str, Any]) -> None:
        assert operations["loads"]
        assert operations["carriers"]

    def test_every_fixture_status_is_a_lifecycle_state(
        self, operations: dict[str, Any]
    ) -> None:
        for load in operations["loads"].values():
            assert load["status"] in LOAD_STATES

    def test_the_fixture_covers_every_lifecycle_state(
        self, operations: dict[str, Any]
    ) -> None:
        present = {load["status"] for load in operations["loads"].values()}

        assert present == set(LOAD_STATES), (
            "each state needs a load so every branch is reachable"
        )

    def test_a_missing_file_names_the_remedial_command(self, tmp_path: Path) -> None:
        with pytest.raises(RetrievalError, match="git checkout --"):
            load_operations_data(tmp_path / "absent.json")

    def test_malformed_json_is_a_diagnostic_error(self, tmp_path: Path) -> None:
        path = tmp_path / "loads.json"
        path.write_text("{not json", encoding="utf-8")

        with pytest.raises(RetrievalError, match="not valid JSON"):
            load_operations_data(path)

    def test_a_file_without_loads_is_refused(self, tmp_path: Path) -> None:
        path = tmp_path / "loads.json"
        path.write_text(json.dumps({"carriers": {}}), encoding="utf-8")

        with pytest.raises(RetrievalError, match="missing its 'loads' object"):
            load_operations_data(path)

    def test_a_file_without_carriers_is_refused(self, tmp_path: Path) -> None:
        path = tmp_path / "loads.json"
        path.write_text(json.dumps({"loads": {}}), encoding="utf-8")

        with pytest.raises(RetrievalError, match="missing its 'carriers' object"):
            load_operations_data(path)

    def test_a_status_outside_the_lifecycle_is_refused(self, tmp_path: Path) -> None:
        path = tmp_path / "loads.json"
        path.write_text(
            json.dumps(
                {
                    "carriers": {},
                    "loads": {"FX-2026-000001": a_load(status="teleporting")},
                }
            ),
            encoding="utf-8",
        )

        with pytest.raises(RetrievalError, match="not one of the lifecycle states"):
            load_operations_data(path)


# --------------------------------------------------------------------------------------------
# The tools
# --------------------------------------------------------------------------------------------


class TestGetLoadStatusTool:
    def test_a_known_load_returns_its_live_state(
        self, operations: dict[str, Any]
    ) -> None:
        result = get_load_status("FX-2026-000042", data=operations)

        assert result.ok
        assert result.data is not None
        assert result.data["status"] == "in_transit"
        assert result.data["carrier"]["carrier_id"] == "CAR-00817"
        assert result.data["eta"]

    def test_position_staleness_is_reported_not_left_to_the_model(
        self, operations: dict[str, Any]
    ) -> None:
        fresh = get_load_status("FX-2026-000042", data=operations)
        stale = get_load_status("FX-2026-000407", data=operations)

        assert fresh.data is not None and stale.data is not None
        assert fresh.data["last_position_age_s"] <= STALE_POSITION_S
        assert fresh.data["position_is_stale"] is False
        assert stale.data["position_is_stale"] is True

    def test_a_load_with_no_position_reports_staleness_as_unknown(
        self, operations: dict[str, Any]
    ) -> None:
        result = get_load_status("FX-2026-000211", data=operations)

        assert result.data is not None
        assert result.data["position_is_stale"] is None
        assert result.data["carrier"] is None

    def test_an_unknown_load_is_a_refusal_not_an_exception(
        self, operations: dict[str, Any]
    ) -> None:
        result = get_load_status("FX-2026-999999", data=operations)

        assert result.ok is False
        assert result.error == "unknown_load"
        assert result.payload()["ok"] is False


class TestBookLoadTool:
    def test_an_open_load_books(self, operations: dict[str, Any]) -> None:
        result = book_load("FX-2026-000211", "CAR-00817", data=operations)

        assert result.ok
        assert result.data is not None
        assert result.data["booking_reference"] == "BKG-2026-000211"
        assert operations["loads"]["FX-2026-000211"]["status"] == "booked"

    def test_a_matched_load_is_still_open(self, operations: dict[str, Any]) -> None:
        assert operations["loads"]["FX-2026-000318"]["status"] in OPEN_STATUSES

        assert book_load("FX-2026-000318", "CAR-00412", data=operations).ok

    def test_booking_the_same_load_twice_is_refused(
        self, operations: dict[str, Any]
    ) -> None:
        first = book_load("FX-2026-000211", "CAR-00817", data=operations)
        second = book_load("FX-2026-000211", "CAR-00412", data=operations)

        assert first.ok
        assert second.ok is False
        assert second.error == "already_booked"
        assert operations["loads"]["FX-2026-000211"]["carrier_id"] == "CAR-00817", (
            "the refused second booking must not have moved the load to another carrier"
        )

    def test_an_already_committed_load_reports_its_existing_booking(
        self, operations: dict[str, Any]
    ) -> None:
        result = book_load("FX-2026-000105", "CAR-00817", data=operations)

        assert result.error == "already_booked"
        assert result.data is not None
        assert result.data["booking_reference"] == "BKG-2026-004498"

    def test_a_load_in_transit_cannot_be_rebooked(
        self, operations: dict[str, Any]
    ) -> None:
        assert (
            book_load("FX-2026-000042", "CAR-00412", data=operations).error
            == "already_booked"
        )

    def test_a_suspended_carrier_may_not_take_a_load(
        self, operations: dict[str, Any]
    ) -> None:
        result = book_load("FX-2026-000211", "CAR-00555", data=operations)

        assert result.error == "carrier_not_permitted"
        assert operations["loads"]["FX-2026-000211"]["status"] == "posted"

    def test_an_unknown_carrier_is_refused(self, operations: dict[str, Any]) -> None:
        assert (
            book_load("FX-2026-000211", "CAR-99999", data=operations).error
            == "unknown_carrier"
        )

    def test_an_unknown_load_is_refused(self, operations: dict[str, Any]) -> None:
        assert (
            book_load("FX-2026-999999", "CAR-00817", data=operations).error
            == "unknown_load"
        )

    def test_a_booking_never_writes_the_committed_fixture_back_to_disk(self) -> None:
        # The fixture is a fixed input: if a write persisted, every committed example would start
        # from a different state than the one its Markdown records.
        before = hashlib.sha256(DEFAULT_LOADS.read_bytes()).hexdigest()
        data = load_operations_data(DEFAULT_LOADS)

        assert book_load("FX-2026-000211", "CAR-00817", data=data).ok

        assert hashlib.sha256(DEFAULT_LOADS.read_bytes()).hexdigest() == before


# --------------------------------------------------------------------------------------------
# Dispatch
# --------------------------------------------------------------------------------------------


class TestDispatch:
    def test_a_hallucinated_tool_name_is_a_refusal(
        self, operations: dict[str, Any]
    ) -> None:
        invocation = dispatch(
            call_of("drop_database", {}), data=operations, operator_confirmed=False
        )

        assert invocation.result.error == "unknown_tool"
        assert invocation.arguments is None

    def test_validation_runs_before_the_data_layer_is_consulted(self) -> None:
        # An empty operations set would answer "unknown_load" for ANY well-formed id. Getting
        # "invalid_load_id_format" back instead is what proves the lookup never happened.
        invocation = dispatch(
            call_of("get_load_status", {"load_id": "FX-26-42"}),
            data={"loads": {}, "carriers": {}},
            operator_confirmed=False,
        )

        assert invocation.result.error == "invalid_load_id_format"

    def test_a_valid_read_reaches_the_tool(self, operations: dict[str, Any]) -> None:
        invocation = dispatch(
            call_of("get_load_status", {"load_id": "FX-2026-000042"}),
            data=operations,
            operator_confirmed=False,
        )

        assert invocation.result.ok
        assert invocation.arguments == {"load_id": "FX-2026-000042"}

    def test_an_unconfirmed_write_never_reaches_the_tool(
        self, operations: dict[str, Any]
    ) -> None:
        invocation = dispatch(
            call_of(
                "book_load", {"load_id": "FX-2026-000211", "carrier_id": "CAR-00817"}
            ),
            data=operations,
            operator_confirmed=False,
        )

        assert invocation.result.error == "confirmation_required"
        assert operations["loads"]["FX-2026-000211"]["status"] == "posted"

    def test_a_confirmed_write_reaches_the_tool(
        self, operations: dict[str, Any]
    ) -> None:
        invocation = dispatch(
            call_of(
                "book_load", {"load_id": "FX-2026-000211", "carrier_id": "CAR-00817"}
            ),
            data=operations,
            operator_confirmed=True,
        )

        assert invocation.result.ok
        assert operations["loads"]["FX-2026-000211"]["status"] == "booked"


# --------------------------------------------------------------------------------------------
# The LLM boundary
# --------------------------------------------------------------------------------------------


class TestCompleteWithTools:
    def test_the_tool_contract_is_sent_on_every_turn(self, settings: Settings) -> None:
        client = FakeToolClient("done")

        complete_with_tools(
            [{"role": "user", "content": "hi"}], settings, client=client
        )

        sent = client.chat_calls[0].tools
        assert sent is not None
        assert {schema["function"]["name"] for schema in sent} == set(TOOLS)

    def test_withdrawing_the_tools_forbids_them_rather_than_dropping_them(
        self, settings: Settings
    ) -> None:
        # Dropping the `tools` key from a conversation that still contains tool_calls and
        # role="tool" messages leaves the request describing tools it no longer declares.
        # tool_choice="none" says "do not call one" in a shape the API documents.
        client = FakeToolClient("done")

        complete_with_tools(
            [{"role": "user", "content": "hi"}], settings, client=client, tools=None
        )

        assert client.chat_calls[0].tool_choice == "none"
        assert client.chat_calls[0].tools is not None

    def test_an_sdk_error_names_the_model_override(self, settings: Settings) -> None:
        client = FakeToolClient(fails_with=OpenAIError("no access"))

        with pytest.raises(RetrievalError, match="--answer-model"):
            complete_with_tools(
                [{"role": "user", "content": "hi"}], settings, client=client
            )

    def test_an_empty_choices_array_is_a_diagnostic_error(
        self, settings: Settings
    ) -> None:
        client = FakeToolClient("done", no_choices=True)

        with pytest.raises(RetrievalError, match="returned no choices"):
            complete_with_tools(
                [{"role": "user", "content": "hi"}], settings, client=client
            )


class TestAssistantEcho:
    def test_tool_calls_are_rebuilt_in_wire_shape(self) -> None:
        message = FakeToolMessage(
            content=None,
            tool_calls=[
                FakeToolCall(
                    id="call_9", function=FakeFunction("get_load_status", "{}")
                )
            ],
        )

        echo = assistant_echo(message)

        assert echo["role"] == "assistant"
        assert echo["tool_calls"] == [
            {
                "id": "call_9",
                "type": "function",
                "function": {"name": "get_load_status", "arguments": "{}"},
            }
        ]

    def test_a_plain_answer_carries_no_tool_calls_key(self) -> None:
        echo = assistant_echo(FakeToolMessage(content="hello"))

        assert "tool_calls" not in echo
        assert echo["content"] == "hello"


# --------------------------------------------------------------------------------------------
# Orchestration
# --------------------------------------------------------------------------------------------


class TestOrchestrate:
    def test_a_load_question_routes_to_the_tool(
        self, settings: Settings, operations: dict[str, Any]
    ) -> None:
        client = FakeToolClient(
            (ScriptedCall("get_load_status", '{"load_id": "FX-2026-000042"}'),),
            "FX-2026-000042 is in transit, ETA 14 Aug.",
        )

        result = orchestrate(
            "Where is FX-2026-000042?", settings, client=client, data=operations
        )

        assert result.used_tools
        assert result.rounds == 1
        assert result.invocations[0].result.ok
        assert result.answer.startswith("FX-2026-000042 is in transit")
        assert result.grounded is None

    def test_the_tool_result_goes_back_as_a_tool_message(
        self, settings: Settings, operations: dict[str, Any]
    ) -> None:
        client = FakeToolClient(
            (
                ScriptedCall(
                    "get_load_status", '{"load_id": "FX-2026-000042"}', call_id="call_7"
                ),
            ),
            "Answered.",
        )

        orchestrate(
            "Where is FX-2026-000042?", settings, client=client, data=operations
        )

        second_turn = client.chat_calls[1].messages
        tool_message = second_turn[-1]
        assert tool_message["role"] == "tool"
        assert tool_message["tool_call_id"] == "call_7"
        assert json.loads(tool_message["content"])["status"] == "in_transit"

    def test_a_refused_call_still_reaches_the_model(
        self, settings: Settings, operations: dict[str, Any]
    ) -> None:
        client = FakeToolClient(
            (ScriptedCall("get_load_status", '{"load_id": "FX-26-42"}'),),
            "That is not a valid load identifier.",
        )

        result = orchestrate(
            "Status of FX-26-42?", settings, client=client, data=operations
        )

        assert result.invocations[0].result.error == "invalid_load_id_format"
        payload = json.loads(client.chat_calls[1].messages[-1]["content"])
        assert payload["ok"] is False

    def test_a_documentation_question_falls_through_to_retrieval(
        self, index: Settings, operations: dict[str, Any]
    ) -> None:
        client = FakeToolClient(
            "I will not use a tool for this.",
            "A booked load is committed to one carrier [primer_chunk_001].",
        )

        result = orchestrate(
            "What does it mean for a load to be booked?",
            index,
            k=3,
            client=client,
            data=operations,
        )

        assert result.used_tools is False
        assert result.grounded is not None
        assert result.grounded.cited_chunk_ids == ("primer_chunk_001",)
        assert result.source() == "data/raw/primer.md"

    def test_an_unconfirmed_booking_leaves_the_state_untouched(
        self, settings: Settings, operations: dict[str, Any]
    ) -> None:
        client = FakeToolClient(
            (
                ScriptedCall(
                    "book_load",
                    '{"load_id": "FX-2026-000211", "carrier_id": "CAR-00817"}',
                ),
            ),
            "The booking needs operator confirmation.",
        )

        result = orchestrate(
            "Book FX-2026-000211 for CAR-00817.",
            settings,
            client=client,
            data=operations,
        )

        assert result.invocations[0].result.error == "confirmation_required"
        assert operations["loads"]["FX-2026-000211"]["status"] == "posted"

    def test_an_authorised_booking_commits(
        self, settings: Settings, operations: dict[str, Any]
    ) -> None:
        client = FakeToolClient(
            (
                ScriptedCall(
                    "book_load",
                    '{"load_id": "FX-2026-000211", "carrier_id": "CAR-00817"}',
                ),
            ),
            "Booked under BKG-2026-000211.",
        )

        result = orchestrate(
            "Book FX-2026-000211 for CAR-00817.",
            settings,
            client=client,
            data=operations,
            operator_confirmed=True,
        )

        assert result.invocations[0].result.ok
        assert operations["loads"]["FX-2026-000211"]["status"] == "booked"

    def test_a_model_that_never_stops_calling_still_terminates(
        self, settings: Settings, operations: dict[str, Any]
    ) -> None:
        # Every offered turn asks for another tool call, so the bound is the only thing that ends
        # this. The trailing text is what the forced tools-withdrawn turn returns.
        asks_again = (ScriptedCall("get_load_status", '{"load_id": "FX-2026-000042"}'),)
        client = FakeToolClient(*([asks_again] * MAX_TOOL_ROUNDS), "Enough.")

        result = orchestrate(
            "Where is FX-2026-000042?", settings, client=client, data=operations
        )

        assert result.rounds == MAX_TOOL_ROUNDS
        assert result.rounds_exhausted is True
        assert client.chat_calls[-1].tool_choice == "none", (
            "the final turn forbids tool use"
        )
        assert result.answer == "Enough."

    def test_a_missing_operations_file_stops_the_run(
        self, settings: Settings, tmp_path: Path
    ) -> None:
        with pytest.raises(RetrievalError, match="git checkout --"):
            orchestrate(
                "Where is FX-2026-000042?",
                settings,
                client=FakeToolClient("x"),
                loads_path=tmp_path / "absent.json",
            )


class TestWriteAuthorisationScope:
    """One --confirm authorises one committed booking, not the whole invocation.

    Nothing bounds how many tool calls the model puts in a single turn, so an authorisation scoped
    to the run would let one human decision cover every write the model chose to emit.
    """

    def test_two_bookings_in_one_turn_spend_only_one_authorisation(
        self, settings: Settings, operations: dict[str, Any]
    ) -> None:
        client = FakeToolClient(
            (
                ScriptedCall(
                    "book_load",
                    '{"load_id": "FX-2026-000211", "carrier_id": "CAR-00817"}',
                    call_id="call_a",
                ),
                ScriptedCall(
                    "book_load",
                    '{"load_id": "FX-2026-000633", "carrier_id": "CAR-00412"}',
                    call_id="call_b",
                ),
            ),
            "One booked, one refused.",
        )

        result = orchestrate(
            "Book FX-2026-000211 and FX-2026-000633.",
            settings,
            client=client,
            data=operations,
            operator_confirmed=True,
        )

        first, second = result.invocations
        assert first.result.ok
        assert second.result.error == "authorisation_spent"
        assert operations["loads"]["FX-2026-000211"]["status"] == "booked"
        assert operations["loads"]["FX-2026-000633"]["status"] == "posted", (
            "the second booking must not ride on the first booking's confirmation"
        )

    def test_a_refused_write_does_not_burn_the_authorisation(
        self, settings: Settings, operations: dict[str, Any]
    ) -> None:
        # FX-2026-000105 is already booked, so the first call commits nothing. The operator's
        # decision is still unspent and the genuine booking behind it must go through.
        client = FakeToolClient(
            (
                ScriptedCall(
                    "book_load",
                    '{"load_id": "FX-2026-000105", "carrier_id": "CAR-00817"}',
                    call_id="call_a",
                ),
                ScriptedCall(
                    "book_load",
                    '{"load_id": "FX-2026-000211", "carrier_id": "CAR-00817"}',
                    call_id="call_b",
                ),
            ),
            "Done.",
        )

        result = orchestrate(
            "Book both.",
            settings,
            client=client,
            data=operations,
            operator_confirmed=True,
        )

        first, second = result.invocations
        assert first.result.error == "already_booked"
        assert second.result.ok
        assert operations["loads"]["FX-2026-000211"]["status"] == "booked"

    def test_an_unconfirmed_batch_is_refused_call_by_call(
        self, settings: Settings, operations: dict[str, Any]
    ) -> None:
        client = FakeToolClient(
            (
                ScriptedCall(
                    "book_load",
                    '{"load_id": "FX-2026-000211", "carrier_id": "CAR-00817"}',
                    call_id="call_a",
                ),
                ScriptedCall(
                    "book_load",
                    '{"load_id": "FX-2026-000633", "carrier_id": "CAR-00412"}',
                    call_id="call_b",
                ),
            ),
            "Both need authorisation.",
        )

        result = orchestrate(
            "Book every open load.", settings, client=client, data=operations
        )

        assert [i.result.error for i in result.invocations] == [
            "confirmation_required",
            "confirmation_required",
        ]
        assert all(
            load["status"] == "posted"
            for load in (
                operations["loads"]["FX-2026-000211"],
                operations["loads"]["FX-2026-000633"],
            )
        )

    def test_a_multi_call_turn_returns_one_tool_message_per_call_id(
        self, settings: Settings, operations: dict[str, Any]
    ) -> None:
        # The parallel-tool-call path: the loop must answer every call the model made, each keyed
        # to its own tool_call_id, or the next request is malformed.
        client = FakeToolClient(
            (
                ScriptedCall(
                    "get_load_status", '{"load_id": "FX-2026-000042"}', call_id="call_a"
                ),
                ScriptedCall(
                    "get_load_status", '{"load_id": "FX-2026-000105"}', call_id="call_b"
                ),
            ),
            "Both looked up.",
        )

        result = orchestrate(
            "Where are both?", settings, client=client, data=operations
        )

        assert len(result.invocations) == 2
        second_turn = client.chat_calls[1].messages
        tool_messages = [m for m in second_turn if m["role"] == "tool"]
        assert [m["tool_call_id"] for m in tool_messages] == ["call_a", "call_b"]
        assert json.loads(tool_messages[0]["content"])["status"] == "in_transit"
        assert json.loads(tool_messages[1]["content"])["status"] == "booked"


# --------------------------------------------------------------------------------------------
# Presentation and artifacts
# --------------------------------------------------------------------------------------------


class TestPresentation:
    def test_the_answer_block_names_the_tool_and_its_input(
        self, settings: Settings, operations: dict[str, Any]
    ) -> None:
        client = FakeToolClient(
            (ScriptedCall("get_load_status", '{"load_id": "FX-2026-000042"}'),),
            "In transit.",
        )
        result = orchestrate("Where?", settings, client=client, data=operations)

        rendered = format_answer(result)

        assert "Tool called: get_load_status" in rendered
        assert '"load_id": "FX-2026-000042"' in rendered
        assert "Route: tool" in rendered

    def test_a_refused_call_still_shows_the_arguments_the_model_sent(
        self, settings: Settings, operations: dict[str, Any]
    ) -> None:
        client = FakeToolClient(
            (ScriptedCall("get_load_status", '{"load_id": "FX-26-42"}'),), "Invalid."
        )
        result = orchestrate("Where?", settings, client=client, data=operations)

        assert "FX-26-42" in format_answer(result)

    def test_the_record_keeps_the_raw_and_validated_arguments_apart(
        self, settings: Settings, operations: dict[str, Any]
    ) -> None:
        client = FakeToolClient(
            (ScriptedCall("get_load_status", '{"load_id": "FX-26-42"}'),), "Invalid."
        )
        record = result_record(
            orchestrate("Where?", settings, client=client, data=operations)
        )

        assert record["invocations"][0]["raw_arguments"] == '{"load_id": "FX-26-42"}'
        assert record["invocations"][0]["validated_arguments"] is None
        assert record["route"] == "tool"


class TestGuardOutputs:
    @pytest.mark.parametrize("protected", PROTECTED_OUTPUTS)
    def test_every_committed_deliverable_is_refused(self, protected: Path) -> None:
        with pytest.raises(RetrievalError, match="committed deliverable"):
            guard_outputs({"output": protected})

    def test_the_run_refuses_to_overwrite_its_own_input(self, tmp_path: Path) -> None:
        queries = tmp_path / "test_queries.json"

        with pytest.raises(RetrievalError, match="an input of this run"):
            guard_outputs({"output": queries}, reads=queries)

    def test_an_ordinary_path_is_allowed(self, tmp_path: Path) -> None:
        guard_outputs({"output": tmp_path / "tool_examples.md"})


class TestGuardOutputsCollisions:
    def test_two_outputs_on_one_path_are_refused(self, tmp_path: Path) -> None:
        # Both promotions would succeed and the second would destroy the first artifact, so the
        # run has to stop here rather than report success over one missing deliverable.
        same = tmp_path / "artifact.md"

        with pytest.raises(RetrievalError, match="point at the same file"):
            guard_outputs({"output": same, "results": same})

    def test_a_symlink_onto_a_deliverable_is_refused(self, tmp_path: Path) -> None:
        # Identity is by inode, not by spelling: a resolved-string compare would wave this through.
        alias = tmp_path / "innocent-looking.md"
        alias.symlink_to(PROTECTED_OUTPUTS[0])

        with pytest.raises(RetrievalError, match="committed deliverable"):
            guard_outputs({"output": alias})

    def test_a_differently_spelled_path_onto_a_deliverable_is_refused(
        self, tmp_path: Path
    ) -> None:
        probe = tmp_path / "CaseProbe"
        probe.write_text("x", encoding="utf-8")
        if not (tmp_path / "caseprobe").exists():
            pytest.skip("filesystem is case-sensitive; the alias cannot occur here")
        target = PROTECTED_OUTPUTS[0]
        shouted = target.parent / target.name.upper()

        with pytest.raises(RetrievalError, match="committed deliverable"):
            guard_outputs({"output": shouted})


class TestOperationsFixtureIntegrity:
    def _write(self, tmp_path: Path, payload: dict[str, Any]) -> Path:
        path = tmp_path / "loads.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def test_a_load_that_is_not_an_object_is_a_diagnostic_error(
        self, tmp_path: Path
    ) -> None:
        # Without the guard this surfaces as a bare AttributeError past main()'s boundary catch.
        path = self._write(
            tmp_path, {"carriers": {}, "loads": {"FX-2026-000001": None}}
        )

        with pytest.raises(RetrievalError, match="is not an object"):
            load_operations_data(path)

    def test_a_carrier_that_is_not_an_object_is_a_diagnostic_error(
        self, tmp_path: Path
    ) -> None:
        path = self._write(tmp_path, {"carriers": {"CAR-00001": "active"}, "loads": {}})

        with pytest.raises(RetrievalError, match="is not an object"):
            load_operations_data(path)

    def test_a_carrier_status_outside_the_known_set_is_refused(
        self, tmp_path: Path
    ) -> None:
        path = self._write(
            tmp_path,
            {"carriers": {"CAR-00001": a_carrier(status="Active")}, "loads": {}},
        )

        with pytest.raises(RetrievalError, match="not one of active, suspended"):
            load_operations_data(path)

    def test_a_dangling_carrier_reference_is_refused(self, tmp_path: Path) -> None:
        # Otherwise get_load_status returns "carrier": null on an ok result — corruption that
        # reads as a load merely not yet assigned.
        path = self._write(
            tmp_path,
            {
                "carriers": {},
                "loads": {
                    "FX-2026-000001": a_load(status="booked", carrier_id="CAR-00404")
                },
            },
        )

        with pytest.raises(RetrievalError, match="references carrier"):
            load_operations_data(path)

    def test_a_load_missing_a_field_the_tool_indexes_is_refused(
        self, tmp_path: Path
    ) -> None:
        # Otherwise get_load_status raises KeyError from inside the tool, past main()'s boundary.
        truncated = a_load()
        del truncated["origin"]
        path = self._write(
            tmp_path, {"carriers": {}, "loads": {"FX-2026-000001": truncated}}
        )

        with pytest.raises(RetrievalError, match="is missing origin"):
            load_operations_data(path)

    def test_a_carrier_missing_a_field_the_tool_indexes_is_refused(
        self, tmp_path: Path
    ) -> None:
        truncated = a_carrier()
        del truncated["name"]
        path = self._write(
            tmp_path, {"carriers": {"CAR-00001": truncated}, "loads": {}}
        )

        with pytest.raises(RetrievalError, match="is missing name"):
            load_operations_data(path)

    def test_the_committed_fixture_passes_every_integrity_check(self) -> None:
        assert load_operations_data(DEFAULT_LOADS)["loads"]


class TestCommentaryLoading:
    def test_a_missing_file_names_the_remedial_command(self, tmp_path: Path) -> None:
        with pytest.raises(RetrievalError, match="git checkout --"):
            load_commentary(tmp_path / "absent.json")

    def test_malformed_json_is_a_diagnostic_error(self, tmp_path: Path) -> None:
        path = tmp_path / "queries.json"
        path.write_text("{nope", encoding="utf-8")

        with pytest.raises(RetrievalError, match="not valid JSON"):
            load_commentary(path)

    def test_a_non_object_scenarios_key_is_refused(self, tmp_path: Path) -> None:
        path = tmp_path / "queries.json"
        path.write_text(json.dumps({"hw5_scenarios": ["s1"]}), encoding="utf-8")

        with pytest.raises(RetrievalError, match="must be an object"):
            load_commentary(path)


class TestRunQuestion:
    def test_the_json_mode_emits_the_machine_readable_record(
        self, settings: Settings, capsys: pytest.CaptureFixture[str]
    ) -> None:
        client = FakeToolClient(
            (ScriptedCall("get_load_status", '{"load_id": "FX-2026-000042"}'),),
            "In transit.",
        )

        code = run_question(
            settings,
            "Where is FX-2026-000042?",
            k=3,
            loads_path=DEFAULT_LOADS,
            operator_confirmed=False,
            as_json=True,
            client=client,
        )

        assert code == 0
        record = json.loads(capsys.readouterr().out)
        assert record["route"] == "tool"
        assert record["invocations"][0]["validated_arguments"] == {
            "load_id": "FX-2026-000042"
        }

    def test_an_empty_answer_from_the_model_is_a_diagnostic_error(
        self, settings: Settings
    ) -> None:
        with pytest.raises(RetrievalError, match="returned an empty answer"):
            run_question(
                settings,
                "Where is FX-2026-000042?",
                k=3,
                loads_path=DEFAULT_LOADS,
                operator_confirmed=False,
                as_json=False,
                client=FakeToolClient(
                    (ScriptedCall("get_load_status", '{"load_id": "FX-2026-000042"}'),),
                    "   ",
                ),
            )

    def test_the_source_line_names_the_file_actually_read(
        self, settings: Settings, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # Provenance is graded output, so it must not report the default path under --loads.
        elsewhere = tmp_path / "other_ops.json"
        elsewhere.write_text(
            DEFAULT_LOADS.read_text(encoding="utf-8"), encoding="utf-8"
        )
        client = FakeToolClient(
            (ScriptedCall("get_load_status", '{"load_id": "FX-2026-000042"}'),),
            "In transit.",
        )

        run_question(
            settings,
            "Where is FX-2026-000042?",
            k=3,
            loads_path=elsewhere,
            operator_confirmed=False,
            as_json=False,
            client=client,
        )

        out = capsys.readouterr().out
        assert "other_ops.json" in out
        assert "data/external/loads.json" not in out


class TestExamplesArtifact:
    def test_the_rendered_block_carries_every_required_label(self) -> None:
        records = [
            {
                "scenario_id": "s1",
                "title": "live state",
                "rubric_role": "the happy read",
                "question": "Where is FX-2026-000042?",
                "runs": [
                    {
                        "label": "",
                        "question": "Where is FX-2026-000042?",
                        "answer": "In transit.",
                        "source": "data/external/loads.json",
                        "retrieved_chunks": [],
                        "citations": [],
                        "invocations": [
                            {
                                "tool": "get_load_status",
                                "raw_arguments": '{"load_id": "FX-2026-000042"}',
                                "validated_arguments": {"load_id": "FX-2026-000042"},
                                "result": {"ok": True, "status": "in_transit"},
                            }
                        ],
                    }
                ],
            }
        ]

        rendered = render_examples_markdown(
            records,
            commentary={
                "s1": {"why_better_than_retrieval": "live data", "comment": "good"}
            },
            conclusion="It worked.",
            answer_model="gpt-4.1-mini",
        )

        for label in (
            "User question:",
            "Tool called:",
            "Input:",
            "Result:",
            "Final answer:",
            "Why tool is better than retrieval:",
        ):
            assert label in rendered, f"§ 3 requires the {label!r} line"

    def test_complete_commentary_renders_the_artifact(
        self, index: Settings, commentary_file: Path, tmp_path: Path
    ) -> None:
        output = tmp_path / "tool_examples.md"
        results = tmp_path / "tool_results.json"
        client = FakeToolClient(
            "No tool needed.", "A grounded answer [primer_chunk_001]."
        )

        code = run_examples(
            index,
            queries_path=commentary_file,
            output_path=output,
            results_path=results,
            loads_path=DEFAULT_LOADS,
            k=3,
            client=client,
        )

        assert code == 0
        rendered = output.read_text(encoding="utf-8")
        assert "A conclusion authored by hand." in rendered
        for scenario in SCENARIOS:
            assert f"## {scenario.id} \u00b7 {scenario.title}" in rendered
            assert f"why {scenario.id}" in rendered

    def test_incomplete_commentary_blocks_the_markdown(
        self, index: Settings, tmp_path: Path
    ) -> None:
        queries = tmp_path / "queries.json"
        queries.write_text(json.dumps({"hw5_scenarios": {}}), encoding="utf-8")
        output = tmp_path / "tool_examples.md"
        results = tmp_path / "tool_results.json"
        client = FakeToolClient(
            "No tool needed.", "A grounded answer [primer_chunk_001]."
        )

        code = run_examples(
            index,
            queries_path=queries,
            output_path=output,
            results_path=results,
            loads_path=DEFAULT_LOADS,
            k=3,
            client=client,
        )

        assert code == 1
        assert results.is_file(), (
            "the mechanical results are still written for the second pass"
        )
        assert not output.exists(), (
            "a placeholder-filled artifact must never be rendered"
        )

    def test_the_missing_entries_are_named_on_stderr(
        self, index: Settings, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        queries = tmp_path / "queries.json"
        queries.write_text(json.dumps({"hw5_scenarios": {}}), encoding="utf-8")
        client = FakeToolClient("No tool needed.", "An answer.")

        run_examples(
            index,
            queries_path=queries,
            output_path=tmp_path / "out.md",
            results_path=tmp_path / "out.json",
            loads_path=DEFAULT_LOADS,
            k=3,
            client=client,
        )

        errors = capsys.readouterr().err
        assert "hw5_conclusion" in errors
        assert "hw5_scenarios.s1.comment" in errors


# --------------------------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------------------------


class TestCliValidation:
    @pytest.mark.parametrize(
        "argv",
        [
            [],
            ["--question", "x", "--examples"],
            ["--question", "x", "--list-tools"],
            ["--examples", "--list-tools"],
            ["--question", "x", "--examples", "--list-tools"],
        ],
    )
    def test_exactly_one_mode_is_required(self, argv: list[str]) -> None:
        with pytest.raises(SystemExit) as excinfo:
            main(argv)

        assert excinfo.value.code == 2

    def test_k_must_be_positive(self) -> None:
        with pytest.raises(SystemExit) as excinfo:
            main(["--question", "x", "--k", "0"])

        assert excinfo.value.code == 2

    def test_the_question_mode_reaches_the_orchestrator(
        self,
        monkeypatch: pytest.MonkeyPatch,
        index: Settings,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        # main() builds its own client, so the seam under test here is the CLI wiring itself:
        # argparse -> Settings -> run_question -> orchestrate. Everything below that has its own
        # tests; what this pins is that the wiring exists at all.
        client = FakeToolClient(
            (ScriptedCall("get_load_status", '{"load_id": "FX-2026-000042"}'),),
            "FX-2026-000042 is in transit.",
        )
        monkeypatch.setattr(
            external_tool.Settings, "from_env", classmethod(lambda cls, **kwargs: index)
        )
        monkeypatch.setattr(external_tool, "_real_client", lambda settings: client)

        assert main(["--question", "Where is load FX-2026-000042?"]) == 0

        out = capsys.readouterr().out
        assert "Route: tool" in out
        assert "Tool called: get_load_status" in out

    def test_confirm_carries_the_operator_authorisation_through_the_cli(
        self,
        monkeypatch: pytest.MonkeyPatch,
        index: Settings,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        booking = ScriptedCall(
            "book_load", '{"load_id": "FX-2026-000633", "carrier_id": "CAR-00412"}'
        )
        monkeypatch.setattr(
            external_tool.Settings, "from_env", classmethod(lambda cls, **kwargs: index)
        )
        client = FakeToolClient((booking,), "Booked.")
        monkeypatch.setattr(external_tool, "_real_client", lambda settings: client)

        assert (
            main(["--question", "Book FX-2026-000633 for CAR-00412.", "--confirm"]) == 0
        )

        assert '"booking_reference": "BKG-2026-000633"' in capsys.readouterr().out

    def test_the_same_request_without_confirm_is_refused_through_the_cli(
        self,
        monkeypatch: pytest.MonkeyPatch,
        index: Settings,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        booking = ScriptedCall(
            "book_load", '{"load_id": "FX-2026-000633", "carrier_id": "CAR-00412"}'
        )
        monkeypatch.setattr(
            external_tool.Settings, "from_env", classmethod(lambda cls, **kwargs: index)
        )
        client = FakeToolClient((booking,), "Needs authorisation.")
        monkeypatch.setattr(external_tool, "_real_client", lambda settings: client)

        assert main(["--question", "Book FX-2026-000633 for CAR-00412."]) == 0

        assert '"error": "confirmation_required"' in capsys.readouterr().out

    def test_a_domain_error_exits_one_with_a_diagnostic(
        self,
        monkeypatch: pytest.MonkeyPatch,
        index: Settings,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.setattr(
            external_tool.Settings, "from_env", classmethod(lambda cls, **kwargs: index)
        )

        code = main(
            [
                "--question",
                "Where is FX-2026-000042?",
                "--loads",
                str(tmp_path / "gone.json"),
            ]
        )

        assert code == 1
        assert capsys.readouterr().err.startswith("error: ")

    def test_listing_the_contract_needs_no_key_and_no_network(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setattr(external_tool.Settings, "from_env", _explode)

        assert main(["--list-tools"]) == 0

        assert "get_load_status" in capsys.readouterr().out


def _explode(**kwargs: Any) -> Settings:
    raise AssertionError("--list-tools must not read the environment or build a client")
