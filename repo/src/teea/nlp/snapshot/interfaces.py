"""The document analyser abstraction (interface) for TEEA.

Stage 12 is driven through this protocol rather than a concrete class, consistent
with every other stage. It is the interface the Local IPC layer will call: the
Level-1 Data Flow Diagram routes an "Analysis Request" to the Language Server and
a "Context Payload" back, and these two methods are the shape of that call.

Two methods, because FR-4 requires two
--------------------------------------
:meth:`DocumentAnalyzer.analyze` is the cold path -- a document arrives and is
analysed in full. :meth:`DocumentAnalyzer.reanalyze` is the path SRS 3.1 and FR-4
actually mandate: "only modified sentences trigger full pipeline re-parsing".
Stating both on the protocol means an implementation cannot satisfy the contract
while quietly re-parsing everything on every keystroke.

The division of labour is deliberate. This layer decides *what needs re-analysis*
by comparing content hashes, which FR-4 assigns to the Language Server. The
daemon decides *when to ask*, which is FR-1's debounced typing interval and is
not implemented here.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from teea.nlp.snapshot.models import DocumentSnapshot


@runtime_checkable
class DocumentAnalyzer(Protocol):
    """A whole-document analysis contract.

    Implementations must be safe to share across threads for read-only use, and
    must return snapshots that are safe to share likewise -- Figure 5 has every
    plugin read the snapshot concurrently.
    """

    def analyze(self, text: str) -> DocumentSnapshot:
        """Analyse a document from scratch.

        Implementations must be total: empty or unsegmentable input yields an
        empty snapshot rather than raising, matching every earlier stage.

        ``text`` is taken as given and recorded verbatim as the snapshot's
        source, so every offset in the result addresses exactly the string that
        was passed. Implementations must not normalize it; Stage 02 is a separate
        step the caller applies first, exactly as Stage 04 requires.

        Args:
            text: The document to analyse, already normalized by Stage 02.

        Returns:
            The immutable snapshot.
        """
        ...

    def reanalyze(self, previous: DocumentSnapshot, text: str) -> DocumentSnapshot:
        """Analyse a document, reusing whatever ``previous`` still describes.

        The FR-4 path. Implementations must produce a snapshot **identical** to
        the one :meth:`analyze` would produce for the same text -- reuse is an
        optimisation, never a difference in result. A test pins that equality.

        Args:
            previous: The snapshot of the document before the edit.
            text: The document after the edit, already normalized by Stage 02.

        Returns:
            The immutable snapshot of the new text.
        """
        ...


__all__ = ["DocumentAnalyzer"]
