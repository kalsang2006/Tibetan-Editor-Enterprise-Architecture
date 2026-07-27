"""Hidden Markov Model part-of-speech tagger (Language pipeline Stage 7).

Figure 5 assigns Stage 7 the job of labelling each unit with its part of speech,
which in practice means resolving what Stage 6 could not. Stage 6 recognizes
affixes but deliberately refuses to guess: roughly a quarter of Tibetan affix
surfaces also occur as ordinary content words, so it reports them as
``AMBIGUOUS``. Choosing between "``ལས`` the ablative particle" and "``ལས`` the
noun *work*" needs the surrounding sequence, and that is exactly what this stage
supplies.

Why an HMM
----------
A bigram HMM decoded with Viterbi is the right tool here for reasons that are
architectural, not just statistical:

* **Deterministic and auditable.** The same input always produces the same tags,
  and every decision traces back to counts in the reference corpus. For a
  writing assistant that must justify corrections to a scholar, that matters.
* **No new dependencies, and fast.** Decoding is O(n · |candidate tags|²) over a
  sentence, which comfortably fits the sub-50ms interactivity budget of NFR 5.1
  without a neural runtime.
* **Corpus-derived throughout.** Emissions and transitions come from the
  annotated corpus via the Dictionary Repository; nothing is hand-authored.

Measured performance
--------------------
Evaluated on a *held-out text by a different author* -- trained on Milarepa,
tested on Marpa -- over 52,379 aligned morphemes:

===========================  ==========  ==========
Model                        Fine tag    Coarse
===========================  ==========  ==========
Most-frequent-tag baseline      63.1%       79.8%
Bigram HMM + Viterbi            72.3%       82.0%
===========================  ==========  ==========

The unit matters more than the model. Tagging happens on *syllables*, because
Stage 6 emits syllable-level morphemes, so the statistics are trained on
syllables too: gold token tags are projected onto their constituent syllables
when the model is built. Training on word units while inferring on syllables is
a train/test mismatch that measured 22 points of accuracy -- 24.6% of gold
tokens span more than one syllable.

The residual gap is dominated by distinctions no context-free model recovers:
proper versus common noun (``n.prop`` / ``n.count``) accounts for the largest
share of remaining errors and would need a name gazetteer.

Where Stage 6 helps
-------------------
Stage 6's output is used, not ignored. For a surface the lexicon has never seen,
the candidate tag set would otherwise be all 77 tags; when Stage 6 recognized the
morpheme as an affix, the candidates are narrowed to the tags compatible with the
grammatical categories it identified. That is the two stages composing as the
pipeline intends.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence

from teea.nlp.morphology import AffixCategory, MorphemeKind, MorphologicalAnalysis
from teea.nlp.postagging.models import (
    PosCategory,
    TaggedMorpheme,
    TaggedText,
    coarse_category,
)
from teea.persistence import (
    SENTENCE_START,
    DictionaryRepository,
    default_dictionary,
)

#: Maps a Stage 6 grammatical category onto the corpus tags that express it.
#: Used only to constrain candidates for out-of-vocabulary surfaces; in-vocabulary
#: surfaces are constrained by their observed emissions instead.
_CATEGORY_TAGS: Mapping[AffixCategory, frozenset[str]] = {
    AffixCategory.GENITIVE: frozenset({"case.gen", "cv.gen"}),
    AffixCategory.AGENTIVE: frozenset({"case.agn", "cv.agn"}),
    AffixCategory.ALLATIVE: frozenset({"case.all", "cv.all"}),
    AffixCategory.TERMINATIVE: frozenset({"case.term", "cv.term"}),
    AffixCategory.LOCATIVE: frozenset({"case.loc", "cv.loc"}),
    AffixCategory.ABLATIVE: frozenset({"case.abl"}),
    AffixCategory.ELATIVE: frozenset({"case.ela", "cv.ela"}),
    AffixCategory.ASSOCIATIVE: frozenset({"case.ass", "cv.ass"}),
    AffixCategory.COMPARATIVE: frozenset({"case.comp"}),
    AffixCategory.SEMI_FINAL: frozenset({"cv.sem"}),
    AffixCategory.IMPERFECTIVE: frozenset({"cv.impf"}),
    AffixCategory.CONTINUATIVE: frozenset({"cv.cont"}),
    AffixCategory.FINAL: frozenset({"cv.fin"}),
    AffixCategory.IMPERATIVE: frozenset({"cv.imp"}),
    AffixCategory.INTERROGATIVE: frozenset({"cv.ques"}),
    AffixCategory.CONCESSIVE: frozenset({"cv.rung"}),
    AffixCategory.FOCUS: frozenset({"cl.focus"}),
    AffixCategory.QUOTATIVE: frozenset({"cl.quot", "case.nare"}),
    AffixCategory.NEGATION: frozenset({"neg"}),
    AffixCategory.INDEFINITE: frozenset({"d.indef"}),
}

#: Fallback tag when nothing else can be determined. The corpus's most frequent
#: open-class tag, which is the standard choice for an unknown word.
_DEFAULT_TAG = "n.count"


class HmmPosTagger:
    """Assigns parts of speech by Viterbi decoding over a bigram HMM.

    Satisfies the :class:`~teea.nlp.postagging.interfaces.PosTagger` protocol.
    The tagger holds no mutable state and is safe to share across threads.

    Args:
        dictionary: Source of emission and transition statistics. Defaults to
            the shared corpus-derived repository.
        smoothing: Additive smoothing constant applied to both distributions.
            The default of 0.1 was chosen by measurement on held-out text;
            larger values wash out genuine lexical preferences, smaller ones
            make unseen transitions effectively impossible.

    Raises:
        ConfigurationError: If the default repository cannot be loaded.
    """

    def __init__(
        self,
        *,
        dictionary: DictionaryRepository | None = None,
        smoothing: float = 0.1,
    ) -> None:
        if smoothing <= 0:
            raise ValueError("smoothing must be positive")
        # `is None`, not `or`: an empty repository is falsy because it defines
        # __len__, so `or` would silently discard a legitimately-empty injected
        # store and load the shipped model in its place.
        self._dictionary = default_dictionary() if dictionary is None else dictionary
        self._smoothing = smoothing
        self._tags = tuple(sorted(self._dictionary.tags))
        self._vocabulary_size = sum(1 for _ in self._tags) + 1

        # Transition rows and their totals are constant for the lifetime of the
        # repository, but Viterbi asks for them once per (previous, candidate)
        # pair -- and for an out-of-vocabulary surface the candidate set is the
        # whole tagset, so that is |tags|^2 lookups per morpheme. Recomputing
        # sum(row.values()) inside that loop cost 3.8 ms per morpheme against
        # 0.015 ms for in-vocabulary text, which pushed a short phrase of
        # embedded Latin past the 50 ms interactive budget of NFR 5.1.
        # Hoisting the sums here is a pure caching change: identical output.
        # The whole table is |tags| x |tags| floats -- about 6,000 entries, a few
        # hundred KiB -- and every value is a constant of the repository, so it
        # is built once here instead of |tags|^2 times per morpheme.
        denominator_tags = self._smoothing * len(self._tags)
        self._transition_logp_table: dict[str, dict[str, float]] = {}
        for previous in (*self._tags, SENTENCE_START):
            row = self._dictionary.transitions(previous)
            total = sum(row.values()) + denominator_tags
            self._transition_logp_table[previous] = {
                tag: math.log((row.get(tag, 0) + self._smoothing) / total) for tag in self._tags
            }

        # An out-of-vocabulary surface has no observed counts, so its emission
        # probability depends only on the tag. Precomputing that vector removes
        # another |tags| logarithms per unknown morpheme -- and unknown
        # morphemes are exactly the slow case.
        self._oov_emission_logp: dict[str, float] = {
            tag: math.log(
                self._smoothing
                / (
                    self._dictionary.tag_counts.get(tag, 0)
                    + self._smoothing * self._vocabulary_size
                )
            )
            for tag in self._tags
        }

    @property
    def smoothing(self) -> float:
        """The additive smoothing constant in use."""
        return self._smoothing

    @property
    def tagset(self) -> tuple[str, ...]:
        """Every tag this tagger can emit, sorted."""
        return self._tags

    def tag(self, analysis: MorphologicalAnalysis) -> TaggedText:
        """Assign a part of speech to every morpheme of ``analysis``.

        Total: an empty analysis yields an empty result rather than raising.

        Args:
            analysis: Stage 6 output for one sentence.

        Returns:
            The tagged sentence, preserving every span exactly.
        """
        if not analysis.morphemes:
            return TaggedText(source=analysis.source, morphemes=())

        candidates = [self._candidates(index, analysis) for index in range(len(analysis.morphemes))]
        chosen = self._viterbi([m.text for m in analysis.morphemes], candidates)

        tagged = tuple(
            TaggedMorpheme(
                morpheme=morpheme,
                tag=tag,
                category=coarse_category(tag),
                was_ambiguous=morpheme.kind is MorphemeKind.AMBIGUOUS,
            )
            for morpheme, tag in zip(analysis.morphemes, chosen, strict=True)
        )
        return TaggedText(source=analysis.source, morphemes=tagged)

    # -- Internals ----------------------------------------------------------
    def _candidates(self, index: int, analysis: MorphologicalAnalysis) -> tuple[str, ...]:
        """Return the tags worth considering for one morpheme.

        In-vocabulary surfaces are restricted to tags actually observed with
        them. Unknown surfaces fall back to whatever Stage 6 determined, and
        only failing that to the full tagset.
        """
        morpheme = analysis.morphemes[index]
        observed = self._dictionary.lookup(morpheme.text)
        if observed:
            return tuple(sorted(observed))

        if morpheme.categories:
            constrained = sorted(
                tag
                for category in morpheme.categories
                for tag in _CATEGORY_TAGS.get(category, frozenset())
                if tag in self._dictionary.tags
            )
            if constrained:
                return tuple(constrained)

        return self._tags

    def _emission_logp(self, surface: str, tag: str) -> float:
        """Log P(surface | tag), additively smoothed."""
        observed = self._dictionary.lookup(surface)
        if not observed:
            return self._oov_emission_logp[tag]
        total = self._dictionary.tag_counts.get(tag, 0)
        return math.log(
            (observed.get(tag, 0) + self._smoothing)
            / (total + self._smoothing * self._vocabulary_size)
        )

    def _transition_logp(self, previous: str, tag: str) -> float:
        """Log P(tag | previous), additively smoothed.

        A lookup into the table built in ``__init__``; see there for why this is
        not recomputed per call.
        """
        row = self._transition_logp_table.get(previous)
        if row is None:  # pragma: no cover - defensive
            # Unreachable: ``previous`` is always SENTENCE_START or a tag drawn
            # from the tagset, and the table covers both. Kept so a future
            # candidate source cannot turn a bad key into a KeyError mid-decode.
            return self._transition_logp_table[SENTENCE_START][tag]
        return row[tag]

    def _viterbi(self, surfaces: Sequence[str], candidates: Sequence[tuple[str, ...]]) -> list[str]:
        """Decode the most probable tag sequence.

        Standard Viterbi over log-probabilities: sums rather than products, so
        long sentences cannot underflow.
        """
        best: dict[str, float] = {SENTENCE_START: 0.0}
        backpointers: list[dict[str, str]] = []

        for surface, allowed in zip(surfaces, candidates, strict=True):
            layer: dict[str, float] = {}
            pointer: dict[str, str] = {}
            for tag in allowed:
                emission = self._emission_logp(surface, tag)
                best_previous = SENTENCE_START
                best_score = -math.inf
                for previous, score in best.items():
                    total = score + self._transition_logp(previous, tag) + emission
                    if total > best_score:
                        best_score, best_previous = total, previous
                layer[tag] = best_score
                pointer[tag] = best_previous
            best = layer
            backpointers.append(pointer)

        final = max(best, key=lambda tag: best[tag]) if best else _DEFAULT_TAG
        reversed_tags = [final]
        for pointer in reversed(backpointers[1:]):
            final = pointer[final]
            reversed_tags.append(final)
        return list(reversed(reversed_tags))


__all__ = ["HmmPosTagger", "PosCategory"]
