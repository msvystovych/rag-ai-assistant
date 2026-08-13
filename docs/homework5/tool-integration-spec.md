# External tool integration — design decisions

The Homework #5 counterpart to [`../homework4/generation-spec.md`](../homework4/generation-spec.md).
That file owns the answer layer — the prompt versions, the relevance floor and the citation
contract; this one owns everything the tool layer adds in front of it: the tool contract, the
validation boundary, the confirmation gate, and the orchestration turn that decides between live
data and the knowledge base. Homework #4 closed by ruling out an "agentic re-query loop", and that
deferral is **not** the one this homework consumes — what it claims is the tool-calling turn
Homework #4 never had, which is a different thing and is bounded on purpose.

Assignment spec:
[`../tasks/Домашнє завдання №5 — Інтеграція зовнішнього tool або джерела`](../tasks/Домашнє%20завдання%20№5%20—%20Інтеграція%20зовнішнього%20tool%20або%20джерела).

## Decisions

| # | Decision | Rationale |
|---|---|---|
| 1 | **The tool reads a committed JSON fixture (`data/external/loads.json`), not a live third-party API** | The rubric grades the integration pattern, not the existence of a network hop. A real endpoint would make the committed artifacts irreproducible (rates and statuses move), would add a second credential to a repo whose one key is already the only secret, and would break the standing invariant that the test suite runs offline. The fixture is shaped like the response an operations API would return, so the tool boundary is real even though the transport is not — and `rag_lib._openai_client` already demonstrates this repo's HTTP posture (independent connect/read timeouts) for the day it becomes one. |
| 2 | **Two tools ship, `get_load_status` (read) and `book_load` (write)** | § 2 asks for one tool *type* — an API tool — not one tool. A read-only integration can demonstrate two of the four validation clauses the rubric names; the write-action confirmation clause is only demonstrable if a write action exists. `book_load` also makes the tool layer answer the one question retrieval structurally cannot: not "what do the documents say", but "do the thing". |
| 3 | **Orchestration is native OpenAI tool calling — the model routes, and there is no hand-written router** | The alternative, a regex over the question, would make "when NOT to call the tool" a property of *our* dispatch code, which is trivially true by construction and worth nothing as evidence. Handing both schemas to the model on every turn and letting it choose means the routing is an observed behaviour: scenario s5 is graded on the model *not* calling a tool it was offered. |
| 4 | **The JSON Schema dicts ARE the `tools=` payload** (`GET_LOAD_STATUS_SCHEMA`, `BOOK_LOAD_SCHEMA`) | § 2 allows "JSON schema **or** Pydantic model". A Pydantic model would have to be serialised into this shape anyway, and would add the first declared production dependency since Homework #2 against a hard invariant that prefers a few standard-library lines. Keeping the schema literal means the contract the model is shown, the contract `--list-tools` prints, and the contract this document quotes are one object that cannot drift. `LOAD_ID_PATTERN` is likewise single-sourced into both the schema's `pattern` and the compiled regex validation uses. |
| 5 | **Failures split into two tiers by who has to react** | The assignment's own § 5 sample returns `{"error": ...}` dicts; this repo's binding style says every failure raises a domain error. Both are right about different things. A tool-domain outcome — unknown load, refused booking — is an ordinary business answer the **model** must relay, and raising would abort the conversation over it. An environment failure — fixture missing or malformed — is repairable only by the **operator**, so it raises `RetrievalError` with the remedial command, exactly like every other stop-the-run failure in this repo. Nothing is swallowed: every tier-one refusal is printed, recorded in `outputs/tool_results.json`, and surfaced in the answer. |
| 6 | **`scripts/external_tool.py` is self-contained; no Homework #1–#4 *code* file was modified** | `rag_answer.complete()` returns a string and cannot carry `tool_calls`, so reusing it would mean widening its return type and re-verifying Homework #4's rubric checklist and its 77 tests to deliver Homework #5. The cost of not reusing it is ~25 lines of completion boundary that resemble `complete()`; the cost of reusing it is touching a graded deliverable. The seam that *is* reused is the one that matters: `answer_question` is imported read-only for the fallback branch. (`data/eval/test_queries.json` *is* modified, additively, per decision 15 — it is the shared evaluation file every homework extends, not code.) |
| 7 | **Validation re-checks the schema's own contract on arrival, `additionalProperties` included** | The schema is guidance sent to a model, not a guarantee about what comes back. The unknown-property check is the one that earns its place: an unexpected key is the shape an injected instruction would arrive in, and `additionalProperties: false` is enforced nowhere else in the stack. |
| 8 | **Authorisation for a write comes from `--confirm`, never from the model's `confirmed` argument** | `confirmed` stays in the schema so the model can express what it believes the user asked for, but it is never the authority — a booking authorised by the thing being authorised is not authorised. When the model sets it anyway the refusal records `model_self_confirmed: true`, so the attempt is visible in the artifact rather than silently ignored. |
| 9 | **The write commits to the in-process copy of the operations data and is never persisted to disk** | The fixture is a fixed input. If a booking persisted, every subsequent run would start from a different state than the one the committed Markdown records, and `--examples` would stop being re-runnable. A test asserts the file's SHA-256 is unchanged across a successful booking. |
| 10 | **The booking reference is derived from the load id (`FX-2026-000211` → `BKG-2026-000211`)** | Same reproducibility argument as Homework #4's fixed temperature. A reference from a clock or a random source would change every run and make the committed examples impossible to reproduce, for no gain the rubric asks for. |
| 11 | **The tool loop is bounded at `MAX_TOOL_ROUNDS = 3`, ending in a forced tools-withdrawn turn** | Two rounds is the deepest any supported question needs — look a load up, then act on it. The third exists so a model that keeps re-calling still terminates. The final turn withdraws the tools rather than raising, so a looping model still produces something the user can read; the exhaustion is recorded on the result and printed, so it is a visible outcome rather than a hidden one. The bound is what keeps this an integration and not an agent. |
| 12 | **The "when NOT to call" rule lives in the tool `description` the model actually reads, not only in this document** | A schema description is a routing instruction, and this is where the design was measured to be load-bearing: the first version of `book_load`'s description told the model the call would be refused without operator authorisation, and the model correctly concluded there was no point calling it. It emitted no tool call, the write path was unreachable, and the confirmation gate could not be exercised at all. The description now instructs it to always call and let the tool decide — which is also the correct division of responsibility, because a permission the model can decline to request is not a permission the system controls. |
| 13 | **Position staleness is computed by the tool (`position_is_stale`), not left to the model** | `data/raw/scaling-and-zero-downtime-operations.md` § Caching Strategy requires a latest-known position to "expose its own age so callers can distinguish a fresh position from a stale one". Handing the model a raw `214` and a threshold would make freshness a judgement; returning the verdict makes it a fact. |
| 14 | **Retrieval state is built per call rather than up front** | A question that routes to a tool never touches the vector index, so `--question "Where is FX-2026-000042?"` works on a checkout with no index built. Opening the collection eagerly would have made every tool call depend on Homework #2's artifacts for no reason. |
| 15 | **`hw5_scenarios` and `hw5_conclusion` are authored by hand after a real run, added additively to `data/eval/test_queries.json`** | The same two-pass discipline as Homework #2's relevance comments, Homework #3's `hw3_comment` and Homework #4's `hw4_*` keys; the file's own `description` documents the convention and this is its fourth iteration. `--examples` names every missing entry on stderr and refuses to render the Markdown rather than emitting a placeholder. The pre-existing keys are never touched. |
| 16 | **`PROTECTED_OUTPUTS` covers every committed Homework #1–#4 artifact plus this homework's own external source** | Same family as Homework #3's baseline guard and Homework #4's output guard, widened because there is now more to destroy. A mistyped `--output` should stop the run, not delete a delivered homework. `data/external/loads.json` is in the tuple too: it is this homework's input, and an output routed onto it would destroy the run's own source. Review added the two checks that make the guard actually hold — a pairwise comparison so `--output` and `--results` cannot land on one path (the sibling in `rag_answer.py` had it; this copy had dropped it), and identity by inode rather than by resolved string, because `os.path.normcase` is the identity function on POSIX and would wave a differently-cased alias straight past on macOS. |
| 17 | **One `--confirm` authorises one committed booking, not the invocation** | Found by review, and it was a real hole rather than a theoretical one. `operator_confirmed` was a single boolean handed to every call in every round, while nothing bounds how many calls the model puts in one turn — so an injected "book every open load" would have spent one human decision on N irreversible commits. That is a confused deputy: the operator confirms one thing and the model spends the confirmation on others. The authorisation is now consumed by the booking that *commits* (a refused write changed nothing, so it must not burn the decision), and a second write in the same run is refused as `authorisation_spent`. The narrower reading — that the model cannot set `confirmed` for itself — was always true and was never the whole property. |
| 18 | **Argument names are read out of the schema, not restated in the validator** | `check_shape` takes the tool's schema and derives `required` and the allowed set from it. Review found the names had been hand-copied into the validator, which is the one drift this file single-sources everything else to prevent: a property added to the contract and forgotten in the validator arrives as an `unknown_argument` refusal for an argument the model was explicitly invited to send. |

## Known limits — stated, not hidden

- **Temperature 0 does not buy the reproducibility claim Homework #4 made.** That homework could
  say "re-run it and you get this file" because greedy decoding over a fixed prompt produces fixed
  text. Here the model additionally decides *whether* to call a tool and *what arguments to emit*,
  and neither is guaranteed stable across runs or model versions. What can honestly be said is narrower
  than it first appears: the run was executed twice (a mechanical first pass, then a second to
  render the hand-authored commentary) and both agreed on all six routes and every argument — but
  only the second is committed, so a reader cannot check the first. `outputs/tool_results.json`
  records `raw_arguments` per call so a *future* divergence is visible; the agreement of the two
  passes is a claim from the session, not an artifact.
- **Format validation cannot detect fabrication, and this is measured.** Asked to book a load
  "for carrier 817", the model emitted `CAR-00817` — well formed, real, and almost certainly not
  what someone typing "817" meant:

  ```
  $ python scripts/external_tool.py --question "Book load FX-2026-000633 for carrier 817." --json
  ...
  "raw_arguments": "{\"load_id\":\"FX-2026-000633\",\"carrier_id\":\"CAR-00817\"}"
  "error": "confirmation_required"
  ```

  Every validation rule this homework implements passes that argument, because every one of them
  is syntactic. The gap is not in the pattern — no amount of shape checking separates a correct
  identifier from a plausible one — and the only thing that actually stopped it was the
  confirmation gate putting a human in front of the arguments before the write committed. A read
  tool has no such gate, so the same fabrication against `get_load_status` would simply return the
  wrong load's status, confidently.
- **The malformed-identifier path was never exercised end to end.** Scenario s3 was designed to
  drive `invalid_load_id_format` through the live model and did not: given `FX-26-42` the model
  declined to emit it at all, because the contract it was shown declares the pattern. Three
  phrasings were tried (`FX-26-42`, `fx-2026-42`, `FX-2026-0042`) and none produced a call; only
  the first is committed, so the other two are likewise a session claim rather than an artifact. So the
  validator's rejection branch is proven only by the offline suite — six malformed identifiers
  parametrized, plus a test that distinguishes `invalid_load_id_format` from `unknown_load` against
  an empty data set to prove validation precedes the lookup. The contract is the outer filter and
  validation the inner one; on the committed run only the outer one was needed.
- **The mock has none of a real integration's failure modes.** No authentication, no rate limit, no
  latency, no timeout, no 5xx, no partial response, no pagination, no schema drift on the provider
  side. Every one of those is a validation and error-handling problem this tool has never had to
  solve, and the two-tier error model has only been exercised against a local file that is either
  present and well formed or absent and malformed.
- **The write is not durable, so idempotency is only demonstrated within one process.** Booking the
  same load twice in one run is correctly refused as `already_booked`; booking it twice in two runs
  succeeds twice, because the second run reloads the fixture. Real idempotency is a property of the
  store, and this store is a dictionary that lives for the length of a command.
- **Single-turn, like Homework #4.** Each question is independent and carries no memory of the
  last, so "book it" after a status question cannot work — the identifier is gone. The bounded
  loop keeps context *within* one question only.
- **The model's arithmetic over tool output is unchecked.** The s1 answer rendered
  `last_position_age_s: 214` as "about 3.5 minutes ago". That happens to be right. Nothing in the
  design verifies it, and a tool that returns numbers to a model that presents them in other units
  has an unguarded conversion step in the middle of a grounded answer.
- **The output contract is documented and rendered but not machine-enforced.** `get_load_status`
  and `book_load` return a declared shape, and the tests pin its fields, but there is no output
  JSON Schema validated at the boundary the way the input side is. A tool whose source changed
  shape would be caught by tests, not at runtime.
- **Parallel tool calls are covered offline but never observed live.** The loop iterates every
  entry in `message.tool_calls` and appends one `role="tool"` message per `tool_call_id`. No
  committed run has produced a multi-call turn, so the evidence is
  `test_a_multi_call_turn_returns_one_tool_message_per_call_id` and the three write-scope tests
  beside it, which script two calls with distinct ids. Review caught this bullet claiming suite
  coverage before that suite coverage existed — it was written from the shape of the code rather
  than from a test, which is the exact failure this section is supposed to prevent.
- **The tools-withdrawn final turn has never run against the live API.** It is reachable only from
  a model that requests tools three rounds running, which no committed run did. Review flagged
  that omitting `tools` from a conversation still containing `tool_calls` was an unverified wire
  shape the offline fake would happily mirror either way, so the final turn now supplies the tools
  and sets `tool_choice="none"` — the same instruction in a shape the API documents.

## What is deliberately not built

- **No deterministic pre-router.** Inspecting the question for a load id before the model sees it
  would make routing our behaviour rather than the model's, and § 2's "orchestration layer **or**
  model" is satisfied once. It would also, per the s3 limit above, be the thing that could name a
  mistyped identifier — a real gain, and still not what this homework was asked for.
- **No agentic re-query loop.** Still Homework #4's stated deferral and still not claimed. The loop
  here calls tools the model asks for and stops; it never reformulates a question, retries a failed
  retrieval with different terms, or plans a sequence of steps.
- **No MCP server.** § 2 offers "MCP-compatible tool" as one of five options and this homework took
  the API-tool option. The schemas are already MCP-shaped in every respect that matters (name,
  description, input schema), so the port would be transport work, not design work.
- **No real network call, no new dependency.** See decision 1 and the standing invariant that
  `requirements.txt` grows only when a homework's spec requires it.
- **No tool-result caching.** Six calls per `--examples` run against a local dictionary; an
  invalidation problem for no measurable gain, and caching *live* state is the specific mistake
  `data/raw/scaling-and-zero-downtime-operations.md` warns about for search results.
- **No streaming, and no structured-output mode for the final answer.** Both change nothing about
  whether the tool was called correctly, which is what this homework is graded on.
- **No persistence layer for writes, no audit log.** A real booking would need both, plus the event
  stream `data/raw/cqrs-event-sourcing-for-logistics.md` describes. That is a different homework.
- **No authentication or authorisation model beyond the confirmation gate.** There are no users,
  roles or scopes here; `--confirm` represents one operator with full authority.
