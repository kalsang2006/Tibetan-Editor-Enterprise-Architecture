"""The tokenizer abstraction (interface) for TEEA.

Downstream layers — the Language Server pipeline, the AI Runtime, plugins —
depend on this :class:`Tokenizer` protocol, **not** on the concrete
TiBERT implementation. This is the Dependency Inversion Principle in practice:
high-level policy depends on an abstraction, and the concrete tokenizer is
injected. It also keeps unit tests fast, because a lightweight fake can satisfy
the same contract without loading a model.

The interface is intentionally small (Interface Segregation): encode, decode,
tokenize, plus read-only vocabulary introspection. Anything richer (syllable
segmentation, normalization) lives in dedicated collaborators rather than being
bolted onto every tokenizer implementation.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from teea.nlp.tokenization.models import EncodedText


@runtime_checkable
class Tokenizer(Protocol):
    """A Tibetan tokenizer contract.

    Implementations must be safe to share across threads for read-only
    operations once initialized (the TiBERT implementation loads all state at
    construction and performs no mutation during tokenization).
    """

    @property
    def vocab_size(self) -> int:
        """Number of entries in the tokenizer vocabulary."""
        ...

    @property
    def model_id(self) -> str:
        """Identifier of the underlying model/vocabulary."""
        ...

    def encode(
        self,
        text: str,
        *,
        add_special_tokens: bool | None = None,
        truncate: bool = False,
    ) -> EncodedText:
        """Encode text into an :class:`EncodedText` result.

        Args:
            text: Input text. Implementations validate type/emptiness and apply
                Unicode normalization before tokenizing.
            add_special_tokens: Override for whether to add ``[CLS]``/``[SEP]``.
                ``None`` uses the configured default.
            truncate: When ``True``, silently truncate to the maximum sequence
                length instead of raising.

        Returns:
            The encoding result.

        Raises:
            teea.nlp.tokenization.exceptions.TokenizationError: On invalid input
                or backend failure.
        """
        ...

    def tokenize(self, text: str) -> list[str]:
        """Return the surface subword pieces for text (no special tokens).

        Args:
            text: Input text.

        Returns:
            Ordered list of subword piece strings.
        """
        ...

    def decode(self, ids: Sequence[int], *, skip_special_tokens: bool = True) -> str:
        """Decode vocabulary ids back into text.

        Args:
            ids: Vocabulary ids to decode.
            skip_special_tokens: Whether to omit special tokens from the output.

        Returns:
            The decoded text.

        Raises:
            teea.nlp.tokenization.exceptions.DetokenizationError: On failure.
        """
        ...


__all__ = ["Tokenizer"]
