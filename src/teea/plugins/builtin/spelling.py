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

from teea.nlp.structural_validator import StructuralValidator, StructuralErrorType

if TYPE_CHECKING:
    from teea.plugins.builtin.correction import CorrectionProvider


def _is_tibetan(text: str) -> bool:
    return any("\u0f00" <= ch <= "\u0fff" for ch in text)


class SpellCheckerPlugin:
    """Flags Tibetan morphemes unknown to the corpus-derived dictionary or structurally invalid.

    Args:
        dictionary: The lexicon to check against.
        correction_provider: Optional AI-backed correction provider.
        corpus_repository: Optional BoCorpusRepository for corpus frequency checks.
        validator: Optional StructuralValidator instance.
    """

    def __init__(
        self,
        dictionary: DictionaryRepository | None = None,
        correction_provider: CorrectionProvider | None = None,
        *,
        corpus_repository: Any = None,
        validator: StructuralValidator | None = None,
    ) -> None:
        self._dictionary = dictionary if dictionary is not None else default_dictionary()
        self._corpus_repository = corpus_repository
        self._correction_provider = correction_provider
        self._validator = validator or StructuralValidator()
        self._name = "teea.spelling"

    @property
    def name(self) -> str:
        """Stable identifier for this plugin."""
        return self._name

    def examine(self, snapshot: DocumentSnapshot) -> Iterable[Suggestion]:
        """Check every morpheme in the document against structural rules and dictionary.

        Args:
            snapshot: The immutable analysis of the whole document.

        Yields:
            One Suggestion per unknown or structurally invalid morpheme.
        """
        for analysis in snapshot.analyses:
            tree = analysis.tree
            if tree.is_empty:
                continue

            for node in tree.nodes:
                if node.relation == DependencyRelation.PUNCT or not node.text.strip("། ཿ"):
                    continue

                if node.relation in (
                    DependencyRelation.CASE,
                    DependencyRelation.AUX,
                    DependencyRelation.MARK,
                    DependencyRelation.NEG,
                ) and not _is_tibetan(node.text):
                    continue

                surface = node.text
                if not surface:
                    continue

                # 1. Structural Validation Layer (HARD FAIL BEFORE DICTIONARY LOOKUP)
                struct_res = self._validator.validate_syllable(surface)
                if not struct_res.is_valid:
                    import structlog
                    structlog.get_logger(__name__).debug(
                        "structural_error_detected",
                        surface=surface,
                        error_type=str(struct_res.error_type),
                        description=struct_res.error_description,
                    )
                    doc_span = analysis.document_span(node.span)
                    replacement = struct_res.suggested_corrections[0] if struct_res.suggested_corrections else None
                    if not replacement and self._correction_provider is not None:
                        replacement = self._correction_provider.correct(
                            word=surface,
                            sentence=analysis.sentence.text,
                            word_start=node.span.char_start,
                            word_end=node.span.char_end,
                        )
                    # FIX: If the character immediately following this span in the
                    # source text is already a tsheg (\u0f0b), strip any trailing
                    # tsheg from the replacement to avoid creating a double tsheg.
                    if replacement and replacement.endswith("\u0f0b"):
                        src = snapshot.source
                        next_char_pos = doc_span.char_end
                        if next_char_pos < len(src) and src[next_char_pos] == "\u0f0b":
                            replacement = replacement.rstrip("\u0f0b")
                    error_type_label = getattr(struct_res.error_type, "value", str(struct_res.error_type))
                    yield Suggestion(
                        source=self._name,
                        span=doc_span,
                        replacement=replacement,
                        score=0.95,
                        priority=SuggestionPriority.HIGH,
                        message=f'Structural Error [{error_type_label}]: {struct_res.error_description}',
                    )
                    continue

                is_known = (surface in self._dictionary) or (
                    self._corpus_repository is not None and self._corpus_repository.is_known_syllable(surface, min_frequency=10)
                )
                if not is_known:
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
