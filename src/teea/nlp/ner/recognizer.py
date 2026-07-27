"""Gazetteer- and tag-driven named entity recognition (pipeline Stage 9).

Figure 5 assigns Stage 9 the recognition of names in Tibetan text. Two sources
of evidence are available in the project's data repository, and this module uses
both:

* **A proper-noun gazetteer** of 2,767 entries, drawn from the ``n.prop``
  categories of the classical lexicon and the names attested in the annotated
  corpus. Matching is longest-first over runs of morphemes, because Tibetan
  names span several syllables and may contain internal grammatical particles --
  the corpus annotates ``འཛམ་བུ འི་ གླིང་`` as a single name whose middle token
  is a genitive.
* **The Stage 7 tag**, which marks proper nouns as ``n.prop``. Adjacent
  proper-noun morphemes are joined into one name.

Where the two agree the entity is reported as
:attr:`~teea.nlp.ner.models.EntityEvidence.BOTH`, which is the strongest signal
available without a typed resource.

Why longest-match
-----------------
Gazetteer entries nest: a lama's full title contains his personal name, and a
monastery name contains a place name. Taking the shortest match, or the first,
would fragment a real name into pieces and report several entities where the
text contains one. Scanning left to right and taking the longest entry that
starts at each position is the standard resolution, is deterministic, and
matches how the corpus annotates spans.

Scope
-----
Entities are **untyped**. Figure 5 names five categories, but nothing in the
available data distinguishes them; see ADR-011 and
:mod:`teea.nlp.ner.models`. This module recognises that a run of text is a name,
and does not guess what kind.
"""

from __future__ import annotations

from teea.core.types import TextSpan
from teea.nlp.dependency import DependencyTree
from teea.nlp.ner.models import EntityAnnotation, EntityEvidence, NamedEntity
from teea.nlp.postagging import TaggedMorpheme
from teea.persistence import GazetteerRepository, default_gazetteer

#: Fine-grained tag marking a proper noun in the reference tagset.
_PROPER_NOUN_TAG = "n.prop"


def _is_tagged_proper_noun(morpheme: TaggedMorpheme) -> bool:
    """Whether Stage 7 labelled this morpheme a proper noun."""
    return morpheme.tag == _PROPER_NOUN_TAG


class TibetanEntityRecognizer:
    """Recognises named entities in a parsed Tibetan sentence.

    Satisfies the :class:`~teea.nlp.ner.interfaces.EntityRecognizer` protocol.
    The recogniser holds no mutable state and is safe to share across threads.

    Args:
        gazetteer: Source of attested proper nouns. Defaults to the shared
            corpus-derived gazetteer.
        use_tagger_evidence: Whether a morpheme tagged ``n.prop`` counts as a
            name even when the gazetteer does not list it. Defaults to ``True``.
            Setting it to ``False`` restricts recognition to attested names,
            which trades recall for precision.

    Raises:
        ConfigurationError: If the default gazetteer cannot be loaded.
    """

    def __init__(
        self,
        *,
        gazetteer: GazetteerRepository | None = None,
        use_tagger_evidence: bool = True,
    ) -> None:
        # `is None`, not `or`: an empty gazetteer is falsy because it defines
        # __len__, so `or` would silently substitute the shipped one.
        self._gazetteer = default_gazetteer() if gazetteer is None else gazetteer
        self._use_tagger_evidence = use_tagger_evidence

    @property
    def use_tagger_evidence(self) -> bool:
        """Whether proper-noun tags are treated as evidence."""
        return self._use_tagger_evidence

    def recognize(self, tree: DependencyTree) -> EntityAnnotation:
        """Find every named entity in ``tree``.

        Total: an empty tree yields an empty annotation rather than raising.

        Args:
            tree: Stage 8 output for one sentence.

        Returns:
            The entities found, in surface order and never overlapping.
        """
        morphemes = tuple(node.morpheme for node in tree.nodes)
        if not morphemes:
            return EntityAnnotation(source=tree.source, entities=())

        entities: list[NamedEntity] = []
        index = 0
        limit = min(self._gazetteer.max_length, len(morphemes))

        while index < len(morphemes):
            match_length = self._longest_gazetteer_match(morphemes, index, limit)
            if match_length:
                tagged_too = all(
                    _is_tagged_proper_noun(m) for m in morphemes[index : index + match_length]
                )
                evidence = EntityEvidence.BOTH if tagged_too else EntityEvidence.GAZETTEER
                entities.append(
                    self._build(tree.source, morphemes, index, index + match_length, evidence)
                )
                index += match_length
                continue

            if self._use_tagger_evidence and _is_tagged_proper_noun(morphemes[index]):
                end = index + 1
                while end < len(morphemes) and _is_tagged_proper_noun(morphemes[end]):
                    end += 1
                entities.append(
                    self._build(tree.source, morphemes, index, end, EntityEvidence.TAGGER)
                )
                index = end
                continue

            index += 1

        return EntityAnnotation(source=tree.source, entities=tuple(entities))

    # -- Internals ----------------------------------------------------------
    def _longest_gazetteer_match(
        self, morphemes: tuple[TaggedMorpheme, ...], start: int, limit: int
    ) -> int:
        """Return the length of the longest accepted gazetteer entry at ``start``.

        Returns ``0`` when no entry matches. Longest-first, so a full title wins
        over the personal name nested inside it.

        An entry from the corroboration-required tier is accepted only when the
        tagger independently marks the whole run as a proper noun. Those entries
        are surfaces that also occur as ordinary words, and firing on them
        unconditionally measured as the single largest source of false
        positives.
        """
        longest = min(limit, len(morphemes) - start)
        for length in range(longest, 0, -1):
            window = morphemes[start : start + length]
            run = tuple(m.text for m in window)
            if self._gazetteer.contains(run):
                return length
            if self._gazetteer.contains_ambiguous(run) and all(
                _is_tagged_proper_noun(m) for m in window
            ):
                return length
        return 0

    @staticmethod
    def _build(
        source: str,
        morphemes: tuple[TaggedMorpheme, ...],
        start: int,
        end: int,
        evidence: EntityEvidence,
    ) -> NamedEntity:
        """Assemble an entity covering ``morphemes[start:end]``.

        The span runs from the first morpheme's start to the last morpheme's
        end, and the text is the corresponding slice of the source. Taking the
        slice rather than joining the morphemes matters: a multi-syllable name is
        written with tsheg between its syllables, and those separators lie
        between the morphemes rather than inside them. Joining would produce
        text that does not appear in the document, and the model validator would
        reject it.
        """
        run = morphemes[start:end]
        first, last = run[0], run[-1]
        span = TextSpan(
            char_start=first.span.char_start,
            char_end=last.span.char_end,
            byte_start=first.span.byte_start,
            byte_end=last.span.byte_end,
        )
        return NamedEntity(
            text=source[span.char_start : span.char_end],
            span=span,
            start_index=start,
            end_index=end,
            evidence=evidence,
            morphemes=run,
        )


__all__ = ["TibetanEntityRecognizer"]
