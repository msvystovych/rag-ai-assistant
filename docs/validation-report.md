# Validation report — specs, documents, and Simplified Technical English

Date: 2026-08-13. Base commit: `479bdec`. Test suite: 326 tests, all green.

This report answers two questions:

1. Does the code implement every requirement of the five specs in `docs/tasks/`?
2. Do the documents in `docs/` share one structure, and do they follow ASD-STE100?

The specs in `docs/tasks/` are the arbiter. This report never overrides them.

## Method

Twelve agents read the five Ukrainian specs and the repository:

- Five agents built one requirement matrix per homework.
- Five more agents re-derived each verdict and disputed weak evidence.
- One agent checked every measurable claim in the root `README.md`.
- One agent checked the `outputs/` artifacts against the format each spec shows.

Every verdict cites a file line or a command output. The audit changed no file.
The verifiers disputed six verdicts. The hub accepted five and rejected one.

Verdict values:

- **PASS** — the artifact exists, and its content meets the requirement.
- **PARTIAL** — the artifact exists, but part of the requirement is short.
- **GAP** — no artifact meets the requirement.

## Result

The five specs produce 119 checkable requirements. **0 of them are a GAP.**

| Homework | Rows | PASS | PARTIAL | GAP |
|---|---:|---:|---:|---:|
| Homework #1 — knowledge base preparation | 30 | 27 | 3 | 0 |
| Homework #2 — basic semantic retrieval layer | 21 | 21 | 0 | 0 |
| Homework #3 — improved retrieval pipeline | 17 | 17 | 0 | 0 |
| Homework #4 — grounded answer generation | 25 | 24 | 1 | 0 |
| Homework #5 — external tool integration | 26 | 26 | 0 | 0 |
| **Total** | **119** | **115** | **4** | **0** |

Every spec requirement has an implementation. Four rows are PARTIAL.
Each PARTIAL is a shortfall in a delivered artifact, not a missing artifact.
This pass fixed two of them. The § Open items section records each verdict and its evidence.

## Open items

The four PARTIAL rows collapse into three distinct defects. This pass fixed two of them.
Item 4 below is not a PARTIAL row: it records a dispute that the hub rejected, so the
reader can judge it. None of the four blocks a deliverable.

### 1. 62% of chunks open in mid-sentence (HW1 § 2, rubric row 2)

The overlap carry snaps back to a word boundary, and not to a sentence boundary.
48 of 77 chunk bodies therefore start in lower case, in mid-sentence.
The rubric grades chunks that read on their own.
Three mitigations hold: the breadcrumb prefix covers 77 of 77 chunks, no chunk
truncates a word, and no chunk ends in mid-sentence.
`docs/homework1/reflection.md` risk 3 predicted this, and the README states it.
The fix is the one that document names: snap the overlap window to a sentence boundary.

### 2. README example chunks dropped a mandatory field (HW1 § 4, rubric row 5) — FIXED

`README.md:135` and `README.md:144` reduce the metadata to four keys, plus a literal
`"…": "…"` member. Both examples drop `source_file`.
The spec lists `source_file` among the five mandatory chunk fields.
Both examples therefore fail the repo's own `docs/homework1/assets/chunk.schema.json`.
Example 1 validated clean. The count was 3, the floor of the spec's 3–5 band.

**Fixed.** The section now carries 5 examples, at the top of the band. Each one is a verbatim
line of `chunks.jsonl`, with the full 9-key metadata and the full text. The section elides nothing.
All four source documents now appear. Two examples show a property, and not only a shape:
chunk 4 is the shortest chunk in the corpus at 390 characters, and chunk 5 opens in
mid-sentence and still ranks top-1 for q02.

### 3. `outputs/prompt_improvements.md` hid the system prompt (HW4 § 4, rubric row 5) — FIXED

`PromptTemplate` carries a `system` field and a `user_template` field.
`render_improvements_markdown` writes only `user_template`.
The heading at line 54 says that v2 adds a role. The block below it shows no role.
A reader who copies the shown prompt cannot reproduce the shown answer.
The full v3 prompt, with its system line, sits in the root README, so the rubric row held.

**Fixed.** `prompt_display()` now returns the system message above the user template.
Both the before block and the after block call it.
v1 carries no system message on purpose, so v1 renders unchanged.
Two tests pin the behaviour.
A re-render from the prompt constants updated the committed artifact, and needed no model call.
4 of the 6 blocks changed. The two v1 blocks did not.

### 4. Two of five HW5 scenarios substitute the tool fields (HW5 § 3) — dispute rejected

Scenarios s3 and s5 route to the knowledge base, because the model calls no tool.
`Tool called:` then names no tool, and `Input:` carries retrieved chunk ids.
One verifier graded this PARTIAL. The hub rejected that verdict, for three reasons:

- All six keys the spec names are present in all five scenarios.
- Both scenarios carry real analysis under `Why tool is better than retrieval:`.
- s5 is the scenario that shows the model declining a tool, which § 2 asks for.

The header note at `outputs/tool_examples.md:8` still needs one line: it explains
two of the three `Input:` cases, and omits the knowledge-base route.

## Defects in the graded documents

The README claim audit checked 29 measurable claims. 21 are accurate.
The headline numbers all reproduce. They cover the 324-test count and its
74/52/77/121 split, the 77-chunk corpus, and the chunk-length statistics.
They also cover the HW3 precision progression and every HW4 and HW5 aggregate.
All 55 relative links resolve.
Every offline command in the four grading checklists runs and passes.

Seven claims are wrong. Each one is a number or a description, not a missing artifact.

| # | Location | Claim | Measured |
|---|---|---|---|
| 1 | `README.md:474` | q01/q02/q03 hold "the three highest" scores | They rank 5th, 4th and 1st. q07 and q08 outrank two of them |
| 2 | `README.md:647` | "three of the nine" sit within 0.07 of refusal | Two do. `README.md:653` states the correct figure, so the file contradicts itself |
| 3 | `README.md:464` | q10 "carries neither" a citation nor a source | q10 does carry a `Source:` line. The README's own V3 check counts 10 of them |
| 4 | `README.md:491` | q10 chunk 013 scores 0.244 | The renderer prints 0.245. `outputs/rag_answers_examples.md` shows 0.245 |
| 5 | `README.md:279` | the script prints all four figures | It prints a body statistic of 16.9%, and never the 90.9% text-length figure |
| 6 | `README.md:822` | the tool result is abridged "where marked" | Nine keys drop out of the middle with no mark |
| 7 | `README.md:488` | a verbatim console transcript | Three lines the renderer always prints are absent, with no mark |

Two hand-authored comments in `data/eval/test_queries.json` are wrong:

- The q09 HW2 comment says the top-1 chunk opens on a telematics signal.
  It opens on proof of delivery, in its first sentence.
- The q06 HW4 comment gives q10's top score as 0.26609. The committed value is 0.26611.

Both comments render into `outputs/`, so a correction needs a re-run of the
owning script. The two-pass discipline in `CLAUDE.md` § Pitfalls covers that step.

## Stale statements in `docs/`

The design documents drifted behind the code. No stale statement sits on the graded surface.
`docs/homework1/README.md:3-4` states that the graded artifact is the root README.

| Location | Statement | Current state |
|---|---|---|
| `docs/homework1/README.md:17` | "Nothing is built yet … this scores 0 / 50" | HW1 is complete. 4 documents, 77 chunks, 40 tests |
| `docs/homework1/README.md:20-27` | six rubric rows marked undelivered | All six are delivered |
| `docs/homework1/README.md:22` | "7 documents outlined" | 4 documents were authored |
| `docs/homework1/README.md:107-147` | ranked work list, plus 14 unticked boxes | The work is done |
| `docs/homework1/corpus-plan.md:102-108` | seven documents marked not written | The repo holds four. The plan dropped three |
| `docs/homework1/pipeline-spec.md:343` | the script is "Not written yet" | It is 590 lines, and 40 tests cover it |
| `docs/homework1/pipeline-spec.md:489` | "Optional tests" | `tests/test_prepare_knowledge_base.py` exists |
| `docs/homework2/analysis.md:46` | "no threshold is enforced anywhere" | HW4 enforces 0.35 at `scripts/rag_answer.py:431` |
| `docs/homework2/retrieval-spec.md:52-57` | no threshold, no hybrid BM25, no generation | HW3 and HW4 built all three |
| `docs/homework3/…-spec.md:49` | "No score threshold" | HW4 built it |
| `docs/homework4/generation-spec.md:121` | "Thirteen questions per run" | `--evaluate` runs 10, and `--improvements` runs 6 |
| `docs/homework5/…-spec.md:121` | "Six calls per `--examples` run" | The committed run records four tool calls |

The HW2 and HW3 entries need care. Each one sits under a heading that scopes it
to its own homework, and a later homework claimed the deferral on purpose.
A dated forward pointer preserves the record. A silent rewrite destroys it.

## Pre-existing defects, reported and not fixed

The verification pass found these. Each one predates this work and sits outside its scope.
A measurement backs each one. None of them rests on a suspicion.

| Location | Statement | Measured |
|---|---|---|
| `CLAUDE.md` § Code style | it lists 5 environment overrides | 6 exist. The list omits `RAG_ANSWER_MODEL`, which `Settings.from_env` reads |
| `CLAUDE.md` invariant 3 | "the remedy is always a rebuild" | The model-mismatch branch names two remedies: rebuild the index, or set `RAG_EMBEDDING_MODEL` to match |
| `docs/homework1/corpus-plan.md` sizing rule | "chunks ≈ words ÷ 10" | The same paragraph derives 650 characters per chunk and 6.5 characters per word, which gives ÷ 100. The table beside it already uses ÷ 100 |
| `docs/homework1/corpus-plan.md` estimate | the core four yield 56–72 chunks | The four documents produced 77 |
| `docs/homework3/…-spec.md` decision 8 | the compare run refuses on a model or k mismatch | It refuses on five conditions. It also refuses a missing baseline record, a baseline query-text mismatch, an output path that resolves to the baseline, and two output paths that collide |
| `docs/homework5/…-spec.md` | it cites § 2 for "orchestration layer or model" | That phrase sits in § 1 and § 4 of the assignment spec. § 2 does not carry it |
| `CLAUDE.md` HW5 note | "HW5 … changed no HW1–HW4 file" | HW5 extended `data/eval/test_queries.json` additively. The HW5 spec says "no HW1–HW4 *code* file", which is the accurate claim |
| `CLAUDE.md` § Pitfalls | "HW4's spec then claimed two of HW3's deferrals: answer generation and the score threshold" | Only the score threshold is HW3's. HW3 defers four items, and answer generation is not among them. It is HW2's deferral |
| `docs/homework1/corpus-plan.md` note on #12 | the README "writes around it", quoting "a live digital logistics platform serving 8,500+ logistics service providers across Europe" | That phrase appears nowhere in `README.md`. The claim it supports still holds: the README never names the company |
| `docs/homework1/reflection.md` risk 2 | the breadcrumb costs 40–90 characters per chunk | Breadcrumb length runs 64–104 characters, and 4 of 77 chunks exceed 90. The mean of 79 in the same row is correct |
| `docs/homework5/…-spec.md` known limits | the fixture is "either present and well formed, or absent and malformed" | The suite covers a third case: present and malformed. `test_malformed_json_is_a_diagnostic_error` pins it, in two classes |

## Document structure

Homework #3, #4 and #5 already share one template:

1. A title, a scope paragraph, and a link to the assignment spec.
2. `## Decisions` — a numbered table of decision and rationale.
3. `## Known limits — stated, not hidden`
4. `## What is deliberately not built`

Two folders deviate:

| Folder | Main design document | Deviation |
|---|---|---|
| `docs/homework1/` | `pipeline-spec.md` | Five sections, none of which matches the template |
| `docs/homework2/` | `retrieval-spec.md` | No `## Known limits` section. Three narrative sections sit at H2 |

`docs/homework1/` also holds three further documents, and `docs/homework2/` holds one.
Those documents support the design, and the template does not govern them.

## Simplified Technical English

The gate is `~/.claude/scripts/check-ste.sh`. A file passes on three conditions:

- No sentence is longer than 25 words.
- No sentence uses a word on the deny list.
- The passive count stays at 2.0 per 100 sentences or less.

Every file failed at the start. Every file passes now.

| File | Sentences | >25w before | >25w now | Passive/100 before | Passive/100 now |
|---|---:|---:|---:|---:|---:|
| `README.md` | 205 | 47 | 0 | 20.0 | 0.6 |
| `CLAUDE.md` | 124 | 17 | 0 | 9.7 | 0.0 |
| `docs/homework1/README.md` | 79 | 1 | 0 | 7.6 | 0.9 |
| `docs/homework1/corpus-plan.md` | 136 | 3 | 0 | 5.9 | 1.4 |
| `docs/homework1/pipeline-spec.md` | 117 | 22 | 0 | 12.8 | 0.0 |
| `docs/homework1/reflection.md` | 55 | 1 | 0 | 5.5 | 1.7 |
| `docs/homework2/analysis.md` | 46 | 9 | 0 | 15.2 | 0.0 |
| `docs/homework2/retrieval-spec.md` | 36 | 4 | 0 | 11.1 | 1.3 |
| `docs/homework3/retrieval-improvements-spec.md` | 53 | 6 | 0 | 5.7 | 1.2 |
| `docs/homework4/generation-spec.md` | 120 | 24 | 0 | 23.3 | 1.7 |
| `docs/homework5/tool-integration-spec.md` | 141 | 40 | 0 | 25.5 | 0.9 |

The corpus held 1,112 sentences at the start, and 174 of them ran over 25 words.
It now holds 1904 sentences. None runs over 25 words,
none uses a denied word, and the passive count stays under the 2.0 limit in every file.
The sentence count grew because the rewrite split long sentences into short ones.

Three file groups stay outside this scope, for a stated reason:

- `docs/tasks/` — the Ukrainian specs are the arbiter, and a rewrite would corrupt them.
- `data/raw/` — an edit breaks the chunks digest, and forces a paid re-embedding run.
- `outputs/` — the scripts render these files, and a hand edit drifts from its source.

## Requirement matrix

One row per checkable requirement. The section column names the spec section.

### Homework #1 — knowledge base preparation

Spec: [`docs/tasks/Домашнє завдання №1 — Підготовка knowl`](tasks/%D0%94%D0%BE%D0%BC%D0%B0%D1%88%D0%BD%D1%94%20%D0%B7%D0%B0%D0%B2%D0%B4%D0%B0%D0%BD%D0%BD%D1%8F%20%E2%84%961%20%E2%80%94%20%D0%9F%D1%96%D0%B4%D0%B3%D0%BE%D1%82%D0%BE%D0%B2%D0%BA%D0%B0%20knowl)

| ID | § | Requirement | Verdict | Evidence |
|---|---|---|---|---|
| HW1-R2-01 | § 2 | Choose a subject area for the future chatbot | PASS | `README.md:28-33` |
| HW1-R2-02 | § 2 | The topic must be narrow enough (3–10 documents) but substantive enough for real questions | PASS | `ls -la data/raw/ → 4 files: cqrs-event-sourcing-for-logistics.md, freig…` |
| HW1-R2-03 | § 2 | Collect a minimum of 3 documents in Markdown, TXT, HTML or PDF format | PASS | `ls -la data/raw/` |
| HW1-R2-04 | § 2 | Store the original source files in the folder `data/raw/` | PASS | `git ls-files data/raw` |
| HW1-R2-05 | § 2 | Split documents into chunks with chunk_size between 500 and 1000 characters | PASS | `scripts/prepare_knowledge_base.py:22 DEFAULT_CHUNK_SIZE = 800 and :25 …` |
| HW1-R2-06 | § 2 | Split documents into chunks with overlap between 100 and 200 characters | PASS | `scripts/prepare_knowledge_base.py:23 DEFAULT_OVERLAP = 150` |
| HW1-R2-07 | § 2 | Each chunk must read standalone and contain enough context | **PARTIAL** | `FOR: every one of 77 chunks carries a "<Document Title> > <Section>. "…` |
| HW1-R2-08 | § 2 | Every chunk must carry at minimum: chunk_id, document_id, source_file, chunk_index, text | PASS | `Measured over all 77 lines of data/processed/chunks.jsonl: top-level key…` |
| HW1-R2-09 | § 2 | Desirable additional metadata: title, section, language, domain, document_type | PASS | `Measured: all five optional fields present on 77/77 lines` |
| HW1-R2-10 | § 2 | Save the result to `data/processed/chunks.jsonl`, one line = one chunk | PASS | `ls -la data/processed/` |
| HW1-R3-01 | § 3 | Deliverables table: original documents → `data/raw/` | PASS | `git ls-files data/raw` |
| HW1-R3-02 | § 3 | Deliverables table: prepared script or notebook → `scripts/prepare_knowledge_base.py` or `notebooks/` | PASS | `scripts/prepare_knowledge_base.py` |
| HW1-R3-03 | § 3 | Deliverables table: processed chunks → `data/processed/chunks.jsonl` | PASS | `git ls-files data/processed` |
| HW1-R3-04 | § 3 | Deliverables table: README describing the project → `README.md` | PASS | `README.md exists at repo root, 929 lines, tracked in git` |
| HW1-R3-05 | § 3 | README must contain: the subject-area name | PASS | `README.md:28 '## Subject area'` |
| HW1-R3-06 | § 3 | README must contain: the list of sources | PASS | `README.md:35-45 '## Sources'` |
| HW1-R3-07 | § 3 | README must contain: a description of the metadata structure | PASS | `README.md:47-53 '## Metadata structure'` |
| HW1-R3-08 | § 3 | README must contain: the chunking strategy (size, overlap, method) | PASS | `README.md:55-64 '## Chunking strategy'` |
| HW1-R3-09 | § 3 | README must contain 3–5 chunk examples | PASS | `README.md:116-145 '## Example chunks'` |
| HW1-R3-10 | § 3 | README must contain a short conclusion: what went well, what needs improvement | PASS | `README.md:275-297 '## Conclusions` |
| HW1-R3-11 | § 3 | Submit as a folder or repository containing the four deliverables | PASS | `git remote -v` |
| HW1-R4-01 | § 4 | Rubric (5 pts): at least 3 sources in `data/raw/` — files present and readable | PASS | `4 files in data/raw/, all tracked, 9.6–11.9 KB each` |
| HW1-R4-02 | § 4 | Rubric (15 pts): correct chunking — size, overlap, readability; chunks not cut off and meaningful on their own | **PARTIAL** | `SIZE` |
| HW1-R4-03 | § 4 | Rubric (15 pts): complete metadata structure — chunk_id, document_id, source_file, chunk_index present | PASS | `All four required fields present on 77/77 lines` |
| HW1-R4-04 | § 4 | Rubric (5 pts): saved as JSONL — `chunks.jsonl` exists and the format is valid | PASS | `data/processed/chunks.jsonl exists` |
| HW1-R4-05 | § 4 | Rubric (5 pts): 3–5 chunk examples in the README — illustrative and commented | **PARTIAL** | `3 examples at README.md:116-145` |
| HW1-R4-06 | § 4 | Rubric (5 pts): conclusion — analysis of chunk quality, with reflection on what is good and what to improve | PASS | `README.md:275-297` |
| HW1-R5-01 | § 5 | §5 example block: each chunk is a JSON object with top-level `chunk_id` and `text`, and everything else nested under a… | PASS | `Measured over all 77 lines: top-level key set is exactly ('chunk_id','met…` |
| HW1-R5-02 | § 5 | §5 example block: the metadata object carries document_id, source_file, source_type, title, section, chunk_index, language,… | PASS | `Measured: metadata key set is exactly those 9 keys on 77/77 lines` |
| HW1-R5-03 | § 5 | §5 example block: chunk_id follows a `<document>_chunk_<NNN>` naming convention with a zero-padded index (example:… | PASS | `prepare_knowledge_base.py:373` |

### Homework #2 — basic semantic retrieval layer

Spec: [`docs/tasks/Домашнє завдання №2 — Базовий semantic retrieval layer`](tasks/%D0%94%D0%BE%D0%BC%D0%B0%D1%88%D0%BD%D1%94%20%D0%B7%D0%B0%D0%B2%D0%B4%D0%B0%D0%BD%D0%BD%D1%8F%20%E2%84%962%20%E2%80%94%20%D0%91%D0%B0%D0%B7%D0%BE%D0%B2%D0%B8%D0%B9%20semantic%20retrieval%20layer)

| ID | § | Requirement | Verdict | Evidence |
|---|---|---|---|---|
| HW2-R2-01 | § 2 | Create embeddings for ALL chunks in data/processed/chunks.jsonl | PASS | `scripts/build_index.py:27-42` |
| HW2-R2-02 | § 2 | Use a recommended embedding model: sentence-transformers/all-MiniLM-L6-v2 or OpenAI text-embedding-3-small | PASS | `scripts/rag_lib.py:38` |
| HW2-R2-03 | § 2 | Chunks and the user query must be encoded by the SAME model | PASS | `scripts/rag_lib.py:296-300` |
| HW2-R2-04 | § 2 | Persist embeddings to a local vector index. FAISS recommended; Chroma / Qdrant / NumPy matrix / pgvector listed as… | PASS | `index/chroma/chroma.sqlite3 (1,404,928 bytes) + index/chroma/de5a6df4-...…` |
| HW2-R2-05 | § 2 | The retrieval script/notebook accepts a user query (a text string) | PASS | `scripts/retrieval.py:90` |
| HW2-R2-06 | § 2 | The script creates a query embedding | PASS | `scripts/rag_lib.py:296-300` |
| HW2-R2-07 | § 2 | Search for the top-k nearest chunks, k=3-5 recommended | PASS | `scripts/retrieval.py:91` |
| HW2-R2-08 | § 2 | For each result return chunk_id, score, text preview and metadata | PASS | `scripts/rag_lib.py:184-199` |
| HW2-R2-09 | § 2 | Prepare 5-10 test queries for the chosen subject area | PASS | `data/eval/test_queries.json:33-144` |
| HW2-R2-10 | § 2 | For each query save the query, the top-k chunks, and a short relevance comment | PASS | `outputs/retrieval_examples.md:15-252` |
| HW2-R3-01 | § 3 | Deliverable: retrieval script or notebook at scripts/retrieval.py or notebooks/ | PASS | `scripts/retrieval.py` |
| HW2-R3-02 | § 3 | Deliverable: vector index or embeddings at index/faiss.index or index/ | PASS | `ls -la index/chroma/` |
| HW2-R3-03 | § 3 | Deliverable: examples of 5-10 queries with results at outputs/retrieval_examples.md | PASS | `outputs/retrieval_examples.md` |
| HW2-R3-04 | § 3 | Deliverable: an updated README.md | PASS | `README.md:149` |
| HW2-R3-05 | § 3 | outputs/retrieval_examples.md must contain, per query: `Query: ...`, `Top-1/2/3: chunk_id \| score \| text preview`, and… | PASS | `outputs/retrieval_examples.md:17 Query: What is a backhaul and why does…` |
| HW2-R4-01 | § 4 | Rubric 10 pts — the vector index exists, and it names its model | PASS | `index/chroma/manifest.json:2-9` |
| HW2-R4-02 | § 4 | Rubric (15 pts): top-k semantic search implemented — the script runs and returns chunk_id + score | PASS | `scripts/retrieval.py:42-69 run()` |
| HW2-R4-03 | § 4 | Rubric (10 pts): at least 5 queries tested, results recorded in output or a file | PASS | `data/eval/test_queries.json` |
| HW2-R4-04 | § 4 | Rubric (5 pts): metadata present in results — source_file or document_id visible | PASS | `grep -c '  Source: data/raw/' outputs/retrieval_examples.md` |
| HW2-R4-05 | § 4 | Rubric (10 pts): a short conclusion on where retrieval works well and where it works badly — real analysis, not just a list… | PASS | `docs/homework2/analysis.md:5-20 '### Where it works'` |
| HW2-R5-01 | § 5 | Rubric § 5 output shape — `Query:`, then one `Top-N` line per hit, then `Comment:` | PASS | `outputs/retrieval_examples.md:17-35 reproduces the spec's shape line for…` |

### Homework #3 — improved retrieval pipeline

Spec: [`docs/tasks/Домашнє завдання №3 — Покращення retrieval pipeline`](tasks/%D0%94%D0%BE%D0%BC%D0%B0%D1%88%D0%BD%D1%94%20%D0%B7%D0%B0%D0%B2%D0%B4%D0%B0%D0%BD%D0%BD%D1%8F%20%E2%84%963%20%E2%80%94%20%D0%9F%D0%BE%D0%BA%D1%80%D0%B0%D1%89%D0%B5%D0%BD%D0%BD%D1%8F%20retrieval%20pipeline)

| ID | § | Requirement | Verdict | Evidence |
|---|---|---|---|---|
| HW3-R2-01 | § 2 | Baseline: use the same retrieval pipeline as in HW2 | PASS | `scripts/rag_lib.py:638` |
| HW3-R2-02 | § 2 | Save the results for the same 5–10 test queries as the baseline | PASS | `MEASURED: 10 queries (spec allows 5–10). command: .venv/bin/python -c "le…` |
| HW3-R2-03 | § 2 | Add at least one metadata filter | PASS | `scripts/rag_lib.py:67-84` |
| HW3-R2-04 | § 2 | The filter must narrow the search space and improve precision | PASS | `NARROWING MEASURED: corpus 77 chunks` |
| HW3-R2-05 | § 2 | Add one additional improvement from the menu (query rewriting / query expansion / hybrid search / reranking), implemented… | PASS | `Chosen: hybrid search. scripts/rag_lib.py:492-566` |
| HW3-R2-06 | § 2 | Test the SAME 5–10 queries used in HW2 | PASS | `MEASURED: 10/10 query strings in data/eval/test_queries.json are byte-ide…` |
| HW3-R2-07 | § 2 | For each query show: baseline top result vs improved top result | PASS | `outputs/retrieval_comparison.md:15-26` |
| HW3-R3-01 | § 3 | Deliverable: updated retrieval script at scripts/retrieval_improved.py | PASS | `scripts/retrieval_improved.py` |
| HW3-R3-02 | § 3 | Deliverable: comparison results table at outputs/retrieval_comparison.md | PASS | `outputs/retrieval_comparison.md` |
| HW3-R3-03 | § 3 | Deliverable: updated README.md | PASS | `README.md:301-427` |
| HW3-R3-04 | § 3 | outputs/retrieval_comparison.md must contain a table with columns: Query \| Baseline top-1 \| Improved top-1 \| Що змінилось | PASS | `outputs/retrieval_comparison.md:15-16` |
| HW3-R4-01 | § 4 | Rubric (15 pts): metadata filtering implemented — the filter works and narrows results | PASS | `Implementation: scripts/rag_lib.py:471-489 (inference), :636 (Chroma wher…` |
| HW3-R4-02 | § 4 | Rubric (15 pts): one of the improvements (rewriting / hybrid / reranking) implemented correctly | PASS | `Hybrid search implemented end to end: scripts/rag_lib.py:492-566` |
| HW3-R4-03 | § 4 | Rubric (10 pts): baseline vs improved comparison for 5+ queries (table or side-by-side examples) | PASS | `MEASURED 10 queries (spec floor is 5): grep -c "^\| q[0-9]" outputs/retrie…` |
| HW3-R4-04 | § 4 | Rubric (10 pts): conclusion — what gave the biggest effect, with argued analysis | PASS | `outputs/retrieval_comparison.md:174-176` |
| HW3-R4-05 | § 4 | Rubric total: 50 points across the four criteria | PASS | `All four rubric rows above verified PASS with reproducible evidence` |
| HW3-R5-01 | § 5 | Rubric § 5 table shape — Query, Baseline top-1, Improved top-1, What changed | PASS | `Format matched: outputs/retrieval_comparison.md:17-26` |

### Homework #4 — grounded answer generation

Spec: [`docs/tasks/Домашнє завдання №4 — Генерація відповіді поверх retrieval`](tasks/%D0%94%D0%BE%D0%BC%D0%B0%D1%88%D0%BD%D1%94%20%D0%B7%D0%B0%D0%B2%D0%B4%D0%B0%D0%BD%D0%BD%D1%8F%20%E2%84%964%20%E2%80%94%20%D0%93%D0%B5%D0%BD%D0%B5%D1%80%D0%B0%D1%86%D1%96%D1%8F%20%D0%B2%D1%96%D0%B4%D0%BF%D0%BE%D0%B2%D1%96%D0%B4%D1%96%20%D0%BF%D0%BE%D0%B2%D0%B5%D1%80%D1%85%20retrieval)

| ID | § | Requirement | Verdict | Evidence |
|---|---|---|---|---|
| HW4-R4-01 | § 2 | The prompt must contain a role or instruction for the model | PASS | `scripts/rag_answer.py:141-147` |
| HW4-R4-02 | § 2 | The prompt must contain the rule: answer ONLY on the basis of the supplied context | PASS | `scripts/rag_answer.py:149` |
| HW4-R4-03 | § 2 | Fallback rule: if the context is insufficient, say so explicitly | PASS | `scripts/rag_answer.py:66-68` |
| HW4-R4-04 | § 2 | The prompt must require citing the source (chunk_id or source_file) | PASS | `scripts/rag_answer.py:155-157` |
| HW4-R4-05 | § 2 | Implement the pipeline: user question -> retrieve top-k chunks -> build prompt with context -> call LLM -> return grounded… | PASS | `scripts/rag_answer.py:450-477 answer_question()` |
| HW4-R4-06 | § 2 | Prepare 5-10 test questions | PASS | `MEASURED 10. command: grep -c "^Question: " outputs/rag_answers_examples.md` |
| HW4-R4-07 | § 2 | The set must include a simple question whose answer is definitely in the context | PASS | `MEASURED 3` |
| HW4-R4-08 | § 2 | The set must include a reformulated (paraphrased) question | PASS | `MEASURED 3` |
| HW4-R4-09 | § 2 | The set must include a question where the context is insufficient (fallback) | PASS | `MEASURED 1` |
| HW4-R4-10 | § 2 | The set must include a question where retrieval returns a weak chunk | PASS | `MEASURED, q06: outputs/rag_answers_results.json q06 rank-3 chunk scaling_…` |
| HW4-R4-11 | § 2 | Find 2-3 cases where the first prompt performed badly, change it, and describe the result | PASS | `MEASURED 3. command: grep -c "^## case-" outputs/prompt_improvements.md` |
| HW4-R4-12 | § 3 | Deliverable: prompt template, in the README or a separate file | PASS | `README.md:553-583` |
| HW4-R4-13 | § 3 | Deliverable: QA pipeline script or notebook at scripts/rag_answer.py or notebooks/ | PASS | `scripts/rag_answer.py exists` |
| HW4-R4-14 | § 3 | Deliverable: 5-10 questions with answers in outputs/rag_answers_examples.md | PASS | `MEASURED 10 question blocks. command: grep -c "^Question: " outputs/rag_a…` |
| HW4-R4-15 | § 3 | Deliverable: 2-3 prompt-improvement examples, in the README or outputs/ | PASS | `MEASURED 3. outputs/prompt_improvements.md` |
| HW4-R4-16 | § 3 | outputs/rag_answers_examples.md must contain, for each question, the block: Question: / Retrieved chunks: / Answer: /… | PASS | `command: for key in "Retrieved chunks: " "Answer: " "Source: " "Comment:…` |
| HW4-R4-17 | § 4 | Rubric (10 pts): prompt template with a grounded-answering rule — an explicit instruction to answer only from context | PASS | `scripts/rag_answer.py:148-162 v3.user_template` |
| HW4-R4-18 | § 4 | Rubric (15 pts): QA pipeline implemented (retrieval -> answer); the script or notebook runs | PASS | `command: .venv/bin/python scripts/rag_answer.py --help` |
| HW4-R4-19 | § 4 | Rubric (10 pts): citation or source in every answer — chunk_id or source_file present | PASS | `MEASURED 9 of 9 answered questions carry BOTH an inline [chunk_id] and a…` |
| HW4-R4-20 | § 4 | Rubric (5 pts): fallback behaviour for an empty/weak context — the model does not invent an answer | PASS | `EMPTY half, fully evidenced in the committed run: outputs/rag_answers_res…` |
| HW4-R4-21 | § 4 | Rubric (10 pts): 2-3 prompt improvements with explanation — before/after present and a description of what changed | PASS | `MEASURED 3 cases with 3 Result sections. command: grep -c "^## case-"` |
| HW4-R4-22 | § 5 | Prompt template format (§5 example): role line; answer using only the provided context; explicit refusal sentence when… | PASS | `Role` |
| HW4-R4-23 | § 5 | Output format (§6 example): Question / Retrieved chunks with per-chunk score / Answer / Source: <file path> / Comment | PASS | `outputs/rag_answers_examples.md:14-22` |
| HW4-R4-24 | § 5 | Prompt-improvement format (§7 example): the problem, the original prompt, the updated prompt, and the result | **PARTIAL** | `Problem` |
| HW4-R4-25 | § 4 | Rubric (5 pts), 'weak' half specifically: fallback when the context is weak (non-empty but insufficient) — the model must… | PASS | `The only evidence is a hand-pasted transcript, present in two places and…` |

### Homework #5 — external tool integration

Spec: [`docs/tasks/Домашнє завдання №5 — Інтеграція зовнішнього tool або джерела`](tasks/%D0%94%D0%BE%D0%BC%D0%B0%D1%88%D0%BD%D1%94%20%D0%B7%D0%B0%D0%B2%D0%B4%D0%B0%D0%BD%D0%BD%D1%8F%20%E2%84%965%20%E2%80%94%20%D0%86%D0%BD%D1%82%D0%B5%D0%B3%D1%80%D0%B0%D1%86%D1%96%D1%8F%20%D0%B7%D0%BE%D0%B2%D0%BD%D1%96%D1%88%D0%BD%D1%8C%D0%BE%D0%B3%D0%BE%20tool%20%D0%B0%D0%B1%D0%BE%20%D0%B4%D0%B6%D0%B5%D1%80%D0%B5%D0%BB%D0%B0)

| ID | § | Requirement | Verdict | Evidence |
|---|---|---|---|---|
| HW5-R2-01 | § 2 | Choose exactly one tool type from the table (API tool / SQL-NoSQL tool / file-integration tool / web-lookup tool /… | PASS | `scripts/external_tool.py:146-215` |
| HW5-R2-02 | § 2 | Tool description must state the tool's name | PASS | `command .venv/bin/python scripts/external_tool.py --list-tools` |
| HW5-R2-03 | § 2 | Tool description must state the type: read tool or write/active tool | PASS | `command --list-tools` |
| HW5-R2-04 | § 2 | Tool description must state the purpose: what it returns and which source it uses | PASS | `command --list-tools -> 'Purpose: Current live state of one load from t…` |
| HW5-R2-05 | § 2 | Tool description must state when to call the tool and when NOT to call it | PASS | `scripts/external_tool.py:154-156` |
| HW5-R2-06 | § 2 | Describe input parameters as a JSON schema or a Pydantic model | PASS | `scripts/external_tool.py:146-174` |
| HW5-R2-07 | § 2 | Describe the output structure | PASS | `scripts/external_tool.py:237-243` |
| HW5-R2-08 | § 2 | Give an example of a call | PASS | `README.md:819-839` |
| HW5-R2-09 | § 2 | Validation before execution: required fields are present | PASS | `scripts/external_tool.py:391-411` |
| HW5-R2-10 | § 2 | Validation before execution: the ID / parameter format is correct | PASS | `scripts/external_tool.py:74-77` |
| HW5-R2-11 | § 2 | Validation before execution: a write action requires confirmation | PASS | `scripts/external_tool.py:433-475` |
| HW5-R2-12 | § 2 | Validation before execution: the tool does not accept raw SQL or dangerous queries from the model | PASS | `scripts/external_tool.py:391-400` |
| HW5-R2-13 | § 2 | Prepare 3-5 examples, each with an explanation of why the tool is more useful than retrieval in that case | PASS | `command grep -c "^## s" outputs/tool_examples.md` |
| HW5-R3-01 | § 3 | Deliverable: tool implementation / wrapper at scripts/external_tool.py | PASS | `scripts/external_tool.py` |
| HW5-R3-02 | § 3 | Deliverable: tool description + call examples, in outputs/tool_examples.md or the README | PASS | `outputs/tool_examples.md:1-122` |
| HW5-R3-03 | § 3 | Deliverable: validation logic, in the code or described separately | PASS | `scripts/external_tool.py:339-476` |
| HW5-R3-04 | § 3 | outputs/tool_examples.md must contain, for EACH example, the block: 'User question:' / 'Tool called: tool_name' / 'Input:… | PASS | `command for key in 'User question: ' 'Tool called: ' 'Input: ' 'Result:…` |
| HW5-R4-01 | § 4 | Rubric 5 pts — tool described (name, type, purpose, when to call); a clear statement of what it is for | PASS | `command .venv/bin/python scripts/external_tool.py --list-tools` |
| HW5-R4-02 | § 4 | Rubric 10 pts — input/output contract defined (schema or example JSON) | PASS | `scripts/external_tool.py:146-215` |
| HW5-R4-03 | § 4 | Rubric 10 pts — validation runs; it checks the required fields and the format | PASS | `command output for all four clauses: missing_argument / invalid_load_id_f…` |
| HW5-R4-04 | § 4 | Rubric 10 pts — the tool runs; the function or the wrapper works | PASS | `command .venv/bin/python scripts/external_tool.py --list-tools` |
| HW5-R4-04b | § 4 | Rubric 10 pts (live-path half) — the end-to-end run against the real model actually works today | PASS | `README.md:766-770` |
| HW5-R4-05 | § 4 | Rubric 10 pts — 3-5 examples with a reasoned explanation of the advantage over retrieval | PASS | `command grep -c "^## s" outputs/tool_examples.md` |
| HW5-R4-06 | § 4 | Rubric 5 pts — the run shows the tool call through the model or an orchestration layer | PASS | `scripts/external_tool.py:835-959` |
| HW5-R5-01 | § 5 | Rubric § 6 output shape — User question, Tool called, Input, Result, Final answer | PASS | `outputs/tool_examples.md:16-24` |
| HW5-R5-02 | § 5 | § 5 reference implementation shape: validation runs before the lookup, and a failed validation returns a structured error… | PASS | `command python -c "dispatch(c('get_load_status',{'load_id':'FX-26-42'}),…` |

## How to reproduce this report

Run each command from the repository root:

```bash
.venv/bin/python -m pytest -q                      # 324 tests, offline
bash ~/.claude/scripts/check-ste.sh --self-test    # trust the gate first
bash ~/.claude/scripts/check-ste.sh --gate README.md CLAUDE.md docs/**/*.md
```

The README grading checklists hold the per-homework verification commands.
Each checklist command runs offline, except the ones that the README marks.

