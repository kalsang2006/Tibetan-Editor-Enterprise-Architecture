"""TiBERT-backed tokenizer implementation.

This module wraps the authoritative TiBERT tokenizer (``CMLI-NLP/TiBERT``, a
WordPiece vocabulary of 29,965 entries, verified against the published model)
behind the
:class:`~teea.nlp.tokenization.interfaces.Tokenizer` protocol and produces the
richly-typed :class:`~teea.nlp.tokenization.models.EncodedText` result.

Key design decisions
--------------------
* **Respect TiBERT exactly.** We load TiBERT's own tokenizer via Hugging Face
  ``AutoTokenizer``; we do not re-implement or substitute segmentation. The
  vocabulary, special tokens and merges are TiBERT's.
* **Dependency injection for testability.** The Hugging Face backend is obtained
  through an injected *loader* callable. Production uses
  :func:`default_tibert_loader` (which lazily imports ``transformers`` so the
  heavy dependency is only touched when actually loading a model). Tests inject
  a lightweight fake implementing the same small backend surface, so the
  wrapper's orchestration logic is verified without any model download.
* **Explicit normalization boundary.** The wrapper normalizes input (pipeline
  Stage 2) via an injected :class:`TextNormalizer` before tokenizing (Stage 5),
  and all emitted spans refer to the *normalized* string.
* **Offsets are best-effort, never fatal.** Token ids and pieces are always
  produced (they are what model inference needs). Character/byte spans are
  additionally computed — from the fast tokenizer's native offset mapping when
  available, otherwise via a SentencePiece-aware forward aligner. If a given
  piece cannot be aligned, its span is ``None`` and a warning is logged; the
  encode call still succeeds.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any, Protocol, runtime_checkable

from teea.core.config import TokenizationSettings
from teea.core.logging import get_logger
from teea.core.types import TextSpan
from teea.nlp.tokenization.exceptions import (
    DetokenizationError,
    EmptyInputError,
    InputNotStringError,
    InputTooLongError,
    TokenizationError,
    TokenizerLoadError,
)
from teea.nlp.tokenization.models import EncodedText, Token
from teea.nlp.tokenization.normalization import TextNormalizer

_logger = get_logger(__name__)

#: SentencePiece metaspace marker denoting a word boundary (leading space).
_METASPACE = "\u2581"  # ▁

#: WordPiece continuation prefix (used by some BERT tokenizers).
_WORDPIECE_CONT = "##"


@runtime_checkable
class BackendTokenizer(Protocol):
    """Minimal surface of the Hugging Face tokenizer the wrapper relies upon.

    Declaring this explicitly (rather than depending on the full
    ``PreTrainedTokenizerBase``) keeps the coupling small and makes the fake used
    in tests obvious and faithful.
    """

    is_fast: bool
    unk_token_id: int | None
    all_special_ids: list[int]

    def get_vocab(self) -> dict[str, int]:
        """Return the full token-to-id vocabulary mapping."""
        ...

    def convert_ids_to_tokens(self, ids: list[int]) -> list[str]:
        """Convert a list of ids to their surface piece strings."""
        ...

    def decode(self, ids: Sequence[int], *, skip_special_tokens: bool) -> str:
        """Decode ids back to text."""
        ...

    def __call__(
        self,
        text: str,
        *,
        add_special_tokens: bool,
        truncation: bool,
        max_length: int,
        return_offsets_mapping: bool,
    ) -> Mapping[str, Any]:
        """Tokenize ``text`` and return at least an ``input_ids`` entry."""
        ...


BackendLoader = Callable[[TokenizationSettings], BackendTokenizer]


def default_tibert_loader(settings: TokenizationSettings) -> BackendTokenizer:
    """Load the real TiBERT tokenizer via Hugging Face ``AutoTokenizer``.

    ``transformers`` is imported lazily so that importing this module (and unit
    testing the wrapper with a fake backend) does not require the heavy
    dependency or any network access.

    Args:
        settings: Tokenization settings (model id/path, cache dir, options).

    Returns:
        A loaded backend tokenizer.

    Raises:
        TokenizerLoadError: If the tokenizer cannot be loaded.
    """
    try:
        from transformers import AutoTokenizer  # noqa: PLC0415 (intentional lazy import)
    except ImportError as exc:  # pragma: no cover - environment-specific
        raise TokenizerLoadError(
            "The 'transformers' package is required to load TiBERT.",
            context={"model_id": settings.model_id},
            cause=exc,
        ) from exc

    source = (
        str(settings.model_local_path)
        if settings.model_local_path is not None
        else settings.model_id
    )
    try:
        backend = AutoTokenizer.from_pretrained(
            source,
            cache_dir=str(settings.model_cache_dir),
            use_fast=True,
            trust_remote_code=settings.trust_remote_code,
            # TiBERT's published tokenizer_config.json sets do_lower_case=True,
            # which switches on BERT's basic-tokenizer accent stripping. That
            # routine deletes every Unicode Mn character -- and in Tibetan the Mn
            # class is not accents but the vowel signs and subjoined letters that
            # carry the orthography. Left at the model default it silently
            # rewrites བཀྲ as བཀ and turns ཤིས into [UNK].
            #
            # Passing the configured value (False for Tibetan, which is caseless)
            # and pinning strip_accents=False keeps the script intact.
            do_lower_case=settings.do_lower_case,
            strip_accents=False,
        )
    except Exception as exc:  # convert any load failure to a typed error
        raise TokenizerLoadError(
            "Failed to load the TiBERT tokenizer.",
            context={"source": source, "cache_dir": str(settings.model_cache_dir)},
            cause=exc,
        ) from exc

    return backend  # type: ignore[return-value]


def _piece_surface(piece: str) -> str:
    """Return the human-facing surface of a subword piece.

    Strips the SentencePiece metaspace marker or a WordPiece continuation
    prefix, if present.
    """
    if piece.startswith(_METASPACE):
        return piece[len(_METASPACE) :]
    if piece.startswith(_WORDPIECE_CONT):
        return piece[len(_WORDPIECE_CONT) :]
    return piece


def _is_continuation(piece: str, has_any_metaspace: bool) -> bool:
    """Best-effort determination of whether a piece continues the prior word.

    Args:
        piece: The raw subword piece.
        has_any_metaspace: Whether the sequence uses SentencePiece metaspace
            markers at all (affects how to interpret the absence of a marker).
    """
    if piece.startswith(_WORDPIECE_CONT):
        return True
    if has_any_metaspace:
        # In SentencePiece output, a leading ▁ marks a word start; its absence
        # marks a continuation piece.
        return not piece.startswith(_METASPACE)
    return False


class TiBERTTokenizer:
    """Tokenizer implementation backed by the TiBERT SentencePiece model.

    Satisfies the :class:`~teea.nlp.tokenization.interfaces.Tokenizer` protocol.
    All heavy state (the backend tokenizer) is loaded once at construction; the
    instance is safe to reuse for read-only tokenization.

    Args:
        settings: Tokenization settings.
        normalizer: Text normalizer applied before tokenization. If ``None``, a
            :class:`TextNormalizer` is constructed from ``settings``.
        loader: Backend loader. Defaults to :func:`default_tibert_loader`.
            Injecting a fake enables model-free unit testing.

    Raises:
        TokenizerLoadError: If the backend fails to load.
    """

    def __init__(
        self,
        settings: TokenizationSettings,
        *,
        normalizer: TextNormalizer | None = None,
        loader: BackendLoader = default_tibert_loader,
    ) -> None:
        self._settings = settings
        self._normalizer = normalizer or TextNormalizer(
            form=settings.normalization_form,
            collapse_whitespace=True,
            strip_controls=True,
        )
        _logger.info(
            "loading_tokenizer",
            model_id=settings.model_id,
            local_path=str(settings.model_local_path) if settings.model_local_path else None,
        )
        self._backend = loader(settings)
        self._vocab_size = len(self._backend.get_vocab())
        self._special_ids = frozenset(self._backend.all_special_ids)
        self._unk_id = self._backend.unk_token_id
        _logger.info(
            "tokenizer_loaded",
            model_id=settings.model_id,
            vocab_size=self._vocab_size,
            is_fast=self._backend.is_fast,
        )

    # -- Introspection ------------------------------------------------------
    @property
    def vocab_size(self) -> int:
        """Number of entries in the TiBERT vocabulary."""
        return self._vocab_size

    @property
    def model_id(self) -> str:
        """The configured model identifier."""
        return self._settings.model_id

    # -- Core operations ----------------------------------------------------
    def encode(
        self,
        text: str,
        *,
        add_special_tokens: bool | None = None,
        truncate: bool = False,
    ) -> EncodedText:
        """Encode ``text`` into an :class:`EncodedText`.

        See :meth:`Tokenizer.encode` for the contract.
        """
        self._validate_input(text)
        add_special = (
            self._settings.add_special_tokens if add_special_tokens is None else add_special_tokens
        )
        normalized = self._normalizer.normalize(text)
        if not normalized:
            raise EmptyInputError()

        max_len = self._settings.max_sequence_length

        try:
            offsets_supported = bool(self._backend.is_fast)
            encoding = self._backend(
                normalized,
                add_special_tokens=add_special,
                truncation=truncate,
                max_length=max_len,
                return_offsets_mapping=offsets_supported,
            )
        except TokenizationError:
            raise
        except Exception as exc:  # normalize backend failures into the taxonomy
            _logger.error("tokenization_backend_failed", error=str(exc))
            raise TokenizationError(
                "TiBERT backend failed to tokenize input.",
                cause=exc,
            ) from exc

        ids = list(encoding["input_ids"])
        if truncate and len(ids) == max_len:
            # Cannot distinguish exact-fit from truly-truncated by the output
            # alone, so check the pre-truncation length with a second call.
            pre_ids = self._backend(
                normalized,
                add_special_tokens=add_special,
                truncation=False,
                max_length=max_len,
                return_offsets_mapping=False,
            )["input_ids"]
            was_truncated = len(pre_ids) > max_len
        else:
            was_truncated = False

        if not truncate and len(ids) > max_len:
            raise InputTooLongError(produced=len(ids), maximum=max_len)

        pieces = self._backend.convert_ids_to_tokens(ids)
        offset_mapping = encoding.get("offset_mapping") if offsets_supported else None
        spans = self._resolve_spans(normalized, ids, pieces, offset_mapping)

        tokens = self._build_tokens(ids, pieces, spans)

        return EncodedText(
            source=text,
            normalized=normalized,
            tokens=tuple(tokens),
            ids=tuple(ids),
            num_special_tokens=sum(1 for t in tokens if t.is_special),
            was_truncated=was_truncated,
        )

    def tokenize(self, text: str) -> list[str]:
        """Return surface subword pieces (no special tokens)."""
        encoded = self.encode(text, add_special_tokens=False)
        return [t.piece for t in encoded.tokens]

    def decode(self, ids: Sequence[int], *, skip_special_tokens: bool = True) -> str:
        """Decode vocabulary ids back to text."""
        if not isinstance(ids, Sequence) or isinstance(ids, (str, bytes)):
            raise InputNotStringError(type(ids).__name__)
        try:
            return self._backend.decode(list(ids), skip_special_tokens=skip_special_tokens)
        except Exception as exc:  # normalize backend failures into the taxonomy
            _logger.error("detokenization_failed", error=str(exc))
            raise DetokenizationError(
                "Failed to decode token ids.",
                context={"num_ids": len(ids)},
                cause=exc,
            ) from exc

    # -- Internals ----------------------------------------------------------
    @staticmethod
    def _validate_input(text: object) -> None:
        """Validate that ``text`` is a non-empty string."""
        if not isinstance(text, str):
            raise InputNotStringError(type(text).__name__)
        if not text.strip():
            raise EmptyInputError()

    def _build_tokens(
        self,
        ids: list[int],
        pieces: list[str],
        spans: list[TextSpan | None],
    ) -> list[Token]:
        """Assemble :class:`Token` objects from ids, pieces and spans."""
        has_any_metaspace = any(p.startswith(_METASPACE) for p in pieces)
        tokens: list[Token] = []
        for token_id, piece, span in zip(ids, pieces, spans, strict=True):
            is_special = token_id in self._special_ids
            tokens.append(
                Token(
                    id=token_id,
                    piece=piece,
                    text=_piece_surface(piece),
                    span=None if is_special else span,
                    is_special=is_special,
                    is_unknown=(self._unk_id is not None and token_id == self._unk_id),
                    is_continuation=(
                        False if is_special else _is_continuation(piece, has_any_metaspace)
                    ),
                )
            )
        return tokens

    def _resolve_spans(
        self,
        normalized: str,
        ids: list[int],
        pieces: list[str],
        offset_mapping: Sequence[tuple[int, int]] | None,
    ) -> list[TextSpan | None]:
        """Resolve character/byte spans for each piece.

        Prefers the fast tokenizer's native offset mapping; otherwise falls back
        to a forward aligner. Never raises: unresolved pieces get ``None``.
        """
        byte_prefix = self._byte_prefix(normalized)

        if offset_mapping is not None:
            return self._spans_from_offset_mapping(offset_mapping, byte_prefix, len(normalized))

        return self._spans_from_alignment(normalized, ids, pieces, byte_prefix)

    @staticmethod
    def _byte_prefix(text: str) -> list[int]:
        prefix = [0] * (len(text) + 1)
        for index, char in enumerate(text):
            prefix[index + 1] = prefix[index] + len(char.encode("utf-8"))
        return prefix

    def _spans_from_offset_mapping(
        self,
        offset_mapping: Sequence[tuple[int, int]],
        byte_prefix: list[int],
        text_len: int,
    ) -> list[TextSpan | None]:
        spans: list[TextSpan | None] = []
        for start, end in offset_mapping:
            # Special tokens are reported as (0, 0) by Hugging Face.
            if end <= start or end > text_len:
                spans.append(None)
                continue
            spans.append(
                TextSpan(
                    char_start=start,
                    char_end=end,
                    byte_start=byte_prefix[start],
                    byte_end=byte_prefix[end],
                )
            )
        return spans

    def _spans_from_alignment(
        self,
        normalized: str,
        ids: list[int],
        pieces: list[str],
        byte_prefix: list[int],
    ) -> list[TextSpan | None]:
        spans: list[TextSpan | None] = []
        cursor = 0
        alignment_lost = False
        for token_id, piece in zip(ids, pieces, strict=True):
            # Special tokens ([CLS], [SEP], ...) have no extent in the source
            # text. They must be skipped outright: searching for their literal
            # surface always fails, which would otherwise latch `alignment_lost`
            # and strip the spans from every content token that follows.
            if token_id in self._special_ids:
                spans.append(None)
                continue
            surface = _piece_surface(piece)
            if alignment_lost or surface == "":
                spans.append(None)
                continue
            index = normalized.find(surface, cursor)
            if index == -1:
                # Could not locate this piece; stop trying to align the rest to
                # avoid emitting misleading spans, but keep tokens usable.
                _logger.warning(
                    "offset_alignment_lost",
                    piece=piece,
                    cursor=cursor,
                )
                spans.append(None)
                alignment_lost = True
                continue
            end = index + len(surface)
            spans.append(
                TextSpan(
                    char_start=index,
                    char_end=end,
                    byte_start=byte_prefix[index],
                    byte_end=byte_prefix[end],
                )
            )
            cursor = end
        return spans


__all__ = [
    "BackendLoader",
    "BackendTokenizer",
    "TiBERTTokenizer",
    "default_tibert_loader",
]
