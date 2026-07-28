"""Built-in spell checker plugin for TEEA.

Flags Tibetan morphemes that are not attested in the corpus-derived
Dictionary Repository as potential misspellings.  The plugin emits one
advisory Suggestion per unknown root/content morpheme, scored by the
confidence of the unknown classification.

No candidate replacements are generated
---------------------------------------
The shipped Dictionary Repository (``pos_model.json``) is a POS-statistics
model, not a spelling dictionary.  It knows which surface forms occur in the
reference corpus, but it does not store canonical spellings, known variants,
or edit-distance neighbours.  Generating replacements from it alone would
produce guesses indistinguishable from the original text, so this plugin
emits advisories (``replacement=None``) that annotate the suspected range
without recommending an edit.  A future release with a dedicated spelling
lexicon can add replacements while keeping the same detection logic.

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

from teea.fusion import Suggestion, SuggestionPriority
from teea.nlp.dependency import DependencyRelation
from teea.nlp.snapshot import DocumentSnapshot
from teea.persistence import DictionaryRepository, default_dictionary


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
    """

    def __init__(self, dictionary: DictionaryRepository | None = None) -> None:
        self._dictionary = dictionary if dictionary is not None else default_dictionary()
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
                # Skip punctuation and grammatical particles: these are
                # pipeline artifacts, not lexeme candidates.
                if node.relation in (
                    DependencyRelation.PUNCT,
                    DependencyRelation.CASE,
                    DependencyRelation.AUX,
                    DependencyRelation.MARK,
                    DependencyRelation.NEG,
                ):
                    continue

                surface = node.text
                if not surface:
                    continue

                if surface not in self._dictionary:
                    doc_span = analysis.document_span(node.span)
                    yield Suggestion(
                        source=self._name,
                        span=doc_span,
                        replacement=None,
                        score=0.85,
                        priority=SuggestionPriority.MEDIUM,
                        message=f"Unknown word: \"{surface}\"",
                    )


__all__ = ["SpellCheckerPlugin"]
