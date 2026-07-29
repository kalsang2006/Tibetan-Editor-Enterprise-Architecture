"""Built-in spell checker plugin for TEEA.

Flags Tibetan morphemes that are not attested in the corpus-derived
Dictionary Repository as potential misspellings.  The plugin emits one
Suggestion per unknown root/content morpheme.

AI-assisted corrections
-----------------------
When a :class:`~teea.plugins.builtin.correction.CorrectionProvider` is
injected, the plugin attempts to find an AI-ranked correction for each
unknown word.  If a correction is found above the provider's confidence
threshold, the Suggestion carries ``replacement=correction`` as an edit;
otherwise it falls back to the original advisory behaviour
(``replacement=None``).

Without a correction provider, the plugin behaves exactly as before:
advisory-only, no replacement.

Architecture position
---------------------
Figure 5 lists the Spell Checker as the first of eight feature plugins.
It reads the immutable document snapshot and emits suggestions through the
same :class:`~teea.fusion.Suggestion` model every other plugin uses.
The :class:`~teea.plugins.runtime.SupervisedPluginRuntime` supervises it,
and the :class:`~teea.fusion.engine.PriorityRankedFusionEngine` merges its
output with that of other plugins.

Thread safety
-------------
The plugin is stateless after construction (the dictionary repository is
read-only and shared across threads).  It is safe to call from a worker
thread, which is what the Plugin Runtime does when concurrency is enabled.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING

from teea.fusion import Suggestion, SuggestionPriority
from teea.nlp.dependency import DependencyRelation
from teea.nlp.snapshot import DocumentSnapshot
from teea.persistence import DictionaryRepository, default_dictionary

if TYPE_CHECKING:
    from teea.plugins.builtin.correction import CorrectionProvider


class SpellCheckerPlugin:
    """Flags Tibetan morphemes unknown to the corpus-derived dictionary.

    The plugin examines every morpheme in the analysed document.  A morpheme
    whose surface form is not present in the dictionary is flagged as a
    potential misspelling.  Grammatical affixes (particles, case markers) are
    *not* checked -- the dictionary rarely lists them, and an unknown particle
    is likelier to be a parsing gap than a spelling error.

    Args:
        dictionary: The lexicon to check against.  Defaults to the process-wide
            shared :func:`~teea.persistence.dictionary.default_dictionary`.
        correction_provider: Optional AI-backed correction provider.  When set,
            the plugin attempts to find a replacement for each unknown word.
    """

    def __init__(
        self,
        dictionary: DictionaryRepository | None = None,
        correction_provider: CorrectionProvider | None = None,
    ) -> None:
        self._dictionary = dictionary if dictionary is not None else default_dictionary()
        self._correction_provider = correction_provider
        self._name = "teea.spelling"

    @property
    def name(self) -> str:
        """Stable identifier for this plugin."""
        return self._name

    def examine(self, snapshot: DocumentSnapshot) -> Iterable[Suggestion]:
        """Check every morpheme in the document against the dictionary.

        Args:
            snapshot: The immutable analysis of the whole document.

        Yields:
            One advisory :class:`Suggestion` per unknown morpheme, with
            ``replacement=None``.
        """
        for analysis in snapshot.analyses:
            tree = analysis.tree
            if tree.is_empty:
                continue

            for node in tree.nodes:
                if node.relation in (
                    DependencyRelation.PUNCT,
                    DependencyRelation.CASE,
                    DependencyRelation.AUX,
                    DependencyRelation.MARK,
                    DependencyRelation.NEG,
                ) or not node.text.strip("། ཿ"):
                    continue

                surface = node.text
                if not surface:
                    continue

                if surface not in self._dictionary:
                    doc_span = analysis.document_span(node.span)

                    # Attempt AI-assisted correction when a provider is
                    # available.  The sentence text and node span give the
                    # model the context it needs to rank candidates.
                    replacement: str | None = None
                    score = 0.85
                    priority = SuggestionPriority.MEDIUM
                    message = f'Unknown word: "{surface}"'

                    if self._correction_provider is not None:
                        correction = self._correction_provider.correct(
                            word=surface,
                            sentence=analysis.sentence.text,
                            word_start=node.span.char_start,
                            word_end=node.span.char_end,
                        )
                        if correction is not None:
                            replacement = correction
                            score = 0.92
                            priority = SuggestionPriority.HIGH
                            message = (
                                f'Correction: "{surface}" \u2192 "{correction}"'
                            )

                    yield Suggestion(
                        source=self._name,
                        span=doc_span,
                        replacement=replacement,
                        score=score,
                        priority=priority,
                        message=message,
                    )


__all__ = ["SpellCheckerPlugin"]
