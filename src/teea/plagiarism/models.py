"""Immutable domain models for plagiarism detection.

Data flow (Figure 8):

    SourceDocument (corpus entry with Fingerprint set)
        ↓
    FingerprintIndex (maps hash → document ids)
        ↓
    PlagiarismEngine.detect(query_text)
        ↓
    MatchResult (ranked FingerprintMatch entries)

Each :class:`Fingerprint` is one hash produced by the Robust Winnowing
algorithm over a k-gram sequence.  The hash together with its position in
the source text enables both similarity scoring and source alignment.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Fingerprint(BaseModel):
    """One winnowed fingerprint hash.

    Attributes:
        hash_value: The 64-bit rolling hash of a k-gram.
        char_start: Character offset of the k-gram in the source text.
        char_end: Exclusive character offset (char_start + k).
    """

    model_config = ConfigDict(frozen=True)

    hash_value: int
    char_start: int = Field(ge=0)
    char_end: int = Field(ge=1)


class SourceDocument(BaseModel):
    """A document in the plagiarism detection corpus.

    Attributes:
        document_id: Unique identifier (e.g. a filename or UUID).
        source: The original text of the document.
        fingerprints: The fingerprint hash set for this document, used for
            efficient similarity computation.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    document_id: str
    source: str
    fingerprints: frozenset[int] = frozenset()

    @model_validator(mode="after")
    def _validate_consistency(self) -> SourceDocument:
        if not self.document_id:
            raise ValueError("document_id must not be empty")
        return self


class FingerprintMatch(BaseModel):
    """One matched document from the corpus.

    Attributes:
        document_id: The matched corpus document.
        similarity: Asymmetric containment similarity in ``[0, 1]``.  This is
            the fraction of query fingerprints that matched the corpus
            document.  ``1.0`` means every query fingerprint was found in
            this document (the document may be much longer).
        coverage: Fraction of the corpus document's fingerprints that were
            matched.  ``1.0`` means every fingerprint of the corpus document
            was found in the query (the query may be a superset).
        overlap_count: Number of matching fingerprints.
        query_fingerprint_count: Total fingerprints in the query.
        doc_fingerprint_count: Total fingerprints in the corpus document.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    document_id: str
    similarity: float = Field(ge=0.0, le=1.0)
    coverage: float = Field(ge=0.0, le=1.0)
    overlap_count: int = Field(ge=0)
    query_fingerprint_count: int = Field(ge=1)
    doc_fingerprint_count: int = Field(ge=0)

    @model_validator(mode="after")
    def _validate_consistency(self) -> FingerprintMatch:
        if not self.document_id:
            raise ValueError("document_id must not be empty")
        if self.overlap_count > self.query_fingerprint_count:
            raise ValueError("overlap cannot exceed query fingerprint count")
        if self.overlap_count > self.doc_fingerprint_count:
            raise ValueError("overlap cannot exceed document fingerprint count")
        return self


class MatchResult(BaseModel):
    """The complete result of a plagiarism detection query.

    Attributes:
        matches: Ranked matches, most similar first.
        query_text: The original query text.
        query_fingerprint_count: Number of fingerprints generated from the
            query.
        total_corpus_documents: Number of documents in the indexed corpus
            at query time.
        elapsed_ms: Approximate wall-clock time for detection, in
            milliseconds.  ``0`` when timing was not performed.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    matches: tuple[FingerprintMatch, ...] = ()
    query_text: str = ""
    query_fingerprint_count: int = Field(default=0, ge=0)
    total_corpus_documents: int = Field(default=0, ge=0)
    elapsed_ms: float = Field(default=0.0, ge=0.0)

    @property
    def num_matches(self) -> int:
        """Number of matches above the threshold."""
        return len(self.matches)

    @property
    def best_match(self) -> FingerprintMatch | None:
        """The highest-similarity match, or ``None`` if there are none."""
        return self.matches[0] if self.matches else None

    @property
    def max_similarity(self) -> float:
        """The highest similarity score across all matches."""
        return max((m.similarity for m in self.matches), default=0.0)

    def above(self, threshold: float) -> MatchResult:
        """Return a new result containing only matches above ``threshold``."""
        return MatchResult(
            matches=tuple(m for m in self.matches if m.similarity >= threshold),
            query_text=self.query_text,
            query_fingerprint_count=self.query_fingerprint_count,
            total_corpus_documents=self.total_corpus_documents,
            elapsed_ms=self.elapsed_ms,
        )


__all__ = ["Fingerprint", "FingerprintMatch", "MatchResult", "SourceDocument"]
