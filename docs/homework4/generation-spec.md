# Answer generation — design decisions

The Homework #4 counterpart to [`../homework3/retrieval-improvements-spec.md`](../homework3/retrieval-improvements-spec.md).
That file owns the improved retrieval pipeline; this one owns everything the answer layer adds on
top of it: the prompt versions, the relevance floor, the citation contract, and the grounded-QA
evaluation. Homework #2 closed with "No LLM answer generation. This homework ends at retrieved
chunks." — this is the homework that consumes that deferral.

Assignment spec:
[`../tasks/Домашнє завдання №4 — Генерація відповіді поверх retrieval`](../tasks/Домашнє%20завдання%20№4%20—%20Генерація%20відповіді%20поверх%20retrieval).

## Decisions

| # | Decision | Rationale |
|---|---|---|
| 1 | **Three prompt versions ship as runnable constants** (`PROMPT_VERSIONS`, `--prompt-version v1\|v2\|v3`), not as quoted prose in a document | The rubric asks for before/after evidence. A "before" that exists only as a string inside a Markdown file cannot be re-run, so its recorded output is an assertion rather than a measurement. Keeping every version executable makes each improvement reproducible by one command, and lets offline tests pin the clauses each version must contain — an edit that silently drops the refusal rule or the citation requirement fails the suite instead of quietly degrading the grade. |
| 2 | **v1 is the assignment's own § 7 "original prompt", kept verbatim** — no role, no grounding rule, no refusal rule, no citation requirement | The baseline has to be the naive prompt the assignment itself names, or the improvements are measured against a strawman of our own construction. v1 deliberately has no system message at all. |
| 3 | **Answer model `gpt-4.1-mini`, reached through `Settings.answer_model`** (`RAG_ANSWER_MODEL` env override, `--answer-model` flag) | The project's one-env-read-point rule forces every environment variable through `Settings.from_env`; a chat model read locally in the new script would be the first exception. Routing it through `Settings` also means an account without access to this model needs a flag, not a code change — and the `OpenAIError` boundary names that flag in its diagnostic. |
| 4 | **Temperature is fixed at 0 as a module constant, not a CLI flag** | The committed answers are graded artifacts. Sampled decoding would make "re-run it and you get this file" a hope rather than an instruction, and would make a prompt-improvement comparison unfalsifiable — a difference between v1 and v3 could always be resampling noise. Configurability here would buy nothing the homework asks for and would cost the reproducibility claim. |
| 5 | **Two independent fallback gates: a retrieval-side relevance floor AND the prompt's own refusal rule** | Either alone leaves a hole. A score floor cannot tell that three on-topic chunks all miss the specific fact asked for — it only sees distance. A prompt rule alone never sees an empty context, so the "порожній context" half of the rubric row is untestable. Together the floor answers "is anything here close enough to be worth showing?" and the prompt answers "does what I was shown actually contain the answer?" |
| 6 | **Floor = `0.35`, applied to the best non-`None` `semantic_score` in the retrieved set** | Not a fresh guess: Homework #2's evaluation measured the out-of-corpus query's top score at **0.266** and the lowest in-corpus top-1 at **0.413**, and its analysis concluded "A score floor near 0.35 would be needed before this feeds an LLM." Homework #3 re-measured the same separation and deferred again. 0.35 sits in the measured gap and is the number this repo's own data produced. |
| 7 | **Below the floor the context is passed **empty** and the model is still called** — the run never short-circuits to a canned string | If the script returned the refusal itself, the refusal would be the script's behaviour and the rubric's "**Модель** не вигадує відповідь" would be untestable, because the model was never asked. Calling the model with an empty context is what turns the fallback into an observation about the model. |
| 8 | **Citations are inline `[chunk_id]` markers **and** a `Source:` line carrying `source_file`** | The spec asks for "chunk_id **or** source_file". Inline ids attribute each claim to the chunk it came from, which a file path cannot do at chunk granularity; the file path is what a reader actually opens. They answer different questions, and both are cheap. |
| 9 | **Citations are parsed back out of the model's own answer** and split into real vs fabricated against the ids actually supplied | The alternative — appending the retrieved ids to the answer — would make "every answer carries a citation" true by construction and worth nothing. Matching the model's markers against the supplied set measures model behaviour, and an id that was never in the context is counted as a hallucination rather than a citation. Below the floor no chunk reaches the model, so any id in a refusal is fabricated by definition. |
| 10 | **Generation feeds off the Homework #3 combined pipeline, with no retrieval knobs re-exposed at all** | The combined configuration is the one HW3 measured best (top-3 expected-document precision 0.963 vs the baseline's 0.889), so it is what a grounded answer should be built on. `--document-type`, `--no-filter` and `--no-hybrid` already exist on `retrieval_improved.py`, which owns them. A `--baseline` toggle (answer over the HW2 semantic-only layer) was built and then **deleted before delivery**: review found no rubric row, no deliverable and no evaluation consuming it — the retrieval-comparison axis was Homework #3's graded deliverable, already shipped as `outputs/retrieval_comparison.md`. Keeping it would have been the "a homework's scope ends where its spec ends" rule broken in the direction that is easiest to excuse. |
| 11 | **Each improvement case retrieves once and runs both prompt versions over the identical chunks** | Re-retrieving between the "before" and the "after" would confound the prompt change with a re-embedded query. This is why `retrieve()` and `generate()` are separate functions rather than one pipeline call. |
| 12 | **`hw4_comment`, `hw4_conclusion` and `hw4_prompt_improvements` are authored by hand after a real run** | The same two-pass discipline as HW2's relevance comments and HW3's `hw3_comment`: both `--evaluate` and `--improvements` report which entries are still empty on stderr instead of rendering a placeholder. |
| 13 | **`data/eval/test_queries.json` is extended additively — new `hw4_*` keys only** | The same ten questions carried Homework #2 and Homework #3, so reusing them makes the three homeworks one continuous evaluation and lets a reader watch a single query travel from "which chunks came back" to "what the model said about them". The existing `comment`, `hw3_comment`, `expected_documents`, `category` and `query` values are graded artifacts and are never touched — the file's own `description` field documents this per-homework additive convention, and HW4 is its third iteration. |
| 14 | **The output guard refuses to write over any committed HW2/HW3 artifact** | Same family as HW3's baseline guard. `outputs/retrieval_examples.md` and its siblings are graded; a mistyped `--output` should stop the run, not destroy a delivered homework. |

## Known limits — stated, not hidden

- **The floor is calibrated on one statistic and applied to another.** 0.35 came from Homework #2's
  **semantic top-1** distribution, but the gate reads the best cosine score among the chunks the
  **RRF-fused top-k** returned — and those are not the same number under hybrid retrieval. The
  arithmetic is unforgiving: a chunk found by both branches scores at least
  `1/(60+10) + 1/(60+10) = 0.0286`, while a chunk the semantic branch ranked **first** but BM25
  never surfaced scores `1/(60+1) = 0.0164`. Three dual-branch chunks therefore displace the
  semantic rank-1 chunk out of a `k=3` result, and the gate then judges the question on cosine
  values drawn from lower down the semantic ranking than the ones 0.35 was derived from. The
  direction of the error is toward **false refusal** — the safe direction, but a failure all the
  same, and the 0.063 margin below leaves little room for it. This is diagnosable from the
  committed artifact without re-running anything: `outputs/rag_answers_results.json` records
  `semantic_rank` for every retrieved chunk, so a record whose chunks include no `semantic_rank: 1`
  is one where the gate saw a displaced statistic. Recalibrating properly would mean measuring the
  fused-top-k cosine distribution, which needs a run this homework does not budget for.
- **The floor's margin is thin.** 0.35 sits only 0.063 below the lowest measured in-corpus top-1
  (0.413). A genuinely answerable question whose best chunk lands just under the floor would be
  refused — the failure mode is a false refusal, not a hallucination, which is the safer direction
  but is still a failure. `outputs/rag_answers_results.json` records `top_semantic_score` for every
  question precisely so a near-miss is visible rather than silent, and `--no-min-score` disables
  the gate entirely.
- **The floor reads the semantic score only.** A chunk that only BM25 surfaced carries no
  `semantic_score`, and a set of nothing but such chunks is treated as "no semantic evidence" →
  empty context. That is the honest reading of the available signal, but it means a strong lexical
  match with a weak embedding match is discarded. RRF scores are rank-based and cannot be compared
  against a cosine threshold, so there is no sound way to fold them into one number.
- **The citation parser recognises a bounded set of shapes.** It reads bracketed spans and accepts
  any token inside one that matches the `chunk_id` schema, so `[a_chunk_001]`,
  `[a_chunk_001, b_chunk_002]` and `` [`a_chunk_001`] `` all count. A model that cited in prose
  ("according to chunk a_chunk_001") would still be scored as having cited nothing. The undercount
  is conservative for the citation rate and **unsafe** for the fabricated-citation count, which is
  why the parser matches the schema shape rather than trusting the brackets.
- **Citation counting measures attribution, not correctness.** A `[chunk_id]` marker proves the
  model named a chunk it was given. It does not prove that chunk actually supports the sentence it
  is attached to. Verifying that would need either a human pass or an LLM judge, and an LLM judge
  scoring its own family's output is weak evidence.
- **Refusal detection is substring matching** on "do not have enough information". Pinning the full
  sentence would score punctuation compliance and would call a correctly-worded refusal a
  hallucination over a trailing period; matching a distinctive fragment is the looser, more honest
  test. A model that refuses in wholly different words would be miscounted as having answered.
- **Grounding is not accuracy.** Every rule here constrains where the model may take facts from.
  None of them stops it from misreading a chunk it was correctly given, and the breadcrumb prefix
  HW3 flagged (`Title > Section.` repeated on every chunk) still gives the model title vocabulary
  it may over-weight.
- **Single-turn only.** Each question is independent; a follow-up re-retrieves from scratch with no
  memory of what was already shown.

## What is deliberately not built

- **No multi-turn conversation or chat history.** The spec's pipeline is
  `question → retrieval → prompt → answer`, one turn. History would change what "grounded" means
  (grounded in the corpus, or in the earlier turn?) without the spec saying which.
- **No streaming.** It changes nothing about groundedness and would complicate capturing a complete
  answer for the committed artifacts.
- **No LLM-as-judge answer scoring.** It would produce impressive-looking numbers whose validity
  rests on the judge, and this homework's evidence is meant to be readable by a human in
  `outputs/rag_answers_examples.md`.
- **No answer caching.** Thirteen questions per run at temperature 0; an invalidation problem for
  no measurable gain.
- **No agentic re-query loop** — no "the context was thin, so retrieve again with different terms".
  That is a different system, and the honest refusal is the behaviour this homework is graded on.
- **No cross-encoder reranking and no persisted BM25 index.** Both still out of scope for the same
  reasons Homework #3 gave, and nothing in Homework #4's spec asks for either.
- **No structured/JSON output mode.** The rubric grades a readable grounded answer with a citation,
  and forcing a schema would trade the thing being graded for machine-parseability nothing consumes.
