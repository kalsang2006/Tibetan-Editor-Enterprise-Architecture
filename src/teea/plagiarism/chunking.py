"""Document chunking strategies for plagiarism indexing.

Supports paragraph-based chunking with fallback to character windowing for
large Tibetan documents.
"""

from __future__ import annotations

from dataclasses import dataclass

from teea.plagiarism.models import SourceDocument


@dataclass(frozen=True)
class DocumentChunk:
    """A segment of a larger document.

    Attributes:
        document_id: Unique identifier for this chunk (e.g. `doc_id#chunk_0`).
        parent_doc_id: The ID of the original unchunked document.
        chunk_index: Zero-based index of this chunk.
        char_start: Character offset start within original text.
        char_end: Character offset end within original text.
        text: Raw text of this chunk.
        collection: Optional collection name.
        filename: Optional filename.
    """

    document_id: str
    parent_doc_id: str
    chunk_index: int
    char_start: int
    char_end: int
    text: str
    collection: str | None = None
    filename: str | None = None


def chunk_document(
    doc: SourceDocument,
    max_chunk_chars: int = 100000,
) -> list[DocumentChunk]:
    """Split a document into paragraph or window chunks.

    Args:
        doc: The source document to split.
        max_chunk_chars: Maximum character length per chunk.

    Returns:
        List of :class:`DocumentChunk` objects.
    """
    text = doc.source
    if not text:
        return []

    if len(text) <= max_chunk_chars:
        return [
            DocumentChunk(
                document_id=doc.document_id,
                parent_doc_id=doc.document_id,
                chunk_index=0,
                char_start=0,
                char_end=len(text),
                text=text,
                collection=doc.collection,
                filename=doc.filename,
            )
        ]

    chunks: list[DocumentChunk] = []
    lines = text.split("\n")
    current_lines: list[str] = []
    current_len = 0
    current_start = 0
    pos = 0
    chunk_idx = 0

    for i, line in enumerate(lines):
        line_len = len(line) + (1 if i < len(lines) - 1 else 0)

        # Fallback windowing for an extraordinarily long single paragraph
        if len(line) > max_chunk_chars:
            if current_lines:
                chunk_text = "\n".join(current_lines)
                chunk_id = f"{doc.document_id}#chunk_{chunk_idx}"
                chunks.append(
                    DocumentChunk(
                        document_id=chunk_id,
                        parent_doc_id=doc.document_id,
                        chunk_index=chunk_idx,
                        char_start=current_start,
                        char_end=current_start + len(chunk_text),
                        text=chunk_text,
                        collection=doc.collection,
                        filename=doc.filename,
                    )
                )
                chunk_idx += 1
                current_lines = []
                current_len = 0

            # Window split for huge line
            line_pos = pos
            for w_start in range(0, len(line), max_chunk_chars):
                w_end = min(w_start + max_chunk_chars, len(line))
                w_text = line[w_start:w_end]
                chunk_id = f"{doc.document_id}#chunk_{chunk_idx}"
                chunks.append(
                    DocumentChunk(
                        document_id=chunk_id,
                        parent_doc_id=doc.document_id,
                        chunk_index=chunk_idx,
                        char_start=line_pos + w_start,
                        char_end=line_pos + w_end,
                        text=w_text,
                        collection=doc.collection,
                        filename=doc.filename,
                    )
                )
                chunk_idx += 1
            pos += line_len
            current_start = pos
            continue

        if current_len + line_len > max_chunk_chars and current_lines:
            chunk_text = "\n".join(current_lines)
            chunk_id = f"{doc.document_id}#chunk_{chunk_idx}"
            chunks.append(
                DocumentChunk(
                    document_id=chunk_id,
                    parent_doc_id=doc.document_id,
                    chunk_index=chunk_idx,
                    char_start=current_start,
                    char_end=current_start + len(chunk_text),
                    text=chunk_text,
                    collection=doc.collection,
                    filename=doc.filename,
                )
            )
            chunk_idx += 1
            current_lines = [line]
            current_start = pos
            current_len = line_len
        else:
            if not current_lines:
                current_start = pos
            current_lines.append(line)
            current_len += line_len

        pos += line_len

    if current_lines:
        chunk_text = "\n".join(current_lines)
        chunk_id = f"{doc.document_id}#chunk_{chunk_idx}" if chunk_idx > 0 else doc.document_id
        chunks.append(
            DocumentChunk(
                document_id=chunk_id,
                parent_doc_id=doc.document_id,
                chunk_index=chunk_idx,
                char_start=current_start,
                char_end=current_start + len(chunk_text),
                text=chunk_text,
                collection=doc.collection,
                filename=doc.filename,
            )
        )

    return chunks


__all__ = ["DocumentChunk", "chunk_document"]
