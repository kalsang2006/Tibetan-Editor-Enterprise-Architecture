"""Immutable domain models produced by the tokenization module.

These are the value objects that cross the boundary out of Stage 5 (Word
Tokenization) of the language processing pipeline. Everything downstream — the
morphological analyzer, the POS tagger, the plugin runtime and ultimately the
Suggestion Fusion Engine — consumes these objects rather than raw backend
output. Isolating them here is what lets the TiBERT backend be replaced or
upgraded without changing a single consumer.

Design decisions
----------------
* **Frozen Pydantic models.** The architecture stores an *immutable document
  snapshot* that every feature plugin reads concurrently. Immutability is
  therefore a correctness requirement, not a stylistic preference: a plugin
  cannot corrupt another plugin's view of the analysis.
* **``extra="forbid"``.** Backend upgrades that start emitting new fields fail
  loudly at the boundary instead of silently propagating unvalidated data.
* **Spans are optional on tokens, mandatory on syllables.** Subword spans come
  from a statistical tokenizer and are best-effort (see
  :mod:`teea.nlp.tokenization.tibert`); syllable spans are computed
  deterministically from the text and are always exact.
* **No dependency on the backend module.** ``models`` sits *below*
  :mod:`teea.nlp.tokenization.tibert` in the dependency graph. In particular
  the surface form of a piece is supplied by the producer rather than recomputed
  here, which keeps the graph acyclic.

All models are hashable and comparable by value, so they can be cached in the
LMDB layer and deduplicated by the fusion engine.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator

from teea.core.types import TextSpan, tibetan_ratio


class Token(BaseModel):
    """A single subword token emitted by the tokenizer.

    A token carries both the raw vocabulary ``piece`` (which may include the
    SentencePiece metaspace marker ``▁`` or a WordPiece ``##`` prefix) and the
    cleaned ``text`` surface. Consumers that render suggestions to the user
    should use ``text``; consumers that reason about the model vocabulary should
    use ``piece``.

    Attributes:
        id: Vocabulary id of the token in the backend model.
        piece: Raw vocabulary piece, including any subword marker.
        text: Human-facing surface form with subword markers stripped.
        span: Character/byte span in the *normalized* text, or ``None`` when the
            token has no source extent (special tokens) or could not be aligned.
        is_special: Whether this is a special token such as ``[CLS]``/``[SEP]``.
        is_unknown: Whether the backend mapped this piece to the unknown token.
        is_continuation: Whether this piece continues the preceding word rather
            than starting a new one.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: int = Field(ge=0)
    piece: str
    text: str
    span: TextSpan | None = None
    is_special: bool = False
    is_unknown: bool = False
    is_continuation: bool = False

    @property
    def has_span(self) -> bool:
        """Whether this token is anchored to a source extent."""
        return self.span is not None

    @property
    def is_content(self) -> bool:
        """Whether this token carries document content (i.e. is not special)."""
        return not self.is_special


class Syllable(BaseModel):
    """An orthographic Tibetan syllable delimited by the tsheg.

    Produced by :class:`~teea.nlp.tokenization.syllable.SyllableSegmenter`.
    Unlike :class:`Token`, a syllable always has an exact span because it is
    derived deterministically from the text rather than from a statistical
    model.

    Attributes:
        text: The syllable's characters, excluding the delimiting tsheg.
        span: Exact character/byte span of ``text`` in the source string.
        has_trailing_tsheg: Whether the syllable was terminated by a tsheg (as
            opposed to a shad, whitespace or end-of-input). Spell checking and
            dadrag handling depend on this distinction.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    text: str
    span: TextSpan
    has_trailing_tsheg: bool = False

    @property
    def is_tibetan(self) -> bool:
        """Whether every character of the syllable is in the Tibetan block."""
        return bool(self.text) and tibetan_ratio(self.text) == 1.0

    def with_tsheg(self) -> str:
        """Return the syllable text with its trailing tsheg restored.

        Useful when reconstructing display text or building dictionary lookup
        keys, since many lexicon entries are stored tsheg-terminated.

        Returns:
            ``text`` followed by a tsheg when ``has_trailing_tsheg`` is set,
            otherwise ``text`` unchanged.
        """
        return f"{self.text}་" if self.has_trailing_tsheg else self.text


class EncodedText(BaseModel):
    """The complete result of encoding one string with the tokenizer.

    This is the object handed to the AI Runtime for inference (``ids``) and to
    the linguistic stages for analysis (``tokens``). It deliberately retains the
    original ``source`` alongside the ``normalized`` form, because the Office.js
    add-in must ultimately map suggestions back onto the user's *original*
    document text, while all spans are expressed against the normalized form.

    Attributes:
        source: The caller-supplied text, exactly as received.
        normalized: The text after Stage 2 normalization. All token spans are
            expressed relative to this string.
        tokens: Ordered tokens, including any special tokens.
        ids: Vocabulary ids, positionally aligned with ``tokens``.
        num_special_tokens: Count of special tokens present in ``tokens``.
        was_truncated: Whether the encoding was cut short at the configured
            maximum sequence length.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    source: str
    normalized: str
    tokens: tuple[Token, ...] = ()
    ids: tuple[int, ...] = ()
    num_special_tokens: int = Field(default=0, ge=0)
    was_truncated: bool = False

    @model_validator(mode="after")
    def _validate_consistency(self) -> EncodedText:
        """Enforce the invariants every consumer is entitled to rely upon."""
        if len(self.ids) != len(self.tokens):
            raise ValueError(
                f"ids/tokens length mismatch: {len(self.ids)} ids vs {len(self.tokens)} tokens"
            )
        if any(token.id != token_id for token, token_id in zip(self.tokens, self.ids, strict=True)):
            raise ValueError("ids must be positionally aligned with token ids")
        actual_special = sum(1 for token in self.tokens if token.is_special)
        if self.num_special_tokens != actual_special:
            raise ValueError(
                f"num_special_tokens={self.num_special_tokens} does not match "
                f"{actual_special} special tokens present"
            )
        return self

    def __len__(self) -> int:
        """Total number of tokens, including special tokens."""
        return len(self.tokens)

    @property
    def num_tokens(self) -> int:
        """Total number of tokens, including special tokens."""
        return len(self.tokens)

    @property
    def content_tokens(self) -> tuple[Token, ...]:
        """Tokens that carry document content (special tokens removed)."""
        return tuple(token for token in self.tokens if not token.is_special)

    @property
    def num_content_tokens(self) -> int:
        """Number of non-special tokens."""
        return len(self.tokens) - self.num_special_tokens

    @property
    def pieces(self) -> tuple[str, ...]:
        """Raw vocabulary pieces for every token, in order."""
        return tuple(token.piece for token in self.tokens)

    @property
    def surfaces(self) -> tuple[str, ...]:
        """Human-facing surface forms for every token, in order."""
        return tuple(token.text for token in self.tokens)

    @property
    def num_unknown(self) -> int:
        """Number of tokens the backend mapped to the unknown token."""
        return sum(1 for token in self.tokens if token.is_unknown)

    @property
    def has_unknown(self) -> bool:
        """Whether any token was mapped to the unknown token.

        A ``True`` value is the primary signal that the input contains script or
        orthography the model was not trained on, and is worth surfacing as a
        diagnostic rather than silently ignoring.
        """
        return self.num_unknown > 0

    @property
    def unknown_ratio(self) -> float:
        """Fraction of *content* tokens that are unknown, in ``[0.0, 1.0]``.

        Special tokens are excluded from the denominator because they are an
        artifact of the encoding, not of the input text. Returns ``0.0`` when
        there are no content tokens.
        """
        denominator = self.num_content_tokens
        if denominator <= 0:
            return 0.0
        return self.num_unknown / denominator

    def token_at_char(self, char_index: int) -> Token | None:
        """Return the token whose span contains ``char_index``.

        The Suggestion Fusion Engine must resolve overlapping range coordinates
        reported by independent plugins; mapping a character offset back to its
        originating token is the primitive that makes that possible.

        Args:
            char_index: Character offset into :attr:`normalized`.

        Returns:
            The first token whose span contains ``char_index``, or ``None`` if
            no aligned token covers that offset.
        """
        for token in self.tokens:
            span = token.span
            if span is not None and span.char_start <= char_index < span.char_end:
                return token
        return None


__all__ = ["EncodedText", "Syllable", "Token"]
