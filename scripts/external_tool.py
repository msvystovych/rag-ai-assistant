#!/usr/bin/env python3
"""External tool integration (Homework #5): question -> model picks a tool -> validated call -> answer.

  python scripts/external_tool.py --question "Where is load FX-2026-000042 right now?"
  python scripts/external_tool.py --question "Book load FX-2026-000211 for carrier CAR-00817" --confirm
  python scripts/external_tool.py --list-tools
  python scripts/external_tool.py --examples

The model, not a hand-written router, decides whether a question needs live operations data. Both
tool schemas are handed to it on every turn; when it emits no tool call the question falls through
to the Homework #4 grounded-answer pipeline unchanged, which is how "when NOT to call the tool" is
enforced rather than merely documented.

Every argument the tool layer receives was written by the model and is therefore untrusted. It is
validated before the data layer is touched: required fields present, identifiers matching their
declared pattern, no unknown properties, and — for the one write tool — an operator confirmation
that the model cannot supply for itself.

Failures split by who has to react. A tool-domain outcome (unknown load, malformed identifier,
refused booking) becomes a structured result the MODEL is told about, because raising there would
abort the conversation over a normal business answer. An environment failure (missing or malformed
operations file) raises RetrievalError and stops the run, because only the OPERATOR can repair it.

Two-pass by design, like run_test_queries.py, retrieval_improved.py and rag_answer.py: the first
pass writes the mechanical results, the per-scenario `why_better_than_retrieval` and `comment` plus
the top-level `hw5_conclusion` are then authored by hand into data/eval/test_queries.json from real
output, and the second pass renders them. Missing ones are reported, never rendered as placeholders.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from openai import OpenAIError

from rag_answer import DEFAULT_K, GroundedAnswer, answer_question
from rag_lib import (
    REPO_ROOT,
    Bm25Index,
    RetrievalError,
    Settings,
    load_chunks,
    open_collection,
)

DEFAULT_LOADS = REPO_ROOT / "data" / "external" / "loads.json"
DEFAULT_QUERIES = REPO_ROOT / "data" / "eval" / "test_queries.json"
DEFAULT_EXAMPLES_OUTPUT = REPO_ROOT / "outputs" / "tool_examples.md"
DEFAULT_RESULTS = REPO_ROOT / "outputs" / "tool_results.json"
DESIGN_DOC = "docs/homework5/tool-integration-spec.md"

# Fixed, not a flag, for the same reason Homework #4 fixed it: the committed examples are graded
# artifacts, and a sampled tool argument would make "re-run it yourself" a hope rather than an
# instruction. Greedy decoding is necessary for that but — unlike HW4 — not sufficient; see
# docs/homework5/tool-integration-spec.md § Known limits.
TEMPERATURE = 0.0

# The bound that keeps this an integration rather than an agent. Two rounds is the deepest any
# supported question needs (look a load up, then act on it); the third exists so a model that keeps
# re-calling still terminates, and exhausting it is reported rather than hidden.
MAX_TOOL_ROUNDS = 3

# Single-sourced: the same string is the JSON Schema `pattern` the model is shown AND the regex
# validation enforces. Two copies would be the one place the contract and its enforcement could
# silently disagree.
LOAD_ID_PATTERN = r"^FX-[0-9]{4}-[0-9]{6}$"
CARRIER_ID_PATTERN = r"^CAR-[0-9]{5}$"
LOAD_ID = re.compile(LOAD_ID_PATTERN)
CARRIER_ID = re.compile(CARRIER_ID_PATTERN)

# The load lifecycle from data/raw/freight-exchange-domain-primer.md § The Load Lifecycle. Booking
# is the first irreversible transition, so only the two states before it are open to a booking.
LOAD_STATES = ("posted", "matched", "booked", "in_transit", "delivered", "settled")
# The keys get_load_status indexes without .get — validated on load so a truncated fixture fails
# with a remedial command instead of a KeyError raised from inside the tool.
REQUIRED_LOAD_KEYS = (
    "load_id",
    "status",
    "origin",
    "destination",
    "equipment",
    "weight_kg",
    "pickup_window",
    "updated_at",
)
REQUIRED_CARRIER_KEYS = ("carrier_id", "name", "status")
OPEN_STATUSES = frozenset({"posted", "matched"})
CARRIER_STATES = ("active", "suspended")

# data/raw/scaling-and-zero-downtime-operations.md § Caching Strategy: latest-known position "must
# expose its own age so callers can distinguish a fresh position from a stale one". The tool
# therefore reports staleness as a fact rather than leaving the model to judge a raw age.
STALE_POSITION_S = 900

# Committed Homework #1-#4 deliverables. Same family as rag_answer.PROTECTED_OUTPUTS: an --output
# typo that lands on one of these destroys a graded artifact, so the run refuses before writing.
PROTECTED_OUTPUTS: tuple[Path, ...] = (
    REPO_ROOT / "data" / "eval" / "test_queries.json",
    REPO_ROOT / "data" / "processed" / "chunks.jsonl",
    REPO_ROOT / "data" / "external" / "loads.json",
    REPO_ROOT / "outputs" / "retrieval_results.json",
    REPO_ROOT / "outputs" / "retrieval_results_improved.json",
    REPO_ROOT / "outputs" / "retrieval_examples.md",
    REPO_ROOT / "outputs" / "retrieval_comparison.md",
    REPO_ROOT / "outputs" / "chunk_size_experiment.md",
    REPO_ROOT / "outputs" / "rag_answers_examples.md",
    REPO_ROOT / "outputs" / "rag_answers_results.json",
    REPO_ROOT / "outputs" / "prompt_improvements.md",
)

SYSTEM_PROMPT = (
    "You are a freight-exchange operations assistant.\n"
    "You have two sources of truth and they answer different kinds of question.\n"
    "1. The tools below read the LIVE operations API. Use one whenever the question is about a "
    "specific load identifier — its current status, position, ETA, assigned carrier — or asks to "
    "book a load.\n"
    "2. Everything else is answered from a knowledge base of platform documentation: what the "
    "load lifecycle is, what a status means, how matching, CQRS, scaling or the migration work. "
    "Do NOT call a tool for those. Emit no tool call and the question is routed to document "
    "retrieval automatically.\n"
    "Never invent a load identifier, a carrier identifier, a status or an ETA. If the user asks "
    "about a specific load but gives no identifier, say that you need one.\n"
    "You do not decide whether a call is permitted — the tool does. When the user asks to book a "
    "load, call book_load and relay whatever it returns, including a refusal. Never skip a call "
    "because you expect it to be refused.\n"
    "When a tool returns an error, report exactly what it says. Do not retry with a guessed "
    "identifier and do not attempt to work around a refused booking.\n"
    "Name the load identifier in your answer, and state that operational facts came from the "
    "operations API."
)


# --------------------------------------------------------------------------------------------
# Input / output contract. These dicts ARE the `tools=` payload sent to the model, so the contract
# the model is shown and the contract the design doc quotes cannot drift apart.
# --------------------------------------------------------------------------------------------

GET_LOAD_STATUS_SCHEMA: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "get_load_status",
        "description": (
            "Read the current live state of ONE load from the freight-exchange operations API: "
            "lifecycle status, assigned carrier, ETA, and last known vehicle position with its "
            "age. Call this when the user names a specific load identifier and asks where it is, "
            "what state it is in, who is carrying it, or when it will arrive. Do NOT call this "
            "for general questions about what the load lifecycle is, what a status means, or how "
            "the exchange works — those are answered from the knowledge base, not from live data."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "load_id": {
                    "type": "string",
                    "pattern": LOAD_ID_PATTERN,
                    "description": (
                        "Load identifier exactly as the user gave it, in the form FX-YYYY-NNNNNN "
                        "(for example FX-2026-000042). Never invent or reformat one."
                    ),
                }
            },
            "required": ["load_id"],
            "additionalProperties": False,
        },
    },
}

BOOK_LOAD_SCHEMA: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "book_load",
        "description": (
            "WRITE ACTION. Commit a load to a carrier in the operations API. Booking is the first "
            "irreversible commercial transition and may happen only once per load. Call this "
            "whenever the user asks to book a named load for a named carrier — always call it, "
            "and report what it returns. The tool itself checks whether the human operator "
            "authorised the booking and refuses when they have not; that decision is the tool's, "
            "never yours, so never skip the call because you expect a refusal. Do NOT call this "
            "to check whether a load can be booked — use get_load_status for that."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "load_id": {
                    "type": "string",
                    "pattern": LOAD_ID_PATTERN,
                    "description": "Load identifier in the form FX-YYYY-NNNNNN.",
                },
                "carrier_id": {
                    "type": "string",
                    "pattern": CARRIER_ID_PATTERN,
                    "description": "Carrier identifier in the form CAR-NNNNN, e.g. CAR-00817.",
                },
                "confirmed": {
                    "type": "boolean",
                    "description": (
                        "Whether the HUMAN operator authorised this irreversible booking. Set it "
                        "only if they said so. The tool verifies authorisation independently and "
                        "refuses a booking you confirmed for yourself."
                    ),
                },
            },
            "required": ["load_id", "carrier_id"],
            "additionalProperties": False,
        },
    },
}

TOOL_SCHEMAS: tuple[dict[str, Any], ...] = (GET_LOAD_STATUS_SCHEMA, BOOK_LOAD_SCHEMA)


@dataclass(frozen=True)
class ToolSpec:
    name: str
    schema: dict[str, Any]
    is_write: bool
    purpose: str
    # The assignment asks for the output structure as well as the input contract. There is no
    # output JSON Schema (nothing consumes one), so this is the declared shape a reader gets.
    returns: str


TOOLS: dict[str, ToolSpec] = {
    "get_load_status": ToolSpec(
        name="get_load_status",
        schema=GET_LOAD_STATUS_SCHEMA,
        is_write=False,
        purpose="Current live state of one load from the operations API.",
        returns=(
            "{ok: true, load_id, status (one of the six lifecycle states), origin, destination, "
            "equipment, weight_kg, pickup_window {from, to}, carrier {carrier_id, name, status} "
            "| null, booking_reference | null, eta | null, last_position {place, lat, lon} | null, "
            "last_position_age_s | null, position_is_stale: bool | null, updated_at, source, "
            "snapshot_at}  —  on refusal: {ok: false, error, message, load_id}"
        ),
    ),
    "book_load": ToolSpec(
        name="book_load",
        schema=BOOK_LOAD_SCHEMA,
        is_write=True,
        purpose="Commit a load to a carrier — irreversible, operator-confirmed, exactly once.",
        returns=(
            "{ok: true, load_id, status: 'booked', carrier {carrier_id, name}, "
            "booking_reference, booked_at, irreversible: true, source}  —  on refusal: "
            "{ok: false, error (confirmation_required | authorisation_spent | already_booked | "
            "load_not_open | unknown_load | unknown_carrier | carrier_not_permitted), message, "
            "load_id, ...context}"
        ),
    ),
}


# --------------------------------------------------------------------------------------------
# Value objects
# --------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class ToolResult:
    """One tool outcome, in the shape that goes back to the model as a `role="tool"` message.

    `ok=False` is a tool-DOMAIN outcome the model must read and relay — an unknown load, a
    malformed identifier, a refused booking. It never raises, because raising would abort the
    conversation over an ordinary business answer that the user is entitled to hear. Environment
    failures are the other tier and do raise RetrievalError; the split is by who must react.
    """

    ok: bool
    data: dict[str, Any] | None = None
    error: str | None = None
    message: str | None = None

    def payload(self) -> dict[str, Any]:
        body: dict[str, Any] = {"ok": self.ok}
        if self.error is not None:
            body["error"] = self.error
        if self.message is not None:
            body["message"] = self.message
        if self.data:
            body.update(self.data)
        return body


@dataclass(frozen=True)
class ToolCall:
    """One tool call as the model emitted it. `raw_arguments` is a JSON string on the wire."""

    call_id: str
    name: str
    raw_arguments: str


@dataclass(frozen=True)
class ToolInvocation:
    call: ToolCall
    result: ToolResult
    # None whenever parsing or validation rejected the call — there are no validated arguments in
    # that case, and recording an empty dict would blur "rejected" into "called with nothing".
    arguments: dict[str, Any] | None


@dataclass(frozen=True)
class OrchestratedAnswer:
    question: str
    answer: str
    answer_model: str
    invocations: tuple[ToolInvocation, ...]
    rounds: int
    rounds_exhausted: bool
    # Set only on the retrieval fallback branch, so a reader can tell a cited knowledge-base
    # answer from a tool answer without re-deriving it from an empty invocation tuple.
    grounded: GroundedAnswer | None
    # The operations file this run actually read. Hardcoding DEFAULT_LOADS here made `Source:`
    # claim data/external/loads.json even under --loads elsewhere, and `Source:` is graded output.
    operations_source: str | None = None

    @property
    def used_tools(self) -> bool:
        return bool(self.invocations)

    def source(self) -> str:
        """Where the answer's facts came from — the counterpart of HW4's `Source:` line."""
        if self.grounded is not None:
            return ", ".join(self.grounded.source_files()) or "(none)"
        if self.invocations:
            source = self.operations_source or _display_path(DEFAULT_LOADS)
            return f"{source} (operations API mock)"
        return "(none)"


# --------------------------------------------------------------------------------------------
# Validation — pure, no I/O, runs before the data layer is ever consulted
# --------------------------------------------------------------------------------------------


def _display_path(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def _reject(error: str, message: str, **data: Any) -> ToolResult:
    """A refusal the model is told about. Which tool produced it is already on the ToolCall the
    ToolInvocation pairs this with, so it is deliberately not duplicated here."""
    return ToolResult(ok=False, error=error, message=message, data=data or None)


def parse_arguments(call: ToolCall) -> tuple[dict[str, Any] | None, ToolResult | None]:
    """Decode the model's argument string.

    The SDK hands arguments over as a raw JSON *string*, not a dict, so a malformed generation
    reaches this function as text. The JSONDecodeError is converted rather than propagated because
    a model that emitted bad JSON must be told so it can correct itself — the exception text is
    carried into the message, so nothing is swallowed.
    """
    try:
        parsed = json.loads(call.raw_arguments or "{}")
    except json.JSONDecodeError as exc:
        return None, _reject(
            "malformed_arguments",
            f"arguments were not valid JSON ({exc}). Re-issue the call with a valid JSON object.",
        )
    if not isinstance(parsed, dict):
        return None, _reject(
            "malformed_arguments",
            f"arguments must be a JSON object, got {type(parsed).__name__}.",
        )
    return parsed, None


def check_shape(schema: dict[str, Any], args: dict[str, Any]) -> ToolResult | None:
    """Re-check the schema's own contract on arrival, reading the contract itself.

    The schema is guidance sent to the model; nothing in the API guarantees the arguments come
    back conforming to it. The unknown-property check matters most: an unexpected key is the shape
    an injection attempt would take, and `additionalProperties: false` is only enforced here.

    The field names come out of the schema rather than being restated, for the same reason the id
    patterns are single-sourced — a property added to the contract and forgotten here would arrive
    as an `unknown_argument` refusal for an argument the model was explicitly invited to send.
    """
    parameters = schema["function"]["parameters"]
    required: tuple[str, ...] = tuple(parameters["required"])
    allowed = set(parameters["properties"])
    unknown = sorted(set(args) - allowed)
    if unknown:
        return _reject(
            "unknown_argument",
            f"unexpected argument(s) {', '.join(unknown)}. This tool accepts only: "
            f"{', '.join(sorted(allowed))}.",
        )
    missing = [
        name
        for name in required
        if not isinstance(args.get(name), str) or not args[name].strip()
    ]
    if missing:
        return _reject(
            "missing_argument",
            f"required argument(s) {', '.join(missing)} are absent or not a non-empty string.",
        )
    return None


def validate_get_load_status(
    call: ToolCall,
) -> tuple[dict[str, Any] | None, ToolResult | None]:
    args, rejection = parse_arguments(call)
    if rejection is not None or args is None:
        return None, rejection
    rejection = check_shape(GET_LOAD_STATUS_SCHEMA, args)
    if rejection is not None:
        return None, rejection
    load_id = args["load_id"].strip()
    if not LOAD_ID.match(load_id):
        return None, _reject(
            "invalid_load_id_format",
            f"load_id {load_id!r} is not a load identifier. Expected the form FX-YYYY-NNNNNN, "
            "for example FX-2026-000042.",
        )
    return {"load_id": load_id}, None


def validate_book_load(
    call: ToolCall, *, operator_confirmed: bool
) -> tuple[dict[str, Any] | None, ToolResult | None]:
    """Validate a write call, including the authorisation the model is not allowed to supply.

    `confirmed` stays in the schema so the model can express what it believes the user asked for,
    but it is never the authority: `operator_confirmed` comes from the human's --confirm flag. A
    model that set the flag for itself is recorded as having done so, because a booking authorised
    by the thing being authorised is exactly the failure the confirmation rule exists to stop.
    """
    args, rejection = parse_arguments(call)
    if rejection is not None or args is None:
        return None, rejection
    rejection = check_shape(BOOK_LOAD_SCHEMA, args)
    if rejection is not None:
        return None, rejection
    load_id = args["load_id"].strip()
    carrier_id = args["carrier_id"].strip()
    if not LOAD_ID.match(load_id):
        return None, _reject(
            "invalid_load_id_format",
            f"load_id {load_id!r} is not a load identifier. Expected the form FX-YYYY-NNNNNN.",
        )
    if not CARRIER_ID.match(carrier_id):
        return None, _reject(
            "invalid_carrier_id_format",
            f"carrier_id {carrier_id!r} is not a carrier identifier. Expected the form CAR-NNNNN.",
        )
    # `is True`, not bool(): the schema declares a boolean but nothing guarantees one arrives, and
    # bool("no") is True. This field is the audit trail for a self-authorisation attempt, so a
    # non-boolean must not be recorded as one.
    model_self_confirmed = args.get("confirmed") is True
    if not operator_confirmed:
        return None, _reject(
            "confirmation_required",
            "booking is irreversible and the human operator has not authorised it. Report this "
            "and stop; re-running the same request with --confirm is the operator's decision, "
            "not yours.",
            load_id=load_id,
            carrier_id=carrier_id,
            model_self_confirmed=model_self_confirmed,
        )
    return {"load_id": load_id, "carrier_id": carrier_id}, None


# --------------------------------------------------------------------------------------------
# Data layer — tier two: only the operator can repair these, so they raise
# --------------------------------------------------------------------------------------------


def load_operations_data(path: Path = DEFAULT_LOADS) -> dict[str, Any]:
    display = _display_path(path)
    if not path.is_file():
        raise RetrievalError(
            f"{display} not found. The external tool reads its operations data from that file. "
            "Restore it:\n"
            f"  git checkout -- {display}"
        )
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RetrievalError(
            f"{display} is not valid JSON ({exc}). Restore it:\n  git checkout -- {display}"
        ) from exc
    if not isinstance(data, dict) or not isinstance(data.get("loads"), dict):
        raise RetrievalError(
            f"{display} is missing its 'loads' object. The file must be a JSON object with "
            "'loads' and 'carriers' keys."
        )
    if not isinstance(data.get("carriers"), dict):
        raise RetrievalError(
            f"{display} is missing its 'carriers' object. The file must be a JSON object with "
            "'loads' and 'carriers' keys."
        )
    for carrier_id, carrier in data["carriers"].items():
        if not isinstance(carrier, dict):
            raise RetrievalError(
                f"{display}: carrier {carrier_id} is not an object. Restore it:\n"
                f"  git checkout -- {display}"
            )
        # Same reasoning as the load-status check below, at the sibling site: `!= "active"` reads
        # an unrecognised status as "not permitted", so a typo would silently refuse every booking
        # for this carrier with a plausible-looking business message instead of failing loudly.
        absent = [key for key in REQUIRED_CARRIER_KEYS if key not in carrier]
        if absent:
            raise RetrievalError(
                f"{display}: carrier {carrier_id} is missing {', '.join(absent)}. Restore it:\n"
                f"  git checkout -- {display}"
            )
        if carrier.get("status") not in CARRIER_STATES:
            raise RetrievalError(
                f"{display}: carrier {carrier_id} has status {carrier.get('status')!r}, which is "
                f"not one of {', '.join(CARRIER_STATES)}. Restore it:\n"
                f"  git checkout -- {display}"
            )
    # A status outside the lifecycle would make every downstream verdict meaningless — the booking
    # invariants are expressed as "not one of the open states", so an unrecognised value would
    # silently read as closed rather than as corrupt.
    for load_id, load in data["loads"].items():
        if not isinstance(load, dict):
            # Without this the next line raises a bare AttributeError, which main()'s boundary
            # catch does not handle — the operator gets a traceback instead of the repair command.
            raise RetrievalError(
                f"{display}: load {load_id} is not an object. Restore it:\n"
                f"  git checkout -- {display}"
            )
        absent = [key for key in REQUIRED_LOAD_KEYS if key not in load]
        if absent:
            raise RetrievalError(
                f"{display}: load {load_id} is missing {', '.join(absent)}. Restore it:\n"
                f"  git checkout -- {display}"
            )
        if load.get("status") not in LOAD_STATES:
            raise RetrievalError(
                f"{display}: load {load_id} has status {load.get('status')!r}, which is not one "
                f"of the lifecycle states {', '.join(LOAD_STATES)}. Restore it:\n"
                f"  git checkout -- {display}"
            )
        # A dangling carrier reference would surface as `"carrier": null` on an ok=True result —
        # live data that looks merely unassigned rather than corrupt. That is the silent-empty
        # result this repo refuses to produce.
        assigned = load.get("carrier_id")
        if assigned is not None and assigned not in data["carriers"]:
            raise RetrievalError(
                f"{display}: load {load_id} references carrier {assigned!r}, which is not in "
                f"'carriers'. Restore it:\n  git checkout -- {display}"
            )
    return data


# --------------------------------------------------------------------------------------------
# Tools
# --------------------------------------------------------------------------------------------


def get_load_status(load_id: str, *, data: dict[str, Any]) -> ToolResult:
    """Tool: get_load_status. Type: read. Returns one load's live state from the operations API.

    When useful: a question about a specific load's status, position, ETA or carrier.
    When NOT useful: any question about what the lifecycle is or what a status means — that is
    documentation, it is in the knowledge base, and retrieval answers it better.
    """
    load = data["loads"].get(load_id)
    if load is None:
        return _reject(
            "unknown_load",
            f"load {load_id} does not exist in the operations API. Check the identifier with the "
            "user; do not substitute a different one.",
            load_id=load_id,
        )
    carrier_id = load.get("carrier_id")
    carrier = data["carriers"].get(carrier_id) if carrier_id else None
    age = load.get("last_position_age_s")
    return ToolResult(
        ok=True,
        data={
            "load_id": load["load_id"],
            "status": load["status"],
            "origin": load["origin"],
            "destination": load["destination"],
            "equipment": load["equipment"],
            "weight_kg": load["weight_kg"],
            "pickup_window": load["pickup_window"],
            "carrier": (
                None
                if carrier is None
                else {
                    "carrier_id": carrier["carrier_id"],
                    "name": carrier["name"],
                    "status": carrier["status"],
                }
            ),
            "booking_reference": load.get("booking_reference"),
            "eta": load.get("eta"),
            "last_position": load.get("last_position"),
            "last_position_age_s": age,
            "position_is_stale": None if age is None else age > STALE_POSITION_S,
            "updated_at": load["updated_at"],
            "source": "freight-exchange operations API (mock)",
            "snapshot_at": data.get("snapshot_at"),
        },
    )


def _booking_reference(load_id: str) -> str:
    # Derived from the load id rather than generated from a clock or a random source: the examples
    # in outputs/ are graded artifacts, and a reference that changed per run would make them
    # irreproducible for no gain.
    return f"BKG-{load_id.removeprefix('FX-')}"


def book_load(load_id: str, carrier_id: str, *, data: dict[str, Any]) -> ToolResult:
    """Tool: book_load. Type: write / active. Commits a load to a carrier.

    The invariants are the ones data/raw/cqrs-event-sourcing-for-logistics.md states for the
    BookLoad command: the load must still be open, the carrier must be permitted to take it, and
    the load must not already be committed elsewhere.

    The commit is applied to the in-process copy of the operations data and is never written back
    to data/external/loads.json — the fixture is a fixed input, so every run starts from the same
    state and the committed examples stay reproducible.
    """
    load = data["loads"].get(load_id)
    if load is None:
        return _reject(
            "unknown_load",
            f"load {load_id} does not exist in the operations API. Nothing was booked.",
            load_id=load_id,
        )
    carrier = data["carriers"].get(carrier_id)
    if carrier is None:
        return _reject(
            "unknown_carrier",
            f"carrier {carrier_id} does not exist in the operations API. Nothing was booked.",
            load_id=load_id,
            carrier_id=carrier_id,
        )
    if carrier["status"] != "active":
        return _reject(
            "carrier_not_permitted",
            f"carrier {carrier_id} ({carrier['name']}) is {carrier['status']} and may not take "
            "loads. Nothing was booked.",
            load_id=load_id,
            carrier_id=carrier_id,
            carrier_status=carrier["status"],
        )
    if load["status"] not in OPEN_STATUSES:
        existing = load.get("booking_reference")
        if existing is not None:
            return _reject(
                "already_booked",
                f"load {load_id} is already committed to carrier {load.get('carrier_id')} under "
                f"booking {existing} and is now {load['status']}. A load is booked exactly once; "
                "nothing was changed.",
                load_id=load_id,
                status=load["status"],
                booking_reference=existing,
                carrier_id=load.get("carrier_id"),
            )
        return _reject(
            "load_not_open",
            f"load {load_id} is {load['status']} and is not open for booking. Nothing was booked.",
            load_id=load_id,
            status=load["status"],
        )
    reference = _booking_reference(load_id)
    load["status"] = "booked"
    load["carrier_id"] = carrier_id
    load["booking_reference"] = reference
    return ToolResult(
        ok=True,
        data={
            "load_id": load_id,
            "status": "booked",
            "carrier": {"carrier_id": carrier["carrier_id"], "name": carrier["name"]},
            "booking_reference": reference,
            "booked_at": data.get("snapshot_at"),
            "irreversible": True,
            "source": "freight-exchange operations API (mock)",
        },
    )


def dispatch(
    call: ToolCall, *, data: dict[str, Any], operator_confirmed: bool
) -> ToolInvocation:
    """Resolve, validate and run one model-requested call.

    An unhandled name is a refused result rather than a KeyError: the model chooses the name, so a
    hallucinated tool is untrusted input like any argument, and the conversation should carry on
    with the model told what it actually has.
    """
    spec = TOOLS.get(call.name)
    if spec is None:
        return ToolInvocation(
            call=call,
            arguments=None,
            result=_reject(
                "unknown_tool",
                f"{call.name!r} is not a tool this assistant exposes. Available tools: "
                f"{', '.join(sorted(TOOLS))}.",
            ),
        )
    if spec.is_write:
        args, rejection = validate_book_load(
            call, operator_confirmed=operator_confirmed
        )
    else:
        args, rejection = validate_get_load_status(call)
    if rejection is not None or args is None:
        return ToolInvocation(
            call=call,
            arguments=None,
            result=rejection
            if rejection is not None
            else _reject(
                call.name, "invalid_arguments", "arguments failed validation."
            ),
        )
    if spec.is_write:
        result = book_load(args["load_id"], args["carrier_id"], data=data)
    else:
        result = get_load_status(args["load_id"], data=data)
    return ToolInvocation(call=call, arguments=args, result=result)


# --------------------------------------------------------------------------------------------
# LLM boundary and orchestration
# --------------------------------------------------------------------------------------------


def _real_client(settings: Settings) -> Any:
    # Same lazy import as rag_answer._real_client, so every OpenAI call in this repo is built by
    # one factory with the same independent connect/read timeouts and retry policy.
    from rag_lib import _openai_client

    return _openai_client(settings)


def complete_with_tools(
    messages: list[dict[str, Any]],
    settings: Settings,
    *,
    client: Any | None = None,
    tools: Sequence[dict[str, Any]] | None = TOOL_SCHEMAS,
) -> Any:
    """One chat completion that may answer or may request tools. Returns the message object.

    rag_answer.complete() returns a string because a grounded answer is only ever text. This one
    returns the message: the tool calls live on it, and flattening it to text would throw away the
    thing this homework is about. `client=` is the same duck-typed seam.
    """
    api = client if client is not None else _real_client(settings)
    request: dict[str, Any] = {
        "model": settings.answer_model,
        "messages": messages,
        "temperature": TEMPERATURE,
    }
    if tools:
        request["tools"] = list(tools)
    else:
        # Withdrawing the tools by omitting the key would leave a conversation that still contains
        # tool_calls and role="tool" messages describing tools the request no longer declares. The
        # offline fake accepts that shape and could not tell us it was wrong. Declaring the tools
        # and forbidding their use says the same thing in a shape the API documents.
        request["tools"] = list(TOOL_SCHEMAS)
        request["tool_choice"] = "none"
    try:
        response = api.chat.completions.create(**request)
    except OpenAIError as exc:
        raise RetrievalError(
            f"tool-calling completion failed for model {settings.answer_model!r}: {exc}\n"
            "If that model is not available on this account, or does not support tool calling, "
            "pick another one — no code change is needed:\n"
            "  python scripts/external_tool.py --answer-model gpt-4o-mini ...\n"
            "or set RAG_ANSWER_MODEL=gpt-4o-mini in the environment."
        ) from exc
    if not response.choices:
        # rag_lib.search names a structured absence rather than letting it surface as an unrelated
        # IndexError; the same reasoning applies here.
        raise RetrievalError(
            f"model {settings.answer_model!r} returned no choices for this request. Re-run, or "
            "choose another model with --answer-model / RAG_ANSWER_MODEL."
        )
    return response.choices[0].message


def assistant_echo(message: Any) -> dict[str, Any]:
    """Rebuild the assistant turn as a plain dict for the next request.

    Built field by field rather than dumped from the SDK object: a dump carries nulls and
    provider-specific extras that the API rejects on the way back in, and the hand-built shape is
    also the one the offline fake produces, so test and production agree on a single contract.
    """
    calls: list[dict[str, Any]] = []
    for call in message.tool_calls or ():
        calls.append(
            {
                "id": call.id,
                "type": "function",
                "function": {
                    "name": call.function.name,
                    "arguments": call.function.arguments,
                },
            }
        )
    echo: dict[str, Any] = {"role": "assistant", "content": message.content}
    if calls:
        echo["tool_calls"] = calls
    return echo


def _answer_text(message: Any, settings: Settings) -> str:
    content = message.content
    if content is None or not content.strip():
        raise RetrievalError(
            f"model {settings.answer_model!r} returned an empty answer. Re-run, or choose another "
            "model with --answer-model / RAG_ANSWER_MODEL."
        )
    return content.strip()


def orchestrate(
    question: str,
    settings: Settings,
    *,
    k: int = DEFAULT_K,
    client: Any | None = None,
    collection: Any | None = None,
    bm25: Bm25Index | None = None,
    data: dict[str, Any] | None = None,
    loads_path: Path = DEFAULT_LOADS,
    operator_confirmed: bool = False,
) -> OrchestratedAnswer:
    """question -> model chooses -> validate -> tool -> model answers, or fall through to RAG.

    The retrieval branch is not a fallback for failure; it is the answer for every question that
    is about documented knowledge rather than live state. That the model picks between them is
    what makes "when NOT to call the tool" an observed behaviour instead of a claim.
    """
    operations = data if data is not None else load_operations_data(loads_path)
    source = _display_path(loads_path)
    # Resolved once for the whole question, not per turn: complete_with_tools falls back to
    # _real_client on every call, so leaving this None would build a fresh OpenAI client — and a
    # fresh connection pool — for each round and again for the retrieval branch. rag_answer.run_query
    # threads one client through its two calls for the same reason.
    api = client if client is not None else _real_client(settings)
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": question},
    ]
    invocations: list[ToolInvocation] = []
    # One human decision authorises one write. See the spend rule inside the loop below.
    writes_left = 1 if operator_confirmed else 0
    rounds = 0
    while rounds < MAX_TOOL_ROUNDS:
        message = complete_with_tools(messages, settings, client=api)
        calls = tuple(message.tool_calls or ())
        if not calls:
            if invocations:
                return OrchestratedAnswer(
                    question=question,
                    answer=_answer_text(message, settings),
                    answer_model=settings.answer_model,
                    invocations=tuple(invocations),
                    rounds=rounds,
                    rounds_exhausted=False,
                    grounded=None,
                    operations_source=source,
                )
            # No tool wanted and none used: this is a knowledge-base question, so hand it to the
            # Homework #4 pipeline untouched. Retrieval state is built per call rather than up
            # front precisely so a tool-only run never needs the vector index at all.
            grounded = answer_question(
                question, settings, k=k, client=api, collection=collection, bm25=bm25
            )
            return OrchestratedAnswer(
                question=question,
                answer=grounded.answer,
                answer_model=settings.answer_model,
                invocations=(),
                rounds=rounds,
                rounds_exhausted=False,
                grounded=grounded,
                operations_source=source,
            )
        rounds += 1
        messages.append(assistant_echo(message))
        for raw in calls:
            call = ToolCall(
                call_id=raw.id,
                name=raw.function.name,
                raw_arguments=raw.function.arguments,
            )
            spec = TOOLS.get(call.name)
            if (
                spec is not None
                and spec.is_write
                and operator_confirmed
                and writes_left <= 0
            ):
                # The operator authorised a booking, not a session. Nothing bounds how many calls
                # the model puts in one turn, so without this a single --confirm would cover every
                # book_load it emits — and an injected "book every open load" would spend one
                # human decision on N commits. That is a confused deputy, and the gate exists to
                # stop exactly it.
                invocation = ToolInvocation(
                    call=call,
                    arguments=None,
                    result=_reject(
                        "authorisation_spent",
                        "the operator authorised one booking and it has already been committed in "
                        "this run. A confirmation covers a single write. Report this and stop.",
                    ),
                )
            else:
                invocation = dispatch(
                    call, data=operations, operator_confirmed=writes_left > 0
                )
                # Consumed by a booking that COMMITTED. A refused write (already booked, carrier
                # not permitted) changed nothing, so it must not burn the operator's decision.
                if spec is not None and spec.is_write and invocation.result.ok:
                    writes_left -= 1
            invocations.append(invocation)
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call.call_id,
                    "content": json.dumps(
                        invocation.result.payload(), ensure_ascii=False
                    ),
                }
            )
    # The bound was reached. One final call with no tools offered forces a prose answer out of
    # what has already been gathered, so a looping model still terminates with something the user
    # can read. The exhaustion is recorded and printed rather than hidden.
    final = complete_with_tools(messages, settings, client=api, tools=None)
    return OrchestratedAnswer(
        question=question,
        answer=_answer_text(final, settings),
        answer_model=settings.answer_model,
        invocations=tuple(invocations),
        rounds=rounds,
        rounds_exhausted=True,
        grounded=None,
        operations_source=source,
    )


# --------------------------------------------------------------------------------------------
# Presentation
# --------------------------------------------------------------------------------------------


def format_invocation(invocation: ToolInvocation) -> str:
    arguments = invocation.arguments
    shown = (
        arguments if arguments is not None else _safe_raw(invocation.call.raw_arguments)
    )
    lines = [
        f"Tool called: {invocation.call.name}",
        f"Input: {json.dumps(shown, ensure_ascii=False, sort_keys=True)}",
        f"Result: {json.dumps(invocation.result.payload(), ensure_ascii=False, sort_keys=True)}",
    ]
    return "\n".join(lines)


def _safe_raw(raw: str) -> Any:
    """Show the model's raw arguments when validation rejected them before they became a dict."""
    try:
        return json.loads(raw or "{}")
    except json.JSONDecodeError:
        # Deliberately not an error path: this runs only to *display* a call that was already
        # refused, and the refusal itself already carried the decode failure to the model.
        return {"__unparsed__": raw}


def format_answer(result: OrchestratedAnswer) -> str:
    lines = [f"Question: {result.question}", f"Model: {result.answer_model}"]
    if result.used_tools:
        lines.append(f"Route: tool ({result.rounds} round(s))")
        for invocation in result.invocations:
            lines.extend(["", format_invocation(invocation)])
    else:
        lines.append("Route: knowledge base (no tool call — Homework #4 pipeline)")
        if result.grounded is not None:
            lines.append(
                f"Retrieved chunks: "
                f"{', '.join(hit.chunk_id for hit in result.grounded.hits) or '(none)'}"
            )
    lines.extend(["", f"Answer: {result.answer}", "", f"Source: {result.source()}"])
    if result.grounded is not None and result.grounded.cited_chunk_ids:
        lines.append(f"Citations: {', '.join(result.grounded.cited_chunk_ids)}")
    if result.rounds_exhausted:
        lines.append(
            f"Note: the {MAX_TOOL_ROUNDS}-round tool bound was reached; the answer above was "
            "produced with tools withdrawn."
        )
    return "\n".join(lines)


def result_record(result: OrchestratedAnswer) -> dict[str, Any]:
    return {
        "question": result.question,
        "route": "tool" if result.used_tools else "knowledge_base",
        "answer": result.answer,
        "answer_model": result.answer_model,
        "rounds": result.rounds,
        "rounds_exhausted": result.rounds_exhausted,
        "source": result.source(),
        "invocations": [
            {
                "tool": invocation.call.name,
                "raw_arguments": invocation.call.raw_arguments,
                "validated_arguments": invocation.arguments,
                "ok": invocation.result.ok,
                "error": invocation.result.error,
                "result": invocation.result.payload(),
            }
            for invocation in result.invocations
        ],
        "retrieved_chunks": (
            []
            if result.grounded is None
            else [hit.chunk_id for hit in result.grounded.hits]
        ),
        "citations": (
            [] if result.grounded is None else list(result.grounded.cited_chunk_ids)
        ),
    }


def render_tool_catalogue() -> str:
    """The § 2 tool description: name, type, purpose, when to call and when not to."""
    blocks: list[str] = []
    for name in sorted(TOOLS):
        spec = TOOLS[name]
        function = spec.schema["function"]
        blocks.append(
            f"Tool: {spec.name}\n"
            f"Type: {'write / active' if spec.is_write else 'read'}\n"
            f"Purpose: {spec.purpose}\n"
            f"Source: {_display_path(DEFAULT_LOADS)} (freight-exchange operations API mock)\n"
            f"Description sent to the model:\n  {function['description']}\n"
            f"Input schema:\n{json.dumps(function['parameters'], indent=2)}\n"
            f"Returns:\n  {spec.returns}"
        )
    return "\n\n".join(blocks)


# --------------------------------------------------------------------------------------------
# Scenarios and the examples artifact
# --------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class ScenarioRun:
    label: str
    operator_confirmed: bool


@dataclass(frozen=True)
class Scenario:
    id: str
    title: str
    question: str
    rubric_role: str
    runs: tuple[ScenarioRun, ...] = (ScenarioRun(label="", operator_confirmed=False),)


SCENARIOS: tuple[Scenario, ...] = (
    Scenario(
        id="s1",
        title="live state of a specific load",
        question="Where is load FX-2026-000042 right now, and when is it due to arrive?",
        rubric_role="the happy read — dynamic state no static corpus can hold",
    ),
    Scenario(
        id="s2",
        title="a load that does not exist",
        question="What is the current status of load FX-2026-999999?",
        rubric_role="honest miss — retrieval would answer from lifecycle prose instead",
    ),
    Scenario(
        id="s3",
        title="a malformed identifier",
        question="Give me the status of load FX-26-42.",
        rubric_role=(
            "the untrusted-input boundary — the contract's own pattern is the outer filter, "
            "validation the inner one"
        ),
    ),
    Scenario(
        id="s4",
        title="an irreversible write, refused then authorised",
        question="Book load FX-2026-000211 for carrier CAR-00817.",
        rubric_role="the confirmation gate — the model cannot authorise its own write",
        runs=(
            ScenarioRun(label="without --confirm", operator_confirmed=False),
            ScenarioRun(label="with --confirm", operator_confirmed=True),
        ),
    ),
    Scenario(
        id="s5",
        title="a question the tool must not answer",
        question=(
            "What does it mean for a load to be booked, and why is that transition treated as "
            "irreversible?"
        ),
        rubric_role="when NOT to call the tool — documented knowledge, answered by retrieval",
    ),
)


def load_commentary(path: Path) -> tuple[dict[str, Any], str]:
    """Read the hand-authored Homework #5 prose out of the shared evaluation file."""
    if not path.is_file():
        raise RetrievalError(
            f"{_display_path(path)} not found. It carries the hand-authored Homework #5 "
            "commentary. Restore it:\n"
            f"  git checkout -- {_display_path(path)}"
        )
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RetrievalError(
            f"{_display_path(path)} is not valid JSON ({exc})."
        ) from exc
    scenarios = payload.get("hw5_scenarios") or {}
    if not isinstance(scenarios, dict):
        raise RetrievalError(
            f"{_display_path(path)}: 'hw5_scenarios' must be an object keyed by scenario id."
        )
    conclusion = str(payload.get("hw5_conclusion") or "").strip()
    return scenarios, conclusion


def _same_file(left: Path, right: Path) -> bool:
    """True when two paths name the same file, whatever they are spelled like.

    A resolved-string compare misses two real cases: a case-insensitive filesystem (the macOS
    default), where `Outputs/Tool_Examples.MD` and `outputs/tool_examples.md` are one file with two
    spellings, and a symlink pointing into a protected path. `os.path.normcase` cannot help — on
    POSIX it is the identity function even when the filesystem underneath is case-insensitive.
    Comparing inodes answers the question directly, and it needs both files to exist, so the string
    compare remains the fallback for an output path that has not been created yet.
    """
    if left == right:
        return True
    try:
        return left.samefile(right)
    except OSError:
        # Not an error path: samefile raises when either side does not exist yet, which is the
        # normal case for a fresh --output. Fall back to the weaker comparison rather than let a
        # missing file decide the guard.
        return left.resolve() == right.resolve()


def guard_outputs(paths: dict[str, Path], *, reads: Path | None = None) -> None:
    """Refuse to write over a committed deliverable, over an input of this run, or over a sibling.

    The third check is the one that is easy to omit and expensive to lose: `--output` and
    `--results` landing on the same path passes every other check, and then the second promotion
    silently destroys the first artifact. rag_answer.guard_outputs carries the same pairwise loop.
    """
    protected: list[tuple[str, Path]] = [
        ("a committed deliverable", path) for path in PROTECTED_OUTPUTS
    ]
    if reads is not None:
        protected.append(("an input of this run", reads))
    for flag, path in paths.items():
        for label, target in protected:
            if _same_file(path, target):
                raise RetrievalError(
                    f"--{flag} points at {_display_path(target)}, which is {label}. Writing it "
                    "would destroy graded work. Choose another path."
                )
    items = list(paths.items())
    for position, (flag, path) in enumerate(items):
        for other_flag, other in items[position + 1 :]:
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
    answer_model: str,
) -> str:
    lines = [
        "# Tool integration examples — Homework #5",
        "",
        "Generated by `scripts/external_tool.py --examples`.",
        f"Answer model: `{answer_model}`, temperature {TEMPERATURE:.1f}, tool bound "
        f"{MAX_TOOL_ROUNDS} rounds.",
        f"Tools offered on every turn: {', '.join(f'`{name}`' for name in sorted(TOOLS))}. "
        "The model chooses; there is no hand-written router.",
        f"External source: `{_display_path(DEFAULT_LOADS)}` — a mock of the freight-exchange "
        "operations API.",
        "",
        "Each block is the format required by § 3 of the assignment. `Input:` is what reached the "
        "tool after validation, or the model's raw arguments when validation refused the call.",
        "",
        "---",
        "",
    ]
    for record in records:
        scenario_id = record["scenario_id"]
        entry = commentary.get(scenario_id) or {}
        lines.append(f"## {scenario_id} · {record['title']}")
        lines.append("")
        lines.append(f"*Rubric role: {record['rubric_role']}*")
        lines.append("")
        for run in record["runs"]:
            if run["label"]:
                lines.append(f"### Run — {run['label']}")
                lines.append("")
            lines.append(f"User question: {run['question']}")
            lines.append("")
            if run["invocations"]:
                for invocation in run["invocations"]:
                    lines.append(f"Tool called: {invocation['tool']}")
                    lines.append(
                        "Input: "
                        + json.dumps(
                            invocation["validated_arguments"]
                            if invocation["validated_arguments"] is not None
                            else _safe_raw(invocation["raw_arguments"]),
                            ensure_ascii=False,
                            sort_keys=True,
                        )
                    )
                    lines.append(
                        "Result: "
                        + json.dumps(
                            invocation["result"], ensure_ascii=False, sort_keys=True
                        )
                    )
                    lines.append("")
            else:
                lines.append("Tool called: (none — routed to knowledge-base retrieval)")
                lines.append(
                    "Input: "
                    + json.dumps(
                        {"retrieved_chunks": run["retrieved_chunks"]},
                        ensure_ascii=False,
                        sort_keys=True,
                    )
                )
                lines.append(
                    "Result: "
                    + json.dumps(
                        {"citations": run["citations"], "source": run["source"]},
                        ensure_ascii=False,
                        sort_keys=True,
                    )
                )
                lines.append("")
            lines.append(f"Final answer: {run['answer']}")
            lines.append("")
        why = str(entry.get("why_better_than_retrieval") or "").strip()
        comment = str(entry.get("comment") or "").strip()
        lines.append(f"Why tool is better than retrieval: {why}")
        lines.append("")
        lines.append(f"Comment: {comment}")
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


def _missing_commentary(commentary: dict[str, Any], conclusion: str) -> list[str]:
    missing: list[str] = []
    for scenario in SCENARIOS:
        entry = commentary.get(scenario.id) or {}
        for field_name in ("why_better_than_retrieval", "comment"):
            if not str(entry.get(field_name) or "").strip():
                missing.append(f"hw5_scenarios.{scenario.id}.{field_name}")
    if not conclusion:
        missing.append("hw5_conclusion")
    return missing


def _promote(candidate: Path, target: Path) -> None:
    # An atomic swap, so a crash mid-write cannot leave a half-written deliverable behind: the
    # target is either the old file or the new one, never a truncated one. (The HW2-HW4 writers
    # call write_text directly and do not have this property; HW1's prepare_knowledge_base.py
    # does. CLAUDE.md's Testing section asks for it, so this follows HW1 rather than its nearer
    # siblings.)
    os.replace(candidate, target)


def run_examples(
    settings: Settings,
    *,
    queries_path: Path,
    output_path: Path,
    results_path: Path,
    loads_path: Path,
    k: int,
    client: Any | None = None,
) -> int:
    guard_outputs({"output": output_path, "results": results_path}, reads=queries_path)
    commentary, conclusion = load_commentary(queries_path)
    # One operations dict for the whole run, so scenario 4's refusal genuinely leaves the state its
    # second run then changes — the two runs are a sequence, not two independent simulations.
    operations = load_operations_data(loads_path)
    # Built once for the whole run rather than per scenario: the scenarios that emit no tool call
    # fall through to retrieval, and rebuilding the BM25 index from chunks.jsonl for each of them
    # is pure waste. rag_answer.run_evaluate hoists the same two handles for the same reason.
    collection = open_collection(settings)
    bm25 = Bm25Index(load_chunks(settings.chunks_path))
    records: list[dict[str, Any]] = []
    for scenario in SCENARIOS:
        runs: list[dict[str, Any]] = []
        for run in scenario.runs:
            result = orchestrate(
                scenario.question,
                settings,
                k=k,
                client=client,
                data=operations,
                loads_path=loads_path,
                collection=collection,
                bm25=bm25,
                operator_confirmed=run.operator_confirmed,
            )
            record = result_record(result)
            record["label"] = run.label
            record["operator_confirmed"] = run.operator_confirmed
            runs.append(record)
            print(
                f"{scenario.id}{'/' + run.label if run.label else ''}  "
                f"route={record['route']}  "
                f"tools={','.join(i['tool'] for i in record['invocations']) or '-'}"
            )
        records.append(
            {
                "scenario_id": scenario.id,
                "title": scenario.title,
                "rubric_role": scenario.rubric_role,
                "question": scenario.question,
                "runs": runs,
            }
        )

    missing = _missing_commentary(commentary, conclusion)
    if missing:
        # Reported, never rendered as a placeholder: the hand-authored judgement is the graded part
        # of this artifact, and a filled-in-looking file would hide that it was never written.
        print(
            "\nHand-authored commentary still missing from "
            f"{_display_path(queries_path)}:",
            file=sys.stderr,
        )
        for entry in missing:
            print(f"  - {entry}", file=sys.stderr)
        print(
            "Write them from the real output above, then re-run --examples to render.",
            file=sys.stderr,
        )

    payload = {
        "answer_model": settings.answer_model,
        "temperature": TEMPERATURE,
        "max_tool_rounds": MAX_TOOL_ROUNDS,
        "k": k,
        "tools": sorted(TOOLS),
        "operations_source": _display_path(loads_path),
        "scenarios": records,
    }
    results_candidate = results_path.with_suffix(results_path.suffix + ".tmp")
    results_path.parent.mkdir(parents=True, exist_ok=True)
    results_candidate.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    _promote(results_candidate, results_path)
    print(f"\nwrote {_display_path(results_path)}")

    if missing:
        print(
            f"{_display_path(output_path)} not rendered — commentary incomplete.",
            file=sys.stderr,
        )
        return 1
    markdown = render_examples_markdown(
        records,
        commentary=commentary,
        conclusion=conclusion,
        answer_model=settings.answer_model,
    )
    output_candidate = output_path.with_suffix(output_path.suffix + ".tmp")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_candidate.write_text(markdown, encoding="utf-8")
    _promote(output_candidate, output_path)
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
    client: Any | None = None,
) -> int:
    result = orchestrate(
        question,
        settings,
        k=k,
        client=client,
        loads_path=loads_path,
        operator_confirmed=operator_confirmed,
    )
    if as_json:
        print(json.dumps(result_record(result), indent=2, ensure_ascii=False))
    else:
        print(format_answer(result))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--question", "-q", type=str, default=None)
    parser.add_argument(
        "--examples", action="store_true", help="run the 5 graded scenarios"
    )
    parser.add_argument(
        "--list-tools",
        dest="list_tools",
        action="store_true",
        help="print the tool contract",
    )
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="operator authorisation for a write tool; the model can never set this",
    )
    parser.add_argument("--k", type=int, default=DEFAULT_K)
    parser.add_argument("--answer-model", dest="answer_model", type=str, default=None)
    parser.add_argument("--loads", type=Path, default=DEFAULT_LOADS)
    parser.add_argument("--queries", type=Path, default=DEFAULT_QUERIES)
    parser.add_argument("--output", type=Path, default=DEFAULT_EXAMPLES_OUTPUT)
    parser.add_argument("--results", type=Path, default=DEFAULT_RESULTS)
    parser.add_argument("--json", dest="as_json", action="store_true")
    args = parser.parse_args(argv)

    # Mode exclusivity is settled before the try block, so a usage mistake exits 2 without having
    # cost an API call.
    modes = [bool(args.question), args.examples, args.list_tools]
    if sum(modes) != 1:
        parser.error(
            "provide exactly one of --question TEXT, --examples or --list-tools"
        )
    if args.k < 1:
        parser.error("--k must be at least 1")
    # --confirm --examples reads as "authorise the scenario write" and does nothing: run_examples
    # takes authorisation from each ScenarioRun. Silently ignoring it would be the worst outcome
    # for a flag whose whole purpose is that a human meant it.
    if args.examples and (args.confirm or args.as_json):
        parser.error(
            "--examples takes neither --confirm nor --json; the scenarios set their own"
        )
    if args.list_tools and (args.confirm or args.as_json):
        parser.error("--list-tools takes neither --confirm nor --json")

    # The contract is a set of module constants, so printing it needs neither a key nor a network.
    if args.list_tools:
        print(render_tool_catalogue())
        return 0

    try:
        settings = Settings.from_env(answer_model=args.answer_model)
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
