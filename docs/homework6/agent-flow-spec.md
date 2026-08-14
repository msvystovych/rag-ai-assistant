# Deterministic agent workflow — design decisions

The Homework #6 counterpart to [`../homework5/tool-integration-spec.md`](../homework5/tool-integration-spec.md).
That file owns the tool layer: the tool contract, the validation boundary, the confirmation gate and
the model-routed orchestration turn. This one owns the layer above it:

- the router, and the order of its rules
- the plan each route commits to before acting
- the state, and the steps that read it
- the answer composed from the recorded observations

Homework #5 closed by ruling out a "deterministic pre-router", because handing routing to the model
was the point of that homework. Homework #6's spec asks for exactly that router — § 2 says
`without LLM у routing — це нормально для цього завдання` — so this homework **claims that
deferral**, in the same way Homework #4 claimed Homework #3's answer-generation deferral. The
forward pointer is recorded in the Homework #5 doc under § What is deliberately not built.

Assignment spec:
[`../tasks/Домашнє завдання №6 — Перша agentic-структура`](../tasks/Домашнє%20завдання%20№6%20—%20Перша%20agentic-структура).

## Contents

- [Vocabulary](#vocabulary)
- [The router's rules](#the-routers-rules)
- [Decisions](#decisions)
  - [1. Nothing in this layer calls a model](#1-nothing-in-this-layer-calls-a-model)
  - [2. Four routes, and a fixed plan per route](#2-four-routes-and-a-fixed-plan-per-route)
  - [3. A step is a tool step or a gate step, and only tool steps are tools](#3-a-step-is-a-tool-step-or-a-gate-step-and-only-tool-steps-are-tools)
  - [4. The booking plan is verify → authorise → write, and the gate reads the state](#4-the-booking-plan-is-verify--authorise--write-and-the-gate-reads-the-state)
  - [5. The tools are Homework #3's and Homework #5's, imported read-only](#5-the-tools-are-homework-3s-and-homework-5s-imported-read-only)
  - [6. The knowledge tool is Homework #3's pipeline with the semantic half removed](#6-the-knowledge-tool-is-homework-3s-pipeline-with-the-semantic-half-removed)
  - [7. The rule ORDER is the design, and the trace records which rule fired](#7-the-rule-order-is-the-design-and-the-trace-records-which-rule-fired)
  - [8. Identifier patterns are single-sourced from the tool contract and unanchored here](#8-identifier-patterns-are-single-sourced-from-the-tool-contract-and-unanchored-here)
  - [9. A mistyped identifier is named — the gain Homework #5 predicted](#9-a-mistyped-identifier-is-named--the-gain-homework-5-predicted)
  - [10. A booking verb alone is not a booking request](#10-a-booking-verb-alone-is-not-a-booking-request)
  - [11. A booking resolves its operands from the clause that asks for it](#11-a-booking-resolves-its-operands-from-the-clause-that-asks-for-it)
  - [12. Clarification is a route with a step, not an early return](#12-clarification-is-a-route-with-a-step-not-an-early-return)
  - [13. Answers are composed from the observations, and the knowledge answer is extractive](#13-answers-are-composed-from-the-observations-and-the-knowledge-answer-is-extractive)
  - [14. `run_agent` receives its world instead of loading it](#14-run_agent-receives-its-world-instead-of-loading-it)
  - [15. A state snapshot never knows the future](#15-a-state-snapshot-never-knows-the-future)
  - [16. The five examples share one operations dict, in order](#16-the-five-examples-share-one-operations-dict-in-order)
  - [17. `PROTECTED_OUTPUTS` imports Homework #5's list and extends it](#17-protected_outputs-imports-homework-5s-list-and-extends-it)
  - [18. Hand-authored `hw6_scenarios` and `hw6_conclusion` follow a real run](#18-hand-authored-hw6_scenarios-and-hw6_conclusion-follow-a-real-run)
  - [19. Three defects found by adversarial review, and what they had in common](#19-three-defects-found-by-adversarial-review-and-what-they-had-in-common)
- [Known limits — stated, not hidden](#known-limits--stated-not-hidden)
  - [What the router cannot see](#what-the-router-cannot-see)
  - [Where the rule order is knowingly wrong](#where-the-rule-order-is-knowingly-wrong)
  - [What the knowledge route costs](#what-the-knowledge-route-costs)
  - [What the mock is not](#what-the-mock-is-not)
  - [What determinism hides](#what-determinism-hides)
- [What is deliberately not built](#what-is-deliberately-not-built)

## Vocabulary

One word per concept, used the same way in the code, the README and the rendered traces.

| Term | Meaning |
|---|---|
| **Route** | the deterministic classification of a user goal into one of four workflows |
| **Plan** | the ordered list of steps a route commits to *before* the first action |
| **Step** | one plan entry — either a tool step or a gate step |
| **Observation** | the dict a step recorded, always carrying `ok` |
| **State** | `AgentState` — the accumulating record of goal, route, plan, steps and answer |
| **Halt** | a step whose observation ends the plan early; recorded in `halted_at` |

## The router's rules

First match wins. `route()` returns the rule id as well as the route, so a trace can be audited
against this table rather than trusted.

| Rule | Fires when | Result |
|---|---|---|
| R1 | a booking request naming more than one distinct load or carrier | `clarification` — `ambiguous_load_id` / `ambiguous_carrier_id` |
| R2 | a booking request with exactly one load id and one carrier id | `booking` |
| R3 | a booking request with an identifier missing or mistyped | `clarification` — `missing_*` / `malformed_*` |
| R4 | a well-formed load id appears anywhere in the question | `load_status` |
| R5 | an identifier was attempted and mistyped | `clarification` — `malformed_load_id` / `malformed_carrier_id` |
| R6 | the question asks what something *means* (`mean`, `explain`, `define`, `why`, …) | `knowledge_base` |
| R7 | live-state vocabulary (`where`, `eta`, `status`, `position`, …) with no load named | `clarification` — `missing_load_id` |
| R8 | `rag_lib.infer_document_type` recognises the corpus's own vocabulary | `knowledge_base` |
| R9 | nothing matched | `clarification` — `no_route_matched` |

A "booking request" is a booking verb token (`book`, `assign`, `commit`, `reserve`) **plus** an
operand — an identifier of any kind, even a mistyped one — **or** the verb standing in the first
three words. Decision 10 explains why the bare verb is not enough.

R1 scans the **whole** question, because two candidate identifiers anywhere in it mean the user has
not settled on one. R2 and R3 then resolve the operands from the **booking clause only** — the span
from the verb to the next sentence boundary. Decision 11 explains why those two scopes differ.

## Decisions

### 1. Nothing in this layer calls a model

§ 2 asks for deterministic rule-based routing and says an LLM in the router is unnecessary. This
homework takes that further and removes the model from the whole flow: the router, the three tools
and the answer composition are all rules over the question text and the recorded observations.

Three things follow, and each is worth more than the fluency given up.
`outputs/agent_flow_examples.md` reproduces **byte for byte** — two consecutive runs produce
identical files, which no previous homework's artifact can claim. `tests/test_agent_flow.py`
exercises the shipped flow instead of a fake of it, because there is no non-determinism to fake
away; every other test file in this repo has to duck-type an OpenAI client. And the entire homework
runs with **no `OPENAI_API_KEY`**, so a grader can reproduce all of it without a credential.

The cost is stated plainly in § Known limits: the answers are worse than Homework #4's.

### 2. Four routes, and a fixed plan per route

`knowledge_base` (1 step), `load_status` (1 step), `booking` (3 steps), `clarification` (1 step).
§ 2 asks for a minimum of two routes **or** three steps; the booking route satisfies the step
threshold on its own and the four routes satisfy the other, so neither reading of the rubric is
left to interpretation.

Each route's plan is a module constant, not something assembled as the run proceeds. A plan that
grows in response to its own observations is a planner, and § 1 asks for a *simple controlled*
workflow. What the observations decide here is **how far along a fixed plan a run gets** — which is
enough to make the state load-bearing without making the control flow unpredictable.

### 3. A step is a tool step or a gate step, and only tool steps are tools

A **tool step** consults a source outside the workflow. A **gate step** reads only the state the
workflow has already accumulated. `check_authorisation` and `ask_user` are gates; the other three
are tools.

The distinction earns its place in the rendered trace. `Tool called:` means something only if a
decision is not counted as an integration, and `state.tool_calls` would otherwise overstate what the
workflow actually called — a five-tool catalogue where two of the entries consult nothing.

### 4. The booking plan is verify → authorise → write, and the gate reads the state

`get_load_status` → `check_authorisation` → `book_load`. The middle step is the whole demonstration
that state is used: it looks up the first step's recorded observation through
`AgentState.observation_of`, and refuses on either of two conditions — the recorded status is not
one of `external_tool.OPEN_STATUSES`, or the human operator did not pass `--confirm`.

Two consequences are deliberate. The gate consults the **record**, not the live operations dict it
is never handed, so "the workflow remembers what it already did" is a property of the code and not
a description of it (a test pins this by mutating the dict behind the gate's back). And a failed
observation halts the plan rather than raising: `book_load` after a refused gate is precisely the
confused-deputy commit the gate exists to prevent, so the remaining steps are dropped and
`halted_at` records where.

`--confirm` survives from Homework #5 unchanged. The workflow cannot set it, and a booking
authorised by the thing being authorised is the failure the rule exists to stop.

### 5. The tools are Homework #3's and Homework #5's, imported read-only

`scripts/agent_flow.py` imports, read-only and in full:

- from `external_tool` — `load_operations_data`, `get_load_status`, `book_load`, plus
  `LOAD_ID_PATTERN`, `CARRIER_ID_PATTERN` (decision 8), `OPEN_STATUSES` (the booking-eligibility
  test the gate applies), `DEFAULT_LOADS` and `PROTECTED_OUTPUTS` (decision 17);
- from `rag_lib` — `Bm25Index`, `load_chunks`, `infer_document_type`, plus `Chunk`, `Settings`,
  `RetrievalError` and `REPO_ROOT`.

The constants matter as much as the functions: editing `external_tool.LOAD_ID_PATTERN` or
`OPEN_STATUSES` changes this router's behaviour, which is exactly the single-sourcing decisions 8
and 4 are buying. **No Homework #1–#5 file changed.** That
is the same pattern Homework #5 used when it imported `rag_answer.answer_question` for its fallback
branch, and it is what keeps one contract for the operations data: a second copy of `book_load`'s
invariants is the one place two homeworks could silently disagree about what `booked` means.

§ 2 asks for "at least 2 mock tools with a fixed result". Three ship, all offline, all over
committed fixtures.

### 6. The knowledge tool is Homework #3's pipeline with the semantic half removed

`search_knowledge_base` runs `infer_document_type` to pick a `document_type` filter, then
`Bm25Index.top` restricted to that document's chunk ids. Both halves are rule-based and need no
network. What is missing is `search_improved`'s semantic branch and the RRF fusion over it, because
embedding a query needs the API key this homework refuses to require.

The filter is not a consolation prize. On the committed e1 example it cut the candidate set from 77
chunks to the 23 of one document before BM25 ranked anything, which is Homework #3's measured
precision gain arriving without a single embedding call.

### 7. The rule ORDER is the design, and the trace records which rule fired

The nine rules are ordered by how much a signal constrains the answer. A booking request is settled
first, because it is the only route that writes. Identifier evidence beats vocabulary evidence,
because a user who typed `FX-2026-000042` named a specific load and means it. An explicit
"what does X *mean*" beats live-state vocabulary, because the question is about the word and not
about a shipment — this is what keeps "What does the status `matched` mean?" out of the
clarification route while "What is the status of my load?" stays in it. Corpus vocabulary is tested
last, because it is the weakest: `rag_lib.DOCUMENT_TYPE_KEYWORDS` contains words as common as
`load` and `carrier`, so testing it earlier would swallow whole routes.

`RouteDecision.rule` carries the id into the state, the trace and `outputs/agent_flow_results.json`.
"The routing works" is a graded claim, and a trace that names R4 can be checked against the table
above; one that names only a route cannot.

### 8. Identifier patterns are single-sourced from the tool contract and unanchored here

`LOAD_ID_IN_TEXT` and `CARRIER_ID_IN_TEXT` are built from `external_tool.LOAD_ID_PATTERN` and
`CARRIER_ID_PATTERN` with the `^`/`$` anchors stripped. The tool patterns validate a whole argument;
a router has to find an identifier in the middle of a sentence. Restating the shape would create the
one place the router and the tool contract could disagree — a router that accepted an identifier the
tool then rejected, or the reverse.

Stripping anchors introduces a hazard that the surrounding guards close: without
`(?<![0-9A-Za-z-])` and `(?![0-9A-Za-z-])`, `FX-2026-0000421` yields the real-looking
`FX-2026-000042` and the workflow answers about a load the user never named. A test covers that
case specifically.

### 9. A mistyped identifier is named — the gain Homework #5 predicted

`LOAD_ID_ATTEMPT` and `CARRIER_ID_ATTEMPT` match near misses: `FX-26-42`, `fx-2026-000042`,
`CAR-817`. A match means the user tried to name an identifier and mistyped it, so the clarification
route says so and states the correct shape.

Homework #5's own § What is deliberately not built named this as the single thing a deterministic
pre-router could do that model routing structurally cannot. Its scenario s3 measured the
alternative: given `FX-26-42`, the model declined to emit the identifier at all, the question fell
through to retrieval, and the answer told the user the documents were insufficient — true,
unhelpful, and silent about the typo that caused it. Committed example e5 is the same question
through this router.

### 10. A booking verb alone is not a booking request

A booking request needs a verb **and** an operand: an identifier of any kind, or the verb standing
within the first three words.

The verb alone is not enough because `book`, `commit`, `assign` and `reserve` are corpus vocabulary
as well as imperatives. Ten documentation questions were traced through a verb-only rule and all ten
landed in the clarification route, including *"How do I book a load on the exchange?"* — which is
close to the first thing a reader of this repo would type. Whole-token matching only protects the
past participle (`booked` ≠ `book`); it does nothing for the bare infinitive.

The identifier half alone is also not enough: *"Book a load for me."* has no identifier and is
plainly a request. Word position is the only signal that separates the two without a parser, since
an imperative puts its verb first. Three words is measured rather than chosen — five re-swallows
*"How do I book a load on the exchange?"*, whose verb is the fourth word. The residual cost is in
§ Known limits.

### 11. A booking resolves its operands from the clause that asks for it

`_find` returns the **first** match in the whole sentence, regardless of which clause the booking
verb governs. Two failures follow from that, and both were live-reproduced against shipped code
before they were fixed (decision 19).

**Borrowed operands.** *"Where is load FX-2026-000633 right now? Also, book a truck from carrier
CAR-00817."* bound to `FX-2026-000633` — an identifier that appears only in the read clause — and
committed it. Delete the first sentence and the identical booking request routes to
`missing_load_id`, so an unrelated clause standing beside it was what turned a request the router
itself calls unactionable into an irreversible write.

`_booking_clause` fixes it: the operands for R2 and R3 come from the span running **from the
booking verb to the next sentence boundary**, never from the whole question. Both bounds are
conservative on purpose. An identifier typed *before* the request is being asked about rather than
booked, and an operand the workflow is unsure of must produce a question, never a commit. The cost
is a spurious "which load?" on an unusual phrasing, which is the safe direction to be wrong in.

**Discarded ambiguity.** R1 scans the whole question and refuses when it finds more than one
candidate — *"Where is FX-2026-000042 and should I book FX-2026-000318 for CAR-00817?"* is a
question about one load and a musing about another, and refusing beats committing either. It counts
over the **ATTEMPT** patterns, not the strict ones: *"Book FX-2026-000211 or FX-26-42 for
CAR-00817."* offers one well-formed candidate and one mistyped one, and counting only well-formed
matches finds a single candidate and books it — discarding uncertainty the user had made visible.
Matches are upper-cased and de-duplicated first, so one identifier typed twice, or typed once in
each case, is still one candidate.

**Nothing downstream catches either.** `check_authorisation` verifies the load the router already
chose, finds it genuinely `posted`, and authorises it. **A confirmation gate is not a defence
against a router that picked the wrong operand.** That is why the gate's every outcome now prints
both operands (decision 4): it is the last point at which a human can still notice.

### 12. Clarification is a route with a step, not an early return

`ask_user` is a real gate step with a real observation, so the clarification route has a plan like
every other route. That keeps the step loop uniform, keeps `State after step:` renderable for every
example the § 3 format demands, and makes the reason a first-class part of the record rather than
something inferred from an empty step list.

Nothing is read from stdin. The clarifying question **is** the final answer, which is what the
assignment's own worked example does, and it keeps `run_agent` a pure function of its inputs.

### 13. Answers are composed from the observations, and the knowledge answer is extractive

Each route has one composer that reads the recorded observations and fills a template. On the
knowledge route the answer is a quotation of the top-ranked chunk with its title, section and
`[chunk_id]` — the same citation contract Homework #4 uses, over a quotation instead of a generated
paragraph. It is an extraction, and § Known limits says so rather than letting the phrasing imply
otherwise.

Two small rules keep the output honest. The chunk's `"Title > Section. "` breadcrumb is stripped
before quoting, because the attribution already travels as its own fields and printing it twice
reads as padding. And a relayed tool message is capitalised, because Homework #5 wrote those strings
to sit inside a model's prose and this workflow relays one as a whole answer.

### 14. `run_agent` receives its world instead of loading it

The signature takes `operations` and `knowledge` rather than paths. No file, socket or stdin is read
inside the flow. Its one side effect is Homework #5's in-memory booking commit.

That is what lets a caller decide whether several questions share a world. `--examples` passes one
operations dict through all five, so e3's refusal genuinely precedes the state e4 changes; the tests
pass a fresh one per test so a booking cannot leak between them. A function that loaded its own data
could express neither.

### 15. A state snapshot never knows the future

`AgentState.snapshot(after_step=n)` renders the state as of after step *n*. Two fields are
suppressed for an intermediate snapshot: `final_answer`, which is composed after the loop, and
`halted_at`, which is recorded on the step that caused the halt.

Without the second rule, e3's step-1 snapshot reports `halted_at: "check_authorisation"` — the state
knowing at step 1 something it only learned at step 2. The trace is the graded artifact for
"the workflow remembers previous steps", so a snapshot that leaks a later fact backwards is worse
than no snapshot.

The observations inside a snapshot are summarised to `{step, ok, error}`. The full payload is already
on the `Observation:` line directly above, and repeating it pushes the one line a reader scans past
several screens of JSON.

### 16. The five examples share one operations dict, in order

e1 knowledge, e2 read, e3 booking refused, e4 the same booking authorised, e5 clarification. All
four routes appear, all three tools are called, and the booking pair is a sequence rather than two
independent simulations.

Ordering is therefore load-bearing, and a test enforces it: no example may read a load that an
earlier example committed. e4 books `FX-2026-000211`, so no later example may name it.

### 17. `PROTECTED_OUTPUTS` imports Homework #5's list and extends it

`agent_flow.PROTECTED_OUTPUTS` is `external_tool.PROTECTED_OUTPUTS` plus `outputs/tool_examples.md`
and `outputs/tool_results.json`. Importing rather than restating means a future addition to the
Homework #1–#4 list protects this script too. The two extra entries are the artifacts
`external_tool.py` writes, which is why it cannot list them itself.

`guard_outputs` refuses three things: a protected target, an input of the run, and two destinations
resolving to the same file. Each destination is checked **twice** — once as itself and once as the
`.tmp` candidate that `_write_atomically` lands on before promoting. Checking only the destinations
passed `--output examples.md --results examples.md.tmp`, and then the output's candidate write
destroyed the results file while both writes reported success. The candidate name is derived in one
place (`_candidate`) so the guard and the writer cannot drift. Every input of the run is protected,
`--loads` as well as `--queries`: a custom operations fixture is as losable as the commentary file.

A future homework that adds a script should import `agent_flow.PROTECTED_OUTPUTS` and extend it,
rather than restating the list from scratch as Homework #4 and #5 each did. Importing is what keeps
the accumulated list single-sourced; restating it forks the two conventions silently.

### 18. Hand-authored `hw6_scenarios` and `hw6_conclusion` follow a real run

Same two-pass discipline as Homework #2 through #5. The first pass writes
`outputs/agent_flow_results.json` and names every empty commentary entry on stderr; the second
renders `outputs/agent_flow_examples.md`. A missing entry is reported and the Markdown is **not**
written, because a filled-in-looking artifact would hide that the judgement was never made.

Determinism removes the reproducibility argument for two passes but not the honesty one: the
mechanical half of the artifact is generated, and the part that is graded as understanding is not.

### 19. Three defects found by adversarial review, and what they had in common

An adversarial review ran eight independent reviewers over the shipped code and then tried to refute
each finding. Three survived, and it is worth recording that **all three were the same shape**: the
router selecting an operand the user had not offered.

1. **A booking borrowed its load from another clause** — decision 11.
2. **Ambiguity was measured over well-formed identifiers only**, so a valid id beside a mistyped one
   was not ambiguous and the valid one was booked — decision 11.
3. **A well-formed carrier id was reported as malformed.** No rule before R5 consumed a bare
   `carrier_id`, so all four carriers in the fixture reached the near-miss branch and the workflow
   told the user a real identifier was a typo. R5's carrier test is now guarded on
   `carrier_id is None`, which restores the invariant its own comment asserts.

Two things generalise. First, **a confirmation gate is only as correct as whatever chose its
operands** — the gate reported `ok: true` on all three, because it verifies the load the router
already picked. Second, **rules do not test themselves.** Every one of these was found by
constructing questions against the rule list, never by running the flow, and the suite was green
throughout. Each fix is now mutation-tested: reverting any one of them turns the suite red.

A fourth, larger fix was **declined**: a `carrier_lookup_unsupported` clarification reason for
questions naming only a carrier. R9's message already enumerates the three things this workflow can
do, which answers the question honestly, and a seventh reason for a route that does not exist is
the gold-plating the simplicity gate exists to stop. The residual is in § Known limits.

## Known limits — stated, not hidden

### What the router cannot see

**Intent, negation and modality are invisible.** The router reads vocabulary and word position.
*"Do NOT book FX-2026-000211 for CAR-00817"* routes to `booking`. What prevents the write is not the
router but the operator gate: without `--confirm` the plan halts at `check_authorisation` with
`confirmation_required` and nothing is written, and the whole plan is visible in the trace before
the operator decides. An operator who types "do NOT book" and then passes `--confirm` has overridden
their own instruction.

**It cannot repair an identifier, only reject it.** e5 reports that `FX-26-42` is the wrong shape.
It cannot say that `FX-2026-000042` was probably meant. Identifiers are also case-sensitive, because
the tool contract's patterns are and the router single-sources them: `fx-2026-000042` is reported as
malformed, and the clarification text states the case requirement explicitly.

**When a booking request supplies neither identifier, only `missing_load_id` is reported.** The
load-first order is deliberate — a booking cannot proceed without the load — but it costs a fully
unspecified request two round trips.

### Where the rule order is knowingly wrong

Every ordering choice buys one case and loses another. These are the losses, measured:

- **A named load beats a definitional question.** R4 fires before R6, so *"What does the settlement
  process look like for FX-2026-000512?"* returns that load's live record rather than the documented
  settlement process. The workaround is to ask the concept question without the identifier. Fixing
  it needs intent modelling that a rule router cannot do without introducing more misroutes than it
  removes.
- **A documentation question that OPENS with a booking verb is read as an imperative.**
  *"Commit semantics in the event log?"* clarifies instead of searching the corpus. This is the
  measured price of the three-word imperative window that keeps *"Book a load for me."* on the
  clarification route (decision 10). Chasing it with a longer word list trades a rare miss for an
  unpredictable router.
- **A polite, non-imperative booking request without identifiers is read as documentation.**
  *"I would like to book a load"* puts its verb fifth and reaches the knowledge route. It is the
  mirror image of the case above; the window cannot satisfy both.
- **On a read route, a question naming several loads is answered for the first one.** The answer
  always names the load it used, but it does not mention that a second identifier was dropped. The
  ambiguity guard is scoped to writes on purpose (decision 11).
- **A well-formed carrier id names no route.** There is no carrier-status workflow — a carrier is
  checked only as part of a booking — so *"Is CAR-00817 active?"* reaches R9 and gets the capability
  list rather than an answer. That is a scope decision, not a defect, but the reason string is the
  generic `no_route_matched`, and a question that also carries a domain noun
  (*"Is CAR-00412 allowed to take loads?"*) reaches R8 and gets documentation instead. A dedicated
  reason was considered and declined — decision 19.
- **The booking clause is bounded by punctuation and by the verb, not by grammar.** Decision 11's
  fix stops an identifier being borrowed from a neighbouring clause, and it cannot stop one being
  borrowed from *inside* the same clause: *"book the FX-2026-000042 replacement for CAR-00817"*
  reads that identifier as the operand. Nothing short of parsing separates "the load" from "the
  load it replaces", and the gate's printed operands are the control that remains.
- **A question carrying one generic domain noun and no other signal is treated as documentation.**
  `DOCUMENT_TYPE_KEYWORDS` contains `load`, `loads`, `carrier`, `carriers` and `trucks`, so
  *"Any trucks available?"* asks for live capacity and gets prose. It stays a limit rather than a
  fix: there is no capacity tool, so the knowledge route is the least-bad terminal, and **pruning
  those keywords is not an option** — that dictionary is Homework #3 graded surface, and its own
  comment records that the keywords were drawn from the source documents rather than tuned to
  queries. Editing it to serve this router would destroy that property.
- **An empty question routes to `no_route_matched`.** The route is right and the reason is generic,
  because the taxonomy has no `empty_question` value. `run_agent` raises on it before any step runs.

### What the knowledge route costs

BM25 over a rule-inferred filter is **lexically weaker than Homework #3's hybrid and than the
retrieval under Homework #4's answers.** A question phrased in vocabulary the corpus does not use
scores zero and returns `no_match`; the semantic branch existed precisely to catch that, and it is
gone here. `Bm25Index.top` returns only positive-scoring chunks, so a step can observe fewer than
`k` hits, and zero surfaces as an explicit diagnostic observation rather than as a silent empty
answer.

The answer is a **quotation, not a synthesis.** It cannot combine two chunks, resolve a
contradiction between them, or answer a question the corpus only implies. On a documentation
question Homework #4 is simply better — and it cannot run without a key. That is the trade this
homework makes.

This route also **skips the manifest digest check** that `rag_lib.search` performs, because it never
touches the vector index. Editing `chunks.jsonl` breaks Homework #2–#4 retrieval loudly and changes
this route's answers quietly.

### What the mock is not

`data/external/loads.json` is a fixture, not an operations API: seven loads, four carriers, a frozen
`snapshot_at`. `book_load` does not bump `updated_at`, and `booked_at` is `snapshot_at` rather than a
clock reading — deliberate determinism, so a committed trace does not go stale the day after it is
written, but it means no temporal claim in a trace is a real timestamp.

The write commits to the in-process copy only and is never persisted (Homework #5's decision 9,
re-pinned here by a digest test because this workflow is a second caller of the same tool).
Reproducibility of the committed examples therefore depends on the refused booking preceding the
authorised one.

### What determinism hides

A deterministic flow cannot surprise its author, which is a benefit and a blind spot. Every failure
mode in this document was found by reading rules and tracing questions, never by watching a model do
something unexpected — and Homework #5's two most useful findings (a tool description that made a
code path unreachable, and a model fabricating `CAR-00817` from "carrier 817") both came from
exactly that kind of surprise. Three real defects in this router were caught only by an adversarial
review that deliberately tried to break it; the ambiguity rule of decision 11 exists because of one
of them. Rules do not test themselves.

## What is deliberately not built

- **No LLM anywhere.** Not in the router, not in the answer. § 2 explicitly permits this for
  routing, and decision 1 extends it to the whole flow for the reproducibility it buys. A later
  homework that asks for a model-in-the-loop agent wins over this entry.
- **No dynamic planner.** Plans are fixed per route. Nothing re-plans, retries with different terms,
  or decides mid-run to add a step. Homework #4 ruled out an "agentic re-query loop" and Homework #5
  did not claim it; this homework does not claim it either. What it adds over Homework #5 is a
  *multi-step plan whose later steps depend on earlier observations*, which is a different thing
  from a planner.
- **No unfiltered retry when the inferred filter finds nothing.** A wrong `document_type` filter can
  empty the result. The workflow reports it, naming the filter it applied, instead of silently
  searching again — an unplanned second search would make the plan's length depend on its own
  observations, which is the planner this homework is not.
- **No carrier-status route and no capacity route.** A carrier is checked inside a booking, and there
  is no tool for available capacity. Both would need a route, a tool and a fixture that the
  assignment does not ask for.
- **No interactive clarification loop.** The clarification route returns the question rather than
  reading stdin (decision 12). A REPL would add an I/O path that neither the committed examples nor
  the offline tests could exercise the same way.
- **No multi-turn state across questions.** Each `run_agent` call starts from an empty state. The
  operations dict can be shared by a caller, and nothing else is.
- **No persistence for writes and no audit log.** Homework #5 declined both for the same reason: a
  real booking needs the event stream `data/raw/cqrs-event-sourcing-for-logistics.md` describes, and
  that is a different homework.
- **No confidence scores and no LLM-as-judge.** The router is rules; a confidence number over a
  rule is decoration. Homework #4's deferral of judge-based scoring stands.
- **No new dependency.** `requirements.txt` is unchanged. This layer uses the standard library plus
  what Homework #3 and Homework #5 already import.
