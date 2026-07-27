"""Test doubles for the tokenization module.

:class:`FakeBackendTokenizer` implements the small
:class:`~teea.nlp.tokenization.tibert.BackendTokenizer` protocol that
:class:`~teea.nlp.tokenization.tibert.TiBERTTokenizer` depends on. It lets the
wrapper's orchestration (validation, normalization boundary, special-token
handling, truncation, offset resolution, decoding) be unit-tested deterministically
without downloading the real TiBERT model.

The fake mimics SentencePiece behavior closely enough to exercise the wrapper's
real code paths:

* Content is segmented at the tsheg into contiguous substrings, so both the fast
  (native offset mapping) and slow (forward alignment) span-resolution paths can
  be verified against ground truth.
* The first content piece receives the SentencePiece metaspace marker (``▁``),
  matching how an unspaced Tibetan run is tokenized (one word-start followed by
  continuation pieces).
* Special tokens (``[CLS]``, ``[SEP]``, ``[PAD]``, ``[UNK]``, ``[MASK]``) are
  modeled with fixed ids and reported with ``(0, 0)`` offsets, exactly as
  Hugging Face fast tokenizers do.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

_METASPACE = "\u2581"
_TSHEG_CHARS = frozenset({"\u0f0b", "\u0f0c"})

# Fixed special-token ids used by the fake.
_PAD_ID = 0
_CLS_ID = 1
_SEP_ID = 2
_UNK_ID = 3
_MASK_ID = 4

_SPECIAL_PIECES: dict[int, str] = {
    _PAD_ID: "[PAD]",
    _CLS_ID: "[CLS]",
    _SEP_ID: "[SEP]",
    _UNK_ID: "[UNK]",
    _MASK_ID: "[MASK]",
}


def _segment(text: str) -> list[tuple[str, int, int]]:
    """Segment text into contiguous ``(surface, start, end)`` pieces.

    Pieces are split at the tsheg (kept attached to the preceding syllable). Any
    trailing run (for example a shad) becomes its own piece. The pieces exactly
    tile the input, which is what allows offset ground-truth checks.
    """
    pieces: list[tuple[str, int, int]] = []
    start = 0
    for index, char in enumerate(text):
        if char in _TSHEG_CHARS:
            pieces.append((text[start : index + 1], start, index + 1))
            start = index + 1
    if start < len(text):
        pieces.append((text[start:], start, len(text)))
    return pieces


class FakeBackendTokenizer:
    """An in-memory stand-in for a Hugging Face tokenizer.

    Args:
        is_fast: Whether to advertise native offset-mapping support. Controls
            which span-resolution path the wrapper exercises.
        unk_surface: If set, any content piece whose surface equals this value is
            emitted as the unknown token, letting tests trigger ``has_unknown``.
    """

    def __init__(self, *, is_fast: bool = True, unk_surface: str | None = None) -> None:
        self.is_fast = is_fast
        self.unk_token_id: int | None = _UNK_ID
        self.all_special_ids: list[int] = [_PAD_ID, _CLS_ID, _SEP_ID, _UNK_ID, _MASK_ID]
        self._unk_surface = unk_surface
        self._id_to_piece: dict[int, str] = dict(_SPECIAL_PIECES)
        self._counter = 100
        # A small, fixed base vocabulary so ``vocab_size`` is deterministic.
        self._base_vocab: dict[str, int] = {piece: tid for tid, piece in _SPECIAL_PIECES.items()}
        for offset, letter in enumerate("abcdefghij"):
            self._base_vocab[letter] = 5 + offset

    # -- BackendTokenizer protocol -----------------------------------------
    def get_vocab(self) -> dict[str, int]:
        return dict(self._base_vocab)

    def convert_ids_to_tokens(self, ids: list[int]) -> list[str]:
        return [self._id_to_piece.get(token_id, "[UNK]") for token_id in ids]

    def decode(self, ids: Sequence[int], *, skip_special_tokens: bool) -> str:
        parts: list[str] = []
        for token_id in ids:
            if skip_special_tokens and token_id in self.all_special_ids:
                continue
            piece = self._id_to_piece.get(token_id, "")
            parts.append(piece[len(_METASPACE) :] if piece.startswith(_METASPACE) else piece)
        return "".join(parts)

    def __call__(
        self,
        text: str,
        *,
        add_special_tokens: bool,
        truncation: bool,
        max_length: int,
        return_offsets_mapping: bool,
    ) -> Mapping[str, Any]:
        content: list[tuple[int, int, int]] = []
        for position, (surface, start, end) in enumerate(_segment(text)):
            if self._unk_surface is not None and surface == self._unk_surface:
                token_id = _UNK_ID
                display = "[UNK]"
            else:
                token_id = self._counter
                self._counter += 1
                display = (_METASPACE + surface) if position == 0 else surface
            self._id_to_piece[token_id] = display
            content.append((token_id, start, end))

        sequence: list[tuple[int, int, int]] = []
        if add_special_tokens:
            sequence.append((_CLS_ID, 0, 0))
        sequence.extend(content)
        if add_special_tokens:
            sequence.append((_SEP_ID, 0, 0))

        if truncation and len(sequence) > max_length:
            sequence = sequence[:max_length]

        result: dict[str, Any] = {"input_ids": [token_id for token_id, _, _ in sequence]}
        if return_offsets_mapping:
            result["offset_mapping"] = [(start, end) for _, start, end in sequence]
        return result


__all__ = ["FakeBackendTokenizer"]
