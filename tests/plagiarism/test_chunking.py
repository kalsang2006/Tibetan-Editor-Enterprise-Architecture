"""Unit tests for document chunking."""

from __future__ import annotations

from teea.plagiarism.chunking import chunk_document
from teea.plagiarism.models import SourceDocument


def test_chunking_short_document() -> None:
    doc = SourceDocument(document_id="doc1", source="༄༅། ཀྱི་ཁྱི་བྱི་གྱི་དགའ་བ།")
    chunks = chunk_document(doc, max_chunk_chars=100)
    assert len(chunks) == 1
    assert chunks[0].document_id == "doc1"
    assert chunks[0].char_start == 0
    assert chunks[0].char_end == len(doc.source)


def test_chunking_paragraph_split() -> None:
    text = "Paragraph 1 line text\nParagraph 2 line text\nParagraph 3 line text"
    doc = SourceDocument(
        document_id="doc2",
        source=text,
        collection="Test Collection",
        filename="test.txt",
    )
    chunks = chunk_document(doc, max_chunk_chars=25)
    assert len(chunks) > 1
    assert chunks[0].collection == "Test Collection"
    assert chunks[0].filename == "test.txt"
    assert chunks[0].parent_doc_id == "doc2"
    assert chunks[0].chunk_index == 0


def test_chunking_fallback_windowing() -> None:
    long_line = "A" * 150
    doc = SourceDocument(document_id="doc3", source=long_line)
    chunks = chunk_document(doc, max_chunk_chars=50)
    assert len(chunks) == 3
    assert chunks[0].char_start == 0
    assert chunks[0].char_end == 50
    assert chunks[1].char_start == 50
    assert chunks[1].char_end == 100
    assert chunks[2].char_start == 100
    assert chunks[2].char_end == 150
