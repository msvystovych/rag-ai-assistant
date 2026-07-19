# Decisions

Two authority levels. The first table is settled with the user; the second was resolved during
planning and may be revisited if you disagree — but change it in **one** place and propagate.

## User-confirmed — do not revisit

| # | Decision | Detail |
|---|---|---|
| 1 | **Subject area** | Logistics-Domain Engineering Assistant — a chatbot answering freight-exchange / logistics-platform engineering questions. **Not** a career or recruiter bot. |
| 2 | **Session scope** | Ideas and blueprint only. The user authors the actual source documents personally, later. |
| 3 | **Stack** | All-Python, minimal dependencies. For HW1 this resolves to **stdlib only**; LangChain / LlamaIndex remain acceptable in later homeworks. |
| 4 | **Language** | All output in English. |

## Resolved during planning — revisitable

| # | Decision | Rationale |
|---|---|---|
| 5 | Target `chunk_size` = **800**, not 900 | Specialist drafts disagreed; 800 leaves ~200 chars of headroom under the 1000 cap for the breadcrumb prefix. See [`05-chunking-strategy.md`](05-chunking-strategy.md). |
| 6 | `chunk_index` is **1-based** | Matches the spec's own sample (`chunk_index: 1` ↔ `..._chunk_001`). |
| 7 | `document_type` vocabulary | `concept-guide` · `architecture-guide` · `case-study` · `playbook`. The enum in [`assets/chunk.schema.json`](assets/chunk.schema.json) is the single source of truth. |
| 8 | Sample-chunk `document_id`s follow the real document filenames | Keeps `assets/` internally consistent with `assets/document-set.json`. |
| 9 | Corpus is **100% self-authored Markdown** | Therefore the loader is markdown-only by design — no HTML/PDF/TXT readers for inputs that cannot occur. |

## Why stdlib only

LangChain would add roughly a hundred transitive dependencies to replicate a splitter that fits in
well under a hundred lines. For a graded script the author must be able to explain line by line,
that is a poor trade. If a non-Markdown source ever genuinely lands in `data/raw/`, add the
matching reader then — not speculatively.

---

Related: [`02-approved-facts.md`](02-approved-facts.md) constrains *what* may be written;
this file constrains *how* the pipeline behaves.
