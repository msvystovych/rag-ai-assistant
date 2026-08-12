#!/usr/bin/env python3
"""Grounded answer generation over retrieval (Homework #4): question -> chunks -> prompt -> answer.

  python scripts/rag_answer.py --query "What is a backhaul and why does it matter to a carrier?" --k 3
  python scripts/rag_answer.py --evaluate --k 3
  python scripts/rag_answer.py --improvements

The model answers only from retrieved context and says so explicitly when the context cannot
support an answer. Retrieval is the Homework #3 combined pipeline (inferred document_type filter +
hybrid BM25/RRF) — the configuration Homework #3 measured best.

Two gates produce the "I don't know" behaviour, and they are deliberately independent. The
relevance floor (--min-score) decides whether any retrieved chunk is close enough to be worth
showing the model at all; below it the context is passed EMPTY. The prompt's own refusal rule then
decides whether the context it did receive actually answers the question. Either gate alone leaves
a hole: a floor cannot tell that three on-topic chunks miss the specific fact asked for, and a
prompt rule alone never sees an empty context.

Two-pass by design, like run_test_queries.py and retrieval_improved.py: the first pass writes the
mechanical results, the per-question `hw4_comment` and the top-level `hw4_conclusion` are then
authored by hand into data/eval/test_queries.json from real output, and the second pass renders
them. Missing ones are reported, never rendered as placeholders.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from openai import OpenAIError

from rag_lib import (
    REPO_ROOT,
    Bm25Index,
    HybridHit,
    RetrievalError,
    Settings,
    infer_document_type,
    load_chunks,
    open_collection,
    search_improved,
)
from run_test_queries import CATEGORY_BLURB, DEFAULT_QUERIES, load_queries, verdict

DEFAULT_ANSWERS_OUTPUT = REPO_ROOT / "outputs" / "rag_answers_examples.md"
DEFAULT_ANSWERS_RESULTS = REPO_ROOT / "outputs" / "rag_answers_results.json"
DEFAULT_IMPROVEMENTS_OUTPUT = REPO_ROOT / "outputs" / "prompt_improvements.md"
DESIGN_DOC = "docs/homework4/generation-spec.md"

# Tuning values, single-sourced so the dataclass defaults, the function defaults and the argparse
# defaults cannot drift apart. Rationale for each: docs/homework4/generation-spec.md.
DEFAULT_K = 3
DEFAULT_MIN_SCORE = 0.35
DEFAULT_PROMPT_VERSION = "v3"
# Fixed, not a flag: the committed outputs are graded artifacts and a sampled answer would make
# them irreproducible. Greedy decoding is the only setting under which "re-run it yourself" is a
# real instruction rather than a hope.
TEMPERATURE = 0.0

INSUFFICIENT_CONTEXT_ANSWER = (
    "I do not have enough information in the available documents to answer this question."
)
# Matched instead of the full sentence: the refusal is judged by substance, not by the model
# reproducing punctuation exactly. Pinning the whole string would score formatting compliance and
# call a correct refusal a hallucination over a trailing period.
REFUSAL_MARKER = "do not have enough information"
EMPTY_CONTEXT = "(no context: no retrieved chunk cleared the relevance floor)"

# Bracketed spans first, then the ids inside them. A single-id-per-bracket regex silently dropped
# BOTH ids of a "[a_chunk_001, b_chunk_002]" citation and every backtick-wrapped id — and a dropped
# id is unsafe in the fabricated direction, where the whole point is to notice an invented source.
CITATION_SPAN = re.compile(r"\[([^\]\n]{1,400})\]")
CHUNK_ID_SHAPE = re.compile(r"^[a-z0-9_]+_chunk_[0-9]{3,}$")
PLACEHOLDER = re.compile(r"\{(context|question)\}")

# Committed Homework #2/#3 deliverables. Same family as retrieval_improved.py's baseline guard:
# an output path that lands on one of these destroys a graded artifact, so the run refuses.
PROTECTED_OUTPUTS: tuple[Path, ...] = (
    # The evaluation question set is graded HW2/HW3 work — 10 hand-authored `comment` values, 10
    # `hw3_comment` values and `hw3_conclusion`, none of them regenerable. It is the file this
    # script READS, which is exactly why an --output typo could destroy it.
    REPO_ROOT / "data" / "eval" / "test_queries.json",
    REPO_ROOT / "outputs" / "retrieval_results.json",
    REPO_ROOT / "outputs" / "retrieval_results_improved.json",
    REPO_ROOT / "outputs" / "retrieval_examples.md",
    REPO_ROOT / "outputs" / "retrieval_comparison.md",
    REPO_ROOT / "outputs" / "chunk_size_experiment.md",
)


@dataclass(frozen=True)
class PromptTemplate:
    """One version of the answering prompt.

    `system` may be empty: v1 deliberately has no system message, because the point of keeping it
    runnable is to show what the assignment's own starting prompt actually produces.
    """

    version: str
    system: str
    user_template: str
    summary: str
    adds: str


PROMPT_VERSIONS: dict[str, PromptTemplate] = {
    "v1": PromptTemplate(
        version="v1",
        system="",
        user_template=(
            "Answer the question using the context.\n"
            "Context: {context}\n"
            "Question: {question}"
        ),
        summary="the assignment's starting prompt, kept verbatim",
        adds="nothing — this is the baseline every later version is measured against",
    ),
    "v2": PromptTemplate(
        version="v2",
        system=(
            "You are a documentation assistant for a freight-exchange engineering "
            "knowledge base."
        ),
        user_template=(
            "Answer the engineer's question using only the provided context.\n"
            "If the context does not contain enough information to answer, reply with exactly "
            f'this sentence and nothing else:\n"{INSUFFICIENT_CONTEXT_ANSWER}"\n\n'
            "Context:\n{context}\n\n"
            "Question:\n{question}\n\n"
            "Answer:"
        ),
        summary="adds a role, the only-from-context rule, and an explicit refusal sentence",
        adds="role instruction · only-from-context rule · verbatim refusal sentence",
    ),
    "v3": PromptTemplate(
        version="v3",
        system=(
            "You are a documentation assistant for a freight-exchange engineering "
            "knowledge base. You answer strictly from the source material you are given, "
            "and you never fall back on general knowledge."
        ),
        user_template=(
            "Answer the engineer's question using ONLY the context below.\n\n"
            "Rules:\n"
            "1. Use only the provided context. Do not add facts from general knowledge, "
            "even when you are confident they are correct.\n"
            "2. If the context does not contain enough information to answer, reply with "
            f'exactly this sentence and nothing else:\n   "{INSUFFICIENT_CONTEXT_ANSWER}"\n'
            "3. Cite the chunk every claim came from, inline, in square brackets — for example "
            "[freight_exchange_domain_primer_chunk_018]. Use the ids exactly as they appear in "
            "the context headers. Never cite an id that is not in the context.\n"
            "4. Answer in at most five sentences. Do not restate the question.\n\n"
            "Context:\n{context}\n\n"
            "Question:\n{question}\n\n"
            "Answer:"
        ),
        summary="adds mandatory inline chunk_id citation and bans outside knowledge",
        adds="mandatory [chunk_id] citation · explicit no-outside-knowledge ban · length bound",
    ),
}


@dataclass(frozen=True)
class ImprovementCase:
    """One before/after prompt comparison.

    `tests` states what the case puts under test — chosen before the run. What actually happened
    is authored afterwards from real output, never predicted here.
    """

    case_id: str
    query_id: str
    before: str
    after: str
    tests: str


IMPROVEMENT_CASES: tuple[ImprovementCase, ...] = (
    ImprovementCase(
        case_id="case-1",
        query_id="q10",
        before="v1",
        after="v2",
        tests=(
            "Whether the model invents an answer when the corpus cannot support one. q10 asks "
            "about fine-tuning language models, which no logistics document covers."
        ),
    ),
    ImprovementCase(
        case_id="case-2",
        query_id="q01",
        before="v2",
        after="v3",
        tests=(
            "Whether the answer names the chunk it came from. q01 is the easy in-corpus case, so "
            "any difference here is attributable to the citation rule and not to weak retrieval."
        ),
    ),
    ImprovementCase(
        case_id="case-3",
        query_id="q05",
        before="v1",
        after="v3",
        tests=(
            "The cumulative effect on the hardest in-corpus question. q05 is the paraphrase whose "
            "top-3 leaked across three documents at the Homework #2 baseline, so its context is "
            "genuinely mixed and general event-sourcing knowledge is an easy substitute."
        ),
    ),
)


@dataclass(frozen=True)
class GroundedAnswer:
    question: str
    answer: str
    prompt_version: str
    answer_model: str
    hits: tuple[HybridHit, ...]
    context_used: bool
    top_semantic_score: float | None
    min_score: float | None
    cited_chunk_ids: tuple[str, ...]
    fabricated_citations: tuple[str, ...]
    refused: bool

    def source_files(self) -> tuple[str, ...]:
        """Distinct source files behind the answer — cited chunks when the model cited any.

        Empty when the context was withheld: a chunk the model never saw is not a source, and
        reporting one would attribute a refusal to documents that had no part in it.
        """
        if not self.context_used:
            return ()
        cited = set(self.cited_chunk_ids)
        chosen = [hit for hit in self.hits if hit.chunk_id in cited] or list(self.hits)
        files: list[str] = []
        for hit in chosen:
            source = str(hit.metadata.get("source_file", "?"))
            if source not in files:
                files.append(source)
        return tuple(files)


def get_template(version: str) -> PromptTemplate:
    template = PROMPT_VERSIONS.get(version)
    if template is None:
        valid = ", ".join(sorted(PROMPT_VERSIONS))
        raise RetrievalError(
            f"unknown prompt version {version!r}. Valid versions: {valid}"
        )
    return template


def render_context(hits: Sequence[HybridHit]) -> str:
    """Render retrieved chunks as the context block, headed by the id the model must cite."""
    blocks: list[str] = []
    for hit in hits:
        metadata = hit.metadata
        blocks.append(
            f"[{hit.chunk_id}]\n"
            f"source_file: {metadata.get('source_file', '?')}\n"
            f"section: {metadata.get('section', '?')}\n"
            f"{hit.text.strip()}"
        )
    return "\n\n".join(blocks)


def _fill(template: str, *, context: str, question: str) -> str:
    # Not str.format: chunk text is arbitrary prose and a stray brace in the corpus would make
    # format() raise KeyError on a value that is data, not a placeholder. And not two chained
    # str.replace calls either — the second pass would scan the text the first pass just inserted,
    # so a chunk containing the literal "{question}" would have it substituted.
    values = {"context": context, "question": question}
    return PLACEHOLDER.sub(lambda match: values[match.group(1)], template)


def build_messages(
    question: str, hits: Sequence[HybridHit], template: PromptTemplate, *, context_used: bool
) -> list[dict[str, str]]:
    context = render_context(hits) if context_used and hits else EMPTY_CONTEXT
    messages: list[dict[str, str]] = []
    if template.system:
        messages.append({"role": "system", "content": template.system})
    messages.append(
        {
            "role": "user",
            "content": _fill(template.user_template, context=context, question=question),
        }
    )
    return messages


def top_semantic_score(hits: Sequence[HybridHit]) -> float | None:
    """The best cosine score in the set, or None when no hit carries one.

    HybridHit.semantic_score is None for a chunk that only BM25 surfaced, and rrf_score is in a
    different unit entirely — so the floor is computed over the semantic scores that exist. An
    all-None set means the vector side found nothing, which is itself "no semantic evidence".
    """
    scores = [hit.semantic_score for hit in hits if hit.semantic_score is not None]
    return max(scores) if scores else None


def extract_citations(
    answer: str, hits: Sequence[HybridHit]
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Split the answer's [chunk_id] markers into (real citations, invented ones).

    The second tuple is the counter-check to "every answer carries a citation": a marker naming a
    chunk that was never in the context is not a citation, and counting it as one would grade the
    output format instead of the grounding.
    """
    supplied = {hit.chunk_id for hit in hits}
    cited: list[str] = []
    fabricated: list[str] = []
    for span in CITATION_SPAN.findall(answer):
        for token in re.split(r"[,;\s`]+", span):
            chunk_id = token.strip().strip("`'\"")
            if not CHUNK_ID_SHAPE.match(chunk_id):
                continue
            target = cited if chunk_id in supplied else fabricated
            if chunk_id not in target:
                target.append(chunk_id)
    return tuple(cited), tuple(fabricated)


def _real_client(settings: Settings) -> Any:
    # Imported lazily from rag_lib's own factory so generation builds exactly the client the
    # retrieval layer uses — same independent connect/read timeouts, same retry policy.
    from rag_lib import _openai_client

    return _openai_client(settings)


def complete(
    messages: list[dict[str, str]], settings: Settings, *, client: Any | None = None
) -> str:
    """One chat completion. `client=` is the same duck-typed seam as rag_lib.embed_texts."""
    api = client if client is not None else _real_client(settings)
    try:
        response = api.chat.completions.create(
            model=settings.answer_model,
            # chromadb-style stub narrowing: the SDK types messages as a union of TypedDicts and
            # rejects a plain list[dict[str, str]] that is valid at runtime.
            messages=messages,  # type: ignore[arg-type]
            temperature=TEMPERATURE,
        )
    except OpenAIError as exc:
        raise RetrievalError(
            f"answer generation failed for model {settings.answer_model!r}: {exc}\n"
            "If that model is not available on this account, pick another one — no code change "
            "is needed:\n"
            "  python scripts/rag_answer.py --answer-model gpt-4o-mini ...\n"
            "or set RAG_ANSWER_MODEL=gpt-4o-mini in the environment."
        ) from exc
    if not response.choices:
        # rag_lib.search names a structured absence rather than letting it surface as an
        # unrelated IndexError; the same reasoning applies to an empty choices array.
        raise RetrievalError(
            f"model {settings.answer_model!r} returned no choices for this request. Re-run, or "
            "choose another model with --answer-model / RAG_ANSWER_MODEL."
        )
    content = response.choices[0].message.content
    if content is None or not content.strip():
        raise RetrievalError(
            f"model {settings.answer_model!r} returned an empty answer. Re-run, or choose "
            "another model with --answer-model / RAG_ANSWER_MODEL."
        )
    return content.strip()


def retrieve(
    question: str,
    settings: Settings,
    *,
    k: int,
    client: Any | None = None,
    collection: Any | None = None,
    bm25: Bm25Index | None = None,
) -> list[HybridHit]:
    """Retrieve the context for `question` with the Homework #3 combined pipeline.

    That configuration measured best there (top-3 expected-document precision 0.963 against the
    Homework #2 baseline's 0.889), so it is what a grounded answer is built on. Retrieval knobs
    are deliberately not re-exposed here — retrieval_improved.py owns them.
    """
    return search_improved(
        question,
        settings,
        k=k,
        client=client,
        collection=collection,
        bm25=bm25,
        document_type=infer_document_type(question),
        hybrid=True,
    )


def generate(
    question: str,
    hits: Sequence[HybridHit],
    settings: Settings,
    *,
    client: Any | None = None,
    prompt_version: str = DEFAULT_PROMPT_VERSION,
    min_score: float | None = DEFAULT_MIN_SCORE,
) -> GroundedAnswer:
    """Turn retrieved chunks into a grounded answer. Separate from retrieve() so the improvements
    run can put two prompt versions over the SAME hits — otherwise the comparison would confound
    the prompt change with a re-embedded query."""
    template = get_template(prompt_version)
    top = top_semantic_score(hits)
    context_used = min_score is None or (top is not None and top >= min_score)
    messages = build_messages(question, hits, template, context_used=context_used)
    answer = complete(messages, settings, client=client)
    cited, fabricated = extract_citations(answer, hits if context_used else ())
    return GroundedAnswer(
        question=question,
        answer=answer,
        prompt_version=template.version,
        answer_model=settings.answer_model,
        hits=tuple(hits),
        context_used=context_used,
        top_semantic_score=top,
        min_score=min_score,
        cited_chunk_ids=cited,
        fabricated_citations=fabricated,
        refused=REFUSAL_MARKER in answer.lower(),
    )


def answer_question(
    question: str,
    settings: Settings,
    *,
    k: int = DEFAULT_K,
    client: Any | None = None,
    collection: Any | None = None,
    bm25: Bm25Index | None = None,
    prompt_version: str = DEFAULT_PROMPT_VERSION,
    min_score: float | None = DEFAULT_MIN_SCORE,
) -> GroundedAnswer:
    """The full pipeline: question -> retrieve top-k -> build prompt -> call LLM -> answer."""
    hits = retrieve(
        question,
        settings,
        k=k,
        client=client,
        collection=collection,
        bm25=bm25,
    )
    return generate(
        question,
        hits,
        settings,
        client=client,
        prompt_version=prompt_version,
        min_score=min_score,
    )


def format_chunk_list(result: GroundedAnswer) -> str:
    """The `Retrieved chunks:` value — ids first, because the spec's format contract names ids."""
    if not result.hits:
        return "(none)"
    parts = []
    for hit in result.hits:
        score = (
            f"semantic {hit.semantic_score:.3f}"
            if hit.semantic_score is not None
            else "bm25-only"
        )
        parts.append(f"{hit.chunk_id} ({score})")
    return ", ".join(parts)


def format_answer(result: GroundedAnswer) -> str:
    """Human-readable single-question output."""
    floor = (
        "disabled"
        if result.min_score is None
        else f"{result.min_score:.2f}"
    )
    top = (
        f"{result.top_semantic_score:.3f}"
        if result.top_semantic_score is not None
        else "n/a"
    )
    if result.context_used:
        context_line = (
            f"Context: {len(result.hits)} chunk(s) (top semantic {top}, floor {floor})"
        )
    elif result.top_semantic_score is None:
        context_line = "Context: none — no retrieved chunk carries a semantic score"
    else:
        context_line = f"Context: none — top semantic {top} is below the floor {floor}"
    lines = [
        f"Question: {result.question}",
        f"Prompt: {result.prompt_version} | Model: {result.answer_model}",
        context_line,
        "",
        f"Retrieved chunks: {format_chunk_list(result)}",
        "",
        f"Answer: {result.answer}",
        "",
        f"Source: {', '.join(result.source_files()) or '(none)'}",
        f"Citations: {', '.join(result.cited_chunk_ids) or '(none)'}",
    ]
    if result.fabricated_citations:
        lines.append(
            f"Fabricated citations: {', '.join(result.fabricated_citations)} "
            "— these ids were never in the context"
        )
    return "\n".join(lines)


def run_query(
    settings: Settings,
    question: str,
    k: int,
    *,
    prompt_version: str,
    min_score: float | None,
    as_json: bool,
    client: Any | None = None,
) -> int:
    # One client for both the embedding and the chat call. Passing None would let each path build
    # its own, doubling connection setup for a single question.
    api = client if client is not None else _real_client(settings)
    result = answer_question(
        question,
        settings,
        k=k,
        client=api,
        prompt_version=prompt_version,
        min_score=min_score,
    )
    if as_json:
        print(
            json.dumps(
                {
                    "question": result.question,
                    "answer": result.answer,
                    "prompt_version": result.prompt_version,
                    "answer_model": result.answer_model,
                    "context_used": result.context_used,
                    "refused": result.refused,
                    "top_semantic_score": result.top_semantic_score,
                    "min_score": result.min_score,
                    "cited_chunk_ids": list(result.cited_chunk_ids),
                    "fabricated_citations": list(result.fabricated_citations),
                    "source_files": list(result.source_files()),
                    "retrieved_chunks": [
                        {
                            "rank": hit.rank,
                            "chunk_id": hit.chunk_id,
                            "semantic_score": hit.semantic_score,
                            "rrf_score": hit.rrf_score,
                            "bm25_rank": hit.bm25_rank,
                            "source_file": hit.metadata.get("source_file", "?"),
                            "section": hit.metadata.get("section", "?"),
                        }
                        for hit in result.hits
                    ],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    print(format_answer(result))
    return 0


def guard_outputs(paths: dict[str, Path], *, reads: Path | None = None) -> None:
    """Refuse to overwrite a graded artifact, the input file, or another output.

    `reads` is the file this run is about to read. retrieval_improved.py guards its baseline the
    same way: an output routed onto the input destroys the source of the very run producing it.
    """
    protected = {path.resolve() for path in PROTECTED_OUTPUTS}
    for label, path in paths.items():
        if path.resolve() in protected:
            raise RetrievalError(
                f"{label} points at {path}, a committed Homework #2/#3 deliverable — refusing "
                "to overwrite it. Choose a different output path."
            )
        if reads is not None and path.resolve() == reads.resolve():
            raise RetrievalError(
                f"{label} points at {reads}, the question file this run reads — writing there "
                "would destroy the input mid-run. Choose a different output path."
            )
    items = [(label, path.resolve()) for label, path in paths.items()]
    for position, (label, resolved) in enumerate(items):
        for other_label, other in items[position + 1 :]:
            if resolved == other:
                raise RetrievalError(
                    f"{label} and {other_label} point at the same file — one would overwrite "
                    "the other. Choose distinct paths."
                )


def aggregates(records: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(records)
    # "not refused" is not the same as "answered from context": an answer produced from an EMPTY
    # context that failed to refuse is the hallucination this homework is measuring, so it must
    # not be counted as a grounded answer.
    grounded = [
        record
        for record in records
        if not record["refused"] and record["context_used"]
    ]
    with_citation = [record for record in grounded if record["cited_chunk_ids"]]
    return {
        "questions": total,
        "answered": len(grounded),
        "refused": sum(1 for record in records if record["refused"]),
        "answered_without_context": sum(
            1
            for record in records
            if not record["refused"] and not record["context_used"]
        ),
        "context_empty": sum(1 for record in records if not record["context_used"]),
        "answers_with_citation": len(with_citation),
        "citation_rate": round(len(with_citation) / len(grounded), 3) if grounded else 0.0,
        "fabricated_citations": sum(
            len(record["fabricated_citations"]) for record in records
        ),
    }


def render_answers_markdown(
    records: list[dict[str, Any]],
    *,
    k: int,
    settings: Settings,
    prompt_version: str,
    min_score: float | None,
    conclusion: str,
) -> str:
    totals = aggregates(records)
    floor = "disabled" if min_score is None else f"{min_score:.2f}"
    lines = [
        "# Grounded answers — Homework #4",
        "",
        f"Generated by `scripts/rag_answer.py --evaluate --k {k}`.",
        f"Answer model: `{settings.answer_model}` at temperature {TEMPERATURE:.0f} "
        f"(fixed, so these answers are reproducible). Prompt version: `{prompt_version}`.",
        f"Retrieval: the Homework #3 combined pipeline (inferred `document_type` filter + hybrid "
        f"BM25/RRF), embedded with `{settings.embedding_model}`.",
        f"Relevance floor: {floor} on the best cosine score — below it the context is passed to "
        "the model **empty**, and the prompt's refusal rule decides the rest.",
        "",
        "The question set is the same one Homework #2 and Homework #3 were measured on, so the "
        "three homeworks form one continuous evaluation: q01–q03 direct, q04–q06 paraphrased, "
        "q07–q09 cross-document, q10 out-of-corpus. Method and known limits: "
        f"[`{DESIGN_DOC}`](../{DESIGN_DOC}).",
        "",
        "---",
        "",
    ]

    for record in records:
        category = record["category"]
        lines.append(
            f"## {record['id']} · {category} — {CATEGORY_BLURB.get(category, '')}"
        )
        lines.append("")
        lines.append(f"Question: {record['query']}")
        lines.append("")
        lines.append(f"Retrieved chunks: {record['retrieved_chunks_display']}")
        lines.append("")
        lines.append(f"Answer: {record['answer']}")
        lines.append("")
        lines.append(f"Source: {record['source_display']}")
        lines.append("")
        lines.append(f"Comment: {record['hw4_comment']}")
        lines.append("")
        lines.append("---")
        lines.append("")

    lines.extend(
        [
            "## Aggregate behaviour",
            "",
            "| Measure | Value |",
            "|---|---|",
            f"| Questions | {totals['questions']} |",
            f"| Answered from context | {totals['answered']} |",
            f"| Answered despite an empty context (hallucination) | "
            f"{totals['answered_without_context']} |",
            f"| Refused (\"not enough information\") | {totals['refused']} |",
            f"| Context passed empty (below the floor) | {totals['context_empty']} |",
            f"| Answers carrying at least one citation | "
            f"{totals['answers_with_citation']} of {totals['answered']} |",
            f"| Citations naming a chunk that was never supplied | "
            f"{totals['fabricated_citations']} |",
            "",
        ]
    )
    if conclusion:
        lines.extend(["## Conclusion", "", conclusion, ""])
    return "\n".join(lines)


def run_evaluate(
    settings: Settings,
    queries_path: Path,
    output_path: Path,
    results_path: Path,
    k: int,
    *,
    prompt_version: str,
    min_score: float | None,
    client: Any | None = None,
) -> int:
    guard_outputs(
        {"--output": output_path, "--results": results_path}, reads=queries_path
    )
    queries = load_queries(queries_path)
    payload = json.loads(queries_path.read_text(encoding="utf-8"))
    conclusion = str(payload.get("hw4_conclusion", "")).strip()

    collection = open_collection(settings)
    bm25 = Bm25Index(load_chunks(settings.chunks_path))
    api = client if client is not None else _real_client(settings)

    records: list[dict[str, Any]] = []
    for entry in queries:
        result = answer_question(
            entry["query"],
            settings,
            k=k,
            client=api,
            collection=collection,
            bm25=bm25,
            prompt_version=prompt_version,
            min_score=min_score,
        )
        source_display = ", ".join(result.source_files()) or (
            "(none — retrieval returned no chunks)"
            if not result.hits
            else "(none — no chunk cleared the relevance floor)"
        )
        records.append(
            {
                "id": entry["id"],
                "category": entry["category"],
                "query": entry["query"],
                "expected_documents": entry.get("expected_documents", []),
                "verdict": verdict(result.hits, entry.get("expected_documents", [])),
                "inferred_document_type": infer_document_type(entry["query"]),
                "top_semantic_score": result.top_semantic_score,
                "context_used": result.context_used,
                "refused": result.refused,
                "answer": result.answer,
                "cited_chunk_ids": list(result.cited_chunk_ids),
                "fabricated_citations": list(result.fabricated_citations),
                "source_files": list(result.source_files()),
                "source_display": source_display,
                "retrieved_chunks_display": format_chunk_list(result),
                "retrieved_chunks": [
                    {
                        "rank": hit.rank,
                        "chunk_id": hit.chunk_id,
                        "semantic_score": hit.semantic_score,
                        "rrf_score": hit.rrf_score,
                        "bm25_rank": hit.bm25_rank,
                        "source_file": hit.metadata.get("source_file", "?"),
                        "document_id": hit.metadata.get("document_id", "?"),
                        "section": hit.metadata.get("section", "?"),
                    }
                    for hit in result.hits
                ],
                "hw4_comment": str(entry.get("hw4_comment", "")).strip(),
            }
        )
        state = "REFUSED" if result.refused else f"{len(result.cited_chunk_ids)} citation(s)"
        top = (
            f"{result.top_semantic_score:.3f}"
            if result.top_semantic_score is not None
            else "  n/a"
        )
        print(f"{entry['id']}  top {top}  {state}")

    results_path.parent.mkdir(parents=True, exist_ok=True)
    results_path.write_text(
        json.dumps(
            {
                "embedding_model": settings.embedding_model,
                "answer_model": settings.answer_model,
                "prompt_version": prompt_version,
                "temperature": TEMPERATURE,
                "min_score": min_score,
                "retrieval": "hw3-combined",
                "k": k,
                "aggregates": aggregates(records),
                "records": records,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        render_answers_markdown(
            records,
            k=k,
            settings=settings,
            prompt_version=prompt_version,
            min_score=min_score,
            conclusion=conclusion,
        ),
        encoding="utf-8",
    )
    print(f"\nwrote {results_path}")
    print(f"wrote {output_path}")

    notes: list[str] = []
    missing = [record["id"] for record in records if not record["hw4_comment"]]
    if missing:
        notes.append(
            f"{len(missing)} question(s) still have an empty hw4_comment: {', '.join(missing)}"
        )
    if not conclusion:
        notes.append("the top-level hw4_conclusion is still empty")
    if notes:
        print(
            "\nNOTE: "
            + "; ".join(notes)
            + f"\nAuthor them in {queries_path} from the real results above, then re-run.",
            file=sys.stderr,
        )
    return 0


def render_improvements_markdown(
    cases: list[dict[str, Any]], *, settings: Settings, k: int
) -> str:
    lines = [
        "# Prompt improvements — Homework #4",
        "",
        "Generated by `scripts/rag_answer.py --improvements`.",
        f"Answer model: `{settings.answer_model}` at temperature {TEMPERATURE:.0f}; "
        f"k = {k}. Every case retrieves **once** and runs both prompt versions over the same "
        "chunks, so each difference below is attributable to the prompt and not to a re-embedded "
        "query.",
        "",
        "The three prompt versions ship in `scripts/rag_answer.py` and stay runnable: "
        "`--prompt-version v1|v2|v3` reproduces any row here.",
        "",
        "| Version | What it adds |",
        "|---|---|",
    ]
    for version in ("v1", "v2", "v3"):
        template = PROMPT_VERSIONS[version]
        lines.append(f"| `{version}` | {template.adds} |")
    lines.extend(["", "---", ""])

    for case in cases:
        lines.extend(
            [
                f"## {case['case_id']} · {case['query_id']} — "
                f"`{case['before']}` → `{case['after']}`",
                "",
                f"**Under test.** {case['tests']}",
                "",
                f"Question: {case['question']}",
                "",
                f"Retrieved chunks: {case['retrieved_chunks_display']}",
                "",
                f"### Before — `{case['before']}` ({PROMPT_VERSIONS[case['before']].summary})",
                "",
                "```",
                PROMPT_VERSIONS[case["before"]].user_template,
                "```",
                "",
                f"Answer: {case['before_answer']}",
                "",
                f"Citations: {', '.join(case['before_citations']) or '(none)'}"
                + (
                    f" | fabricated: {', '.join(case['before_fabricated'])}"
                    if case["before_fabricated"]
                    else ""
                ),
                "",
                f"### After — `{case['after']}` ({PROMPT_VERSIONS[case['after']].summary})",
                "",
                "```",
                PROMPT_VERSIONS[case["after"]].user_template,
                "```",
                "",
                f"Answer: {case['after_answer']}",
                "",
                f"Citations: {', '.join(case['after_citations']) or '(none)'}"
                + (
                    f" | fabricated: {', '.join(case['after_fabricated'])}"
                    if case["after_fabricated"]
                    else ""
                ),
                "",
                "### Result",
                "",
                case["result"] or "",
                "",
                "---",
                "",
            ]
        )
    lines.append(f"Design decisions and known limits: [`{DESIGN_DOC}`](../{DESIGN_DOC}).")
    lines.append("")
    return "\n".join(lines)


def run_improvements(
    settings: Settings,
    queries_path: Path,
    output_path: Path,
    k: int,
    *,
    min_score: float | None,
    client: Any | None = None,
) -> int:
    guard_outputs({"--output": output_path}, reads=queries_path)
    queries = {entry["id"]: entry for entry in load_queries(queries_path)}
    payload = json.loads(queries_path.read_text(encoding="utf-8"))
    authored = payload.get("hw4_prompt_improvements", {})
    if not isinstance(authored, dict):
        raise RetrievalError(
            f"{queries_path}: 'hw4_prompt_improvements' must be an object keyed by case id "
            f"(case-1, case-2, …), got {type(authored).__name__}."
        )

    collection = open_collection(settings)
    bm25 = Bm25Index(load_chunks(settings.chunks_path))
    api = client if client is not None else _real_client(settings)

    cases: list[dict[str, Any]] = []
    for case in IMPROVEMENT_CASES:
        entry = queries.get(case.query_id)
        if entry is None:
            raise RetrievalError(
                f"{queries_path} has no query {case.query_id!r}, which improvement "
                f"{case.case_id} compares prompts on."
            )
        question = entry["query"]
        # Retrieved once; both prompt versions see the identical context.
        hits = retrieve(question, settings, k=k, client=api, collection=collection, bm25=bm25)
        before = generate(
            question,
            hits,
            settings,
            client=api,
            prompt_version=case.before,
            min_score=min_score,
        )
        after = generate(
            question,
            hits,
            settings,
            client=api,
            prompt_version=case.after,
            min_score=min_score,
        )
        cases.append(
            {
                "case_id": case.case_id,
                "query_id": case.query_id,
                "question": question,
                "tests": case.tests,
                "before": case.before,
                "after": case.after,
                "retrieved_chunks_display": format_chunk_list(before),
                "before_answer": before.answer,
                "before_citations": list(before.cited_chunk_ids),
                "before_fabricated": list(before.fabricated_citations),
                "before_refused": before.refused,
                "after_answer": after.answer,
                "after_citations": list(after.cited_chunk_ids),
                "after_fabricated": list(after.fabricated_citations),
                "after_refused": after.refused,
                "result": str(authored.get(case.case_id, "")).strip(),
            }
        )
        print(
            f"{case.case_id}  {case.query_id}  {case.before}→{case.after}  "
            f"citations {len(before.cited_chunk_ids)}→{len(after.cited_chunk_ids)}  "
            f"refused {before.refused}→{after.refused}"
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        render_improvements_markdown(cases, settings=settings, k=k), encoding="utf-8"
    )
    print(f"\nwrote {output_path}")

    missing = [case["case_id"] for case in cases if not case["result"]]
    if missing:
        print(
            f"\nNOTE: {len(missing)} case(s) still have an empty result write-up: "
            f"{', '.join(missing)}\n"
            f"Author them under 'hw4_prompt_improvements' in {queries_path} from the real "
            "answers above, then re-run.",
            file=sys.stderr,
        )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--query", "-q", type=str, default=None)
    parser.add_argument("--evaluate", action="store_true")
    parser.add_argument("--improvements", action="store_true")
    parser.add_argument(
        "--k",
        type=int,
        default=DEFAULT_K,
        help="committed evaluations use 3 (assignment recommends 3-5)",
    )
    parser.add_argument(
        "--prompt-version",
        type=str,
        default=DEFAULT_PROMPT_VERSION,
        choices=sorted(PROMPT_VERSIONS),
        help="prompt template version to answer with",
    )
    parser.add_argument(
        "--min-score",
        type=float,
        default=None,
        help=(
            "relevance floor on the best cosine score; below it the context is passed empty "
            f"(default {DEFAULT_MIN_SCORE})"
        ),
    )
    parser.add_argument(
        "--no-min-score",
        action="store_true",
        help="disable the floor, so the prompt's refusal rule alone decides",
    )
    parser.add_argument("--answer-model", type=str, default=None)
    parser.add_argument("--queries", type=Path, default=DEFAULT_QUERIES)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--results", type=Path, default=DEFAULT_ANSWERS_RESULTS)
    parser.add_argument("--index-dir", type=Path, default=None)
    parser.add_argument("--collection", type=str, default=None)
    parser.add_argument("--model", type=str, default=None)
    parser.add_argument("--json", dest="as_json", action="store_true")
    args = parser.parse_args(argv)

    modes = [bool(args.query), args.evaluate, args.improvements]
    if sum(modes) != 1:
        parser.error("provide exactly one of --query TEXT, --evaluate or --improvements")
    if args.k < 1:
        parser.error(f"--k must be a positive integer, got {args.k}")
    if args.min_score is not None and args.no_min_score:
        parser.error("--min-score and --no-min-score are mutually exclusive")
    if args.min_score is not None and not 0.0 <= args.min_score <= 1.0:
        # The score unit is `1 - cosine_distance`, so the bound is exact. Without this, --min-score
        # nan silently refuses every question (nan comparisons are always False) across a whole
        # graded run, and the floor renders as "nan" in the committed artifact.
        parser.error(
            f"--min-score must be between 0.0 and 1.0 (the 1 - cosine_distance range), got "
            f"{args.min_score}"
        )
    if args.improvements and args.prompt_version != DEFAULT_PROMPT_VERSION:
        parser.error(
            "--improvements compares the prompt versions named in IMPROVEMENT_CASES; "
            "--prompt-version applies to --query and --evaluate only"
        )
    if args.as_json and not args.query:
        parser.error("--json applies to --query mode only")

    min_score = (
        None
        if args.no_min_score
        else (DEFAULT_MIN_SCORE if args.min_score is None else args.min_score)
    )
    output = args.output or (
        DEFAULT_IMPROVEMENTS_OUTPUT if args.improvements else DEFAULT_ANSWERS_OUTPUT
    )

    try:
        settings = Settings.from_env(
            index_dir=args.index_dir,
            collection_name=args.collection,
            embedding_model=args.model,
            answer_model=args.answer_model,
        )
        # Fail on an unknown version before any API call rather than after the embedding spend.
        get_template(args.prompt_version)
        if args.evaluate:
            return run_evaluate(
                settings,
                args.queries,
                output,
                args.results,
                args.k,
                prompt_version=args.prompt_version,
                min_score=min_score,
            )
        if args.improvements:
            return run_improvements(
                settings, args.queries, output, args.k, min_score=min_score
            )
        return run_query(
            settings,
            args.query,
            args.k,
            prompt_version=args.prompt_version,
            min_score=min_score,
            as_json=args.as_json,
        )
    except RetrievalError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
