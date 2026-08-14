"""Tests for the Homework #6 deterministic agent workflow.

Offline like the rest of the suite, and more so: this layer calls no model, so there is nothing to
fake. Every test drives the production functions directly, which means a green suite is evidence
about the shipped flow rather than about a stand-in for it.

The routing matrix deliberately contains questions that are NOT among the five committed examples.
A router tested only against its own demo is fitted to it, and the cases that matter are the ones
where two rules could plausibly fire.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import agent_flow  # noqa: E402
from agent_flow import (  # noqa: E402
    ANSWER_COMPOSERS,
    CARRIER_ID_IN_TEXT,
    CLARIFICATION_QUESTIONS,
    EXAMPLES,
    KIND_GATE,
    KIND_TOOL,
    LOAD_ID_IN_TEXT,
    PLANS,
    PROTECTED_OUTPUTS,
    REASON_AMBIGUOUS_CARRIER_ID,
    REASON_AMBIGUOUS_LOAD_ID,
    REASON_MALFORMED_CARRIER_ID,
    REASON_MALFORMED_LOAD_ID,
    REASON_MISSING_CARRIER_ID,
    REASON_MISSING_LOAD_ID,
    REASON_NO_ROUTE_MATCHED,
    ROUTE_BOOKING,
    ROUTE_CLARIFICATION,
    ROUTE_KNOWLEDGE_BASE,
    ROUTE_LOAD_STATUS,
    ROUTE_PURPOSE,
    ROUTES,
    STATE_FIELDS,
    STEP_ASK_USER,
    STEP_BOOK_LOAD,
    STEP_CHECK_AUTHORISATION,
    STEP_GET_LOAD_STATUS,
    STEP_KINDS,
    STEP_SEARCH_KNOWLEDGE_BASE,
    TOOLS,
    AgentState,
    _missing_commentary,
    _unanchored,
    build_knowledge_index,
    check_authorisation,
    format_state,
    guard_outputs,
    load_commentary,
    main,
    render_contract,
    result_record,
    route,
    run_agent,
    search_knowledge_base,
    source_of,
)
from external_tool import (  # noqa: E402
    CARRIER_ID_PATTERN,
    DEFAULT_LOADS,
    LOAD_ID_PATTERN,
    load_operations_data,
)
import rag_lib  # noqa: E402
from rag_lib import Bm25Index, RetrievalError, Settings  # noqa: E402

# Loads that the committed fixture holds in each state the workflow reasons about. Named here so a
# fixture edit breaks one obvious constant instead of a dozen literals.
OPEN_LOAD = "FX-2026-000211"
SECOND_OPEN_LOAD = "FX-2026-000633"
MATCHED_LOAD = "FX-2026-000318"
IN_TRANSIT_LOAD = "FX-2026-000042"
DELIVERED_LOAD = "FX-2026-000407"
ALREADY_BOOKED_LOAD = "FX-2026-000105"
ACTIVE_CARRIER = "CAR-00817"
SUSPENDED_CARRIER = "CAR-00555"
UNKNOWN_LOAD = "FX-2026-999999"


# --------------------------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------------------------


@pytest.fixture
def operations() -> dict[str, Any]:
    """The committed operations fixture, freshly loaded so a booking cannot leak between tests."""
    return load_operations_data(DEFAULT_LOADS)


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        openai_api_key="",
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
def corpus(settings: Settings) -> Settings:
    """Three chunks, one per document_type the router's inference can select."""
    rows = [
        {
            "chunk_id": "primer_chunk_001",
            "text": (
                "Primer > Load Lifecycle. A load becomes booked when the demand side confirms one "
                "candidate carrier, and that is the first irreversible commercial transition."
            ),
            "metadata": {
                "document_id": "primer",
                "title": "Primer",
                "section": "Load Lifecycle",
                "document_type": "concept-guide",
            },
        },
        {
            "chunk_id": "cqrs_chunk_001",
            "text": (
                "CQRS > Command Side. A BookLoad command checks that the load is still open and "
                "not already committed elsewhere, then appends an event."
            ),
            "metadata": {
                "document_id": "cqrs",
                "title": "CQRS",
                "section": "Command Side",
                "document_type": "architecture-guide",
            },
        },
        {
            "chunk_id": "scaling_chunk_001",
            "text": (
                "Scaling > Deploys. Blue green deployment swaps traffic between two releases with "
                "zero downtime."
            ),
            "metadata": {
                "document_id": "scaling",
                "title": "Scaling",
                "section": "Deploys",
                "document_type": "playbook",
            },
        },
    ]
    settings.chunks_path.parent.mkdir(parents=True, exist_ok=True)
    settings.chunks_path.write_text(
        "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
    )
    return settings


@pytest.fixture
def knowledge(corpus: Settings) -> Bm25Index:
    return build_knowledge_index(corpus)


@pytest.fixture
def commentary_file(tmp_path: Path) -> Path:
    """A complete hand-authored commentary file, so the renderer has nothing to report missing."""
    payload = {
        "description": "offline fixture",
        "hw6_scenarios": {
            example.id: {"comment": f"comment {example.id}"} for example in EXAMPLES
        },
        "hw6_conclusion": "A conclusion authored by hand.",
    }
    path = tmp_path / "test_queries.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


# --------------------------------------------------------------------------------------------
# The workflow contract
# --------------------------------------------------------------------------------------------


class TestWorkflowContract:
    def test_every_route_has_a_plan_a_purpose_and_an_answer_composer(self) -> None:
        assert set(ROUTES) == set(PLANS) == set(ROUTE_PURPOSE) == set(ANSWER_COMPOSERS)

    def test_every_plan_step_has_a_declared_kind(self) -> None:
        planned = {step for plan in PLANS.values() for step in plan}
        assert planned == set(STEP_KINDS), (
            "a step in a plan with no kind would crash mid-run; a kind with no plan is dead code"
        )

    def test_tool_steps_and_only_tool_steps_are_in_the_tool_catalogue(self) -> None:
        tool_steps = {name for name, kind in STEP_KINDS.items() if kind == KIND_TOOL}
        assert tool_steps == set(TOOLS)

    def test_gate_steps_are_never_advertised_as_tools(self) -> None:
        for name, kind in STEP_KINDS.items():
            if kind == KIND_GATE:
                assert name not in TOOLS, f"{name} reads state, not a source"

    def test_no_route_has_an_empty_plan(self) -> None:
        # Every route records at least one step, so the § 3 block format always has a
        # `State after step:` line to render — including the clarification route, whose plan is a
        # single gate rather than an early return out of the step loop.
        for name, plan in PLANS.items():
            assert plan, f"route {name} would render a trace with no steps"
        assert PLANS[ROUTE_CLARIFICATION] == (STEP_ASK_USER,)

    def test_the_booking_plan_verifies_then_authorises_then_writes(self) -> None:
        assert PLANS[ROUTE_BOOKING] == (
            STEP_GET_LOAD_STATUS,
            STEP_CHECK_AUTHORISATION,
            STEP_BOOK_LOAD,
        ), "the write must be last, and the gate must sit between it and the read"

    def test_the_assignment_minimum_is_met(self) -> None:
        # § 2: at least 2 routes or 3 steps, and at least 2 mock tools.
        assert len(ROUTES) >= 2
        assert max(len(plan) for plan in PLANS.values()) >= 3
        assert len(TOOLS) >= 2

    def test_every_tool_declares_when_not_to_call_it(self) -> None:
        for tool in TOOLS.values():
            assert tool.when_not_to_call.strip()
            assert tool.returns.strip()
            assert tool.kind in {"read", "write"}

    def test_exactly_one_tool_writes(self) -> None:
        assert [name for name, tool in TOOLS.items() if tool.kind == "write"] == [
            STEP_BOOK_LOAD
        ]

    def test_every_clarification_reason_has_a_question_to_ask(self) -> None:
        reasons = {
            REASON_MISSING_LOAD_ID,
            REASON_MISSING_CARRIER_ID,
            REASON_MALFORMED_LOAD_ID,
            REASON_MALFORMED_CARRIER_ID,
            REASON_AMBIGUOUS_LOAD_ID,
            REASON_AMBIGUOUS_CARRIER_ID,
            REASON_NO_ROUTE_MATCHED,
        }
        assert set(CLARIFICATION_QUESTIONS) == reasons

    def test_state_fields_documents_every_field_the_state_carries(self) -> None:
        state = AgentState(user_goal="q")
        documented = set(STATE_FIELDS)
        # `observations` and `tool_calls` are properties, not dataclass fields, but they are part
        # of the state the assignment asks to be described — so the doc lists both kinds.
        actual = set(vars(state)) | {"observations", "tool_calls"}
        assert documented == actual

    def test_describe_prints_the_routes_tools_and_state(self) -> None:
        text = render_contract()
        for name in ROUTES:
            assert f"Route: {name}" in text
        for name in TOOLS:
            assert f"Tool: {name}" in text
        for name in STATE_FIELDS:
            assert f"{name}:" in text


# --------------------------------------------------------------------------------------------
# Identifier detection
# --------------------------------------------------------------------------------------------


class TestIdentifierDetection:
    def test_the_router_patterns_derive_from_the_tool_contract(self) -> None:
        # Single-sourced with external_tool: a second copy of the identifier shape is the one
        # place the router and the tool contract could silently disagree.
        assert _unanchored(LOAD_ID_PATTERN) in LOAD_ID_IN_TEXT.pattern
        assert _unanchored(CARRIER_ID_PATTERN) in CARRIER_ID_IN_TEXT.pattern

    def test_unanchored_strips_only_the_anchors(self) -> None:
        assert _unanchored("^abc$") == "abc"
        assert _unanchored("abc") == "abc"

    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("Where is FX-2026-000042?", "FX-2026-000042"),
            ("(FX-2026-000042)", "FX-2026-000042"),
            ("load FX-2026-000042, please", "FX-2026-000042"),
            ("FX-2026-000042", "FX-2026-000042"),
        ],
        ids=["trailing-punctuation", "parenthesised", "comma", "bare"],
    )
    def test_a_well_formed_load_id_is_found_inside_a_sentence(
        self, text: str, expected: str
    ) -> None:
        match = LOAD_ID_IN_TEXT.search(text)
        assert match is not None and match.group(0) == expected

    @pytest.mark.parametrize(
        "text",
        [
            "FX-2026-0000421",
            "XFX-2026-000042",
            "fx-2026-000042",
            "FX-26-42",
            "FX-2026-00042",
        ],
        ids=["too-long", "prefixed", "lower-case", "short-groups", "five-digits"],
    )
    def test_a_near_miss_is_not_read_as_a_load_id(self, text: str) -> None:
        # The over-long case is the dangerous one: without the trailing guard the pattern would
        # yield a real-looking FX-2026-000042 and the workflow would answer about another load.
        assert LOAD_ID_IN_TEXT.search(text) is None

    def test_a_carrier_id_is_found_but_a_bare_number_is_not(self) -> None:
        assert CARRIER_ID_IN_TEXT.search("for carrier CAR-00817.") is not None
        assert CARRIER_ID_IN_TEXT.search("for carrier 817") is None


# --------------------------------------------------------------------------------------------
# Routing
# --------------------------------------------------------------------------------------------

# (question, expected route, expected clarification reason). Cases marked "not an example" exist
# precisely because they are absent from outputs/agent_flow_examples.md.
# (question, expected route, expected clarification reason, expected router rule). The rule is
# pinned per case on purpose: CLAUDE.md records the rule ORDER as load-bearing, every trace prints
# it, and without this assertion swapping two rules in route() leaves the whole suite green.
# Cases marked NEW-REGRESSION reproduce a defect an adversarial review found in a shipped version.
ROUTING_MATRIX: tuple[tuple[str, str, str | None, str], ...] = (
    # R1 — more than one candidate identifier, refused before an irreversible write.
    (
        f"Where is {IN_TRANSIT_LOAD} and should I book {MATCHED_LOAD} for {ACTIVE_CARRIER}?",
        ROUTE_CLARIFICATION,
        REASON_AMBIGUOUS_LOAD_ID,
        "R1",
    ),
    (
        f"Book {OPEN_LOAD} for {ACTIVE_CARRIER} or CAR-00933?",
        ROUTE_CLARIFICATION,
        REASON_AMBIGUOUS_CARRIER_ID,
        "R1",
    ),
    # NEW-REGRESSION: a valid id beside a mistyped one is still two candidates.
    (
        f"Book {OPEN_LOAD} or FX-26-42 for {ACTIVE_CARRIER}.",
        ROUTE_CLARIFICATION,
        REASON_AMBIGUOUS_LOAD_ID,
        "R1",
    ),
    # R2 — an actionable booking request.
    (f"Book load {OPEN_LOAD} for carrier {ACTIVE_CARRIER}.", ROUTE_BOOKING, None, "R2"),
    (f"Assign {MATCHED_LOAD} to CAR-00412", ROUTE_BOOKING, None, "R2"),
    (
        f"Please commit {OPEN_LOAD} to {SUSPENDED_CARRIER} now",
        ROUTE_BOOKING,
        None,
        "R2",
    ),
    (
        f"Book {OPEN_LOAD} for {ACTIVE_CARRIER}. {OPEN_LOAD} is the Antwerp one.",
        ROUTE_BOOKING,
        None,
        "R2",
    ),
    # R3 — a booking request the workflow cannot act on.
    ("Book a load for me.", ROUTE_CLARIFICATION, REASON_MISSING_LOAD_ID, "R3"),
    (f"Book load {OPEN_LOAD}.", ROUTE_CLARIFICATION, REASON_MISSING_CARRIER_ID, "R3"),
    (
        f"Book load {OPEN_LOAD} for carrier 817.",
        ROUTE_CLARIFICATION,
        REASON_MISSING_CARRIER_ID,
        "R3",
    ),
    (
        f"Book load {OPEN_LOAD} for carrier CAR-817.",
        ROUTE_CLARIFICATION,
        REASON_MALFORMED_CARRIER_ID,
        "R3",
    ),
    (
        f"Book load FX-26-42 for {ACTIVE_CARRIER}",
        ROUTE_CLARIFICATION,
        REASON_MALFORMED_LOAD_ID,
        "R3",
    ),
    (
        "Reserve capacity with CAR-00412 next week.",
        ROUTE_CLARIFICATION,
        REASON_MISSING_LOAD_ID,
        "R3",
    ),
    # NEW-REGRESSION: the booking clause names no load, so none may be borrowed from the read
    # clause beside it — with or without the sentence boundary.
    (
        f"Where is load {SECOND_OPEN_LOAD} right now? Also, book a truck from carrier "
        f"{ACTIVE_CARRIER}.",
        ROUTE_CLARIFICATION,
        REASON_MISSING_LOAD_ID,
        "R3",
    ),
    (
        f"Where is {SECOND_OPEN_LOAD} and book a truck for {ACTIVE_CARRIER}?",
        ROUTE_CLARIFICATION,
        REASON_MISSING_LOAD_ID,
        "R3",
    ),
    # R4 — a load is named, so answer about that load.
    (f"Where is load {IN_TRANSIT_LOAD} right now?", ROUTE_LOAD_STATUS, None, "R4"),
    (f"Is ({IN_TRANSIT_LOAD}) delivered yet?", ROUTE_LOAD_STATUS, None, "R4"),
    (f"{UNKNOWN_LOAD}", ROUTE_LOAD_STATUS, None, "R4"),
    (f"Who is carrying {IN_TRANSIT_LOAD}?", ROUTE_LOAD_STATUS, None, "R4"),
    # R5 — an identifier was attempted and mistyped.
    (
        "Give me the status of load FX-26-42.",
        ROUTE_CLARIFICATION,
        REASON_MALFORMED_LOAD_ID,
        "R5",
    ),
    ("Where is fx-2026-000042?", ROUTE_CLARIFICATION, REASON_MALFORMED_LOAD_ID, "R5"),
    ("Status of FX-2026-0000421?", ROUTE_CLARIFICATION, REASON_MALFORMED_LOAD_ID, "R5"),
    ("Tell me about CAR-817", ROUTE_CLARIFICATION, REASON_MALFORMED_CARRIER_ID, "R5"),
    # R6 — the question asks what something means, whatever else it mentions.
    (
        "What does it mean for a load to be booked, and why is that irreversible?",
        ROUTE_KNOWLEDGE_BASE,
        None,
        "R6",
    ),
    ("What does the status matched mean?", ROUTE_KNOWLEDGE_BASE, None, "R6"),
    (
        "Explain the difference between a broker and a carrier.",
        ROUTE_KNOWLEDGE_BASE,
        None,
        "R6",
    ),
    ("Why was the strangler pattern chosen?", ROUTE_KNOWLEDGE_BASE, None, "R6"),
    (
        "What does it mean to book a load that is only matched?",
        ROUTE_KNOWLEDGE_BASE,
        None,
        "R6",
    ),
    (
        "Why is a commit irreversible in the event log?",
        ROUTE_KNOWLEDGE_BASE,
        None,
        "R6",
    ),
    # R7 — live state wanted, no load named.
    ("Where is my load?", ROUTE_CLARIFICATION, REASON_MISSING_LOAD_ID, "R7"),
    (
        "What is the status of my shipment?",
        ROUTE_CLARIFICATION,
        REASON_MISSING_LOAD_ID,
        "R7",
    ),
    ("Give me the ETA.", ROUTE_CLARIFICATION, REASON_MISSING_LOAD_ID, "R7"),
    # R8 — the corpus's own vocabulary, via Homework #3's inference.
    ("How does load matching work?", ROUTE_KNOWLEDGE_BASE, None, "R8"),
    ("How do we release code without interruption?", ROUTE_KNOWLEDGE_BASE, None, "R8"),
    ("Tell me about event sourcing and projections.", ROUTE_KNOWLEDGE_BASE, None, "R8"),
    # NEW-REGRESSION: a bare booking verb with no operand is documentation, not a request.
    ("How do I book a load on the exchange?", ROUTE_KNOWLEDGE_BASE, None, "R8"),
    (
        "What happens when two carriers commit to the same load?",
        ROUTE_KNOWLEDGE_BASE,
        None,
        "R8",
    ),
    # R9 — nothing matched. Never guess a route.
    (
        "Tell me something interesting.",
        ROUTE_CLARIFICATION,
        REASON_NO_ROUTE_MATCHED,
        "R9",
    ),
    ("Hello!", ROUTE_CLARIFICATION, REASON_NO_ROUTE_MATCHED, "R9"),
    ("", ROUTE_CLARIFICATION, REASON_NO_ROUTE_MATCHED, "R9"),
    # NEW-REGRESSION: a well-formed carrier id is not a malformed one; it simply names no route.
    (
        f"Is {ACTIVE_CARRIER} active?",
        ROUTE_CLARIFICATION,
        REASON_NO_ROUTE_MATCHED,
        "R9",
    ),
)


class TestRouting:
    @pytest.mark.parametrize(
        ("question", "expected_route", "expected_reason", "expected_rule"),
        ROUTING_MATRIX,
        ids=[
            f"{rule}:{expected}:{question[:32]!r}"
            for question, expected, _, rule in ROUTING_MATRIX
        ],
    )
    def test_the_router_sends_each_question_where_the_rules_say(
        self,
        question: str,
        expected_route: str,
        expected_reason: str | None,
        expected_rule: str,
    ) -> None:
        decision = route(question)

        assert decision.route == expected_route
        assert decision.reason == expected_reason
        # The rule id is pinned, not merely the route: CLAUDE.md records the rule ORDER as
        # load-bearing and every trace prints it, so a reorder that happens to preserve the
        # routes must still fail here.
        assert decision.rule == expected_rule

    def test_the_matrix_exercises_every_route(self) -> None:
        assert {expected for _, expected, _, _ in ROUTING_MATRIX} == set(ROUTES)

    def test_the_matrix_exercises_every_rule(self) -> None:
        fired = {rule for _, _, _, rule in ROUTING_MATRIX}
        assert fired == {f"R{number}" for number in range(1, 10)}

    def test_the_matrix_is_not_merely_the_committed_examples(self) -> None:
        example_questions = {example.question for example in EXAMPLES}
        novel = [q for q, _, _, _ in ROUTING_MATRIX if q not in example_questions]
        assert len(novel) >= 20, "a router tested only on its own demo is fitted to it"

    def test_the_past_participle_is_not_a_booking_request(self) -> None:
        # "booked" is a different token from "book". Without whole-token matching, every question
        # about what booking *means* would be routed as a request to book something.
        assert route("Which loads are already booked?").route != ROUTE_BOOKING
        assert route("What is the booking process?").route != ROUTE_BOOKING

    def test_an_explicit_definition_question_beats_live_state_vocabulary(self) -> None:
        # "status" is live-state vocabulary and "mean" is knowledge intent; the question is about
        # the word, so the corpus wins.
        assert route("What does the status matched mean?").route == ROUTE_KNOWLEDGE_BASE
        assert route("What is the status of my load?").route == ROUTE_CLARIFICATION

    def test_the_booking_operands_come_from_the_booking_clause(self) -> None:
        # The router reads operands from the span that asks for the booking, not from the whole
        # sentence. Otherwise the load in the read clause is the one that gets committed, and the
        # gate authorises it because the gate verifies whatever the router chose.
        borrowed = route(
            f"Where is load {SECOND_OPEN_LOAD} right now? Also, book a truck from carrier "
            f"{ACTIVE_CARRIER}."
        )
        direct = route(f"Book load {SECOND_OPEN_LOAD} for carrier {ACTIVE_CARRIER}.")

        assert borrowed.route == ROUTE_CLARIFICATION
        assert borrowed.load_id is None
        assert direct.route == ROUTE_BOOKING
        assert direct.load_id == SECOND_OPEN_LOAD

    def test_a_mistyped_identifier_beside_a_valid_one_is_ambiguous(self) -> None:
        # Counting only strictly-valid ids finds one candidate here and books it, discarding the
        # user's own visible uncertainty right before an irreversible write.
        decision = route(f"Book {OPEN_LOAD} or FX-26-42 for {ACTIVE_CARRIER}.")

        assert decision.route == ROUTE_CLARIFICATION
        assert decision.reason == REASON_AMBIGUOUS_LOAD_ID

    def test_the_same_identifier_in_two_cases_is_one_candidate(self) -> None:
        # The ATTEMPT patterns are case-tolerant, so without normalisation this reads as two
        # candidates and refuses a request that names exactly one load.
        decision = route(
            f"Book {OPEN_LOAD} for {ACTIVE_CARRIER}, i.e. {OPEN_LOAD.lower()}."
        )

        assert decision.reason != REASON_AMBIGUOUS_LOAD_ID

    def test_a_named_load_beats_a_definition_question(self) -> None:
        # The documented misroute: the user named a live load, so the workflow answers about that
        # load rather than about the word. docs/homework6/agent-flow-spec.md § Known limits.
        decision = route(
            f"What does it mean that load {IN_TRANSIT_LOAD} is in transit?"
        )

        assert decision.route == ROUTE_LOAD_STATUS
        assert decision.rule == "R4"

    def test_the_router_never_invents_an_identifier(self) -> None:
        # Homework #5 measured its model padding "carrier 817" into CAR-00817 — a fabrication every
        # syntactic validator accepts. A rule-based router cannot do that; it asks.
        decision = route(f"Book load {OPEN_LOAD} for carrier 817.")

        assert decision.carrier_id is None
        assert decision.reason == REASON_MISSING_CARRIER_ID

    def test_routing_is_a_pure_function_of_the_question(self) -> None:
        question = f"Book load {OPEN_LOAD} for carrier {ACTIVE_CARRIER}."
        assert route(question) == route(question)

    def test_a_second_load_identifier_stops_the_booking_route(self) -> None:
        # The router binds to the FIRST identifier in the sentence, whichever clause the booking
        # verb governs. Without this guard the request below books the load the user only asked
        # "where is" about, and the confirmation gate cannot catch it: it verifies the load the
        # router already chose, finds it genuinely open, and authorises it.
        decision = route(
            f"Where is {IN_TRANSIT_LOAD} and should I book {MATCHED_LOAD} for {ACTIVE_CARRIER}?"
        )

        assert decision.route == ROUTE_CLARIFICATION
        assert decision.reason == REASON_AMBIGUOUS_LOAD_ID

    def test_a_repeated_identifier_is_emphasis_and_not_ambiguity(self) -> None:
        # Distinct matches, not the raw count: naming one load twice is still one load.
        decision = route(
            f"Book {OPEN_LOAD} for {ACTIVE_CARRIER}. {OPEN_LOAD} is the Antwerp one."
        )

        assert decision.route == ROUTE_BOOKING
        assert decision.load_id == OPEN_LOAD

    def test_the_ambiguity_guard_is_scoped_to_the_write_route(self) -> None:
        # A read that names two loads answers about the first. The guard's justification is
        # irreversibility, not tidiness, so it deliberately does not fire here.
        decision = route(f"Status of {IN_TRANSIT_LOAD} and {OPEN_LOAD}?")

        assert decision.route == ROUTE_LOAD_STATUS
        assert decision.load_id == IN_TRANSIT_LOAD

    @pytest.mark.parametrize(
        "carrier_id", ["CAR-00817", "CAR-00412", "CAR-00933", "CAR-00555"]
    )
    def test_a_well_formed_carrier_id_is_never_called_malformed(
        self, carrier_id: str
    ) -> None:
        # No rule before R5 consumes a carrier id on its own, so without the `carrier_id is None`
        # guard every real carrier in the fixture reaches the near-miss branch and the workflow
        # tells the user a valid identifier is mistyped.
        decision = route(f"Is {carrier_id} active?")

        assert decision.reason != REASON_MALFORMED_CARRIER_ID

    @pytest.mark.parametrize(
        "question",
        [
            "How do I book a load on the exchange?",
            "What happens when I book a load?",
            "How does the system decide which carrier to assign?",
            "Can a shipper reserve capacity in advance?",
        ],
        ids=["how-to-book", "what-happens", "how-assign", "can-reserve"],
    )
    def test_a_booking_verb_with_no_operand_is_documentation(
        self, question: str
    ) -> None:
        # "book", "commit", "assign" and "reserve" are corpus vocabulary as well as imperatives.
        # Firing the booking route on their bare presence sends the reader's most likely first
        # question to "which load do you mean?".
        assert route(question).route == ROUTE_KNOWLEDGE_BASE

    @pytest.mark.parametrize(
        "question",
        [
            "Book a load for me.",
            "Please book the Antwerp to Milan load.",
            "Reserve capacity with CAR-00412 next week.",
        ],
        ids=["bare", "polite", "carrier-only"],
    )
    def test_an_imperative_booking_request_survives_without_a_load_id(
        self, question: str
    ) -> None:
        # The other half of the same guard: an identifier-only test would send these to the corpus.
        assert route(question).route == ROUTE_CLARIFICATION
        assert route(question).reason == REASON_MISSING_LOAD_ID


# --------------------------------------------------------------------------------------------
# Tools
# --------------------------------------------------------------------------------------------


class TestKnowledgeBaseTool:
    def test_it_returns_ranked_matches_with_their_metadata(
        self, knowledge: Bm25Index
    ) -> None:
        observation = search_knowledge_base(
            "What does it mean for a load to be booked?", knowledge=knowledge, k=3
        )

        assert observation["ok"] is True
        assert observation["top_chunk_id"] == "primer_chunk_001"
        top = observation["matches"][0]
        assert top["title"] == "Primer"
        assert top["section"] == "Load Lifecycle"
        assert top["document_type"] == "concept-guide"
        assert top["rank"] == 1

    def test_it_reuses_homework_3s_rule_based_document_type_inference(
        self, knowledge: Bm25Index
    ) -> None:
        observation = search_knowledge_base(
            "How does blue green deployment avoid downtime?", knowledge=knowledge, k=3
        )

        assert observation["document_type_filter"] == "playbook"
        assert all(
            match["document_type"] == "playbook" for match in observation["matches"]
        )

    def test_two_keywords_from_one_document_select_that_document(
        self, knowledge: Bm25Index
    ) -> None:
        observation = search_knowledge_base(
            "command and projection", knowledge=knowledge, k=3
        )

        assert observation["document_type_filter"] == "architecture-guide"

    def test_a_tie_between_documents_leaves_the_search_unfiltered(
        self, knowledge: Bm25Index
    ) -> None:
        # Homework #3's rule: ambiguity means filtering would be a guess, and a wrong filter
        # excludes the right document entirely. The tool inherits that, so the whole corpus is
        # searched rather than an arbitrary half of it.
        observation = search_knowledge_base(
            "carrier and event", knowledge=knowledge, k=3
        )

        assert observation["document_type_filter"] is None

    def test_k_bounds_the_number_of_matches(self, knowledge: Bm25Index) -> None:
        observation = search_knowledge_base("load", knowledge=knowledge, k=1)

        assert observation["match_count"] == 1

    def test_a_miss_is_reported_and_never_returned_as_an_empty_success(
        self, knowledge: Bm25Index
    ) -> None:
        observation = search_knowledge_base(
            "quantum chromodynamics", knowledge=knowledge, k=3
        )

        assert observation["ok"] is False
        assert observation["error"] == "no_match"
        assert "matches" not in observation

    def test_the_quoted_excerpt_drops_the_breadcrumb_the_attribution_already_carries(
        self, knowledge: Bm25Index
    ) -> None:
        observation = search_knowledge_base(
            "irreversible commercial transition", knowledge=knowledge, k=1
        )
        excerpt = observation["matches"][0]["excerpt"]

        assert not excerpt.startswith("Primer > Load Lifecycle.")
        assert excerpt.startswith("A load becomes booked")


class TestKnowledgeIndexIntegrity:
    @pytest.mark.parametrize("missing", ["title", "section", "document_type"])
    def test_a_chunk_missing_quoted_metadata_stops_the_run(
        self, settings: Settings, missing: str
    ) -> None:
        # The answer cites title and section by name. Without this check a corrupt corpus is
        # reported as a successful match and the graded answer reads "According to None § None".
        row = {
            "chunk_id": "broken_chunk_001",
            "text": "Broken > Section. Some text.",
            "metadata": {
                "title": "Broken",
                "section": "Section",
                "document_type": "playbook",
            },
        }
        del row["metadata"][missing]
        settings.chunks_path.parent.mkdir(parents=True, exist_ok=True)
        settings.chunks_path.write_text(json.dumps(row) + "\n", encoding="utf-8")

        with pytest.raises(RetrievalError, match="prepare_knowledge_base.py"):
            build_knowledge_index(settings)

    def test_the_committed_corpus_passes_that_check(self) -> None:
        assert (
            len(build_knowledge_index(Settings.from_env(require_key=False))._by_id) > 0
        )


class TestOperationsTools:
    def test_get_load_status_reports_live_state(
        self, operations: dict[str, Any]
    ) -> None:
        observation = agent_flow.get_load_status(IN_TRANSIT_LOAD, operations=operations)

        assert observation["ok"] is True
        assert observation["status"] == "in_transit"
        assert observation["carrier"]["carrier_id"] == ACTIVE_CARRIER

    def test_an_unknown_load_is_a_refusal_and_not_an_exception(
        self, operations: dict[str, Any]
    ) -> None:
        # A tool-domain miss must reach the state as an observation. Raising would abort a run over
        # an ordinary business answer the user is entitled to hear.
        observation = agent_flow.get_load_status(UNKNOWN_LOAD, operations=operations)

        assert observation["ok"] is False
        assert observation["error"] == "unknown_load"

    def test_book_load_commits_and_returns_a_reference(
        self, operations: dict[str, Any]
    ) -> None:
        observation = agent_flow.book_load(
            OPEN_LOAD, ACTIVE_CARRIER, operations=operations
        )

        assert observation["ok"] is True
        assert observation["booking_reference"] == "BKG-2026-000211"
        assert operations["loads"][OPEN_LOAD]["status"] == "booked"

    def test_a_suspended_carrier_cannot_take_a_load(
        self, operations: dict[str, Any]
    ) -> None:
        observation = agent_flow.book_load(
            OPEN_LOAD, SUSPENDED_CARRIER, operations=operations
        )

        assert observation["ok"] is False
        assert observation["error"] == "carrier_not_permitted"
        assert operations["loads"][OPEN_LOAD]["status"] == "posted"


# --------------------------------------------------------------------------------------------
# The authorisation gate — the step that reads the state
# --------------------------------------------------------------------------------------------


def _state_after_status(
    load_id: str, operations: dict[str, Any], *, plan: tuple[str, ...] = ()
) -> AgentState:
    """An AgentState carrying exactly one recorded get_load_status observation."""
    state = AgentState(user_goal="…", selected_route=ROUTE_BOOKING, plan=plan)
    state.steps.append(
        agent_flow.StepRecord(
            index=1,
            name=STEP_GET_LOAD_STATUS,
            kind=KIND_TOOL,
            arguments={"load_id": load_id},
            observation=agent_flow.get_load_status(load_id, operations=operations),
        )
    )
    return state


class TestCheckAuthorisation:
    def test_it_refuses_when_no_earlier_step_verified_the_load(self) -> None:
        state = AgentState(user_goal="…", selected_route=ROUTE_BOOKING)

        observation = check_authorisation(
            state,
            load_id=OPEN_LOAD,
            carrier_id=ACTIVE_CARRIER,
            operator_confirmed=True,
        )

        assert observation["ok"] is False
        assert observation["error"] == "load_not_verified"

    def test_it_refuses_when_the_earlier_step_could_not_find_the_load(
        self, operations: dict[str, Any]
    ) -> None:
        state = _state_after_status(UNKNOWN_LOAD, operations)

        observation = check_authorisation(
            state,
            load_id=UNKNOWN_LOAD,
            carrier_id=ACTIVE_CARRIER,
            operator_confirmed=True,
        )

        assert observation["error"] == "load_not_verified"

    @pytest.mark.parametrize(
        "load_id", [IN_TRANSIT_LOAD, DELIVERED_LOAD, ALREADY_BOOKED_LOAD]
    )
    def test_it_refuses_a_load_the_recorded_observation_says_is_closed(
        self, load_id: str, operations: dict[str, Any]
    ) -> None:
        state = _state_after_status(load_id, operations)

        observation = check_authorisation(
            state,
            load_id=load_id,
            carrier_id=ACTIVE_CARRIER,
            operator_confirmed=True,
        )

        assert observation["ok"] is False
        assert observation["error"] == "load_not_open"
        assert observation["load_is_open"] is False

    def test_it_refuses_an_open_load_the_operator_never_authorised(
        self, operations: dict[str, Any]
    ) -> None:
        state = _state_after_status(OPEN_LOAD, operations)

        observation = check_authorisation(
            state,
            load_id=OPEN_LOAD,
            carrier_id=ACTIVE_CARRIER,
            operator_confirmed=False,
        )

        assert observation["ok"] is False
        assert observation["error"] == "confirmation_required"
        assert observation["load_is_open"] is True

    @pytest.mark.parametrize("load_id", [OPEN_LOAD, MATCHED_LOAD, SECOND_OPEN_LOAD])
    def test_it_passes_an_open_load_the_operator_authorised(
        self, load_id: str, operations: dict[str, Any]
    ) -> None:
        state = _state_after_status(load_id, operations)

        observation = check_authorisation(
            state,
            load_id=load_id,
            carrier_id=ACTIVE_CARRIER,
            operator_confirmed=True,
        )

        assert observation["ok"] is True
        assert observation["operator_confirmed"] is True

    def test_the_gate_reads_the_state_and_not_the_operations_data(
        self, operations: dict[str, Any]
    ) -> None:
        # Proof that the step is a genuine state consumer: with a stale recorded observation the
        # gate follows the record, not the live dict it was never given.
        state = _state_after_status(OPEN_LOAD, operations)
        operations["loads"][OPEN_LOAD]["status"] = "delivered"

        observation = check_authorisation(
            state,
            load_id=OPEN_LOAD,
            carrier_id=ACTIVE_CARRIER,
            operator_confirmed=True,
        )

        assert observation["ok"] is True, (
            "the gate must consult the recorded observation"
        )


# --------------------------------------------------------------------------------------------
# The flow
# --------------------------------------------------------------------------------------------


class TestRunAgent:
    def test_an_empty_question_is_a_diagnostic_error(
        self, operations: dict[str, Any], knowledge: Bm25Index
    ) -> None:
        with pytest.raises(RetrievalError, match="question is empty"):
            run_agent("   ", operations=operations, knowledge=knowledge)

    def test_the_knowledge_route_runs_one_tool_step(
        self, operations: dict[str, Any], knowledge: Bm25Index
    ) -> None:
        state = run_agent(
            "What does it mean for a load to be booked?",
            operations=operations,
            knowledge=knowledge,
        )

        assert state.selected_route == ROUTE_KNOWLEDGE_BASE
        assert state.tool_calls == [STEP_SEARCH_KNOWLEDGE_BASE]
        assert state.halted_at is None
        assert "primer_chunk_001" in str(state.final_answer)

    def test_the_load_status_route_reports_the_named_load(
        self, operations: dict[str, Any], knowledge: Bm25Index
    ) -> None:
        state = run_agent(
            f"Where is load {IN_TRANSIT_LOAD}?",
            operations=operations,
            knowledge=knowledge,
        )

        assert state.selected_route == ROUTE_LOAD_STATUS
        assert state.tool_calls == [STEP_GET_LOAD_STATUS]
        assert IN_TRANSIT_LOAD in str(state.final_answer)

    def test_an_unknown_load_is_relayed_rather_than_invented(
        self, operations: dict[str, Any], knowledge: Bm25Index
    ) -> None:
        state = run_agent(
            f"What is the status of load {UNKNOWN_LOAD}?",
            operations=operations,
            knowledge=knowledge,
        )

        assert "does not exist" in str(state.final_answer)

    def test_the_clarification_route_calls_no_tool(
        self, operations: dict[str, Any], knowledge: Bm25Index
    ) -> None:
        state = run_agent(
            "Give me the status of load FX-26-42.",
            operations=operations,
            knowledge=knowledge,
        )

        assert state.selected_route == ROUTE_CLARIFICATION
        assert state.tool_calls == []
        assert state.steps[0].kind == KIND_GATE
        assert state.clarification_reason == REASON_MALFORMED_LOAD_ID

    def test_an_unauthorised_booking_halts_before_the_write(
        self, operations: dict[str, Any], knowledge: Bm25Index
    ) -> None:
        state = run_agent(
            f"Book load {OPEN_LOAD} for carrier {ACTIVE_CARRIER}.",
            operations=operations,
            knowledge=knowledge,
            operator_confirmed=False,
        )

        assert state.selected_route == ROUTE_BOOKING
        assert len(state.steps) == 2
        assert state.halted_at == STEP_CHECK_AUTHORISATION
        assert STEP_BOOK_LOAD not in state.tool_calls
        assert operations["loads"][OPEN_LOAD]["status"] == "posted"

    def test_an_authorised_booking_runs_the_whole_plan(
        self, operations: dict[str, Any], knowledge: Bm25Index
    ) -> None:
        state = run_agent(
            f"Book load {OPEN_LOAD} for carrier {ACTIVE_CARRIER}.",
            operations=operations,
            knowledge=knowledge,
            operator_confirmed=True,
        )

        assert len(state.steps) == 3
        assert state.halted_at is None
        assert state.tool_calls == [STEP_GET_LOAD_STATUS, STEP_BOOK_LOAD]
        assert "BKG-2026-000211" in str(state.final_answer)

    def test_a_closed_load_halts_at_the_gate_even_with_authorisation(
        self, operations: dict[str, Any], knowledge: Bm25Index
    ) -> None:
        state = run_agent(
            f"Book load {DELIVERED_LOAD} for carrier {ACTIVE_CARRIER}.",
            operations=operations,
            knowledge=knowledge,
            operator_confirmed=True,
        )

        assert state.halted_at == STEP_CHECK_AUTHORISATION
        assert STEP_BOOK_LOAD not in state.tool_calls

    def test_an_unknown_load_halts_the_booking_at_the_first_step(
        self, operations: dict[str, Any], knowledge: Bm25Index
    ) -> None:
        state = run_agent(
            f"Book load {UNKNOWN_LOAD} for carrier {ACTIVE_CARRIER}.",
            operations=operations,
            knowledge=knowledge,
            operator_confirmed=True,
        )

        assert len(state.steps) == 1
        assert state.halted_at == STEP_GET_LOAD_STATUS

    def test_the_write_step_is_unreachable_without_the_gate(
        self, operations: dict[str, Any], knowledge: Bm25Index
    ) -> None:
        # The whole point of the three-step plan: across every reachable booking outcome, the write
        # runs only when the gate passed.
        for load_id, confirmed in (
            (OPEN_LOAD, False),
            (DELIVERED_LOAD, True),
            (ALREADY_BOOKED_LOAD, True),
            (UNKNOWN_LOAD, True),
        ):
            state = run_agent(
                f"Book load {load_id} for carrier {ACTIVE_CARRIER}.",
                operations=operations,
                knowledge=knowledge,
                operator_confirmed=confirmed,
            )
            gate = state.observation_of(STEP_CHECK_AUTHORISATION)
            wrote = STEP_BOOK_LOAD in state.tool_calls

            assert not wrote, f"{load_id} was written with gate={gate}"

    def test_an_ambiguous_request_writes_nothing_even_under_confirmation(
        self, operations: dict[str, Any], knowledge: Bm25Index
    ) -> None:
        # End to end, the defect the R1 guard exists to stop: --confirm plus a first-clause read
        # identifier would otherwise commit a load the user never asked to book.
        before = operations["loads"][IN_TRANSIT_LOAD]["status"]

        state = run_agent(
            f"Where is {IN_TRANSIT_LOAD} and should I book {MATCHED_LOAD} for {ACTIVE_CARRIER}?",
            operations=operations,
            knowledge=knowledge,
            operator_confirmed=True,
        )

        assert state.selected_route == ROUTE_CLARIFICATION
        assert state.tool_calls == []
        assert operations["loads"][IN_TRANSIT_LOAD]["status"] == before
        assert operations["loads"][MATCHED_LOAD]["status"] == "matched"

    def test_every_run_ends_with_an_answer(
        self, operations: dict[str, Any], knowledge: Bm25Index
    ) -> None:
        for question, _, _, _ in ROUTING_MATRIX:
            if not question.strip():
                continue
            state = run_agent(question, operations=operations, knowledge=knowledge)

            assert state.final_answer, f"no answer for {question!r}"

    def test_a_later_step_reads_an_earlier_steps_observation(
        self, operations: dict[str, Any], knowledge: Bm25Index
    ) -> None:
        state = run_agent(
            f"Book load {OPEN_LOAD} for carrier {ACTIVE_CARRIER}.",
            operations=operations,
            knowledge=knowledge,
            operator_confirmed=True,
        )
        status = state.observation_of(STEP_GET_LOAD_STATUS)
        gate = state.observation_of(STEP_CHECK_AUTHORISATION)

        assert gate is not None and status is not None
        assert gate["status"] == status["status"] == "posted"

    def test_observation_of_returns_none_for_a_step_that_never_ran(
        self, operations: dict[str, Any], knowledge: Bm25Index
    ) -> None:
        state = run_agent(
            "Where is my load?", operations=operations, knowledge=knowledge
        )

        assert state.observation_of(STEP_BOOK_LOAD) is None


class TestStateSnapshot:
    def test_an_earlier_snapshot_does_not_know_about_a_later_halt(
        self, operations: dict[str, Any], knowledge: Bm25Index
    ) -> None:
        state = run_agent(
            f"Book load {OPEN_LOAD} for carrier {ACTIVE_CARRIER}.",
            operations=operations,
            knowledge=knowledge,
        )

        assert state.snapshot(after_step=1)["halted_at"] is None
        assert state.snapshot(after_step=2)["halted_at"] == STEP_CHECK_AUTHORISATION

    def test_an_intermediate_snapshot_carries_no_answer(
        self, operations: dict[str, Any], knowledge: Bm25Index
    ) -> None:
        state = run_agent(
            f"Book load {OPEN_LOAD} for carrier {ACTIVE_CARRIER}.",
            operations=operations,
            knowledge=knowledge,
            operator_confirmed=True,
        )

        assert state.snapshot(after_step=1)["final_answer"] is None
        assert state.snapshot()["final_answer"] == state.final_answer

    def test_the_snapshot_grows_one_observation_per_step(
        self, operations: dict[str, Any], knowledge: Bm25Index
    ) -> None:
        state = run_agent(
            f"Book load {OPEN_LOAD} for carrier {ACTIVE_CARRIER}.",
            operations=operations,
            knowledge=knowledge,
            operator_confirmed=True,
        )
        counts = [
            len(state.snapshot(after_step=index)["observations"])
            for index in range(1, len(state.steps) + 1)
        ]

        assert counts == [1, 2, 3]

    def test_the_observations_view_matches_the_recorded_steps(
        self, operations: dict[str, Any], knowledge: Bm25Index
    ) -> None:
        # `observations` is one of the five state fields § 2 names, and --describe advertises it,
        # so it is part of the contract and not an accessor nothing reads.
        state = run_agent(
            f"Book load {OPEN_LOAD} for carrier {ACTIVE_CARRIER}.",
            operations=operations,
            knowledge=knowledge,
            operator_confirmed=True,
        )

        assert state.observations == [step.observation for step in state.steps]
        assert [o["ok"] for o in state.observations] == [True, True, True]

    def test_gate_steps_are_not_counted_as_tool_calls(
        self, operations: dict[str, Any], knowledge: Bm25Index
    ) -> None:
        state = run_agent(
            f"Book load {OPEN_LOAD} for carrier {ACTIVE_CARRIER}.",
            operations=operations,
            knowledge=knowledge,
            operator_confirmed=True,
        )

        assert STEP_CHECK_AUTHORISATION not in state.snapshot()["tool_calls"]
        assert state.snapshot()["steps_executed"] == "3 of 3"

    def test_a_step_record_cannot_be_repointed_after_the_fact(
        self, operations: dict[str, Any], knowledge: Bm25Index
    ) -> None:
        # What frozen=True buys, stated exactly: a recorded step cannot be made to name a
        # different observation. It does NOT deep-freeze the observation dict, and the docs say so
        # rather than claiming an immutability the code does not provide.
        state = run_agent(
            f"Where is load {IN_TRANSIT_LOAD}?",
            operations=operations,
            knowledge=knowledge,
        )

        with pytest.raises(dataclasses.FrozenInstanceError):
            state.steps[0].name = "something_else"  # type: ignore[misc]
        with pytest.raises(dataclasses.FrozenInstanceError):
            state.steps[0].observation = {}  # type: ignore[misc]


class TestFixtureImmutability:
    def test_a_booking_never_reaches_the_committed_file(
        self, knowledge: Bm25Index
    ) -> None:
        # Homework #5's decision 9, re-pinned here because this workflow is a second caller of the
        # same write tool. A run that persisted would make every committed example irreproducible.
        before = hashlib.sha256(DEFAULT_LOADS.read_bytes()).hexdigest()
        operations = load_operations_data(DEFAULT_LOADS)

        state = run_agent(
            f"Book load {OPEN_LOAD} for carrier {ACTIVE_CARRIER}.",
            operations=operations,
            knowledge=knowledge,
            operator_confirmed=True,
        )

        assert state.observation_of(STEP_BOOK_LOAD)["ok"] is True  # type: ignore[index]
        assert hashlib.sha256(DEFAULT_LOADS.read_bytes()).hexdigest() == before

    def test_a_committed_load_cannot_be_committed_again(
        self, operations: dict[str, Any], knowledge: Bm25Index
    ) -> None:
        # Idempotency across two authorised runs sharing one world. (That one --confirm produces
        # at most one commit is guaranteed structurally instead: the booking plan holds exactly
        # one write step, pinned by test_the_booking_plan_verifies_then_authorises_then_writes.)
        question = f"Book load {OPEN_LOAD} for carrier {ACTIVE_CARRIER}."
        first = run_agent(
            question,
            operations=operations,
            knowledge=knowledge,
            operator_confirmed=True,
        )
        second = run_agent(
            question,
            operations=operations,
            knowledge=knowledge,
            operator_confirmed=True,
        )

        assert first.observation_of(STEP_BOOK_LOAD)["ok"] is True  # type: ignore[index]
        assert second.halted_at == STEP_CHECK_AUTHORISATION
        assert (
            second.observation_of(STEP_CHECK_AUTHORISATION)["error"] == "load_not_open"
        )  # type: ignore[index]


# --------------------------------------------------------------------------------------------
# Presentation
# --------------------------------------------------------------------------------------------


class TestPresentation:
    def test_the_trace_carries_every_key_the_assignment_mandates(
        self, operations: dict[str, Any], knowledge: Bm25Index
    ) -> None:
        state = run_agent(
            f"Book load {OPEN_LOAD} for carrier {ACTIVE_CARRIER}.",
            operations=operations,
            knowledge=knowledge,
            operator_confirmed=True,
        )
        text = format_state(state)

        for key in ("Question: ", "Route: ", "Tool called: ", "Observation: "):
            assert key in text
        assert "State after step: " in text
        assert "Final answer: " in text

    def test_a_gate_step_is_not_rendered_as_a_tool_call(
        self, operations: dict[str, Any], knowledge: Bm25Index
    ) -> None:
        state = run_agent(
            "Where is my load?", operations=operations, knowledge=knowledge
        )
        text = format_state(state)

        assert "Tool called: (none" in text

    def test_the_record_is_json_serialisable(
        self, operations: dict[str, Any], knowledge: Bm25Index
    ) -> None:
        state = run_agent(
            f"Book load {OPEN_LOAD} for carrier {ACTIVE_CARRIER}.",
            operations=operations,
            knowledge=knowledge,
            operator_confirmed=True,
        )
        record = json.loads(json.dumps(result_record(state)))

        assert record["route"] == ROUTE_BOOKING
        assert [step["index"] for step in record["steps"]] == [1, 2, 3]
        assert record["final_state"]["final_answer"] == state.final_answer

    def test_the_source_line_names_each_source_once(
        self, operations: dict[str, Any], knowledge: Bm25Index
    ) -> None:
        state = run_agent(
            f"Book load {OPEN_LOAD} for carrier {ACTIVE_CARRIER}.",
            operations=operations,
            knowledge=knowledge,
            operator_confirmed=True,
        )

        assert source_of(state) == "freight-exchange operations API (mock)"

    def test_a_route_that_consulted_nothing_says_so(
        self, operations: dict[str, Any], knowledge: Bm25Index
    ) -> None:
        state = run_agent(
            "Tell me something interesting.", operations=operations, knowledge=knowledge
        )

        assert source_of(state).startswith("(none")

    def test_a_relayed_tool_message_is_not_left_mid_sentence(
        self, operations: dict[str, Any], knowledge: Bm25Index
    ) -> None:
        state = run_agent(
            f"Book load {OPEN_LOAD} for carrier {ACTIVE_CARRIER}.",
            operations=operations,
            knowledge=knowledge,
        )

        assert str(state.final_answer).startswith("Load ")


# --------------------------------------------------------------------------------------------
# Artifact guards
# --------------------------------------------------------------------------------------------


class TestGuardOutputs:
    def test_it_protects_the_homework_5_artifacts_too(self) -> None:
        # external_tool.py writes those two, so it cannot list itself. This script must.
        names = {path.name for path in PROTECTED_OUTPUTS}
        assert {"tool_examples.md", "tool_results.json"} <= names
        assert {"chunks.jsonl", "loads.json", "test_queries.json"} <= names

    @pytest.mark.parametrize(
        "target", [path for path in PROTECTED_OUTPUTS], ids=lambda p: p.name
    )
    def test_it_refuses_to_overwrite_a_committed_deliverable(
        self, target: Path
    ) -> None:
        with pytest.raises(RetrievalError, match="committed deliverable"):
            guard_outputs({"output": target})

    def test_it_refuses_to_overwrite_an_input_of_this_run(self, tmp_path: Path) -> None:
        queries = tmp_path / "queries.json"

        with pytest.raises(RetrievalError, match="an input of this run"):
            guard_outputs({"output": queries}, reads=(queries,))

    def test_it_refuses_two_flags_pointing_at_one_file(self, tmp_path: Path) -> None:
        same = tmp_path / "collision.md"

        with pytest.raises(RetrievalError, match="same file"):
            guard_outputs({"output": same, "results": same})

    def test_it_refuses_a_destination_that_collides_with_a_siblings_temporary_file(
        self, tmp_path: Path
    ) -> None:
        # --output examples.md writes examples.md.tmp first and promotes it. Guarding only the
        # destinations lets that candidate write destroy a --results pointed at the same name, and
        # both writes still report success.
        target = tmp_path / "examples.md"

        with pytest.raises(RetrievalError, match="same file"):
            guard_outputs({"output": target, "results": tmp_path / "examples.md.tmp"})

    def test_it_refuses_a_temporary_file_that_lands_on_an_input(
        self, tmp_path: Path
    ) -> None:
        # The hand-authored commentary file is read first and would be consumed by the candidate
        # write, before any promotion — the guard's whole reason for taking `reads` at all.
        queries = tmp_path / "test_queries.json.tmp"

        with pytest.raises(RetrievalError, match="an input of this run"):
            guard_outputs({"results": tmp_path / "test_queries.json"}, reads=(queries,))

    def test_the_operations_file_is_a_protected_input_too(self, tmp_path: Path) -> None:
        # A custom --loads fixture is an input of the run exactly as --queries is; writing over it
        # loses the very data the run read.
        loads = tmp_path / "ops.json"

        with pytest.raises(RetrievalError, match="an input of this run"):
            guard_outputs({"results": loads}, reads=(tmp_path / "q.json", loads))

    def test_the_atomic_writer_and_the_guard_derive_one_candidate_name(
        self, tmp_path: Path
    ) -> None:
        # If these two ever disagreed, the guard would be checking a path nothing writes.
        target = tmp_path / "artifact.md"
        agent_flow._write_atomically(target, "content")

        assert agent_flow._candidate(target) == tmp_path / "artifact.md.tmp"
        assert target.read_text(encoding="utf-8") == "content"
        assert not agent_flow._candidate(target).exists(), (
            "the candidate must be promoted"
        )

    def test_distinct_fresh_paths_are_allowed(self, tmp_path: Path) -> None:
        guard_outputs(
            {"output": tmp_path / "a.md", "results": tmp_path / "b.json"},
            reads=(tmp_path / "c.json",),
        )


class TestCommentaryLoading:
    def test_a_missing_file_names_the_remedial_command(self, tmp_path: Path) -> None:
        with pytest.raises(RetrievalError, match="git checkout --"):
            load_commentary(tmp_path / "absent.json")

    def test_malformed_json_is_a_diagnostic_error(self, tmp_path: Path) -> None:
        path = tmp_path / "queries.json"
        path.write_text("{not json", encoding="utf-8")

        with pytest.raises(RetrievalError, match="not valid JSON"):
            load_commentary(path)

    def test_a_wrongly_typed_scenarios_key_is_refused(self, tmp_path: Path) -> None:
        path = tmp_path / "queries.json"
        path.write_text(json.dumps({"hw6_scenarios": ["e1"]}), encoding="utf-8")

        with pytest.raises(RetrievalError, match="must be an object"):
            load_commentary(path)

    def test_an_empty_key_degrades_to_missing_rather_than_raising(
        self, tmp_path: Path
    ) -> None:
        # An absent or empty commentary is the normal first-pass state, not a corrupt file. It is
        # caught by the missing-commentary refusal, which names each gap; raising here would stop
        # the run before it wrote the mechanical results the author needs to write them FROM.
        path = tmp_path / "queries.json"
        path.write_text(json.dumps({"hw6_scenarios": []}), encoding="utf-8")

        scenarios, conclusion = load_commentary(path)

        assert scenarios == {} and conclusion == ""
        assert len(_missing_commentary(scenarios, conclusion)) == len(EXAMPLES) + 1

    def test_every_gap_is_named_rather_than_rendered(self) -> None:
        missing = _missing_commentary({"e1": {"comment": "written"}}, "")

        assert "hw6_conclusion" in missing
        assert "hw6_scenarios.e1.comment" not in missing
        assert len(missing) == len(EXAMPLES)

    def test_a_whitespace_only_comment_counts_as_missing(self) -> None:
        commentary = {example.id: {"comment": "   "} for example in EXAMPLES}

        assert len(_missing_commentary(commentary, "done")) == len(EXAMPLES)


# --------------------------------------------------------------------------------------------
# The committed examples
# --------------------------------------------------------------------------------------------


class TestExamples:
    def test_there_are_between_three_and_five(self) -> None:
        assert 3 <= len(EXAMPLES) <= 5

    def test_the_ids_are_unique(self) -> None:
        assert len({example.id for example in EXAMPLES}) == len(EXAMPLES)

    def test_they_cover_every_route(self) -> None:
        assert {route(example.question).route for example in EXAMPLES} == set(ROUTES)

    def test_they_exercise_at_least_two_tools(self, knowledge: Bm25Index) -> None:
        operations = load_operations_data(DEFAULT_LOADS)
        used = {
            name
            for example in EXAMPLES
            for name in run_agent(
                example.question,
                operations=operations,
                knowledge=knowledge,
                operator_confirmed=example.operator_confirmed,
            ).tool_calls
        }

        assert len(used) >= 2

    def test_no_example_reads_a_load_an_earlier_example_booked(self) -> None:
        # The examples share one in-memory world by design, so ordering is load-bearing: an example
        # placed after the booking pair would observe a load that is booked rather than posted.
        booked: set[str] = set()
        for example in EXAMPLES:
            decision = route(example.question)
            if decision.load_id is not None:
                assert decision.load_id not in booked, (
                    f"{example.id} reads {decision.load_id}, which an earlier example committed"
                )
            if decision.route == ROUTE_BOOKING and example.operator_confirmed:
                booked.add(str(decision.load_id))
        assert booked, "no example demonstrates an authorised write"

    def test_the_booking_pair_is_refused_then_authorised_on_the_same_load(self) -> None:
        bookings = [
            (example, route(example.question))
            for example in EXAMPLES
            if route(example.question).route == ROUTE_BOOKING
        ]

        assert len(bookings) == 2
        assert bookings[0][1].load_id == bookings[1][1].load_id
        assert bookings[0][0].operator_confirmed is False
        assert bookings[1][0].operator_confirmed is True


class TestExamplesArtifact:
    def test_it_writes_both_artifacts_when_the_commentary_is_complete(
        self, corpus: Settings, commentary_file: Path, tmp_path: Path
    ) -> None:
        output = tmp_path / "examples.md"
        results = tmp_path / "results.json"

        code = agent_flow.run_examples(
            corpus,
            queries_path=commentary_file,
            output_path=output,
            results_path=results,
            loads_path=DEFAULT_LOADS,
            k=3,
        )

        assert code == 0
        assert output.is_file() and results.is_file()

    def test_the_rendered_markdown_carries_the_mandated_block_keys(
        self, corpus: Settings, commentary_file: Path, tmp_path: Path
    ) -> None:
        output = tmp_path / "examples.md"
        results = tmp_path / "results.json"
        agent_flow.run_examples(
            corpus,
            queries_path=commentary_file,
            output_path=output,
            results_path=results,
            loads_path=DEFAULT_LOADS,
            k=3,
        )
        text = output.read_text(encoding="utf-8")
        payload = json.loads(results.read_text(encoding="utf-8"))
        executed = sum(len(example["steps"]) for example in payload["examples"])

        for key in ("Question: ", "Route: ", "Final answer: ", "Comment: "):
            assert text.count(f"\n{key}") == len(EXAMPLES), key
        # Per EXECUTED step, not per planned step: e3 halts at 2 of 3, and a trace that rendered a
        # `Tool called:` line for a step that never ran would be reporting fiction.
        for key in ("Tool called: ", "Observation: ", "State after step: "):
            assert text.count(f"\n{key}") == executed, key
        assert executed > len(EXAMPLES), "at least one example must be multi-step"
        assert "## Conclusion" in text

    def test_an_incomplete_commentary_is_reported_and_never_rendered(
        self, corpus: Settings, tmp_path: Path
    ) -> None:
        queries = tmp_path / "queries.json"
        queries.write_text(json.dumps({"hw6_scenarios": {}}), encoding="utf-8")
        output = tmp_path / "examples.md"
        results = tmp_path / "results.json"

        code = agent_flow.run_examples(
            corpus,
            queries_path=queries,
            output_path=output,
            results_path=results,
            loads_path=DEFAULT_LOADS,
            k=3,
        )

        assert code == 1
        assert not output.exists(), "a placeholder artifact is worse than none"
        assert results.is_file(), "the mechanical half is still written, to author from"

    def test_the_examples_run_against_one_shared_world(
        self, corpus: Settings, commentary_file: Path, tmp_path: Path
    ) -> None:
        results = tmp_path / "results.json"
        agent_flow.run_examples(
            corpus,
            queries_path=commentary_file,
            output_path=tmp_path / "examples.md",
            results_path=results,
            loads_path=DEFAULT_LOADS,
            k=3,
        )
        payload = json.loads(results.read_text(encoding="utf-8"))
        bookings = [
            example
            for example in payload["examples"]
            if example["route"] == ROUTE_BOOKING
        ]

        assert [example["halted_at"] for example in bookings] == [
            STEP_CHECK_AUTHORISATION,
            None,
        ], "the refused run must precede, and survive into, the authorised one"

    def test_it_refuses_to_write_over_a_committed_deliverable(
        self, corpus: Settings, commentary_file: Path, tmp_path: Path
    ) -> None:
        with pytest.raises(RetrievalError, match="committed deliverable"):
            agent_flow.run_examples(
                corpus,
                queries_path=commentary_file,
                output_path=PROTECTED_OUTPUTS[0],
                results_path=tmp_path / "results.json",
                loads_path=DEFAULT_LOADS,
                k=3,
            )


# --------------------------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------------------------


class TestCli:
    def test_describe_needs_neither_a_key_nor_any_data(
        self, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)

        assert main(["--describe"]) == 0
        assert "Route: booking" in capsys.readouterr().out

    @pytest.mark.parametrize(
        "argv",
        [
            [],
            ["--question", "x", "--examples"],
            ["--describe", "--examples"],
            ["--question", "x", "--describe"],
        ],
        ids=["no-mode", "question+examples", "describe+examples", "question+describe"],
    )
    def test_exactly_one_mode_is_required(self, argv: list[str]) -> None:
        with pytest.raises(SystemExit) as exit_info:
            main(argv)

        assert exit_info.value.code == 2

    @pytest.mark.parametrize(
        "argv",
        [
            ["--question", "x", "--k", "0"],
            ["--examples", "--confirm"],
            ["--examples", "--json"],
            ["--describe", "--confirm"],
        ],
        ids=["k-zero", "examples+confirm", "examples+json", "describe+confirm"],
    )
    def test_a_flag_combination_that_would_be_ignored_is_a_usage_error(
        self, argv: list[str]
    ) -> None:
        with pytest.raises(SystemExit) as exit_info:
            main(argv)

        assert exit_info.value.code == 2

    def test_the_cli_asks_settings_not_to_require_a_key(
        self, monkeypatch: pytest.MonkeyPatch, corpus: Settings
    ) -> None:
        # The keyless run is this homework's central claim, and the only thing that delivers it is
        # one keyword argument at one call site. Every other keyless test monkeypatches from_env
        # and would stay green if that argument were dropped, so this one asserts the argument.
        seen: dict[str, Any] = {}

        def spy(cls: Any, **kwargs: Any) -> Settings:
            seen.update(kwargs)
            return corpus

        monkeypatch.setattr(agent_flow.Settings, "from_env", classmethod(spy))

        main(["--question", "Where is my load?"])

        assert seen.get("require_key") is False

    def test_settings_really_do_not_demand_a_key_when_asked_not_to(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # The other half: the real rag_lib.Settings.from_env, with no key in the environment and
        # the .env loader neutralised, must refuse by default and succeed under require_key=False.
        monkeypatch.setattr(rag_lib, "load_dotenv", lambda path=None: None)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)

        with pytest.raises(RetrievalError, match="OPENAI_API_KEY is not set"):
            Settings.from_env()

        assert Settings.from_env(require_key=False).openai_api_key == ""

    def test_a_question_runs_end_to_end_with_no_api_key(
        self,
        capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
        corpus: Settings,
    ) -> None:
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.setattr(
            agent_flow.Settings, "from_env", classmethod(lambda cls, **_: corpus)
        )

        code = main(["--question", f"Where is load {IN_TRANSIT_LOAD}?"])

        assert code == 0
        assert "Route: load_status" in capsys.readouterr().out

    def test_json_mode_emits_the_record(
        self,
        capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
        corpus: Settings,
    ) -> None:
        monkeypatch.setattr(
            agent_flow.Settings, "from_env", classmethod(lambda cls, **_: corpus)
        )

        code = main(["--question", "Where is my load?", "--json"])
        record = json.loads(capsys.readouterr().out)

        assert code == 0
        assert record["route"] == ROUTE_CLARIFICATION
        assert record["clarification_reason"] == REASON_MISSING_LOAD_ID

    def test_a_missing_operations_file_exits_one_with_a_remedial_command(
        self,
        capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
        corpus: Settings,
        tmp_path: Path,
    ) -> None:
        monkeypatch.setattr(
            agent_flow.Settings, "from_env", classmethod(lambda cls, **_: corpus)
        )

        code = main(
            ["--question", "Where is my load?", "--loads", str(tmp_path / "gone.json")]
        )

        assert code == 1
        assert "git checkout --" in capsys.readouterr().err
