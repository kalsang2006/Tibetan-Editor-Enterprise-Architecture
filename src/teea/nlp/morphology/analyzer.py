"""Rule-based Tibetan morphological analysis (Language pipeline Stage 6).

Figure 5 assigns Stage 6 three responsibilities, all delivered here:

* **Affix recognition** -- match each syllable against the attested inventory in
  :mod:`teea.nlp.morphology.particles`, derived from the annotated reference
  corpus rather than authored by hand.
* **Root extraction** -- whatever is not an affix is lexical material, reported
  as :attr:`~teea.nlp.morphology.models.MorphologicalAnalysis.roots`.
* **Inflection analysis** -- report the grammatical function each affix carries,
  including the case allomorphs (``གི``/``ཀྱི``/``གྱི``/``འི`` are all the
  genitive) and whether the affix was fused to its host.

Why it builds on syllables
--------------------------
Tibetan is written without spaces, so the orthographic syllable is the smallest
reliably-delimited unit, and grammatical particles are overwhelmingly one
syllable long: only 4 of the 75 attested affix surfaces span more than one. This
module therefore reuses :class:`~teea.nlp.tokenization.syllable.SyllableSegmenter`
(Stage 5) rather than re-deriving syllable boundaries. Depending on Stage 5 is
correct pipeline order -- Stage 6 follows it -- and reuses code that already has
exact span handling.

Deliberate conservatism
-----------------------
Two things this analyzer will **not** do, both for the same reason: without a
lexicon, doing them would be guessing.

* It does not split a trailing ``ས`` or ``ར`` from its host. ``བུས`` really is
  ``བུ`` + agentive, but ``ལས`` is the ablative particle rather than ``ལ`` +
  agentive, and ``སངས`` is a root. Only the vowel-initial fused affixes, whose
  shape cannot begin an independent syllable, are split.
* It does not choose between the candidate readings of an ambiguous surface. A
  quarter of the affix inventory also occurs as content words, so those are
  reported as :attr:`MorphemeKind.AMBIGUOUS` for Stage 7 to resolve.

Both gaps close once the Dictionary Repository from Figure 2's Persistence layer
exists; see :mod:`teea.nlp.morphology.interfaces`.
"""

from __future__ import annotations

from teea.core.types import TextSpan, utf8_byte_offsets
from teea.nlp.morphology.models import (
    AffixCategory,
    Morpheme,
    MorphemeKind,
    MorphologicalAnalysis,
)
from teea.nlp.morphology.particles import FUSED_AFFIXES, lookup
from teea.nlp.tokenization import SyllableSegmenter


class TibetanMorphologicalAnalyzer:
    """Decomposes Tibetan text into roots and grammatical affixes.

    Satisfies the
    :class:`~teea.nlp.morphology.interfaces.MorphologicalAnalyzer` protocol. The
    analyzer is stateless and safe to share across threads.

    Args:
        segmenter: Syllable segmenter used to find analysis units. Defaults to a
            new :class:`~teea.nlp.tokenization.syllable.SyllableSegmenter`;
            injecting one lets callers share a single instance.
        split_fused_affixes: Whether to split vowel-initial affixes written
            attached to their host (``མིའི`` -> ``མི`` + ``འི``). Defaults to
            ``True``. Turning it off yields a purely syllable-level analysis.
    """

    def __init__(
        self,
        *,
        segmenter: SyllableSegmenter | None = None,
        split_fused_affixes: bool = True,
    ) -> None:
        self._segmenter = segmenter or SyllableSegmenter()
        self._split_fused_affixes = split_fused_affixes

    @property
    def split_fused_affixes(self) -> bool:
        """Whether fused affixes are separated from their host."""
        return self._split_fused_affixes

    def analyze(self, text: str) -> MorphologicalAnalysis:
        """Decompose ``text`` into roots and affixes.

        Total: any input, including empty or punctuation-only text, produces a
        :class:`MorphologicalAnalysis` rather than raising.

        Args:
            text: Normalized Tibetan text. All offsets in the result are
                relative to this exact string.

        Returns:
            The analysis, whose morphemes are ordered, non-overlapping, and each
            of which satisfies
            ``text[span.char_start:span.char_end] == morpheme.text``.
        """
        if not text:
            return MorphologicalAnalysis(source=text, morphemes=())

        byte_offsets = utf8_byte_offsets(text)
        morphemes: list[Morpheme] = []

        for syllable in self._segmenter.segment(text):
            morphemes.extend(
                self._analyze_syllable(
                    syllable.text, syllable.span.char_start, byte_offsets
                )
            )

        return MorphologicalAnalysis(source=text, morphemes=tuple(morphemes))

    # -- Internals ----------------------------------------------------------
    def _analyze_syllable(
        self, surface: str, start: int, byte_offsets: list[int]
    ) -> list[Morpheme]:
        """Analyze one syllable into one or two morphemes."""
        # The inventory is consulted before any fused-affix split. That ordering
        # is what keeps `ལས` recognised as the ablative particle instead of
        # being mistaken for a host plus a suffix.
        attested = lookup(surface)
        if attested is not None:
            categories, ambiguous = attested
            kind = MorphemeKind.AMBIGUOUS if ambiguous else MorphemeKind.AFFIX
            return [
                self._morpheme(surface, start, byte_offsets, kind=kind, categories=categories)
            ]

        if self._split_fused_affixes:
            split = self._split_fused(surface, start, byte_offsets)
            if split is not None:
                return split

        return [
            self._morpheme(surface, start, byte_offsets, kind=MorphemeKind.ROOT)
        ]

    def _split_fused(
        self, surface: str, start: int, byte_offsets: list[int]
    ) -> list[Morpheme] | None:
        """Split a host from a trailing vowel-initial affix, if present."""
        for sequence, category in FUSED_AFFIXES:
            if not surface.endswith(sequence) or len(surface) <= len(sequence):
                continue
            boundary = len(surface) - len(sequence)
            host = surface[:boundary]
            return [
                self._morpheme(host, start, byte_offsets, kind=MorphemeKind.ROOT),
                self._morpheme(
                    sequence,
                    start + boundary,
                    byte_offsets,
                    kind=MorphemeKind.AFFIX,
                    categories=frozenset({category}),
                    is_fused=True,
                ),
            ]
        return None

    @staticmethod
    def _morpheme(
        text: str,
        start: int,
        byte_offsets: list[int],
        *,
        kind: MorphemeKind,
        categories: frozenset[AffixCategory] = frozenset(),
        is_fused: bool = False,
    ) -> Morpheme:
        """Build a morpheme with an exact character/byte span."""
        end = start + len(text)
        return Morpheme(
            text=text,
            span=TextSpan(
                char_start=start,
                char_end=end,
                byte_start=byte_offsets[start],
                byte_end=byte_offsets[end],
            ),
            kind=kind,
            categories=categories,
            is_fused=is_fused,
        )


__all__ = ["TibetanMorphologicalAnalyzer"]
