"""Glossary-driven terminology recognition (Language pipeline Stage 10).

Figure 5 assigns Stage 10 the recognition of *"Technical Terms · Buddhist
Vocabulary · User Dictionary"*. Step 6 of the UML Sequence Diagram shows the
Language Server performing a "Terminology Lookup" against the Storage Platform,
and the Deployment Diagram lists "Grammar & Terminology" among the Dictionary
Repo's deployed contents. This module performs that lookup over a parsed
sentence.

Matching
--------
Longest-first over runs of morphemes, exactly as Stage 9 matches names, and for
the same reason: technical vocabulary nests. "truth" is a term and "the two
truths" is a different one; reporting the shorter inside the longer would
fragment a single concept.

The user dictionary wins over the shipped glossary, because a scholar who has
defined a term has stated the reading they want.

Why the glossary is what it is
------------------------------
Every shipped entry satisfies two independent criteria: it is a headword in the
curated classical lexicon, **and** it occurs at least fifteen times in the BDRC
Buddhist canon while occurring zero times in 437,000 characters of general
narrative Tibetan. Contrastive frequency alone was measured and rejected -- its
top-ranked output is scholastic *register* ("therefore", "if one says"), not
terminology. See ADR-012.
"""

from __future__ import annotations

from teea.core.types import TextSpan
from teea.nlp.dependency import DependencyTree
from teea.nlp.postagging import TaggedMorpheme
from teea.nlp.terminology.models import RecognizedTerm, TerminologyAnnotation
from teea.persistence import TerminologyRepository, TermSource, default_terminology


class GlossaryTerminologyRecognizer:
    """Recognises technical terms in a parsed Tibetan sentence.

    Satisfies the :class:`~teea.nlp.terminology.interfaces.TerminologyRecognizer`
    protocol. Holds no mutable state and is safe to share across threads.

    Args:
        terminology: Source of known terms. Defaults to the shared glossary,
            which carries no user dictionary; a deployment with user terms
            constructs its own
            :class:`~teea.persistence.terminology.InMemoryTerminology`.

    Raises:
        ConfigurationError: If the default glossary cannot be loaded.
    """

    def __init__(self, *, terminology: TerminologyRepository | None = None) -> None:
        # `is None`, not `or`: an empty repository is falsy because it defines
        # __len__, so `or` would silently substitute the shipped glossary.
        self._terminology = default_terminology() if terminology is None else terminology

    def recognize(self, tree: DependencyTree) -> TerminologyAnnotation:
        """Find every technical term in ``tree``.

        Total: an empty tree yields an empty annotation rather than raising.

        Args:
            tree: Stage 8 output for one sentence.

        Returns:
            The terms found, in surface order and never overlapping.
        """
        morphemes = tuple(node.morpheme for node in tree.nodes)
        if not morphemes:
            return TerminologyAnnotation(source=tree.source, terms=())

        terms: list[RecognizedTerm] = []
        index = 0
        limit = min(self._terminology.max_length, len(morphemes))

        while index < len(morphemes):
            match = self._longest_match(morphemes, index, limit)
            if match is None:
                index += 1
                continue
            length, source = match
            terms.append(self._build(tree.source, morphemes, index, index + length, source))
            index += length

        return TerminologyAnnotation(source=tree.source, terms=tuple(terms))

    # -- Internals ----------------------------------------------------------
    def _longest_match(
        self, morphemes: tuple[TaggedMorpheme, ...], start: int, limit: int
    ) -> tuple[int, TermSource] | None:
        """Return ``(length, source)`` of the longest term starting at ``start``.

        Terms are compounds, so the search stops at length two; a single
        syllable is never a term on its own.
        """
        longest = min(limit, len(morphemes) - start)
        for length in range(longest, 1, -1):
            run = tuple(m.text for m in morphemes[start : start + length])
            source = self._terminology.lookup(run)
            if source is not None:
                return length, source
        return None

    @staticmethod
    def _build(
        source_text: str,
        morphemes: tuple[TaggedMorpheme, ...],
        start: int,
        end: int,
        source: TermSource,
    ) -> RecognizedTerm:
        """Assemble a term covering ``morphemes[start:end]``.

        The text is the source slice rather than the morphemes joined, so the
        tsheg separating the syllables is preserved -- a joined string would not
        appear in the document and the model validator would reject it.
        """
        run = morphemes[start:end]
        span = TextSpan(
            char_start=run[0].span.char_start,
            char_end=run[-1].span.char_end,
            byte_start=run[0].span.byte_start,
            byte_end=run[-1].span.byte_end,
        )
        return RecognizedTerm(
            text=source_text[span.char_start : span.char_end],
            span=span,
            start_index=start,
            end_index=end,
            source=source,
            morphemes=run,
        )


__all__ = ["GlossaryTerminologyRecognizer"]
