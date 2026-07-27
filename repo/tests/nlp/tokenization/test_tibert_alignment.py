from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, ClassVar

from teea.core.config import TokenizationSettings
from teea.nlp.tokenization.tibert import TiBERTTokenizer

_SILENT_CLS = 1
_SILENT_SEP = 2


class _MisalignedBackend:
    """A slow (non-fast) tokenizer whose pieces do not tile the input exactly.

    Exercises the ``_spans_from_alignment`` paths where:
    - a piece is a pure prefix that strips to empty surface (line 428-429)
    - a piece cannot be found in the normalized text (lines 435-442)
    """

    is_fast: bool = False
    unk_token_id: int | None = 3
    all_special_ids: ClassVar[list[int]] = [0, 1, 2, 3, 4]

    def __init__(self) -> None:
        self._counter = 100
        self._id_to_piece: dict[int, str] = {
            1: "[CLS]",
            2: "[SEP]",
            3: "[UNK]",
            0: "[PAD]",
            4: "[MASK]",
        }

    def get_vocab(self) -> dict[str, int]:
        return {"a": 1}

    def convert_ids_to_tokens(self, ids: list[int]) -> list[str]:
        return [self._id_to_piece.get(i, "[UNK]") for i in ids]

    def decode(self, ids: Sequence[int], *, skip_special_tokens: bool) -> str:
        parts: list[str] = []
        for i in ids:
            if skip_special_tokens and i in self.all_special_ids:
                continue
            parts.append(self._id_to_piece.get(i, ""))
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
        ids: list[int] = []
        if add_special_tokens:
            ids.append(_SILENT_CLS)

        # First content piece: a pure metaspace marker (surface is "")
        self._id_to_piece[self._counter] = "\u2581"
        ids.append(self._counter)
        self._counter += 1

        # Second content piece: something not in the normalized text
        self._id_to_piece[self._counter] = "\u2581NONEXISTENT"
        ids.append(self._counter)
        self._counter += 1

        if add_special_tokens:
            ids.append(_SILENT_SEP)

        result: dict[str, Any] = {"input_ids": ids}
        if return_offsets_mapping:
            result["offset_mapping"] = [(0, 0)] * len(ids)
        return result


def test_alignment_handles_empty_surface_and_missing_piece() -> None:
    settings = TokenizationSettings()
    tokenizer = TiBERTTokenizer(settings, loader=lambda _s: _MisalignedBackend())
    encoded = tokenizer.encode("test", add_special_tokens=False)
    # The encode must not raise; pieces that cannot be aligned get None spans.
    assert encoded.num_content_tokens >= 2
    assert all(t.span is None for t in encoded.tokens if not t.is_special)


def test_alignment_stays_resilient_after_alignment_loss() -> None:
    """After one unalignable piece, subsequent pieces also get None spans."""
    settings = TokenizationSettings()
    tokenizer = TiBERTTokenizer(settings, loader=lambda _s: _MisalignedBackend())
    encoded = tokenizer.encode("test", add_special_tokens=True)
    assert encoded.num_tokens > 0
    for token in encoded.tokens:
        if token.is_special:
            assert token.span is None
