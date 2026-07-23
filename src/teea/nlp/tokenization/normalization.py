"""Unicode normalization and document cleaning (Language pipeline Stage 2).

The architecture separates *normalization* from *tokenization* (Stage 5).
Keeping it standalone means the plagiarism pipeline, the spell checker and the
tokenizer all share one canonical, well-tested normalization implementation
rather than each rolling its own — satisfying DRY and guaranteeing consistent
behavior across features.

Scope: Stages 2 **and** 3
-------------------------
Per ADR-001 (``docs/ARCHITECTURE_DECISIONS.md``), this module owns Figure 5's
Stage 2 (Unicode Normalization) *and* Stage 3 (Document Cleaning). Stage 3 is an
activity, not a component: it appears in Figure 5's pipeline view but in neither
Figure 1's nor Figure 2's component views, whereas Unicode Normalization appears
in both kinds. The mapping is:

* Stage 2 — normalize Unicode, canonical form: :func:`unicodedata.normalize`.
* Stage 2 — remove invalid characters: ``strip_controls``.
* Stage 3 — remove hidden formatting: ``strip_controls``.
* Stage 3 — normalize whitespace: ``collapse_whitespace``.
* Stage 3 — standardize punctuation: **deliberately not implemented.** No
  document specifies what it means for Tibetan, and the obvious reading —
  folding shad variants to a canonical form — would destroy information the rest
  of the system depends on, since sentence segmentation records the terminator
  verbatim so a *nyis shad* stays distinguishable. See ADR-001 before adding it.

Why normalization matters for Tibetan
-------------------------------------
Tibetan Unicode permits multiple byte sequences that render identically (for
example, precomposed vs decomposed stacks). Feeding inconsistent forms to a
SentencePiece model degrades tokenization and inflates the unknown-token rate.
Normalizing to a canonical form (NFC by default) before tokenizing is standard
practice and materially improves downstream quality.

The normalizer is deliberately conservative: it applies Unicode normalization,
optional whitespace collapsing and control-character stripping, but it does
**not** alter Tibetan letters, reorder stacks or "correct" spelling — those are
the jobs of dedicated linguistic components, not the normalizer.
"""

from __future__ import annotations

import unicodedata

from teea.core.config import NormalizationForm
from teea.core.logging import get_logger
from teea.core.types import LINE_BREAK_CHARS
from teea.nlp.tokenization.exceptions import NormalizationError

_logger = get_logger(__name__)

# Characters removed during cleaning: the Unicode "Cc" (control) and "Cf"
# (format) categories, excluding the ones we explicitly preserve below.
#
# Line breaks are preserved because they are document *structure*, not
# hidden formatting: sentence segmentation (Stage 4) treats them as
# boundaries, and Word encodes a paragraph mark as CR and a manual line
# break as VT. Stripping them here merged every paragraph of a document
# into a single runaway sentence. The set is shared with Stage 4 so the two
# stages cannot drift apart.
_PRESERVED_CONTROLS = frozenset({"\t"}) | LINE_BREAK_CHARS


class TextNormalizer:
    """Applies canonical Unicode normalization and light cleaning to text.

    The normalizer is stateless and safe to share across threads.

    Args:
        form: Unicode normalization form to apply.
        collapse_whitespace: When ``True``, runs of whitespace are collapsed to
            a single ASCII space and the result is stripped. Tibetan intra-word
            structure uses the tsheg (not spaces), so collapsing whitespace is
            safe and useful for cleaning copy-pasted text. Note that this folds
            *all* Unicode whitespace, not only ASCII: U+00A0 NO-BREAK SPACE and
            U+3000 IDEOGRAPHIC SPACE are also replaced by an ordinary space.
            It also supersedes the newline/tab preservation performed by
            ``strip_controls``, which is therefore only observable when
            ``collapse_whitespace`` is ``False``.
        strip_controls: When ``True``, Unicode control/format characters (except
            newline and tab) are removed.
    """

    def __init__(
        self,
        *,
        form: NormalizationForm = "NFC",
        collapse_whitespace: bool = True,
        strip_controls: bool = True,
    ) -> None:
        self._form = form
        self._collapse_whitespace = collapse_whitespace
        self._strip_controls = strip_controls

    @property
    def form(self) -> NormalizationForm:
        """The active normalization form."""
        return self._form

    def normalize(self, text: str) -> str:
        """Normalize and lightly clean ``text``.

        The operation is idempotent: ``normalize(normalize(x)) == normalize(x)``.

        Args:
            text: Input text.

        Returns:
            The normalized text.

        Raises:
            NormalizationError: If normalization fails for any reason.
        """
        try:
            # Control/format characters are removed *before* normalizing. A
            # format character (e.g. U+200B, endemic in copy-pasted Tibetan)
            # sitting between two combining marks acts as a canonical-ordering
            # blocker: normalizing first would leave the surviving marks in
            # non-canonical order once the blocker is stripped, so the result
            # would not be normalized and the idempotence guarantee above would
            # not hold. Tibetan stacks vowel signs of differing combining
            # classes (e.g. U+0F71 ccc=129, U+0F74 ccc=132), so this is a real
            # ordering hazard for this script rather than a theoretical one.
            result = self._remove_controls(text) if self._strip_controls else text

            result = unicodedata.normalize(self._form, result)

            # Collapsing cannot denormalize: whitespace characters are starters,
            # and each run is replaced by a single space that still separates
            # the surrounding combining sequences.
            if self._collapse_whitespace:
                result = " ".join(result.split())

            return result
        except NormalizationError:
            raise
        except Exception as exc:  # pragma: no cover - defensive
            _logger.error("normalization_failed", form=self._form, error=str(exc))
            raise NormalizationError(
                "Failed to normalize text.",
                context={"form": self._form},
                cause=exc,
            ) from exc

    @staticmethod
    def _remove_controls(text: str) -> str:
        """Remove control/format characters except preserved whitespace."""
        return "".join(
            ch
            for ch in text
            if ch in _PRESERVED_CONTROLS or unicodedata.category(ch) not in {"Cc", "Cf"}
        )


__all__ = ["TextNormalizer"]