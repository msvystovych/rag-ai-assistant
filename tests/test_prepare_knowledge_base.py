"""Invariants for the Homework #1 chunking pipeline (docs/homework1/pipeline-spec.md)."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from prepare_knowledge_base import (  # noqa: E402
    Config,
    Piece,
    PipelineError,
    chunk_document,
    discover_raw_files,
    load_document,
    main,
    merge_short,
    normalize_text,
    read_markdown,
    split_section,
    strip_front_matter,
)

FRONT_MATTER = "---\ndocument_type: concept-guide\n---\n\n"


def make_document(path: Path, *, sections: dict[str, str], title: str = "Test Title") -> Path:
    body = "".join(f"## {name}\n\n{text}\n\n" for name, text in sections.items())
    path.write_text(f"{FRONT_MATTER}# {title}\n\n{body}", encoding="utf-8")
    return path


def sentences(count: int, marker: str = "word") -> str:
    return " ".join(f"This is {marker} sentence number {i} in the body." for i in range(count))


class TestFrontMatter:
    def test_parses_document_type(self) -> None:
        body, meta = strip_front_matter(f"{FRONT_MATTER}# Title\n")
        assert meta["document_type"] == "concept-guide"
        assert body.lstrip().startswith("# Title")

    def test_missing_front_matter_is_an_error(self) -> None:
        with pytest.raises(PipelineError, match="missing YAML front-matter"):
            strip_front_matter("# Title\n\nBody.\n")

    def test_unknown_document_type_is_an_error(self, tmp_path: Path) -> None:
        path = tmp_path / "doc.md"
        path.write_text("---\ndocument_type: novel\n---\n\n# T\n\n## S\n\nBody.\n", encoding="utf-8")
        with pytest.raises(PipelineError, match="outside the schema enum"):
            load_document(path)

    def test_empty_file_is_an_error(self, tmp_path: Path) -> None:
        path = tmp_path / "empty.md"
        path.write_text("   \n", encoding="utf-8")
        with pytest.raises(PipelineError, match="file is empty"):
            load_document(path)


class TestNormalization:
    def test_collapses_blank_lines_and_strips_comments(self) -> None:
        result = normalize_text("a\r\n\n\n\n<!-- gone -->b   \n")
        assert "<!--" not in result
        assert "\n\n\n" not in result
        assert "\r" not in result

    def test_trailing_spaces_removed(self) -> None:
        assert normalize_text("line   \nnext  \n") == "line\nnext\n"


class TestSectionDerivation:
    def test_h1_is_title_and_body_before_h2_is_introduction(self) -> None:
        title, sections = read_markdown("# Doc Title\n\nOpening prose.\n\n## First\n\nBody.\n")
        assert title == "Doc Title"
        assert sections[0][0] == "Introduction"
        assert sections[1][0] == "First"

    def test_section_is_never_the_title(self) -> None:
        _, sections = read_markdown("# Doc Title\n\n## A\n\nBody.\n")
        assert all(name != "Doc Title" for name, _ in sections)

    def test_headings_inside_code_fences_are_ignored(self) -> None:
        _, sections = read_markdown("# T\n\n## Real\n\n```\n## Not A Heading\n```\n\nBody.\n")
        assert [name for name, _ in sections] == ["Real"]


class TestSplitSection:
    def test_short_section_is_one_piece(self) -> None:
        assert split_section("Short body.", 800, 150) == ["Short body."]

    def test_pieces_respect_max_chars(self) -> None:
        for piece in split_section(sentences(200), 800, 150):
            assert len(piece) <= 800

    def test_never_splits_mid_word(self) -> None:
        for piece in split_section(sentences(200), 800, 150):
            assert not re.match(r"^\S", piece) or piece[0].isalnum() or piece[0] in ".,\"'("
            assert piece == piece.strip()

    def test_consecutive_pieces_share_overlap(self) -> None:
        pieces = split_section(sentences(200), 800, 150)
        assert len(pieces) > 1
        for earlier, later in zip(pieces, pieces[1:]):
            assert any(earlier.endswith(later[:length]) for length in range(20, 261))


class TestMergeShort:
    def test_undersized_piece_merges_backward(self) -> None:
        pieces = [Piece("S", "x" * 600, True), Piece("S", "y" * 100, False)]
        merged = merge_short(pieces, min_chars=500, cap=1000, overlap=150)
        assert len(merged) == 1
        assert merged[0].merged is True

    def test_first_piece_is_never_merged(self) -> None:
        pieces = [Piece("S", "x" * 100, True), Piece("S", "y" * 600, False)]
        merged = merge_short(pieces, min_chars=500, cap=1000, overlap=150)
        assert len(merged) == 2
        assert merged[0].text == "x" * 100

    def test_merge_is_refused_when_it_would_breach_the_cap(self) -> None:
        pieces = [Piece("S", "x" * 900, True), Piece("S", "y" * 200, False)]
        merged = merge_short(pieces, min_chars=500, cap=1000, overlap=150)
        assert len(merged) == 2

    def test_merged_chunk_keeps_the_predecessor_section_name(self) -> None:
        pieces = [Piece("First", "x" * 600, True), Piece("Second", "y" * 100, True)]
        merged = merge_short(pieces, min_chars=500, cap=1000, overlap=150)
        assert merged[0].section == "First"

    def test_within_section_merge_strips_the_overlap_carry(self) -> None:
        tail = "the shared overlap region that repeats across the boundary"
        pieces = [Piece("S", "a" * 500 + tail, True), Piece("S", tail + " plus new text.", False)]
        merged = merge_short(pieces, min_chars=500, cap=2000, overlap=150)
        assert merged[0].text.count(tail) == 1


class TestChunkDocument:
    def test_ids_indices_and_ceiling(self, tmp_path: Path) -> None:
        path = make_document(tmp_path / "sample-doc.md", sections={"Alpha": sentences(300)})
        chunks = chunk_document(load_document(path), Config(tmp_path, tmp_path / "o.jsonl"))

        assert [c["metadata"]["chunk_index"] for c in chunks] == list(range(1, len(chunks) + 1))
        assert [c["chunk_id"] for c in chunks] == [
            f"sample_doc_chunk_{i:03d}" for i in range(1, len(chunks) + 1)
        ]
        assert all(len(c["text"]) <= 1000 for c in chunks)

    def test_breadcrumb_prefix_is_present(self, tmp_path: Path) -> None:
        path = make_document(tmp_path / "doc-one.md", sections={"Alpha": sentences(30)}, title="T")
        chunks = chunk_document(load_document(path), Config(tmp_path, tmp_path / "o.jsonl"))
        assert chunks[0]["text"].startswith("T > Alpha. ")

    def test_overlong_breadcrumb_is_a_diagnostic_error(self, tmp_path: Path) -> None:
        path = make_document(
            tmp_path / "long.md", sections={"S" * 400: sentences(30)}, title="T" * 400
        )
        with pytest.raises(PipelineError, match="breadcrumb"):
            chunk_document(load_document(path), Config(tmp_path, tmp_path / "o.jsonl"))


class TestDiscovery:
    def test_fewer_than_three_documents_is_an_error(self, tmp_path: Path) -> None:
        make_document(tmp_path / "a.md", sections={"S": sentences(20)})
        with pytest.raises(PipelineError, match="at least 3"):
            discover_raw_files(tmp_path)

    def test_colliding_document_ids_are_detected(self, tmp_path: Path) -> None:
        out = tmp_path / "out.jsonl"
        for name in ("a-b.md", "a_b.md", "c-d.md"):
            make_document(tmp_path / name, sections={"S": sentences(20)})
        exit_code = main(["--raw-dir", str(tmp_path), "--out", str(out)])
        assert exit_code == 1, "a-b.md and a_b.md both normalize to a_b — must not merge silently"


class TestEndToEnd:
    @pytest.fixture
    def corpus(self, tmp_path: Path) -> tuple[Path, Path]:
        for name in ("alpha-doc.md", "beta-doc.md", "gamma-doc.md"):
            make_document(
                tmp_path / name,
                sections={"One": sentences(120, name), "Two": sentences(120, name)},
            )
        return tmp_path, tmp_path / "processed" / "chunks.jsonl"

    def test_run_produces_valid_jsonl(self, corpus: tuple[Path, Path]) -> None:
        raw_dir, out = corpus
        assert main(["--raw-dir", str(raw_dir), "--out", str(out)]) == 0
        rows = [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines()]
        assert rows
        for row in rows:
            assert row["chunk_id"] and row["text"]
            assert row["metadata"]["document_id"]
            assert row["metadata"]["source_file"].startswith("data/raw/")
            assert row["metadata"]["chunk_index"] >= 1

    def test_chunk_ids_are_unique(self, corpus: tuple[Path, Path]) -> None:
        raw_dir, out = corpus
        main(["--raw-dir", str(raw_dir), "--out", str(out)])
        ids = [json.loads(line)["chunk_id"] for line in out.read_text().splitlines()]
        assert len(ids) == len(set(ids))

    def test_rerun_is_byte_identical(self, corpus: tuple[Path, Path]) -> None:
        raw_dir, out = corpus
        main(["--raw-dir", str(raw_dir), "--out", str(out)])
        first = out.read_bytes()
        main(["--raw-dir", str(raw_dir), "--out", str(out)])
        assert out.read_bytes() == first
