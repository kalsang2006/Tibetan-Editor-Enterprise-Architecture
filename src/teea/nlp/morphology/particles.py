"""The attested Tibetan affix inventory (Language pipeline Stage 6).

Every table in this module is **derived from data, not invented**. The source is
the part-of-speech-annotated Milarepa corpus in the project's authoritative data
repository (``Data/Texts/mila-horizontal.txt``), which supplies 60,544 tagged
tokens, of which 16,984 are grammatical morphemes. Hand-authoring a particle list
from memory would risk both omissions and Tibetan transcription errors; deriving
it means the inventory reflects real classical usage, with real frequencies.

Two tables, one distinction
---------------------------
The corpus shows that affix surfaces are not uniformly reliable. Measured as the
share of a surface's occurrences that carry a grammatical tag:

* 44 surfaces are **>=90% grammatical**. Recognizing these as affixes is safe.
* 20 surfaces are **mixed**. ``དེ`` is a demonstrative pronoun in 95% of its
  occurrences and a semi-final converb in only 5%; ``ལས`` is the ablative in 63%
  and the noun "work" in 35%; ``མི`` is negation in 78% and the noun "person" in
  22%.

Treating the second group as affixes would be wrong most of the time, so they are
kept separate and reported as :class:`~teea.nlp.morphology.models.MorphemeKind`
``AMBIGUOUS``. Resolving them needs the surrounding part of speech, which is
Stage 7's job. This is the pipeline's stage split doing exactly what it exists
for.

Allomorphy
----------
Tibetan case particles are conditioned by the final letter of the preceding
syllable -- the genitive appears as ``གི`` after ``ག``/``ང``, ``ཀྱི`` after
``ད``/``ས``, ``གྱི`` after ``ན``/``མ``/``ར``/``ལ``, and ``འི`` after an open
syllable. All allomorphs are listed here and map to the same
:class:`AffixCategory`, so recognition is exact without needing to model the
sandhi. Generating the correct allomorph is a different problem, and is not
Stage 6's concern.

Surfaces are stored **without a trailing tsheg**; callers normalise before
lookup via :func:`lookup`.
"""

from __future__ import annotations

from collections.abc import Mapping

from teea.nlp.morphology.models import AffixCategory

#: Surfaces that are grammatical in at least 90% of their corpus occurrences.
#: Comments record the observed frequency and grammatical share.
UNAMBIGUOUS_AFFIXES: Mapping[str, frozenset[AffixCategory]] = {
    # n=2277, grammatical 100%
    "\u0f60\u0f72": frozenset({AffixCategory.GENITIVE}),
    # n=1975, grammatical 99%
    "\u0f63": frozenset({AffixCategory.ALLATIVE}),
    # n=1946, grammatical 97%
    "\u0f66": frozenset({AffixCategory.AGENTIVE}),
    # n=1638, grammatical 100%
    "\u0f62": frozenset({AffixCategory.TERMINATIVE}),
    # n=1110, grammatical 99%
    "\u0f53\u0f66": frozenset({AffixCategory.ELATIVE}),
    # n=993, grammatical 100%
    "\u0f51\u0f44": frozenset({AffixCategory.ASSOCIATIVE}),
    # n=725, grammatical 100%
    "\u0f51\u0f74": frozenset({AffixCategory.TERMINATIVE}),
    # n=606, grammatical 99%
    "\u0f53": frozenset({AffixCategory.LOCATIVE}),
    # n=514, grammatical 92%
    "\u0f58": frozenset({AffixCategory.NEGATION}),
    # n=511, grammatical 100%
    "\u0f40\u0fb1\u0f72": frozenset({AffixCategory.GENITIVE}),
    # n=409, grammatical 100%
    "\u0f42\u0fb1\u0f72": frozenset({AffixCategory.GENITIVE}),
    # n=403, grammatical 100%
    "\u0f45\u0f72\u0f42": frozenset({AffixCategory.IMPERATIVE, AffixCategory.INDEFINITE}),
    # n=319, grammatical 100%
    "\u0f42\u0f72": frozenset({AffixCategory.GENITIVE}),
    # n=301, grammatical 100%
    "\u0f4f\u0f7a": frozenset({AffixCategory.SEMI_FINAL}),
    # n=258, grammatical 100%
    "\u0f40\u0fb1\u0f72\u0f66": frozenset({AffixCategory.AGENTIVE}),
    # n=243, grammatical 100%
    "\u0f40\u0fb1\u0f44": frozenset({AffixCategory.FOCUS}),
    # n=216, grammatical 100%
    "\u0f66\u0f9f\u0f7a": frozenset({AffixCategory.SEMI_FINAL}),
    # n=203, grammatical 100%
    "\u0f4f\u0f74": frozenset({AffixCategory.TERMINATIVE}),
    # n=168, grammatical 98%
    "\u0f5e\u0f72\u0f42": frozenset({AffixCategory.IMPERATIVE, AffixCategory.INDEFINITE}),
    # n=149, grammatical 99%
    "\u0f42\u0f72\u0f66": frozenset({AffixCategory.AGENTIVE}),
    # n=123, grammatical 100%
    "\u0f53\u0f72": frozenset({AffixCategory.FOCUS}),
    # n=92, grammatical 96%
    "\u0f64\u0f72\u0f42": frozenset({AffixCategory.IMPERATIVE, AffixCategory.INDEFINITE}),
    # n=84, grammatical 100%
    "\u0f45\u0f72\u0f44": frozenset({AffixCategory.IMPERFECTIVE}),
    # n=67, grammatical 100%
    "\u0f60\u0f44": frozenset({AffixCategory.FOCUS}),
    # n=65, grammatical 97%
    "\u0f61\u0f72": frozenset({AffixCategory.GENITIVE}),
    # n=64, grammatical 100%
    "\u0f53\u0f0b\u0f62\u0f7a": frozenset({AffixCategory.QUOTATIVE}),
    # n=52, grammatical 100%
    "\u0f5e\u0f7a\u0f66": frozenset({AffixCategory.QUOTATIVE}),
    # n=44, grammatical 98%
    "\u0f62\u0f74": frozenset({AffixCategory.TERMINATIVE}),
    # n=31, grammatical 100%
    "\u0f61\u0f72\u0f66": frozenset({AffixCategory.AGENTIVE}),
    # n=30, grammatical 100%
    "\u0f68\u0f7a": frozenset({AffixCategory.NEGATION}),
    # n=29, grammatical 100%
    "\u0f56\u0f66": frozenset({AffixCategory.COMPARATIVE}),
    # n=26, grammatical 100%
    "\u0f45\u0f7a\u0f66": frozenset({AffixCategory.QUOTATIVE}),
    # n=16, grammatical 94%
    "\u0f42\u0f58": frozenset({AffixCategory.INTERROGATIVE}),
    # n=16, grammatical 100%
    "\u0f66\u0f58": frozenset({AffixCategory.INTERROGATIVE}),
    # n=16, grammatical 100%
    "\u0f53\u0f7c": frozenset({AffixCategory.FINAL}),
    # n=13, grammatical 100%
    "\u0f42\u0f72\u0f53": frozenset({AffixCategory.CONTINUATIVE}),
    # n=13, grammatical 100%
    "\u0f60\u0f58": frozenset({AffixCategory.INTERROGATIVE}),
    # n=12, grammatical 100%
    "\u0f44\u0f58": frozenset({AffixCategory.INTERROGATIVE}),
    # n=7, grammatical 100%
    "\u0f54\u0f66": frozenset({AffixCategory.COMPARATIVE}),
    # n=6, grammatical 100%
    "\u0f4f\u0f7c": frozenset({AffixCategory.FINAL}),
    # n=5, grammatical 100%
    "\u0f56\u0f7c": frozenset({AffixCategory.FINAL}),
    # n=4, grammatical 100%
    "\u0f62\u0f58": frozenset({AffixCategory.INTERROGATIVE}),
    # n=4, grammatical 100%
    "\u0f40\u0fb1\u0f72\u0f53": frozenset({AffixCategory.CONTINUATIVE}),
    # n=4, grammatical 100%
    "\u0f5e\u0f7a\u0f66\u0f0b\u0f54": frozenset({AffixCategory.QUOTATIVE}),
}

#: Surfaces that occur both as affixes and as ordinary content words. Stage 6
#: reports these as AMBIGUOUS rather than committing to a reading.
AMBIGUOUS_AFFIXES: Mapping[str, frozenset[AffixCategory]] = {
    # n=982, grammatical 5%
    "\u0f51\u0f7a": frozenset({AffixCategory.SEMI_FINAL}),
    # n=597, grammatical 78%
    "\u0f58\u0f72": frozenset({AffixCategory.NEGATION}),
    # n=381, grammatical 74%
    "\u0f61\u0f44": frozenset({AffixCategory.FOCUS}),
    # n=290, grammatical 71%
    "\u0f42\u0fb1\u0f72\u0f66": frozenset({AffixCategory.AGENTIVE}),
    # n=210, grammatical 79%
    "\u0f5e\u0f72\u0f44": frozenset({AffixCategory.IMPERFECTIVE}),
    # n=206, grammatical 87%
    "\u0f66\u0f74": frozenset({AffixCategory.TERMINATIVE}),
    # n=155, grammatical 63%
    "\u0f63\u0f66": frozenset({AffixCategory.ABLATIVE}),
    # n=144, grammatical 88%
    "\u0f62\u0f74\u0f44": frozenset({AffixCategory.CONCESSIVE}),
    # n=71, grammatical 39%
    "\u0f60\u0f7c": frozenset({AffixCategory.FINAL}),
    # n=64, grammatical 84%
    "\u0f66\u0f7c": frozenset({AffixCategory.FINAL}),
    # n=61, grammatical 36%
    "\u0f44\u0f7c": frozenset({AffixCategory.FINAL}),
    # n=57, grammatical 37%
    "\u0f63\u0f7c": frozenset({AffixCategory.FINAL}),
    # n=49, grammatical 78%
    "\u0f53\u0f58": frozenset({AffixCategory.INTERROGATIVE}),
    # n=42, grammatical 7%
    "\u0f63\u0f58": frozenset({AffixCategory.INTERROGATIVE}),
    # n=39, grammatical 87%
    "\u0f64\u0f72\u0f44": frozenset({AffixCategory.IMPERFECTIVE}),
    # n=33, grammatical 9%
    "\u0f42\u0f7c": frozenset({AffixCategory.FINAL}),
    # n=30, grammatical 87%
    "\u0f51\u0f7c": frozenset({AffixCategory.FINAL}),
    # n=29, grammatical 31%
    "\u0f51\u0f42": frozenset({AffixCategory.FOCUS}),
    # n=25, grammatical 28%
    "\u0f62\u0f7c": frozenset({AffixCategory.FINAL}),
    # n=19, grammatical 32%
    "\u0f51\u0f58": frozenset({AffixCategory.INTERROGATIVE}),
}

#: Affixes written *fused* to the preceding syllable, with no intervening tsheg.
#:
#: Each begins with a-chung (U+0F60) carrying only a vowel sign, a shape that
#: cannot start an independent syllable. That makes stripping them safe: across
#: all 60,544 corpus tokens, no single gold token ends in ``འི``, ``འམ`` or
#: ``འང``, and exactly one ends in ``འོ``. Order matters only for readability;
#: the sequences are mutually exclusive.
#:
#: The agentive ``ས`` and terminative ``ར`` also fuse, but are deliberately
#: **not** listed: stripping them is ambiguous without a lexicon (``ལས`` is the
#: ablative particle, not ``ལ`` + agentive; ``སངས`` is a root, not ``སང`` +
#: agentive). Resolving those requires the Dictionary Repository that Figure 2
#: places in the Persistence layer, which is not yet implemented.
FUSED_AFFIXES: tuple[tuple[str, AffixCategory], ...] = (
    ("\u0f60\u0f72", AffixCategory.GENITIVE),  # the genitive, by far the most frequent fused affix
    ("\u0f60\u0f7c", AffixCategory.FINAL),  # the final/declarative particle
    ("\u0f60\u0f58", AffixCategory.INTERROGATIVE),  # the question particle
    ("\u0f60\u0f44", AffixCategory.FOCUS),  # the focus/additive particle
)


def lookup(surface: str) -> tuple[frozenset[AffixCategory], bool] | None:
    """Look up a surface in the attested inventory.

    Args:
        surface: A syllable surface, without its trailing tsheg.

    Returns:
        ``(categories, is_ambiguous)`` when the surface is attested as an affix,
        otherwise ``None``.
    """
    categories = UNAMBIGUOUS_AFFIXES.get(surface)
    if categories is not None:
        return categories, False
    categories = AMBIGUOUS_AFFIXES.get(surface)
    if categories is not None:
        return categories, True
    return None


__all__ = [
    "AMBIGUOUS_AFFIXES",
    "FUSED_AFFIXES",
    "UNAMBIGUOUS_AFFIXES",
    "lookup",
]
