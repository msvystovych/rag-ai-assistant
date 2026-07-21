#!/usr/bin/env python3
"""Build data/processed/chunks.jsonl from the Markdown corpus in data/raw/.

Implements docs/homework1/pipeline-spec.md, which is the sole owner of every splitting rule,
every chunk field, and the merge policy. Standard library only.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

SEPARATORS = ["\n\n", "\n", ". ", " "]
DOCUMENT_TYPES = frozenset({"concept-guide", "architecture-guide", "case-study", "playbook"})
LANGUAGE = "en"
DOMAIN = "logistics-engineering"
SOURCE_TYPE = "markdown"
INTRODUCTION = "Introduction"

_FRONT_MATTER_RE = re.compile(r"\A---[ \t]*\n(.*?)\n---[ \t]*(?:\n|\Z)", re.DOTALL)
_HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
_HEADING_RE = re.compile(r"^(#{1,3})\s+(.*?)\s*#*\s*$")
_FENCE_RE = re.compile(r"^\s*(```|~~~)")
_MIN_CARRY_MATCH = 20


class PipelineError(Exception):
    """A condition that must stop the run with a diagnostic, never a silent empty result."""


@dataclass(frozen=True)
class Config:
    raw_dir: Path
    out_path: Path
    chunk_size: int = 800
    overlap: int = 150
    min_chunk: int = 500
    hard_cap: int = 1000
    dry_run: bool = False
    verbose: bool = False


@dataclass(frozen=True)
class Doc:
    document_id: str
    source_file: str
    source_type: str
    title: str
    language: str
    domain: str
    document_type: str
    sections: list[tuple[str, str]]


@dataclass
class Piece:
    section: str
    text: str
    first_in_section: bool
    merged: bool = False


@dataclass
class ValidationReport:
    docs: int = 0
    chunks: int = 0
    len_min: int = 0
    len_avg: float = 0.0
    len_max: int = 0
    per_doc: dict[str, int] = field(default_factory=dict)
    body_len_min: int = 0
    body_len_max: int = 0
    short_bodies: list[tuple[str, int]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def discover_raw_files(raw_dir: Path) -> list[Path]:
    if not raw_dir.is_dir():
        raise PipelineError(f"raw directory not found: {raw_dir}")
    files = sorted(raw_dir.glob("*.md"), key=lambda p: p.name)
    if len(files) < 3:
        raise PipelineError(
            f"found {len(files)} Markdown file(s) in {raw_dir}; the assignment requires at least 3"
        )
    return files


def strip_front_matter(text: str) -> tuple[str, dict[str, str]]:
    match = _FRONT_MATTER_RE.match(text)
    if match is None:
        raise PipelineError("missing YAML front-matter")
    meta: dict[str, str] = {}
    for line in match.group(1).splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, sep, value = line.partition(":")
        if not sep:
            raise PipelineError(f"malformed front-matter line: {line!r}")
        meta[key.strip()] = value.strip().strip("\"'")
    return text[match.end() :], meta


def normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFC", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _HTML_COMMENT_RE.sub("", text)
    text = "\n".join(line.rstrip() for line in text.split("\n"))
    return re.sub(r"\n{3,}", "\n\n", text)


def read_markdown(text: str) -> tuple[str, list[tuple[str, str]]]:
    title = ""
    sections: list[tuple[str, list[str]]] = []
    current = INTRODUCTION
    buffer: list[str] = []
    in_fence = False

    def flush() -> None:
        body = "\n".join(buffer).strip()
        if body:
            sections.append((current, body))
        buffer.clear()

    for line in text.split("\n"):
        if _FENCE_RE.match(line):
            in_fence = not in_fence
            buffer.append(line)
            continue
        heading = None if in_fence else _HEADING_RE.match(line)
        if heading is None:
            buffer.append(line)
            continue
        level, heading_text = len(heading.group(1)), heading.group(2).strip()
        if level == 1 and not title:
            flush()
            title = heading_text
            current = INTRODUCTION
            continue
        flush()
        current = heading_text
    flush()

    return title, [(name, body) for name, body in sections]


def load_document(path: Path) -> Doc:
    raw = path.read_text(encoding="utf-8")
    if not raw.strip():
        raise PipelineError(f"{path}: file is empty")

    try:
        body, front_matter = strip_front_matter(raw)
    except PipelineError as exc:
        raise PipelineError(f"{path}: {exc}") from exc

    document_type = front_matter.get("document_type", "")
    if not document_type:
        raise PipelineError(f"{path}: front-matter has no 'document_type'")
    if document_type not in DOCUMENT_TYPES:
        raise PipelineError(
            f"{path}: document_type {document_type!r} is outside the schema enum "
            f"{sorted(DOCUMENT_TYPES)}"
        )

    title, sections = read_markdown(normalize_text(body))
    document_id = re.sub(r"[^a-z0-9]+", "_", path.stem.lower()).strip("_")
    if not document_id:
        raise PipelineError(f"{path}: filename yields an empty document_id")
    if not sections:
        raise PipelineError(f"{path}: no content sections found")
    if not title:
        title = path.stem.replace("-", " ").replace("_", " ").title()

    return Doc(
        document_id=document_id,
        source_file=f"data/raw/{path.name}",
        source_type=SOURCE_TYPE,
        title=title,
        language=LANGUAGE,
        domain=DOMAIN,
        document_type=document_type,
        sections=sections,
    )


def _split_atoms(text: str, max_chars: int, separators: list[str]) -> list[str]:
    if len(text) <= max_chars:
        return [text]
    if not separators:
        return [text[i : i + max_chars] for i in range(0, len(text), max_chars)]

    separator, rest = separators[0], separators[1:]
    parts = text.split(separator)
    atoms: list[str] = []
    for index, part in enumerate(parts):
        piece = part + separator if index < len(parts) - 1 else part
        if not piece:
            continue
        if len(piece) <= max_chars:
            atoms.append(piece)
        else:
            atoms.extend(_split_atoms(piece, max_chars, rest))
    return atoms


def _overlap_tail(text: str, overlap: int, budget: int) -> str:
    """Tail of `text` for the next piece's inbound carry, snapped so it never starts mid-word."""
    allowance = min(overlap, budget)
    if allowance <= 0 or not text:
        return ""
    tail = text[-allowance:]
    if len(tail) < len(text):
        boundary = tail.find(" ")
        if boundary == -1:
            return ""
        tail = tail[boundary + 1 :]
    return tail


def split_section(body: str, max_chars: int = 800, overlap: int = 150) -> list[str]:
    body = body.strip()
    if not body:
        return []
    if len(body) <= max_chars:
        return [body]

    atoms = _split_atoms(body, max_chars, SEPARATORS)
    pieces: list[str] = []
    current = ""
    for atom in atoms:
        if not current:
            current = atom
        elif len(current) + len(atom) <= max_chars:
            current += atom
        else:
            pieces.append(current.strip())
            carry = _overlap_tail(current, overlap, max_chars - len(atom))
            current = carry + atom if carry else atom
    if current.strip():
        pieces.append(current.strip())
    return pieces


def _strip_carry(previous: str, following: str, overlap: int) -> str:
    """Remove the leading overlap carry from `following` when it repeats `previous`'s tail."""
    limit = min(len(previous), len(following), overlap + 10)
    for length in range(limit, _MIN_CARRY_MATCH - 1, -1):
        if previous.endswith(following[:length]):
            return following[length:].lstrip()
    return following


def merge_short(pieces: list[Piece], min_chars: int, cap: int, overlap: int) -> list[Piece]:
    """Merge any undersized piece backward into its predecessor while the result fits under `cap`.

    One rule, one direction: a within-section tail, a whole short section, and a document's final
    piece are handled identically. A document's first piece has no predecessor and is never merged.
    """
    merged: list[Piece] = []
    for piece in pieces:
        if merged and len(piece.text) < min_chars:
            previous = merged[-1]
            if piece.first_in_section:
                body, separator = piece.text, "\n\n"
            else:
                body, separator = _strip_carry(previous.text, piece.text, overlap), " "
            candidate = f"{previous.text}{separator}{body}" if body else previous.text
            if len(candidate) <= cap:
                previous.text = candidate
                previous.merged = True
                continue
        merged.append(piece)
    return merged


def _breadcrumb(title: str, section: str) -> str:
    return f"{title} > {section}. "


def chunk_document(doc: Doc, cfg: Config) -> list[dict[str, object]]:
    pieces: list[Piece] = []
    for section, body in doc.sections:
        for index, text in enumerate(split_section(body, cfg.chunk_size, cfg.overlap)):
            pieces.append(Piece(section=section, text=text, first_in_section=index == 0))

    longest_breadcrumb = max(
        (len(_breadcrumb(doc.title, section)) for section, _ in doc.sections), default=0
    )
    cap = cfg.hard_cap - longest_breadcrumb
    if cap < cfg.chunk_size:
        raise PipelineError(
            f"{doc.source_file}: longest breadcrumb is {longest_breadcrumb} chars, leaving only "
            f"{cap} for the body; shorten the H1 title or a section heading"
        )

    chunks: list[dict[str, object]] = []
    for index, piece in enumerate(merge_short(pieces, cfg.min_chunk, cap, cfg.overlap), start=1):
        chunks.append(
            {
                "chunk_id": f"{doc.document_id}_chunk_{index:03d}",
                "text": _breadcrumb(doc.title, piece.section) + piece.text,
                "metadata": {
                    "document_id": doc.document_id,
                    "source_file": doc.source_file,
                    "source_type": doc.source_type,
                    "title": doc.title,
                    "section": piece.section,
                    "chunk_index": index,
                    "language": doc.language,
                    "domain": doc.domain,
                    "document_type": doc.document_type,
                },
            }
        )
    return chunks


def write_jsonl(chunks: list[dict[str, object]], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = out_path.with_suffix(out_path.suffix + ".tmp")
    payload = "".join(json.dumps(chunk, ensure_ascii=False) + "\n" for chunk in chunks)
    temp_path.write_text(payload, encoding="utf-8")
    os.replace(temp_path, out_path)


def validate(out_path: Path, cfg: Config) -> ValidationReport:
    report = ValidationReport()
    seen_ids: set[str] = set()
    per_doc_indices: dict[str, list[int]] = {}
    text_lengths: list[int] = []
    body_lengths: list[int] = []

    for line_number, line in enumerate(out_path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            report.errors.append(f"line {line_number}: invalid JSON ({exc.msg})")
            continue

        metadata = row.get("metadata") or {}
        for name, value in (
            ("chunk_id", row.get("chunk_id")),
            ("text", row.get("text")),
            ("document_id", metadata.get("document_id")),
            ("source_file", metadata.get("source_file")),
            ("chunk_index", metadata.get("chunk_index")),
        ):
            if value is None or value == "":
                report.errors.append(f"line {line_number}: missing field {name}")

        chunk_id = row.get("chunk_id", "")
        if chunk_id in seen_ids:
            report.errors.append(f"duplicate chunk_id: {chunk_id}")
        seen_ids.add(chunk_id)

        document_id = metadata.get("document_id", "")
        per_doc_indices.setdefault(document_id, []).append(metadata.get("chunk_index", -1))

        text = row.get("text", "")
        text_lengths.append(len(text))
        if len(text) > cfg.hard_cap:
            report.errors.append(f"{chunk_id}: text {len(text)} chars exceeds {cfg.hard_cap}")

        breadcrumb = _breadcrumb(metadata.get("title", ""), metadata.get("section", ""))
        body_length = len(text) - len(breadcrumb) if text.startswith(breadcrumb) else len(text)
        body_lengths.append(body_length)
        if body_length < cfg.min_chunk:
            report.short_bodies.append((chunk_id, body_length))
            report.warnings.append(f"{chunk_id}: {body_length}-char residual (merge policy)")

    for document_id, indices in per_doc_indices.items():
        if sorted(indices) != list(range(1, len(indices) + 1)):
            report.errors.append(f"{document_id}: chunk_index is not contiguous 1..{len(indices)}")

    report.docs = len(per_doc_indices)
    report.chunks = len(text_lengths)
    report.per_doc = {doc_id: len(idx) for doc_id, idx in sorted(per_doc_indices.items())}
    if text_lengths:
        report.len_min = min(text_lengths)
        report.len_max = max(text_lengths)
        report.len_avg = sum(text_lengths) / len(text_lengths)
    if body_lengths:
        report.body_len_min = min(body_lengths)
        report.body_len_max = max(body_lengths)
    return report


def _print_summary(report: ValidationReport, cfg: Config) -> None:
    print(f"documents : {report.docs}")
    print(f"chunks    : {report.chunks}")
    for document_id, count in report.per_doc.items():
        print(f"  {document_id}: {count}")
    print(
        f"text len  : min {report.len_min} / avg {report.len_avg:.1f} / max {report.len_max} "
        f"(hard cap {cfg.hard_cap})"
    )
    print(f"body len  : min {report.body_len_min} / max {report.body_len_max}")
    residuals = len(report.short_bodies)
    share = (residuals / report.chunks * 100) if report.chunks else 0.0
    print(f"sub-{cfg.min_chunk} bodies: {residuals} ({share:.1f}%) — reported, not padded")
    if cfg.verbose:
        for chunk_id, length in report.short_bodies:
            print(f"  residual {chunk_id}: {length} chars")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-dir", type=Path, default=Path("data/raw"))
    parser.add_argument("--out", dest="out_path", type=Path, default=Path("data/processed/chunks.jsonl"))
    parser.add_argument("--chunk-size", type=int, default=800)
    parser.add_argument("--overlap", type=int, default=150)
    parser.add_argument("--min-chunk", type=int, default=500)
    parser.add_argument("--hard-cap", type=int, default=1000)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)

    cfg = Config(
        raw_dir=args.raw_dir,
        out_path=args.out_path,
        chunk_size=args.chunk_size,
        overlap=args.overlap,
        min_chunk=args.min_chunk,
        hard_cap=args.hard_cap,
        dry_run=args.dry_run,
        verbose=args.verbose,
    )

    try:
        paths = discover_raw_files(cfg.raw_dir)
        chunks: list[dict[str, object]] = []
        for path in paths:
            document_chunks = chunk_document(load_document(path), cfg)
            if not document_chunks:
                raise PipelineError(f"{path}: produced zero chunks")
            chunks.extend(document_chunks)
    except PipelineError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if cfg.dry_run:
        print(f"dry run: {len(chunks)} chunks from {len(paths)} documents (nothing written)")
        return 0

    write_jsonl(chunks, cfg.out_path)
    report = validate(cfg.out_path, cfg)
    _print_summary(report, cfg)

    if report.errors:
        print("\nvalidation FAILED:", file=sys.stderr)
        for error in report.errors:
            print(f"  {error}", file=sys.stderr)
        return 1

    print(f"\nwrote {cfg.out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
