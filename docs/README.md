# `docs/` — the engineering record

This directory holds the reasoning behind the project. It records what each homework decided, why,
and what the decision cost.

**The graded deliverable is the repo-root [`README.md`](../README.md).** Nothing in this directory
earns marks. The six assignment specs in [`tasks/`](tasks/) are the arbiter for every graded
behaviour. On any conflict between code, tests, README and spec, the spec wins.

## Start here

| You want to | Read |
|---|---|
| Understand what the project is and see the results | the repo-root [`README.md`](../README.md) |
| Change code in `scripts/` | the owning design doc — see § The homework chain |
| Know the rules for chunking `data/raw/` | [`homework1/pipeline-spec.md`](homework1/pipeline-spec.md) |
| Know how retrieval ranks and why | [`homework2/retrieval-spec.md`](homework2/retrieval-spec.md), then [`homework2/analysis.md`](homework2/analysis.md) |
| Judge how honest the claims are | each doc's § Known limits, then [`validation-report.md`](validation-report.md) |
| Start Homework #7 | § Conventions below, then the newest spec as a model |

## The homework chain

Each homework builds on the one before it. Each design doc is the **sole owner** of its layer's
rules. Read the owning doc before you change its code.

| HW | Design doc | It owns | Code it governs | Assignment spec |
|---|---|---|---|---|
| 1 | [`homework1/pipeline-spec.md`](homework1/pipeline-spec.md) | every chunking rule and the chunk contract | `scripts/prepare_knowledge_base.py` | [№1](tasks/Домашнє%20завдання%20№1%20—%20Підготовка%20knowl) |
| 2 | [`homework2/retrieval-spec.md`](homework2/retrieval-spec.md) | the basic semantic layer | `rag_lib.py` (`Settings`, `embed_texts`, `search`), `retrieval.py` | [№2](tasks/Домашнє%20завдання%20№2%20—%20Базовий%20semantic%20retrieval%20layer) |
| 3 | [`homework3/retrieval-improvements-spec.md`](homework3/retrieval-improvements-spec.md) | filtering, hybrid BM25 and RRF | `rag_lib.py` (`infer_document_type`, `Bm25Index`, `rrf_fuse`, `search_improved`), `retrieval_improved.py` | [№3](tasks/Домашнє%20завдання%20№3%20—%20Покращення%20retrieval%20pipeline) |
| 4 | [`homework4/generation-spec.md`](homework4/generation-spec.md) | prompts, the relevance floor, citations | `rag_answer.py`, plus `Settings.answer_model` | [№4](tasks/Домашнє%20завдання%20№4%20—%20Генерація%20відповіді%20поверх%20retrieval) |
| 5 | [`homework5/tool-integration-spec.md`](homework5/tool-integration-spec.md) | the tool contract and the confirmation gate | `scripts/external_tool.py` | [№5](tasks/Домашнє%20завдання%20№5%20—%20Інтеграція%20зовнішнього%20tool%20або%20джерела) |
| 6 | [`homework6/agent-flow-spec.md`](homework6/agent-flow-spec.md) | the router's rules, the plans, and the state | `scripts/agent_flow.py` | [№6](tasks/Домашнє%20завдання%20№6%20—%20Перша%20agentic-структура) |

## Directory map

```
docs/
├── README.md                  this index
├── validation-report.md       a dated audit of the specs against the code
├── tasks/                     the six Ukrainian assignment specs — the arbiter
├── homework1/                 knowledge-base preparation
│   ├── README.md              the folder index and the HW1 status record
│   ├── corpus-plan.md         the source documents, and the sanitization rules
│   ├── pipeline-spec.md       the chunking rules and the chunk contract
│   ├── reflection.md          the risk register behind the README Conclusions
│   └── assets/                the JSON Schema, and a hand-written shape fixture
├── homework2/                 basic semantic retrieval
│   ├── retrieval-spec.md      the design decisions
│   └── analysis.md            where retrieval works, and where it fails
├── homework3/                 improved retrieval
├── homework4/                 grounded answer generation
├── homework5/                 external tool integration
└── homework6/                 the deterministic agent workflow
```

The results these documents reason about live in `outputs/`. The scripts render those files, so a
hand edit drifts from its source.

## Conventions

Every homework design doc from #2 onward carries the same four parts. Follow the shape when you add
Homework #7. Homework #1's [`pipeline-spec.md`](homework1/pipeline-spec.md) predates the shape. It
keeps its own section set, and it carries parts 3 and 4.

1. **A title, a scope paragraph, and a link to the assignment spec.** The scope paragraph names the
   previous homework's doc, and states what this layer adds on top of it.
2. **`## Decisions`** — one numbered entry per decision, each with its rationale.
3. **`## Known limits — stated, not hidden`** — what the layer does badly, measured. Production code
   and the root README both reference this heading by name. Keep the wording.
4. **`## What is deliberately not built`** — the absences, and the reason for each. A later homework
   that claims a deferral adds a dated forward pointer. It never rewrites the original entry.

Three further rules hold across every document here.

- **One owner per rule.** A rule about size, overlap, filtering or prompting lives in exactly one
  document. Every other mention is a copy. Change the owner first.
- **Report the number, never the hope.** These documents carry measured results, and they name the
  cases where a mitigation failed. Do not soften an admission into a claim.
- **Hand-authored commentary follows a real run.** The evaluation scripts name every empty entry on
  stderr, and refuse to render a placeholder.

## Reports

[`validation-report.md`](validation-report.md) checks the code against the first five specs. It is a
**dated snapshot**, not a live document. It records the state at its own base commit. Read its date
line first, then treat every present-tense finding as a statement about that commit.
