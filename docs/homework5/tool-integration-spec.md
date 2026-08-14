# External tool integration — design decisions

The Homework #5 counterpart to [`../homework4/generation-spec.md`](../homework4/generation-spec.md).
That file owns the answer layer: the prompt versions, the relevance floor and the citation contract.
This one owns everything the tool layer adds in front of it:

- the tool contract
- the validation boundary
- the confirmation gate
- the orchestration turn that chooses between live data and the knowledge base

Homework #4 closed by ruling out an "agentic re-query loop". This homework does **not** consume that
deferral. It claims the tool-calling turn Homework #4 never had, which is a different thing. The
bound on that turn is deliberate.

Assignment spec:
[`../tasks/Домашнє завдання №5 — Інтеграція зовнішнього tool або джерела`](../tasks/Домашнє%20завдання%20№5%20—%20Інтеграція%20зовнішнього%20tool%20або%20джерела).

## Contents

- [Decisions](#decisions)
  - [1. The tool reads a committed JSON fixture, not a live third-party API](#1-the-tool-reads-a-committed-json-fixture-not-a-live-third-party-api)
  - [2. Two tools ship — one read tool and one write tool](#2-two-tools-ship--one-read-tool-and-one-write-tool)
  - [3. Orchestration is native OpenAI tool calling, and there is no hand-written router](#3-orchestration-is-native-openai-tool-calling-and-there-is-no-hand-written-router)
  - [4. The JSON Schema dicts ARE the `tools=` payload](#4-the-json-schema-dicts-are-the-tools-payload)
  - [5. Failures split into two tiers by who has to react](#5-failures-split-into-two-tiers-by-who-has-to-react)
  - [6. `scripts/external_tool.py` is self-contained, and no Homework #1–#4 *code* file changed](#6-scriptsexternal_toolpy-is-self-contained-and-no-homework-14-code-file-changed)
  - [7. Validation re-checks the schema's own contract on arrival, `additionalProperties` included](#7-validation-re-checks-the-schemas-own-contract-on-arrival-additionalproperties-included)
  - [8. Authorisation for a write comes from `--confirm`, never from the model's `confirmed` argument](#8-authorisation-for-a-write-comes-from---confirm-never-from-the-models-confirmed-argument)
  - [9. The write commits to the in-process copy of the data, and writes nothing to disk](#9-the-write-commits-to-the-in-process-copy-of-the-data-and-writes-nothing-to-disk)
  - [10. The tool derives the booking reference from the load id](#10-the-tool-derives-the-booking-reference-from-the-load-id)
  - [11. The tool loop stops at `MAX_TOOL_ROUNDS = 3`, and ends in a forced tools-withdrawn turn](#11-the-tool-loop-stops-at-max_tool_rounds--3-and-ends-in-a-forced-tools-withdrawn-turn)
  - [12. The "when NOT to call" rule lives in the tool `description` the model actually reads](#12-the-when-not-to-call-rule-lives-in-the-tool-description-the-model-actually-reads)
  - [13. The tool computes position staleness, and does not leave it to the model](#13-the-tool-computes-position-staleness-and-does-not-leave-it-to-the-model)
  - [14. The tool builds retrieval state per call, not up front](#14-the-tool-builds-retrieval-state-per-call-not-up-front)
  - [15. Hand-authored `hw5_scenarios` and `hw5_conclusion` follow a real run](#15-hand-authored-hw5_scenarios-and-hw5_conclusion-follow-a-real-run)
  - [16. `PROTECTED_OUTPUTS` covers every committed Homework #1–#4 artifact](#16-protected_outputs-covers-every-committed-homework-14-artifact)
  - [17. One `--confirm` authorises one committed booking, not the invocation](#17-one---confirm-authorises-one-committed-booking-not-the-invocation)
  - [18. The validator reads argument names out of the schema, and never restates them](#18-the-validator-reads-argument-names-out-of-the-schema-and-never-restates-them)
- [Known limits — stated, not hidden](#known-limits--stated-not-hidden)
  - [Reproducibility](#reproducibility)
  - [What validation catches, and what it cannot](#what-validation-catches-and-what-it-cannot)
  - [What the mock is not](#what-the-mock-is-not)
  - [Gaps in the guarantees](#gaps-in-the-guarantees)
  - [Paths with offline coverage only](#paths-with-offline-coverage-only)
- [What is deliberately not built](#what-is-deliberately-not-built)

## Decisions

### 1. The tool reads a committed JSON fixture, not a live third-party API

The source is `data/external/loads.json`. The rubric grades the integration pattern, not the
existence of a network hop. A real endpoint would make the committed artifacts irreproducible,
because rates and statuses move. It would add a second credential to a repo whose one key is
already the only secret. It would also break the standing invariant that the test suite runs
offline. The fixture copies the shape of an operations API response. So the tool boundary is real
even though the transport is not. `rag_lib._openai_client` already demonstrates this repo's HTTP
posture — independent connect and read timeouts — for the day the transport becomes a real one.

### 2. Two tools ship — one read tool and one write tool

They are `get_load_status` and `book_load`. § 2 asks for one tool *type* — an API tool — not one
tool. A read-only integration can demonstrate
two of the four validation clauses the rubric names. The write-action confirmation clause needs a
write action to exist. `book_load` also makes the tool layer answer the one question retrieval
structurally cannot. That question is not "what do the documents say", but "do the thing".

### 3. Orchestration is native OpenAI tool calling, and there is no hand-written router

The model routes. The alternative is a regex over the question. That regex would make "when NOT to
call the tool" a property of *our* dispatch code. Such a property is trivially true by
construction, and it is worth nothing as evidence. This design hands both schemas to the model on
every turn, and lets the model choose. The routing then becomes an observed behaviour: scenario s5
grades the model on *not* calling a tool the code offered it.

### 4. The JSON Schema dicts ARE the `tools=` payload

The two constants are `GET_LOAD_STATUS_SCHEMA` and `BOOK_LOAD_SCHEMA`. § 2 allows "JSON schema
**or** Pydantic model". A Pydantic model must serialise into this shape anyway. It would also add
the first declared production dependency since Homework #2, against a hard invariant that prefers
a few standard-library lines. The literal schema keeps three contracts as one object that cannot
drift. The three are the contract the model sees, the contract `--list-tools` prints, and the
contract this document quotes. `LOAD_ID_PATTERN` likewise has one source. It feeds both the
schema's `pattern` and the compiled regex that validation uses.

### 5. Failures split into two tiers by who has to react

The assignment's own § 5 sample returns `{"error": ...}` dicts. This repo's binding style says
every failure raises a domain error. Both are right about different things. A tool-domain outcome —
unknown load, refused booking — is an ordinary business answer. The **model** must relay it, and a
raise would abort the conversation over it. An environment failure — a fixture missing or malformed
— is one that only the **operator** can repair. That tier raises `RetrievalError` with the remedial
command, exactly like every other stop-the-run failure in this repo. The tool swallows nothing. The
run prints every tier-one refusal and records it in `outputs/tool_results.json`. The model relays
it in the answer.

### 6. `scripts/external_tool.py` is self-contained, and no Homework #1–#4 *code* file changed

`rag_answer.complete()` returns a string and cannot carry `tool_calls`. Reuse would mean a wider
return type. It would also mean a re-verification of Homework #4's rubric checklist and its 79
tests to deliver Homework #5. The cost of no reuse is ~25 lines of completion boundary that
resemble `complete()`. The cost of reuse is a touch on a graded deliverable. One seam does carry
over, and it is the one that matters: the fallback branch imports `answer_question` read-only.
This homework does modify `data/eval/test_queries.json`, additively, per decision 15. That file is
the shared evaluation file every homework extends, not code.

### 7. Validation re-checks the schema's own contract on arrival, `additionalProperties` included

The schema is guidance sent to a model, not a guarantee about what comes back. The unknown-property
check is the one that earns its place. An unexpected key is the shape an injected instruction would
arrive in. Nothing else in the stack enforces `additionalProperties: false`.

### 8. Authorisation for a write comes from `--confirm`, never from the model's `confirmed` argument

`confirmed` stays in the schema, so the model can express what it believes the user asked for. It
is never the authority. A booking that the model authorises for itself carries no authorisation.
When the model sets `confirmed` anyway, the refusal records `model_self_confirmed: true`. The
attempt then shows in the artifact, instead of a silent drop.

### 9. The write commits to the in-process copy of the data, and writes nothing to disk

The fixture is a fixed input. If a booking persisted, every later run would start from a different
state than the one the committed Markdown records. `--examples` would then stop being re-runnable.
A test asserts that the file's SHA-256 stays the same across a successful booking.

### 10. The tool derives the booking reference from the load id

`FX-2026-000211` becomes `BKG-2026-000211`. This is the same reproducibility argument as Homework
#4's fixed temperature. A reference from a clock or a random source would change every run. It
would make the committed examples impossible to reproduce, for no gain the rubric asks for.

### 11. The tool loop stops at `MAX_TOOL_ROUNDS = 3`, and ends in a forced tools-withdrawn turn

Two rounds is the deepest any supported question needs: look a load up, then act on it. The third
round exists so that a model that keeps re-calling still terminates. The final turn withdraws the
tools instead of a raise. So a looping model still produces something the user can read. The result
records the exhaustion and the run prints it, so the outcome stays visible rather than hidden. The
bound is what keeps this an integration and not an agent.

### 12. The "when NOT to call" rule lives in the tool `description` the model actually reads

It does not live only in this document. A schema description is a routing instruction. A real run
measured this description as load-bearing. The first version of `book_load`'s description told the
model that the system would refuse the call without operator authorisation. The model then
correctly concluded that a call had no point. It emitted no tool call. Nothing then reached the
write path, and the confirmation gate never ran. The description now instructs
the model to always call, and to let the tool decide. That split is also the correct division of
responsibility. A permission the model can decline to request is not a permission the system
controls.

### 13. The tool computes position staleness, and does not leave it to the model

The field is `position_is_stale`. `data/raw/scaling-and-zero-downtime-operations.md` § Caching
Strategy carries the requirement. A latest-known position must "expose its own age so callers can
distinguish a fresh position from a stale one". Hand the model a raw `214` and a threshold, and
freshness becomes a judgement. Return the verdict, and freshness becomes a fact.

### 14. The tool builds retrieval state per call, not up front

A question that routes to a tool never touches the vector index. `--question "Where is
FX-2026-000042?"` therefore works on a checkout that has no index built. Eager opening of the
collection would make every tool call depend on Homework #2's artifacts for no reason.

### 15. Hand-authored `hw5_scenarios` and `hw5_conclusion` follow a real run

They are additive keys in `data/eval/test_queries.json`. This is the same two-pass discipline as
Homework #2's relevance comments, Homework #3's `hw3_comment` and Homework #4's `hw4_*` keys. The
file's own `description` documents the convention, and this is its fourth iteration. `--examples`
names every missing entry on stderr. It then refuses to render the Markdown, instead of a
placeholder. Homework #5 changed no graded per-query value. The one pre-existing key it did change
is that top-level `description`, which documents the additive convention itself.

### 16. `PROTECTED_OUTPUTS` covers every committed Homework #1–#4 artifact

It also covers this homework's own external source. This guard is the same family as Homework #3's
baseline guard and Homework #4's output guard. It is wider, because there is now more to destroy. A
mistyped `--output` should stop the run, not delete a delivered homework. `data/external/loads.json`
is in the tuple too. It is this homework's input, so an output routed onto it would destroy the
run's own source. Review added the two checks that make the guard actually hold. The first is a
pairwise comparison, so `--output` and `--results` cannot land on one path. The sibling in
`rag_answer.py` had that comparison; this copy had dropped it. The second is identity by inode
rather than by resolved string, because `os.path.normcase` is the identity function on POSIX. That
function would wave a differently-cased alias straight past on macOS.

### 17. One `--confirm` authorises one committed booking, not the invocation

Review found this hole, and it was a real one rather than a theoretical one. `operator_confirmed`
was a single boolean, and every call in every round read it. Nothing bounds how many calls the
model puts in one turn. An injected "book every open load" would then have spent one human decision
on N irreversible commits. That is a confused deputy: the operator confirms one thing, and the
model spends the confirmation on others. The booking that *commits* now consumes the authorisation.
A refused write changes nothing, so it must not burn the decision. A second write in the same run
gets the refusal `authorisation_spent`. The narrower reading — that the model cannot set `confirmed`
for itself — was always true, and it was never the whole property.

### 18. The validator reads argument names out of the schema, and never restates them

`check_shape` takes the tool's schema and derives `required` and the allowed set from it. Review
found the names hand-copied into the validator. That drift is the one this file single-sources
everything else to prevent. A property that reaches the contract but not the validator arrives as
an `unknown_argument` refusal. The model had an explicit invitation to send that argument.


## Known limits — stated, not hidden

### Reproducibility

- **Temperature 0 does not buy the reproducibility claim Homework #4 made.** That homework could
  say "re-run it and you get this file", because greedy decoding over a fixed prompt produces fixed
  text. Here the model also decides *if* it calls a tool and *what arguments to emit*. Nothing
  guarantees that either decision is stable across runs or model versions. The honest claim is
  narrower than it first appears. The run happened twice: a mechanical first pass, then a second
  pass to render the hand-authored commentary. Both passes agreed on all six routes and every
  argument. Only the second pass is in the commit, so a reader cannot check the first.
  `outputs/tool_results.json` records `raw_arguments` per call, so a reader can see a *future*
  divergence. The agreement of the two passes is a claim from the session, not an artifact.

### What validation catches, and what it cannot

- **Format validation cannot detect fabrication, and a run measured that.** A question asked the
  model to book a load "for carrier 817". The model emitted `CAR-00817`, which is well formed and
  real. It is almost certainly not what someone typing "817" meant:

  ```
  $ python scripts/external_tool.py --question "Book load FX-2026-000633 for carrier 817." --json
  ...
  "raw_arguments": "{\"load_id\":\"FX-2026-000633\",\"carrier_id\":\"CAR-00817\"}"
  "error": "confirmation_required"
  ```

  Every validation rule this homework implements passes that argument, because every rule is
  syntactic. The gap is not in the pattern: no amount of shape checking separates a correct
  identifier from a plausible one. The only thing that actually stopped that argument was the
  confirmation gate. It puts a human in front of the arguments before the write commits. A read
  tool has no such gate. The same fabrication against `get_load_status` would simply return the
  wrong load's status, confidently.
- **Nothing ever exercised the malformed-identifier path end to end.** Scenario s3 aimed to drive
  `invalid_load_id_format` through the live model, and it failed to. Given `FX-26-42`, the model
  declined to emit the identifier at all, because the contract it saw declares the pattern. The
  session tried three phrasings (`FX-26-42`, `fx-2026-42`, `FX-2026-0042`), and none produced a
  call. Only the first phrasing is in the commit, so the other two are a session claim rather than
  an artifact. The offline suite is therefore the only proof of the validator's rejection branch.
  That suite parametrizes six malformed identifiers. It adds a test that separates
  `invalid_load_id_format` from `unknown_load` against an empty data set, which proves that
  validation precedes the lookup. The contract is the outer filter, and validation is the inner
  one. The committed run needed only the outer one.

### What the mock is not

- **The mock has none of a real integration's failure modes.** The mock has no authentication, no
  rate limit, no latency, and no timeout. It has no 5xx, no partial response, no pagination, and no
  schema drift on the provider side. Each one of those is a validation and error-handling problem
  that this tool never had to solve. Only a local file ever exercised the two-tier error model.
  That file is either present and well formed, or absent and malformed.
- **The write is not durable, so idempotency holds only within one process.** The tool correctly
  refuses a second booking of the same load in one run, as `already_booked`. The same booking twice
  in two runs succeeds twice, because the second run reloads the fixture. Real idempotency is a
  property of the store, and this store is a dictionary that lives for the length of a command.

### Gaps in the guarantees

- **Single-turn, like Homework #4.** Each question is independent and carries no memory of the
  last. So "book it" after a status question cannot work: the identifier is gone. The bounded
  loop keeps context *within* one question only.
- **Nothing checks the model's arithmetic over tool output.** The s1 answer rendered
  `last_position_age_s: 214` as "about 3.5 minutes ago". That happens to be right. Nothing in the
  design verifies it. A tool returns numbers, and the model presents them in other units. That
  conversion step sits unguarded in the middle of a grounded answer.
- **The output contract has documentation and rendering, but no machine enforcement.**
  `get_load_status` and `book_load` return a declared shape, and the tests pin its fields. No output
  JSON Schema validates the boundary the way the input side does. Tests would catch a tool whose
  source changed shape; runtime would not.

### Paths with offline coverage only

- **The offline suite covers parallel tool calls, but no live run ever showed one.** The loop
  iterates every entry in `message.tool_calls`, and appends one `role="tool"` message per
  `tool_call_id`. No committed run produced a multi-call turn. The evidence is therefore
  `test_a_multi_call_turn_returns_one_tool_message_per_call_id` and the three write-scope tests
  beside it, which script two calls with distinct ids. Review caught this bullet claiming suite
  coverage before that suite coverage existed. The bullet came from the shape of the code rather
  than from a test, which is the exact failure this section is supposed to prevent.
- **The tools-withdrawn final turn never ran against the live API.** Only a model that requests
  tools three rounds running reaches that turn, and no committed run did. Review flagged the wire
  shape: a conversation that still holds `tool_calls` but omits `tools`. Nothing verified that
  shape, and the offline fake would happily mirror it either way. The final turn therefore now
  supplies the tools and sets `tool_choice="none"`, which is the same instruction in a shape the
  API documents.

## What is deliberately not built

- **No deterministic pre-router.** Such a router would inspect the question for a load id before
  the model sees it. Routing would then become our behaviour rather than the model's. The § 2
  clause "orchestration layer **or** model" takes one of the two, and the model already satisfies
  it. Per the s3 limit above, a pre-router would also be the one thing that could name a mistyped
  identifier. That is a real gain, and still not what the assignment asked of this homework.

  **Claimed by Homework #6 (2026-08-14).** Its § 2 asks for deterministic rule-based routing in so
  many words, so `scripts/agent_flow.py` builds the router this entry declined — and it collects
  the predicted gain: the committed example `e5` puts the same malformed `FX-26-42` that scenario
  s3 used, and names the typo instead of falling through to retrieval. See
  [`../homework6/agent-flow-spec.md`](../homework6/agent-flow-spec.md) § Decisions 9. This entry is
  not rewritten; it recorded the right decision for Homework #5.
- **No agentic re-query loop.** This stays Homework #4's stated deferral, and this homework does
  not claim it. The loop here calls the tools the model asks for, and then stops. It never
  reformulates a question, never retries a failed retrieval with different terms, and never plans a
  sequence of steps.
- **No MCP server.** The § 2 list offers "MCP-compatible tool" as one of five options, and this
  homework took the API-tool option. The schemas already carry the MCP shape in every respect that
  matters: name, description, and input schema. A port would therefore be transport work, not
  design work.
- **No real network call, no new dependency.** See decision 1 and the standing invariant that
  `requirements.txt` grows only when a homework's spec requires it.
- **No tool-result caching.** The committed `--examples` run records four tool invocations across
  six runs: two `get_load_status` and two `book_load`. Two of the six runs call no tool at all,
  which is the behaviour scenarios s3 and s5 demonstrate. Four calls against a local dictionary buy
  no measurable gain, and they buy an invalidation problem. A cache over *live* state is also the
  specific mistake `data/raw/scaling-and-zero-downtime-operations.md` warns about for search
  results.
- **No streaming, and no structured-output mode for the final answer.** Neither one changes the
  correctness of the tool call. That correctness is what the rubric grades this homework on.
- **No persistence layer for writes, no audit log.** A real booking would need both, plus the event
  stream `data/raw/cqrs-event-sourcing-for-logistics.md` describes. That is a different homework.
- **No authentication or authorisation model beyond the confirmation gate.** There are no users,
  roles or scopes here. `--confirm` represents one operator with full authority.
