#!/usr/bin/env python3
"""Deterministic agent workflow (Homework #6): goal -> route -> plan -> step -> observation -> answer.

  python scripts/agent_flow.py --question "Where is load FX-2026-000042 right now?"
  python scripts/agent_flow.py --question "Book load FX-2026-000211 for carrier CAR-00817." --confirm
  python scripts/agent_flow.py --describe
  python scripts/agent_flow.py --examples

Nothing here calls a language model. § 2 of the assignment asks for deterministic rule-based
routing, and this layer takes that literally: the router, the tools and the answer composition are
all rules over the question text and the recorded observations. The whole flow therefore runs with
no OPENAI_API_KEY and no network, which is what makes outputs/agent_flow_examples.md reproducible
byte for byte and lets the test suite exercise the real flow rather than a fake of it.

Homework #5 handed routing to the model and listed "no deterministic pre-router" among the things
it deliberately did not build. This homework's spec asks for exactly that router, so it claims that
deferral — the same carve-out by which Homework #4 claimed Homework #3's answer-generation
deferral. See docs/homework6/agent-flow-spec.md.

A route commits to a PLAN before the first action, and the plan's later steps read the earlier
steps' observations out of the state. The booking route is where that matters: `book_load` is
reachable only because `get_load_status` already recorded an open load and the human operator
authorised the write. State is therefore load-bearing, not decorative.

Two-pass by design, like run_test_queries.py, retrieval_improved.py, rag_answer.py and
external_tool.py: the first pass writes the mechanical results, the per-example `comment` and the
top-level `hw6_conclusion` are then authored by hand into data/eval/test_queries.json from real
output, and the second pass renders them. Missing ones are reported, never rendered as placeholders.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from external_tool import (
    CARRIER_ID_PATTERN,
    DEFAULT_LOADS,
    LOAD_ID_PATTERN,
    OPEN_STATUSES,
)
from external_tool import PROTECTED_OUTPUTS as HOMEWORK_1_TO_4_OUTPUTS
from external_tool import book_load as ops_book_load
from external_tool import get_load_status as ops_get_load_status
from external_tool import load_operations_data
from rag_lib import (
    REPO_ROOT,
    Bm25Index,
    Chunk,
    RetrievalError,
    Settings,
    infer_document_type,
    load_chunks,
)

DEFAULT_QUERIES = REPO_ROOT / "data" / "eval" / "test_queries.json"
DEFAULT_EXAMPLES_OUTPUT = REPO_ROOT / "outputs" / "agent_flow_examples.md"
DEFAULT_RESULTS = REPO_ROOT / "outputs" / "agent_flow_results.json"
DESIGN_DOC = "docs/homework6/agent-flow-spec.md"

# How many knowledge-base chunks one search step retrieves. Fixed at the same value the committed
# Homework #2-#4 evaluations use, so a reader comparing this route's evidence against those runs is
# comparing like with like.
DEFAULT_K = 3

# Excerpt width for the chunk this workflow quotes back. Wide enough to carry a claim, narrow
# enough that a rendered example stays readable.
EXCERPT_WIDTH = 320

# What the knowledge-base tool reports as its source. Spelled the same way the operations tool
# spells its own, so the `Source:` line of a trace names comparable things on both routes.
KNOWLEDGE_SOURCE = "data/processed/chunks.jsonl (knowledge base)"

# Committed Homework #1-#5 deliverables. The Homework #1-#4 half is imported rather than restated:
# a future addition to that tuple then protects this script too, and the two lists cannot drift.
# external_tool.py writes the last two, so it cannot list itself; this script must.
PROTECTED_OUTPUTS: tuple[Path, ...] = HOMEWORK_1_TO_4_OUTPUTS + (
    REPO_ROOT / "outputs" / "tool_examples.md",
    REPO_ROOT / "outputs" / "tool_results.json",
)

# --------------------------------------------------------------------------------------------
# The workflow contract: four routes, five steps, three tools. `--describe` prints all of it.
# --------------------------------------------------------------------------------------------

ROUTE_KNOWLEDGE_BASE = "knowledge_base"
ROUTE_LOAD_STATUS = "load_status"
ROUTE_BOOKING = "booking"
ROUTE_CLARIFICATION = "clarification"

STEP_SEARCH_KNOWLEDGE_BASE = "search_knowledge_base"
STEP_GET_LOAD_STATUS = "get_load_status"
STEP_CHECK_AUTHORISATION = "check_authorisation"
STEP_BOOK_LOAD = "book_load"
STEP_ASK_USER = "ask_user"

# A step is either a TOOL step (it consults a source outside the workflow) or a GATE step (it reads
# only the state the workflow has already accumulated). Keeping the two kinds apart is what lets
# `Tool called:` in the rendered trace mean something: a gate is a decision, not an integration.
KIND_TOOL = "tool"
KIND_GATE = "gate"

STEP_KINDS: dict[str, str] = {
    STEP_SEARCH_KNOWLEDGE_BASE: KIND_TOOL,
    STEP_GET_LOAD_STATUS: KIND_TOOL,
    STEP_BOOK_LOAD: KIND_TOOL,
    STEP_CHECK_AUTHORISATION: KIND_GATE,
    STEP_ASK_USER: KIND_GATE,
}

# The plan a route commits to before its first action. Fixed per route rather than assembled as the
# run proceeds: a plan that grows in response to its own observations is a planner, and § 1 asks
# for a simple *controlled* workflow. What the observations decide here is how far along a fixed
# plan the run gets — see `check_authorisation`.
PLANS: dict[str, tuple[str, ...]] = {
    ROUTE_KNOWLEDGE_BASE: (STEP_SEARCH_KNOWLEDGE_BASE,),
    ROUTE_LOAD_STATUS: (STEP_GET_LOAD_STATUS,),
    ROUTE_BOOKING: (STEP_GET_LOAD_STATUS, STEP_CHECK_AUTHORISATION, STEP_BOOK_LOAD),
    ROUTE_CLARIFICATION: (STEP_ASK_USER,),
}

ROUTES: tuple[str, ...] = tuple(PLANS)

ROUTE_PURPOSE: dict[str, str] = {
    ROUTE_KNOWLEDGE_BASE: (
        "Answer from the documented corpus — what a term means, how a mechanism works, why a "
        "decision was taken."
    ),
    ROUTE_LOAD_STATUS: (
        "Report one named load's live state from the operations API — status, carrier, ETA, "
        "position."
    ),
    ROUTE_BOOKING: (
        "Commit a named load to a named carrier, but only after the live state proves the load is "
        "open and the human operator has authorised the irreversible write."
    ),
    ROUTE_CLARIFICATION: (
        "Ask for what is missing instead of guessing — an absent identifier, a malformed one, or a "
        "goal no route can serve."
    ),
}

# Why each clarification happened. Recorded on the state so a trace never has to be re-read to find
# out what the workflow thought was wrong with the question.
REASON_MISSING_LOAD_ID = "missing_load_id"
REASON_MISSING_CARRIER_ID = "missing_carrier_id"
REASON_MALFORMED_LOAD_ID = "malformed_load_id"
REASON_MALFORMED_CARRIER_ID = "malformed_carrier_id"
REASON_AMBIGUOUS_LOAD_ID = "ambiguous_load_id"
REASON_AMBIGUOUS_CARRIER_ID = "ambiguous_carrier_id"
REASON_NO_ROUTE_MATCHED = "no_route_matched"

# --------------------------------------------------------------------------------------------
# Router vocabulary and identifier detection
# --------------------------------------------------------------------------------------------


def _unanchored(pattern: str) -> str:
    """Strip the ^...$ anchors so a contract pattern can also be searched for inside a sentence."""
    return pattern.removeprefix("^").removesuffix("$")


# The identifier shapes come from external_tool's patterns rather than being restated. Those are
# anchored, because they validate a whole argument; a router has to find an identifier in the
# middle of a sentence. The surrounding guards stop a partial match: without them
# "FX-2026-0000421" would yield the real-looking "FX-2026-000042" and the workflow would answer
# about a load the user never named.
# The `(?:...)` wrapper is not cosmetic: the pattern is borrowed from another module, and a
# top-level alternation added there would otherwise bind the guards to one branch only.
LOAD_ID_IN_TEXT = re.compile(
    rf"(?<![0-9A-Za-z-])(?:{_unanchored(LOAD_ID_PATTERN)})(?![0-9A-Za-z-])"
)
CARRIER_ID_IN_TEXT = re.compile(
    rf"(?<![0-9A-Za-z-])(?:{_unanchored(CARRIER_ID_PATTERN)})(?![0-9A-Za-z-])"
)

# A near miss: "FX-26-42", "fx-2026-000042", "CAR-817". Anything reaching these has already failed
# the strict patterns above, so a match means the user tried to name an identifier and mistyped it.
# docs/homework5/tool-integration-spec.md named this the one thing a deterministic pre-router could
# do that model routing could not — tell the user their identifier is malformed, instead of
# silently answering some other question. This is the workflow claiming that gain.
LOAD_ID_ATTEMPT = re.compile(
    r"(?<![0-9A-Za-z-])[Ff][Xx]-?[0-9]{1,8}-?[0-9]{0,8}(?![0-9A-Za-z])"
)
CARRIER_ID_ATTEMPT = re.compile(
    r"(?<![0-9A-Za-z-])[Cc][Aa][Rr]-?[0-9]{1,8}(?![0-9A-Za-z])"
)

# Matched as whole tokens, which is the point: the past participle "booked" is a different token
# from the imperative "book", so "what does it mean for a load to be booked" is a question about
# documented knowledge and never a booking request.
BOOKING_VERBS = frozenset({"book", "assign", "commit", "reserve"})

# How far into a question a booking verb may sit and still read as an imperative. Whole-token
# matching handles the past participle, but "book", "commit", "assign" and "reserve" are also bare
# infinitives AND ordinary corpus vocabulary, so their mere presence cannot mean a booking request:
# "How do I book a load on the exchange?" is documentation, and it is the first thing a reader
# asks. Position is the only signal that separates the two without a parser — an imperative puts
# its verb first. Measured at three words: five re-swallows that question, because its verb is the
# fourth word.
IMPERATIVE_WINDOW = 3

# The part of a question that actually asks for a booking: from the verb to the next sentence
# boundary. Built from BOOKING_VERBS so the two cannot drift.
BOOKING_CLAUSE = re.compile(
    rf"\b(?:{'|'.join(sorted(BOOKING_VERBS))})\b[^.?!;]*", re.IGNORECASE
)

# Words that ask about a load's live state. A question carrying one of these but naming no load is
# answerable in principle and unanswerable in practice, which is what the clarification route is
# for. Deliberately excludes bare adverbs like "now" and "currently": they appear in documentation
# questions just as often, and a router that fires on them stops being predictable.
LIVE_STATE_WORDS = frozenset(
    "where eta status position located location arriving arrive arrives arrival tracking "
    "delayed".split()
)

# Words that ask what something *means*. These beat LIVE_STATE_WORDS deliberately, so
# "what does the status matched mean" reaches the corpus rather than asking which load is meant.
# Deliberately excludes "what", "how" and "is": they open live-state questions just as readily
# ("what is the status of my load"), so including them would swallow the clarification route.
KNOWLEDGE_INTENT_WORDS = frozenset(
    "mean means meaning explain explains explanation define defines definition describe why "
    "difference differences concept concepts documentation".split()
)


def _tokens(text: str) -> frozenset[str]:
    """Lowercased alphanumeric tokens, keeping stopwords.

    Deliberately not rag_lib._tokenize: that one removes rag_lib.STOPWORDS, which contains "where",
    "what", "when" and "why" — the exact words this router decides on. Reusing it would delete the
    routing signal before the router ever saw it.
    """
    return frozenset(re.findall(r"[a-z0-9]+", text.lower()))


def _find(pattern: re.Pattern[str], text: str) -> str | None:
    match = pattern.search(text)
    return match.group(0) if match is not None else None


# --------------------------------------------------------------------------------------------
# Routing — pure, rule-based, no model
# --------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class RouteDecision:
    """Which route the question takes, and which rule sent it there.

    `rule` is recorded because "the routing works" is a graded claim: a trace that names R3 can be
    audited against the rule list, and a trace that merely names a route cannot.
    """

    route: str
    rule: str
    load_id: str | None = None
    carrier_id: str | None = None
    reason: str | None = None


def _identifier_problem(question: str, *, load_id: str | None) -> str:
    """Name the identifier a booking request failed to supply, or supplied malformed.

    Called only when at least one operand is absent, so an unset `load_id` settles it and the
    carrier branch needs no argument of its own — it re-reads the clause. The load id is checked
    first because it is the one a booking cannot proceed without: naming the carrier problem while
    the load is also absent would send the user back for one of two answers.
    """
    if load_id is None:
        return (
            REASON_MALFORMED_LOAD_ID
            if LOAD_ID_ATTEMPT.search(question)
            else REASON_MISSING_LOAD_ID
        )
    return (
        REASON_MALFORMED_CARRIER_ID
        if CARRIER_ID_ATTEMPT.search(question)
        else REASON_MISSING_CARRIER_ID
    )


def _booking_clause(question: str) -> str:
    """The span of the question that asks for a booking — operands are read from here, not from
    the whole sentence.

    `_find` otherwise takes the first identifier anywhere in the text, whichever clause it belongs
    to. "Where is load FX-2026-000633 right now? Also, book a truck from carrier CAR-00817."
    then commits FX-2026-000633 — an identifier the user only asked ABOUT — and the gate authorises
    it, because the gate verifies whatever operand the router already chose.

    The clause starts AT the verb and stops at the next sentence boundary. Both bounds are
    deliberately conservative on the write route: an identifier typed before the request is being
    asked about rather than booked, and an operand the workflow is unsure of must produce a
    question, never a commit. The cost is a false "which load?" on an unusual phrasing, which is
    the safe direction to be wrong in.
    """
    match = BOOKING_CLAUSE.search(question)
    return match.group(0) if match is not None else question


def _opens_with_booking_verb(question: str) -> bool:
    """True when a booking verb sits within the first IMPERATIVE_WINDOW words."""
    ordered = re.findall(r"[a-z0-9]+", question.lower())[:IMPERATIVE_WINDOW]
    return bool(set(ordered) & BOOKING_VERBS)


def _ambiguous_identifier(question: str) -> str | None:
    """Refuse to guess which of several identifiers an irreversible write was meant for.

    `_find` takes the FIRST match in the sentence, regardless of which clause the booking verb
    governs. "Where is FX-2026-000042 and should I book FX-2026-000318 for CAR-00817?" would
    otherwise commit FX-2026-000042 — the load the user only asked about. Nothing downstream
    catches that: `check_authorisation` verifies the load the router already chose, so it confirms
    the wrong load is open and authorises it. The confirmation gate is not a defence against a
    router that picked the wrong operand.

    Scoped to the booking route on purpose. On a read route, answering about the first load named
    and saying which one is harmless; the justification here is irreversibility, not tidiness.

    Counted over the ATTEMPT patterns, which are supersets of the strict ones. "Book FX-2026-000211
    or FX-26-42 for CAR-00817." names one valid load and one mistyped one; counting only valid
    matches finds a single candidate and books it, silently choosing the operand on the user's
    behalf. A mistyped candidate is still a candidate, and this is the write route.

    DISTINCT matches, not the raw count: repeating one identifier is emphasis, not ambiguity.
    """
    # Upper-cased before counting: the ATTEMPT patterns are case-tolerant, so "fx-2026-000211"
    # and "FX-2026-000211" are one candidate typed twice, not two candidates.
    if len({match.upper() for match in LOAD_ID_ATTEMPT.findall(question)}) > 1:
        return REASON_AMBIGUOUS_LOAD_ID
    if len({match.upper() for match in CARRIER_ID_ATTEMPT.findall(question)}) > 1:
        return REASON_AMBIGUOUS_CARRIER_ID
    return None


def route(question: str) -> RouteDecision:
    """Classify a user goal into one of the four routes. First matching rule wins.

    The order is the design. A booking request is settled first, because it is the only route that
    writes. Identifier evidence then beats vocabulary evidence, because a user who typed a load id
    named a specific load and means it. An explicit "what does X mean" beats live-state vocabulary,
    because the question is about the word and not about a shipment. Corpus vocabulary is the last
    positive signal, because it is the weakest — rag_lib's keyword sets contain words as common as
    "load", so testing it earlier would swallow whole routes.
    """
    load_id = _find(LOAD_ID_IN_TEXT, question)
    carrier_id = _find(CARRIER_ID_IN_TEXT, question)
    words = _tokens(question)
    # A booking verb alone is not a booking request. It becomes one when the question also carries
    # an operand — an identifier, even a mistyped one — or when it is phrased as an imperative.
    wants_to_book = bool(words & BOOKING_VERBS) and (
        load_id is not None
        or carrier_id is not None
        or LOAD_ID_ATTEMPT.search(question) is not None
        or CARRIER_ID_ATTEMPT.search(question) is not None
        or _opens_with_booking_verb(question)
    )

    if wants_to_book:
        # R1 — more than one candidate identifier. Never guess before an irreversible write.
        # Scanned over the WHOLE question, deliberately: "Where is FX-A and should I book FX-B for
        # CAR-C?" is a question about one load and a musing about another, and refusing it is
        # safer than committing either.
        ambiguous = _ambiguous_identifier(question)
        if ambiguous is not None:
            return RouteDecision(ROUTE_CLARIFICATION, "R1", reason=ambiguous)
        clause = _booking_clause(question)
        booked_load = _find(LOAD_ID_IN_TEXT, clause)
        booked_carrier = _find(CARRIER_ID_IN_TEXT, clause)
        # R2 — an actionable booking request.
        if booked_load is not None and booked_carrier is not None:
            return RouteDecision(ROUTE_BOOKING, "R2", booked_load, booked_carrier)
        # R3 — a booking request the workflow cannot act on.
        return RouteDecision(
            ROUTE_CLARIFICATION,
            "R3",
            booked_load,
            booked_carrier,
            _identifier_problem(clause, load_id=booked_load),
        )
    # R4 — a load is named, so answer about that load.
    if load_id is not None:
        return RouteDecision(ROUTE_LOAD_STATUS, "R4", load_id)
    # R5 — an identifier was attempted and mistyped. Say so rather than answer something else.
    # The carrier branch is guarded on `carrier_id is None` because no earlier rule consumes a
    # carrier id on its own: without the guard, the well-formed CAR-00817 reaches the near-miss
    # test and the workflow tells the user a real identifier is malformed.
    if LOAD_ID_ATTEMPT.search(question):
        return RouteDecision(ROUTE_CLARIFICATION, "R5", reason=REASON_MALFORMED_LOAD_ID)
    if carrier_id is None and CARRIER_ID_ATTEMPT.search(question):
        return RouteDecision(
            ROUTE_CLARIFICATION, "R5", reason=REASON_MALFORMED_CARRIER_ID
        )
    # R6 — the question asks what something means, whatever else it mentions.
    if words & KNOWLEDGE_INTENT_WORDS:
        return RouteDecision(ROUTE_KNOWLEDGE_BASE, "R6")
    # R7 — live state wanted, no load named.
    if words & LIVE_STATE_WORDS:
        return RouteDecision(ROUTE_CLARIFICATION, "R7", reason=REASON_MISSING_LOAD_ID)
    # R8 — the corpus's own vocabulary, reusing Homework #3's rule-based inference.
    if infer_document_type(question) is not None:
        return RouteDecision(ROUTE_KNOWLEDGE_BASE, "R8")
    # R9 — nothing matched. Never guess a route.
    return RouteDecision(ROUTE_CLARIFICATION, "R9", reason=REASON_NO_ROUTE_MATCHED)


# --------------------------------------------------------------------------------------------
# Tools — three mock tools, each over a committed fixture, each offline
# --------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class AgentTool:
    name: str
    kind: str
    purpose: str
    source: str
    when_to_call: str
    when_not_to_call: str
    returns: str


def _display_path(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        # Not a masked failure: relative_to raises for any path outside the repo, which a --output
        # or --loads pointing elsewhere legitimately is. Such a path is shown in full.
        return str(path)


def _excerpt(text: str, width: int = EXCERPT_WIDTH) -> str:
    collapsed = " ".join(text.split())
    return (
        collapsed if len(collapsed) <= width else collapsed[: width - 1].rstrip() + "…"
    )


def _quotable(chunk: Chunk) -> str:
    """Chunk text minus the "Title > Section. " breadcrumb Homework #1 prepends to every chunk.

    The breadcrumb is genuine chunk content and BM25 ranks on it, so it is not stripped from the
    corpus. It is stripped here because `title` and `section` travel as their own fields on every
    match: quoting it back would print the attribution twice, once outside the quotation and once
    inside it. Only an exact prefix is removed, so a chunk without one is returned untouched.
    """
    breadcrumb = f"{chunk.metadata.get('title')} > {chunk.metadata.get('section')}. "
    return chunk.text.removeprefix(breadcrumb)


def search_knowledge_base(
    question: str, *, knowledge: Bm25Index, k: int = DEFAULT_K
) -> dict[str, Any]:
    """Tool: search_knowledge_base. Type: read. Lexical BM25 over the committed chunk corpus.

    Homework #3's `infer_document_type` picks the metadata filter, so the narrowing is rule-based
    like everything else on this route. The semantic half of Homework #3's hybrid is deliberately
    absent: embedding a query needs the API, and this workflow's whole design point is that it
    needs nothing. What that costs is stated in docs/homework6/agent-flow-spec.md § Known limits.
    """
    document_type = infer_document_type(question)
    allowed = (
        knowledge.matching_ids("document_type", document_type)
        if document_type is not None
        else None
    )
    ranked = knowledge.top(question, k=k, allowed_ids=allowed)
    if not ranked:
        return {
            "ok": False,
            "error": "no_match",
            "message": (
                "no chunk in the knowledge base scored above zero for this question"
                + (
                    f" under the inferred {document_type!r} filter."
                    if document_type is not None
                    else "."
                )
            ),
            "document_type_filter": document_type,
            "source": KNOWLEDGE_SOURCE,
        }
    matches: list[dict[str, Any]] = []
    for rank, (chunk_id, score) in enumerate(ranked, start=1):
        chunk = knowledge.chunk(chunk_id)
        matches.append(
            {
                "rank": rank,
                "chunk_id": chunk_id,
                "bm25_score": round(score, 4),
                "title": chunk.metadata.get("title"),
                "section": chunk.metadata.get("section"),
                "document_type": chunk.metadata.get("document_type"),
                "excerpt": _excerpt(_quotable(chunk)),
            }
        )
    return {
        "ok": True,
        "document_type_filter": document_type,
        "match_count": len(matches),
        "top_chunk_id": matches[0]["chunk_id"],
        "matches": matches,
        "source": KNOWLEDGE_SOURCE,
    }


def get_load_status(load_id: str, *, operations: dict[str, Any]) -> dict[str, Any]:
    """Tool: get_load_status. Type: read. One load's live state from the operations API mock.

    Homework #5 owns the tool itself; this workflow calls it and records what it returned. Sharing
    the implementation is what keeps a single contract for the operations data — a second copy is
    the one place the two homeworks could silently disagree about what `booked` means.
    """
    return ops_get_load_status(load_id, data=operations).payload()


def book_load(
    load_id: str, carrier_id: str, *, operations: dict[str, Any]
) -> dict[str, Any]:
    """Tool: book_load. Type: write. Commits a load to a carrier — irreversible, exactly once.

    The commit lands on the in-process copy of the operations data and is never written back to
    data/external/loads.json (Homework #5's decision 9). The fixture is a fixed input, so every
    `--examples` run starts from the same state and the committed examples stay reproducible.
    """
    return ops_book_load(load_id, carrier_id, data=operations).payload()


TOOLS: dict[str, AgentTool] = {
    STEP_SEARCH_KNOWLEDGE_BASE: AgentTool(
        name=STEP_SEARCH_KNOWLEDGE_BASE,
        kind="read",
        purpose="Top-k chunks of platform documentation for a question, by BM25.",
        source="data/processed/chunks.jsonl (the Homework #1 knowledge base)",
        when_to_call=(
            "The question asks what something means, how a mechanism works, or why a decision was "
            "taken."
        ),
        when_not_to_call=(
            "The question names a specific load. The corpus defines what `in_transit` means and "
            "cannot know which load is in it."
        ),
        returns=(
            "{ok: true, document_type_filter, match_count, top_chunk_id, "
            "matches: [{rank, chunk_id, bm25_score, title, section, document_type, excerpt}], "
            "source}  —  on a miss: {ok: false, error: 'no_match', message, "
            "document_type_filter, source}"
        ),
    ),
    STEP_GET_LOAD_STATUS: AgentTool(
        name=STEP_GET_LOAD_STATUS,
        kind="read",
        purpose="Current live state of one load: status, carrier, ETA, last known position.",
        source="data/external/loads.json (freight-exchange operations API mock)",
        when_to_call=(
            "The question names a load identifier and asks where it is, what state it is in, who "
            "is carrying it, or when it arrives. Also the booking route's first step, because a "
            "load must be proven open before it can be committed."
        ),
        when_not_to_call=(
            "The question is about the lifecycle itself rather than about one shipment in it."
        ),
        returns=(
            "{ok: true, load_id, status, origin, destination, equipment, weight_kg, "
            "pickup_window, carrier | null, booking_reference | null, eta | null, "
            "last_position | null, last_position_age_s | null, position_is_stale | null, "
            "updated_at, source, snapshot_at}  —  on refusal: {ok: false, error, message, load_id}"
        ),
    ),
    STEP_BOOK_LOAD: AgentTool(
        name=STEP_BOOK_LOAD,
        kind="write",
        purpose="Commit a load to a carrier — irreversible, operator-confirmed, exactly once.",
        source="data/external/loads.json (in-process copy; never written back to disk)",
        when_to_call=(
            "Only as the booking route's third step, after `check_authorisation` has passed."
        ),
        when_not_to_call=(
            "To find out whether a load *can* be booked. That is `get_load_status`, and it is the "
            "step this one depends on."
        ),
        returns=(
            "{ok: true, load_id, status: 'booked', carrier {carrier_id, name}, "
            "booking_reference, booked_at, irreversible: true, source}  —  on refusal: "
            "{ok: false, error (already_booked | load_not_open | unknown_load | unknown_carrier | "
            "carrier_not_permitted), message, load_id, ...context}"
        ),
    ),
}


# --------------------------------------------------------------------------------------------
# State
# --------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class StepRecord:
    """One executed step: what it was given, and what it observed."""

    index: int
    name: str
    kind: str
    arguments: dict[str, Any]
    observation: dict[str, Any]


@dataclass
class AgentState:
    """Everything the workflow remembers while it runs.

    Mutable, unlike this repo's value objects, because it is an accumulator — the same exception
    run_test_queries.py's report objects take. The step records inside it are frozen, so a step's
    observation cannot be edited after the fact by whatever runs next.
    """

    user_goal: str
    selected_route: str | None = None
    routing_rule: str | None = None
    plan: tuple[str, ...] = ()
    steps: list[StepRecord] = field(default_factory=list)
    clarification_reason: str | None = None
    halted_at: str | None = None
    final_answer: str | None = None

    @property
    def tool_calls(self) -> list[str]:
        """Names of the TOOL steps that ran, in order. Gate steps consult no source and are not
        tool calls, so counting them here would overstate what the workflow actually integrated."""
        return [step.name for step in self.steps if step.kind == KIND_TOOL]

    @property
    def observations(self) -> list[dict[str, Any]]:
        return [step.observation for step in self.steps]

    def observation_of(self, step_name: str) -> dict[str, Any] | None:
        """The observation an earlier step recorded — how a later step reads the state.

        Returns the FIRST match: a plan names each step once, so a second occurrence would mean the
        plan and this lookup disagree, and picking the last one silently would hide that.
        """
        for step in self.steps:
            if step.name == step_name:
                return step.observation
        return None

    def snapshot(self, *, after_step: int | None = None) -> dict[str, Any]:
        """The state as of after `after_step` steps — the `State after step:` line of a trace.

        Observations are summarised rather than embedded: the full payload is already on the
        `Observation:` line directly above, and repeating it would push the one line a reader
        actually scans past several screens of JSON.
        """
        steps = self.steps if after_step is None else self.steps[:after_step]
        final = self.final_answer if after_step is None else None
        # A halt is recorded on the step that caused it, and that step is always the last one
        # executed. An earlier snapshot must therefore show `halted_at: null`, or the trace would
        # show the state knowing at step 1 something it only learned at step 2.
        halted = self.halted_at if len(steps) == len(self.steps) else None
        return {
            "user_goal": self.user_goal,
            "selected_route": self.selected_route,
            "routing_rule": self.routing_rule,
            "plan": list(self.plan),
            "steps_executed": f"{len(steps)} of {len(self.plan)}",
            "tool_calls": [step.name for step in steps if step.kind == KIND_TOOL],
            "observations": [
                {
                    "step": step.name,
                    "ok": step.observation.get("ok"),
                    "error": step.observation.get("error"),
                }
                for step in steps
            ],
            "clarification_reason": self.clarification_reason,
            "halted_at": halted,
            "final_answer": final,
        }


# --------------------------------------------------------------------------------------------
# Gate steps — they read the state, never a source
# --------------------------------------------------------------------------------------------


def check_authorisation(
    state: AgentState, *, load_id: str, carrier_id: str, operator_confirmed: bool
) -> dict[str, Any]:
    """Gate: may the workflow commit this load?

    Two conditions, and both come from somewhere the model of this workflow cannot fabricate. The
    first is the previous step's recorded observation — this is the single place where "the
    workflow remembers what it already did" stops being a claim. The second is the human's
    --confirm, exactly as in Homework #5: a booking authorised by the thing being authorised is
    the failure the confirmation rule exists to stop.

    Every outcome names BOTH operands. The router selects them from the whole question, and it
    cannot tell which clause of a multi-clause question a given identifier belongs to (see
    docs/homework6/agent-flow-spec.md § Known limits). Printing the pair the run would actually
    commit is what lets the operator catch a borrowed operand before typing --confirm, which is
    the only place that mistake is still catchable.
    """
    operands = {"load_id": load_id, "carrier_id": carrier_id}
    observed = state.observation_of(STEP_GET_LOAD_STATUS)
    if observed is None or not observed.get("ok"):
        return {
            "ok": False,
            "error": "load_not_verified",
            "message": (
                f"the live state of load {load_id} could not be read, so the booking has nothing "
                "to authorise. Nothing was booked."
            ),
            **operands,
        }
    status = observed.get("status")
    load_is_open = status in OPEN_STATUSES
    if not load_is_open:
        # A closed load may already be committed elsewhere, and the observation this gate is
        # reading holds that detail. Repeating it turns "not open" into something the user can act
        # on without a second lookup.
        elsewhere = observed.get("booking_reference")
        context = (
            ""
            if not elsewhere
            else f" It is already committed to {observed.get('carrier', {}).get('carrier_id')} "
            f"under booking {elsewhere}."
        )
        return {
            "ok": False,
            "error": "load_not_open",
            "message": (
                f"load {load_id} is {status} and is not open for booking, so it cannot be "
                f"committed to {carrier_id}.{context} Nothing was booked."
            ),
            **operands,
            "status": status,
            "load_is_open": False,
            "operator_confirmed": operator_confirmed,
        }
    if not operator_confirmed:
        return {
            "ok": False,
            "error": "confirmation_required",
            "message": (
                f"load {load_id} is {status} and open, and the request would commit it to "
                f"{carrier_id}. Booking is irreversible and no human operator authorised it. "
                "Check that both identifiers are the ones you meant, then re-run the same request "
                "with --confirm; that decision is the operator's."
            ),
            **operands,
            "status": status,
            "load_is_open": True,
            "operator_confirmed": False,
        }
    return {
        "ok": True,
        **operands,
        "status": status,
        "load_is_open": True,
        "operator_confirmed": True,
        "message": (
            f"load {load_id} is {status} and open, and the operator authorised committing it to "
            f"{carrier_id}."
        ),
    }


CLARIFICATION_QUESTIONS: dict[str, str] = {
    REASON_MISSING_LOAD_ID: (
        "I need the load identifier before I can look anything up. It has the form "
        "FX-YYYY-NNNNNN, for example FX-2026-000042. Which load do you mean?"
    ),
    REASON_MISSING_CARRIER_ID: (
        "I have the load but not the carrier. A carrier identifier has the form CAR-NNNNN, for "
        "example CAR-00817. Which carrier should take it?"
    ),
    REASON_MALFORMED_LOAD_ID: (
        "That is not a load identifier I can use. A load identifier has the form FX-YYYY-NNNNNN — "
        "four digits for the year and six for the sequence, upper case, for example "
        "FX-2026-000042. Could you give me the full identifier?"
    ),
    REASON_MALFORMED_CARRIER_ID: (
        "That is not a carrier identifier I can use. A carrier identifier has the form CAR-NNNNN — "
        "five digits, upper case, for example CAR-00817. Could you give me the full identifier?"
    ),
    REASON_AMBIGUOUS_LOAD_ID: (
        "That request names more than one load, and booking is irreversible, so I will not guess "
        "which one you meant. Name the single load you want booked, in the form FX-YYYY-NNNNNN."
    ),
    REASON_AMBIGUOUS_CARRIER_ID: (
        "That request names more than one carrier, and a load is committed to exactly one. Name "
        "the single carrier that should take it, in the form CAR-NNNNN."
    ),
    REASON_NO_ROUTE_MATCHED: (
        "I could not tell what you need. I can answer questions about how the freight exchange "
        "works from the platform documentation, report the live state of a load you name, or book "
        "a load for a carrier. Which of those would you like?"
    ),
}


def ask_user(decision: RouteDecision) -> dict[str, Any]:
    """Gate: turn the routing failure into the question that would unblock it.

    Nothing is read from stdin. The clarifying question IS the answer, which keeps `run_agent` a
    pure function of its inputs and keeps the committed examples reproducible.
    """
    reason = decision.reason or REASON_NO_ROUTE_MATCHED
    question = CLARIFICATION_QUESTIONS.get(reason)
    if question is None:
        # Same reasoning as the unknown-plan-step branch in _execute: a REASON_* constant with no
        # question is a drift bug, and a bare KeyError escapes main()'s boundary catch as a raw
        # traceback instead of the module's remedial-message format.
        raise RetrievalError(
            f"clarification reason {reason!r} has no question to ask. CLARIFICATION_QUESTIONS and "
            "the REASON_* constants have drifted apart."
        )
    return {
        "ok": False,
        "error": reason,
        "message": question,
        "detected": {
            "load_id": decision.load_id,
            "carrier_id": decision.carrier_id,
            "routing_rule": decision.rule,
        },
    }


# --------------------------------------------------------------------------------------------
# Answer composition — templated from the recorded observations, never generated
# --------------------------------------------------------------------------------------------


def _required_observation(state: AgentState, step_name: str) -> dict[str, Any]:
    """The observation a composer needs, or a stop.

    Absent means the route's plan and its answer composer disagree about which steps run. That is a
    programming error, and letting it through renders the literal "None" into a graded answer —
    the silent wrong result this repo refuses to produce.
    """
    observation = state.observation_of(step_name)
    if observation is None:
        raise RetrievalError(
            f"the {state.selected_route!r} answer needs the {step_name!r} observation and the plan "
            "recorded none. PLANS and the answer composers disagree about this route."
        )
    return observation


def _sentence(message: Any) -> str:
    """Capitalise a relayed tool message.

    The tool messages are Homework #5's, and they were written to be embedded inside a model's
    prose ("load FX-… does not exist"). This workflow relays one as a whole answer, so without
    this the graded `Final answer:` line begins mid-sentence.
    """
    text = str(message).strip()
    return text[:1].upper() + text[1:]


def _answer_knowledge_base(state: AgentState) -> str:
    observation = _required_observation(state, STEP_SEARCH_KNOWLEDGE_BASE)
    if not observation.get("ok"):
        return (
            f"I could not answer that from the knowledge base: {_sentence(observation.get('message'))} "
            "The corpus covers freight-exchange concepts, CQRS and event sourcing, a "
            "monolith-to-microservices migration, and scaling and zero-downtime operations."
        )
    top = observation["matches"][0]
    return (
        f"According to {top['title']} § {top['section']}: {top['excerpt']} "
        f"[{top['chunk_id']}]"
    )


def _describe_position(observation: dict[str, Any]) -> str:
    position = observation.get("last_position")
    if not position:
        return "No position has been reported for it."
    age = observation.get("last_position_age_s")
    freshness = (
        ""
        if age is None
        else f", {age} s old ({'stale' if observation.get('position_is_stale') else 'fresh'})"
    )
    return f"Last known position: {position.get('place')}{freshness}."


def _answer_load_status(state: AgentState) -> str:
    observation = _required_observation(state, STEP_GET_LOAD_STATUS)
    if not observation.get("ok"):
        return f"{_sentence(observation.get('message'))} (operations API)"
    carrier = observation.get("carrier")
    carried_by = (
        "It has no carrier assigned yet."
        if not carrier
        else f"It is with {carrier['name']} ({carrier['carrier_id']})."
    )
    eta = observation.get("eta")
    due = "No ETA has been published." if not eta else f"ETA {eta}."
    return (
        f"Load {observation['load_id']} is {observation['status']}, running "
        f"{observation['origin']} → {observation['destination']}. {carried_by} {due} "
        f"{_describe_position(observation)} These are live operational facts, from the "
        "operations API rather than from the documentation."
    )


def _answer_booking(state: AgentState) -> str:
    status_observation = _required_observation(state, STEP_GET_LOAD_STATUS)
    if not status_observation.get("ok"):
        return f"{_sentence(status_observation.get('message'))} (operations API)"
    gate = _required_observation(state, STEP_CHECK_AUTHORISATION)
    if not gate.get("ok"):
        return _sentence(gate.get("message"))
    booked = _required_observation(state, STEP_BOOK_LOAD)
    if not booked.get("ok"):
        return _sentence(booked.get("message"))
    carrier = booked["carrier"]
    return (
        f"Booked. Load {booked['load_id']} was {status_observation['status']} and open, the "
        f"operator authorised the commit, and it is now {booked['status']} to {carrier['name']} "
        f"({carrier['carrier_id']}) under booking reference {booked['booking_reference']}. "
        "Booking is irreversible and happens exactly once per load."
    )


def _answer_clarification(state: AgentState) -> str:
    observation = _required_observation(state, STEP_ASK_USER)
    return str(observation["message"])


ANSWER_COMPOSERS: dict[str, Callable[[AgentState], str]] = {
    ROUTE_KNOWLEDGE_BASE: _answer_knowledge_base,
    ROUTE_LOAD_STATUS: _answer_load_status,
    ROUTE_BOOKING: _answer_booking,
    ROUTE_CLARIFICATION: _answer_clarification,
}


# --------------------------------------------------------------------------------------------
# The flow
# --------------------------------------------------------------------------------------------


def run_agent(
    question: str,
    *,
    operations: dict[str, Any],
    knowledge: Bm25Index,
    k: int = DEFAULT_K,
    operator_confirmed: bool = False,
) -> AgentState:
    """goal -> route -> plan -> step -> observation -> state update -> next step -> final answer.

    No I/O: the operations data and the knowledge index arrive already built, and nothing here
    reads a file, a socket or stdin. The one side effect is the in-memory booking commit that
    Homework #5 defines, which is why `operations` is passed in rather than loaded here — a caller
    running several questions in sequence decides whether they share a world.

    A step never runs speculatively. `_should_halt` stops the plan the moment an observation says
    the next step cannot be justified, and the stop is recorded on the state rather than inferred
    later from a short step list.
    """
    if not question.strip():
        raise RetrievalError("question is empty")
    decision = route(question)
    state = AgentState(
        user_goal=question,
        selected_route=decision.route,
        routing_rule=decision.rule,
        plan=PLANS[decision.route],
        clarification_reason=decision.reason,
    )
    for index, step_name in enumerate(state.plan, start=1):
        arguments, observation = _execute(
            step_name,
            state=state,
            decision=decision,
            operations=operations,
            knowledge=knowledge,
            k=k,
            operator_confirmed=operator_confirmed,
        )
        state.steps.append(
            StepRecord(
                index=index,
                name=step_name,
                kind=STEP_KINDS[step_name],
                arguments=arguments,
                observation=observation,
            )
        )
        if not observation.get("ok") and index < len(state.plan):
            # A failed observation is not an error — it is the plan learning that its remaining
            # steps have lost their justification. `book_load` after a refused gate would be the
            # confused-deputy commit the gate exists to prevent.
            state.halted_at = step_name
            break
    state.final_answer = ANSWER_COMPOSERS[decision.route](state)
    return state


def _operand(value: str | None, name: str, step_name: str) -> str:
    """An identifier a step cannot run without.

    `str(None)` would hand the literal "None" to a tool, which then answers "load None does not
    exist" — a programming defect (PLANS and the router disagreeing about what a route binds)
    laundered into a plausible business refusal. The sibling unknown-step branch below raises for
    the same reason.
    """
    if value is None:
        raise RetrievalError(
            f"plan step {step_name!r} needs {name} and the router bound none. PLANS and route() "
            "disagree about this route; this is an internal inconsistency, not a bad question."
        )
    return value


def _execute(
    step_name: str,
    *,
    state: AgentState,
    decision: RouteDecision,
    operations: dict[str, Any],
    knowledge: Bm25Index,
    k: int,
    operator_confirmed: bool,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Run one step. Returns (arguments, observation).

    The dispatch is explicit rather than a registry lookup: five steps take four different argument
    shapes, and a uniform signature would exist only to make this function shorter.
    """
    if step_name == STEP_SEARCH_KNOWLEDGE_BASE:
        arguments = {"question": state.user_goal, "k": k}
        return arguments, search_knowledge_base(
            state.user_goal, knowledge=knowledge, k=k
        )
    if step_name == STEP_GET_LOAD_STATUS:
        load_id = _operand(decision.load_id, "load_id", step_name)
        return {"load_id": load_id}, get_load_status(load_id, operations=operations)
    if step_name == STEP_CHECK_AUTHORISATION:
        load_id = _operand(decision.load_id, "load_id", step_name)
        carrier_id = _operand(decision.carrier_id, "carrier_id", step_name)
        arguments = {
            "load_id": load_id,
            "carrier_id": carrier_id,
            "operator_confirmed": operator_confirmed,
        }
        return arguments, check_authorisation(
            state,
            load_id=load_id,
            carrier_id=carrier_id,
            operator_confirmed=operator_confirmed,
        )
    if step_name == STEP_BOOK_LOAD:
        load_id = _operand(decision.load_id, "load_id", step_name)
        carrier_id = _operand(decision.carrier_id, "carrier_id", step_name)
        arguments = {"load_id": load_id, "carrier_id": carrier_id}
        return arguments, book_load(load_id, carrier_id, operations=operations)
    if step_name == STEP_ASK_USER:
        return {"reason": decision.reason}, ask_user(decision)
    # Unreachable while PLANS and STEP_KINDS agree; raised rather than ignored because a plan
    # naming a step nobody implemented must stop the run, not silently shorten it.
    raise RetrievalError(f"no implementation for plan step {step_name!r}")


# The metadata keys the knowledge answer quotes by name. Validated once when the index is built,
# for the same reason external_tool validates REQUIRED_LOAD_KEYS on load: without the check a chunk
# missing them is reported as a successful match and the graded answer reads "According to None §
# None", which is a corrupt corpus wearing the shape of a good result.
REQUIRED_CHUNK_METADATA = ("title", "section", "document_type")


def build_knowledge_index(settings: Settings) -> Bm25Index:
    """The BM25 index over the committed corpus — the knowledge-base tool's whole data layer."""
    chunks = load_chunks(settings.chunks_path)
    for chunk in chunks:
        absent = [key for key in REQUIRED_CHUNK_METADATA if not chunk.metadata.get(key)]
        if absent:
            raise RetrievalError(
                f"{_display_path(settings.chunks_path)}: chunk {chunk.chunk_id} is missing "
                f"metadata {', '.join(absent)}. The knowledge-base answer cites those fields by "
                "name. Rebuild the knowledge base:\n"
                "  python scripts/prepare_knowledge_base.py"
            )
    return Bm25Index(chunks)


# --------------------------------------------------------------------------------------------
# Presentation
# --------------------------------------------------------------------------------------------


def _compact(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def format_step(state: AgentState, step: StepRecord) -> list[str]:
    """The three per-step lines of the § 3 block format, for one step."""
    called = (
        f"Tool called: {step.name}"
        if step.kind == KIND_TOOL
        else f"Tool called: (none — `{step.name}` is a gate step, it reads state, not a source)"
    )
    return [
        f"Step {step.index}/{len(state.plan)} — {step.name} ({step.kind})",
        f"Input: {_compact(step.arguments)}",
        called,
        f"Observation: {_compact(step.observation)}",
        f"State after step: {_compact(state.snapshot(after_step=step.index))}",
    ]


def format_state(state: AgentState) -> str:
    lines = [
        f"Question: {state.user_goal}",
        f"Route: {state.selected_route} (rule {state.routing_rule})",
        f"Plan: {' → '.join(state.plan)}",
    ]
    for step in state.steps:
        lines.append("")
        lines.extend(format_step(state, step))
    if state.halted_at is not None:
        lines.extend(
            [
                "",
                f"Halted at: {state.halted_at} — the remaining plan steps lost their "
                "justification.",
            ]
        )
    lines.extend(
        ["", f"Final answer: {state.final_answer}", "", f"Source: {source_of(state)}"]
    )
    return "\n".join(lines)


def source_of(state: AgentState) -> str:
    """Where the answer's facts came from — the counterpart of Homework #4's `Source:` line.

    A REFUSED tool observation carries no `source` key (Homework #5's refusals do not set one), but
    the tool was still consulted. Falling back to the catalogue's source keeps the line from
    claiming nothing was queried directly underneath an observation showing that something was.
    """
    seen: list[str] = []
    for step in state.steps:
        if step.kind != KIND_TOOL:
            continue
        reported = step.observation.get("source")
        entry = reported if isinstance(reported, str) else TOOLS[step.name].source
        if entry not in seen:
            seen.append(entry)
    return ", ".join(seen) or "(none — no source was consulted)"


def result_record(state: AgentState) -> dict[str, Any]:
    return {
        "question": state.user_goal,
        "route": state.selected_route,
        "routing_rule": state.routing_rule,
        "plan": list(state.plan),
        "steps": [
            {
                "index": step.index,
                "step": step.name,
                "kind": step.kind,
                "arguments": step.arguments,
                "observation": step.observation,
                "state_after": state.snapshot(after_step=step.index),
            }
            for step in state.steps
        ],
        "tool_calls": state.tool_calls,
        "clarification_reason": state.clarification_reason,
        "halted_at": state.halted_at,
        "final_state": state.snapshot(),
        "final_answer": state.final_answer,
        "source": source_of(state),
    }


def render_contract() -> str:
    """The § 2 lists — routes, steps, tools and state — printed from the code that implements them.

    The README carries the same three lists. Printing them from the module constants is what keeps
    the documented workflow and the executed workflow from drifting apart.
    """
    blocks: list[str] = ["## Routes and their plans", ""]
    for name in ROUTES:
        plan = PLANS[name]
        blocks.append(f"Route: {name}")
        blocks.append(f"Steps: {' → '.join(plan)}  ({len(plan)} step(s))")
        blocks.append(f"Purpose: {ROUTE_PURPOSE[name]}")
        blocks.append("")
    blocks.extend(["## Tools", ""])
    for name in sorted(TOOLS):
        tool = TOOLS[name]
        blocks.append(f"Tool: {tool.name}")
        blocks.append(f"Type: {tool.kind}")
        blocks.append(f"Purpose: {tool.purpose}")
        blocks.append(f"Source: {tool.source}")
        blocks.append(f"When to call: {tool.when_to_call}")
        blocks.append(f"When NOT to call: {tool.when_not_to_call}")
        blocks.append(f"Returns: {tool.returns}")
        blocks.append("")
    blocks.extend(["## State", ""])
    for name, description in STATE_FIELDS.items():
        blocks.append(f"{name}: {description}")
    return "\n".join(blocks)


STATE_FIELDS: dict[str, str] = {
    "user_goal": "the question verbatim, never rewritten",
    "selected_route": "one of " + ", ".join(ROUTES),
    "routing_rule": "which router rule fired (R1-R9), so a trace can be audited",
    "plan": "the ordered step list the route committed to before acting",
    "steps": "one frozen record per executed step: index, name, kind, arguments, observation",
    "tool_calls": "the names of the TOOL steps that ran, in order (gate steps excluded)",
    "observations": "each step's result, read by later steps through observation_of()",
    "clarification_reason": "why the workflow asked instead of acted, or null",
    "halted_at": "the step whose observation ended the plan early, or null",
    "final_answer": "composed from the observations once the plan finishes or halts",
}


# --------------------------------------------------------------------------------------------
# Examples and the graded artifact
# --------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Example:
    id: str
    title: str
    question: str
    rubric_role: str
    operator_confirmed: bool = False


EXAMPLES: tuple[Example, ...] = (
    Example(
        id="e1",
        title="documented knowledge — no live data involved",
        question=(
            "Explain why the migration used the strangler pattern instead of a rewrite."
        ),
        rubric_role="route A · the knowledge-base workflow, one tool, one step",
    ),
    Example(
        id="e2",
        title="live state of a specific load",
        question="Where is load FX-2026-000042 right now, and what is its ETA?",
        rubric_role="route B · the operations workflow — dynamic state no corpus can hold",
    ),
    Example(
        id="e3",
        title="an irreversible write, refused at the gate",
        question="Book load FX-2026-000211 for carrier CAR-00817.",
        rubric_role=(
            "route C · the 3-step plan halting at step 2 — the operator never authorised it"
        ),
    ),
    Example(
        id="e4",
        title="the same write, authorised",
        question="Book load FX-2026-000211 for carrier CAR-00817.",
        rubric_role=(
            "route C again · all 3 steps run, and step 3 is reachable only because step 1's "
            "observation said the load was open"
        ),
        operator_confirmed=True,
    ),
    Example(
        id="e5",
        title="a mistyped identifier",
        question="Give me the status of load FX-26-42.",
        rubric_role=(
            "route D · the clarification workflow — the rule-based router names the typo that "
            "Homework #5's model routing could only fall through"
        ),
    ),
)


def load_commentary(path: Path) -> tuple[dict[str, Any], str]:
    """Read the hand-authored Homework #6 prose out of the shared evaluation file."""
    if not path.is_file():
        raise RetrievalError(
            f"{_display_path(path)} not found. It carries the hand-authored Homework #6 "
            "commentary. Restore it:\n"
            f"  git checkout -- {_display_path(path)}"
        )
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RetrievalError(
            f"{_display_path(path)} is not valid JSON ({exc})."
        ) from exc
    scenarios = payload.get("hw6_scenarios") or {}
    if not isinstance(scenarios, dict):
        raise RetrievalError(
            f"{_display_path(path)}: 'hw6_scenarios' must be an object keyed by example id."
        )
    conclusion = str(payload.get("hw6_conclusion") or "").strip()
    return scenarios, conclusion


def _missing_commentary(commentary: dict[str, Any], conclusion: str) -> list[str]:
    missing: list[str] = []
    for example in EXAMPLES:
        entry = commentary.get(example.id) or {}
        if not str(entry.get("comment") or "").strip():
            missing.append(f"hw6_scenarios.{example.id}.comment")
    if not conclusion:
        missing.append("hw6_conclusion")
    return missing


def _candidate(target: Path) -> Path:
    """The temporary path `_write_atomically` writes before promoting `target`.

    Derived in one place because `guard_outputs` has to refuse a collision with it too: the
    candidate write is exactly as destructive as the promotion, and the naming is predictable, so
    `--output x` alongside `--results x.tmp` collides on the candidate alone — both writes then
    report success and one file is gone.
    """
    return target.with_suffix(target.suffix + ".tmp")


def _same_file(left: Path, right: Path) -> bool:
    """True when two paths name the same file, whatever they are spelled like.

    The inode comparison is what catches a case-insensitive filesystem and a symlink; the string
    compare is the fallback for a path that does not exist yet. external_tool._same_file carries
    the full reasoning, and this repo duplicates the guard per writer rather than sharing it.
    """
    if left == right:
        return True
    try:
        return left.samefile(right)
    except OSError:
        return left.resolve() == right.resolve()


def guard_outputs(paths: dict[str, Path], *, reads: Sequence[Path] = ()) -> None:
    """Refuse to write over a committed deliverable, over an input of this run, or over a sibling.

    Each destination is checked twice — once as itself and once as the candidate path the atomic
    write lands on first. Checking only the destinations passes `--output x --results x.tmp` and
    then loses a file.
    """
    protected: list[tuple[str, Path]] = [
        ("a committed deliverable", path) for path in PROTECTED_OUTPUTS
    ]
    protected.extend(("an input of this run", path) for path in reads)
    # Every write this run performs, under the flag a reader can act on.
    writes: list[tuple[str, Path]] = []
    for flag, path in paths.items():
        writes.append((flag, path))
        writes.append((f"{flag} (its temporary file)", _candidate(path)))
    for flag, path in writes:
        for label, target in protected:
            if _same_file(path, target):
                raise RetrievalError(
                    f"--{flag} points at {_display_path(target)}, which is {label}. Writing it "
                    "would destroy graded work. Choose another path."
                )
    for position, (flag, path) in enumerate(writes):
        for other_flag, other in writes[position + 1 :]:
            if _same_file(path, other):
                raise RetrievalError(
                    f"--{flag} and --{other_flag} point at the same file — one would overwrite "
                    "the other. Choose distinct paths."
                )


def render_examples_markdown(
    records: list[dict[str, Any]],
    *,
    commentary: dict[str, Any],
    conclusion: str,
    k: int,
    corpus_size: int,
) -> str:
    lines = [
        "# Agent workflow examples — Homework #6",
        "",
        "Generated by `python scripts/agent_flow.py --examples`.",
        "No model, no API key, no network: the router, the tools and the answer composition are "
        "all deterministic rules, so every block below reproduces byte for byte.",
        f"Knowledge-base top-k: {k}. Tools: "
        + ", ".join(f"`{name}`" for name in sorted(TOOLS))
        + ".",
        f"Sources: `data/processed/chunks.jsonl` ({corpus_size} chunks) and "
        "`data/external/loads.json` (freight-exchange operations API mock).",
        "",
        "Each block is the format required by § 3 of the assignment. `Tool called:`, "
        "`Observation:` and `State after step:` repeat once per executed step, because that is "
        'what "state after step" means once a plan has more than one.',
        "",
        "All five examples run against ONE shared in-memory copy of the operations data, in the "
        "order shown. e3 and e4 are therefore a sequence and not two independent simulations: e4 "
        "commits the load e3 was refused.",
        "",
        "---",
        "",
    ]
    for record in records:
        entry = commentary.get(record["example_id"]) or {}
        lines.append(f"## {record['example_id']} · {record['title']}")
        lines.append("")
        lines.append(f"*Rubric role: {record['rubric_role']}*")
        lines.append("")
        lines.append(f"Question: {record['question']}")
        lines.append(f"Route: {record['route']} (rule {record['routing_rule']})")
        lines.append(f"Plan: {' → '.join(record['plan'])}")
        lines.append(f"Operator confirmed: {record['operator_confirmed']}")
        lines.append("")
        for step in record["steps"]:
            called = (
                step["step"]
                if step["kind"] == KIND_TOOL
                else f"(none — `{step['step']}` is a gate step, it reads state, not a source)"
            )
            lines.append(
                f"**Step {step['index']} — `{step['step']}` ({step['kind']})**"
            )
            lines.append("")
            lines.append(f"Tool called: {called}")
            lines.append(f"Input: {_compact(step['arguments'])}")
            lines.append(f"Observation: {_compact(step['observation'])}")
            lines.append(f"State after step: {_compact(step['state_after'])}")
            lines.append("")
        if record["halted_at"] is not None:
            lines.append(
                f"Halted at: {record['halted_at']} — the remaining plan steps lost their "
                "justification."
            )
            lines.append("")
        lines.append(f"Final answer: {record['final_answer']}")
        lines.append("")
        lines.append(f"Source: {record['source']}")
        lines.append("")
        lines.append(f"Comment: {str(entry.get('comment') or '').strip()}")
        lines.append("")
        lines.append("---")
        lines.append("")
    lines.append("## Conclusion")
    lines.append("")
    lines.append(conclusion)
    lines.append("")
    lines.append(
        f"Design decisions and known limits: [`{DESIGN_DOC}`](../{DESIGN_DOC})."
    )
    lines.append("")
    return "\n".join(lines)


def _promote(candidate: Path, target: Path) -> None:
    # An atomic swap, so a crash mid-write cannot leave a half-written deliverable behind: the
    # target is either the old file or the new one, never a truncated one.
    os.replace(candidate, target)


def _write_atomically(target: Path, content: str) -> None:
    candidate = _candidate(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    candidate.write_text(content, encoding="utf-8")
    _promote(candidate, target)


def run_examples(
    settings: Settings,
    *,
    queries_path: Path,
    output_path: Path,
    results_path: Path,
    loads_path: Path,
    k: int,
) -> int:
    guard_outputs(
        {"output": output_path, "results": results_path},
        reads=(queries_path, loads_path),
    )
    commentary, conclusion = load_commentary(queries_path)
    # One operations dict for the whole run, so e3's refusal genuinely leaves the state that e4
    # then changes. Homework #5's run_examples shares its data for the same reason.
    operations = load_operations_data(loads_path)
    knowledge = build_knowledge_index(settings)
    # Measured, not asserted: the rendered artifact names the corpus this run actually indexed, so
    # a chunks.jsonl that grew cannot leave a stale count in a graded file.
    corpus_size = len(load_chunks(settings.chunks_path))
    records: list[dict[str, Any]] = []
    for example in EXAMPLES:
        state = run_agent(
            example.question,
            operations=operations,
            knowledge=knowledge,
            k=k,
            operator_confirmed=example.operator_confirmed,
        )
        record = result_record(state)
        record.update(
            {
                "example_id": example.id,
                "title": example.title,
                "rubric_role": example.rubric_role,
                "operator_confirmed": example.operator_confirmed,
            }
        )
        records.append(record)
        print(
            f"{example.id}  route={record['route']} ({record['routing_rule']})  "
            f"steps={len(record['steps'])}/{len(record['plan'])}  "
            f"tools={','.join(record['tool_calls']) or '-'}"
        )

    missing = _missing_commentary(commentary, conclusion)
    if missing:
        # Reported, never rendered as a placeholder: the hand-authored judgement is the part of
        # this artifact a script cannot produce, and a filled-in-looking file would hide that it
        # was never written.
        print(
            f"\nHand-authored commentary still missing from {_display_path(queries_path)}:",
            file=sys.stderr,
        )
        for entry in missing:
            print(f"  - {entry}", file=sys.stderr)
        print(
            "Write them from the real output above, then re-run --examples to render.",
            file=sys.stderr,
        )

    payload = {
        "k": k,
        "corpus_size": corpus_size,
        "routes": list(ROUTES),
        "plans": {name: list(steps) for name, steps in PLANS.items()},
        "tools": sorted(TOOLS),
        "knowledge_source": _display_path(settings.chunks_path),
        "operations_source": _display_path(loads_path),
        "examples": records,
    }
    _write_atomically(
        results_path, json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    )
    print(f"\nwrote {_display_path(results_path)}")

    if missing:
        print(
            f"{_display_path(output_path)} not rendered — commentary incomplete.",
            file=sys.stderr,
        )
        return 1
    _write_atomically(
        output_path,
        render_examples_markdown(
            records,
            commentary=commentary,
            conclusion=conclusion,
            k=k,
            corpus_size=corpus_size,
        ),
    )
    print(f"wrote {_display_path(output_path)}")
    return 0


def run_question(
    settings: Settings,
    question: str,
    *,
    k: int,
    loads_path: Path,
    operator_confirmed: bool,
    as_json: bool,
) -> int:
    state = run_agent(
        question,
        operations=load_operations_data(loads_path),
        knowledge=build_knowledge_index(settings),
        k=k,
        operator_confirmed=operator_confirmed,
    )
    if as_json:
        print(json.dumps(result_record(state), indent=2, ensure_ascii=False))
    else:
        print(format_state(state))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--question", "-q", type=str, default=None)
    parser.add_argument(
        "--examples", action="store_true", help="run the 5 graded examples"
    )
    parser.add_argument(
        "--describe",
        action="store_true",
        help="print the routes, tools and state contract",
    )
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="operator authorisation for the write step; the workflow can never set this itself",
    )
    parser.add_argument("--k", type=int, default=DEFAULT_K)
    parser.add_argument("--loads", type=Path, default=DEFAULT_LOADS)
    parser.add_argument("--queries", type=Path, default=DEFAULT_QUERIES)
    parser.add_argument("--output", type=Path, default=DEFAULT_EXAMPLES_OUTPUT)
    parser.add_argument("--results", type=Path, default=DEFAULT_RESULTS)
    parser.add_argument("--json", dest="as_json", action="store_true")
    args = parser.parse_args(argv)

    modes = [bool(args.question), args.examples, args.describe]
    if sum(modes) != 1:
        parser.error("provide exactly one of --question TEXT, --examples or --describe")
    if args.k < 1:
        parser.error("--k must be at least 1")
    # --confirm --examples reads as "authorise the example write" and does nothing: run_examples
    # takes authorisation from each Example. Silently ignoring it would be the worst outcome for a
    # flag whose whole purpose is that a human meant it.
    if args.examples and (args.confirm or args.as_json):
        parser.error(
            "--examples takes neither --confirm nor --json; the examples set their own"
        )
    if args.describe and (args.confirm or args.as_json):
        parser.error("--describe takes neither --confirm nor --json")

    # The contract is a set of module constants, so printing it needs neither a key nor any data.
    if args.describe:
        print(render_contract())
        return 0

    try:
        # require_key=False is the whole point of this homework: nothing downstream of here calls
        # a model, so demanding a key would refuse runs that cannot possibly need one.
        settings = Settings.from_env(require_key=False)
        if args.examples:
            return run_examples(
                settings,
                queries_path=args.queries,
                output_path=args.output,
                results_path=args.results,
                loads_path=args.loads,
                k=args.k,
            )
        return run_question(
            settings,
            args.question or "",
            k=args.k,
            loads_path=args.loads,
            operator_confirmed=args.confirm,
            as_json=args.as_json,
        )
    except RetrievalError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
