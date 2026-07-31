"""Similarity scoring for plagiarism detection.

Asymmetric containment
---------------------
Plagiarism detection uses *asymmetric* similarity (containment) rather
than symmetric Jaccard similarity.  Given a query document Q and a corpus
document C:

    containment(Q → C) = |fingerprints(Q) ∩ fingerprints(C)|
                         ────────────────────────────────────
                               |fingerprints(Q)|

This is the fraction of the query's content that appears in the corpus
document.  It is asymmetric because ``containment(Q → C)`` and
``containment(C → Q)`` differ when the documents have different lengths:

* A short query that is entirely contained in a long document scores 1.0
  (high confidence that the query was copied from the document).
* The long document scores much lower against the query, because most of
  its content is unrelated.

This asymmetry is intentional: a user wants to know "how much of *my*
document is copied", not "how similar are these two documents".

Coverage
--------
``coverage(Q → C)`` is the reverse containment.  It tells the user how
much of the matched corpus document is accounted for by the query.  A low
coverage with high similarity means the query is a short excerpt from a
much longer work.
"""

from __future__ import annotations

from teea.plagiarism.models import FingerprintMatch


def jaccard_containment(
    query_hashes: frozenset[int],
    doc_hashes: frozenset[int],
    doc_id: str,
    *,
    query_total: int | None = None,
    doc_total: int | None = None,
    collection: str | None = None,
    filename: str | None = None,
) -> FingerprintMatch | None:
    """Compute the asymmetric containment of *query* within *doc*.

    Args:
        query_hashes: Fingerprint hash set of the query document.
        doc_hashes: Fingerprint hash set of the corpus document.
        doc_id: Identifier of the corpus document.
        query_total: Total fingerprints the query produced.
        doc_total: Total fingerprints the doc produced.
        collection: Optional corpus collection name.
        filename: Optional source filename.

    Returns:
        A :class:`FingerprintMatch` or ``None`` if there is no overlap.
    """
    overlap = query_hashes & doc_hashes
    if not overlap:
        return None

    q_total = query_total if query_total is not None else len(query_hashes)
    d_total = doc_total if doc_total is not None else len(doc_hashes)

    # Both totals must be >0 — an empty set would have been caught above.
    return FingerprintMatch(
        document_id=doc_id,
        similarity=len(overlap) / q_total,
        coverage=len(overlap) / d_total,
        overlap_count=len(overlap),
        query_fingerprint_count=q_total,
        doc_fingerprint_count=d_total,
        collection=collection,
        filename=filename,
    )


def rank_matches(matches: list[FingerprintMatch]) -> list[FingerprintMatch]:
    """Sort matches by similarity descending, then coverage descending.

    Ties are broken by ``document_id`` for determinism.
    """
    return sorted(
        matches,
        key=lambda m: (-m.similarity, -m.coverage, m.document_id),
    )


__all__ = ["jaccard_containment", "rank_matches"]
