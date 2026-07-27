from __future__ import annotations

import pytest

from teea.core.types import is_tibetan_char, tibetan_ratio


def test_is_tibetan_char_with_multi_character_raises() -> None:
    with pytest.raises(ValueError, match="single character"):
        is_tibetan_char("ab")


def test_is_tibetan_char_with_empty_string_raises() -> None:
    with pytest.raises(ValueError, match="single character"):
        is_tibetan_char("")


def test_tibetan_ratio_with_empty_input_is_zero() -> None:
    assert tibetan_ratio("") == 0.0


def test_tibetan_ratio_with_whitespace_only_is_zero() -> None:
    assert tibetan_ratio("   ") == 0.0
