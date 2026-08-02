"""Unit tests for grapheme-aware edit distance (:mod:`teea.nlp.edit_distance`)."""

from __future__ import annotations

from teea.nlp.edit_distance import (
    damerau_levenshtein,
    tibetan_damerau,
    tibetan_graphemes,
)


class TestTibetanGraphemes:
    def test_groups_base_letter_with_subjoined_consonant(self) -> None:
        # བ + ཀ + ྲ (subjoined RA) -> [བ, ཀྲ]
        assert tibetan_graphemes("བཀྲ") == ["བ", "ཀྲ"]

    def test_groups_base_letter_with_vowel_sign(self) -> None:
        # ཀ + ི (vowel sign I) -> [ཀི]
        assert tibetan_graphemes("ཀི") == ["ཀི"]

    def test_ascii_passes_through_unchanged(self) -> None:
        assert tibetan_graphemes("abc") == ["a", "b", "c"]

    def test_empty_string(self) -> None:
        assert tibetan_graphemes("") == []

    def test_tsheg_is_its_own_unit(self) -> None:
        assert tibetan_graphemes("བཀྲ་") == ["བ", "ཀྲ", "་"]


class TestDamerauLevenshtein:
    def test_identical_sequences(self) -> None:
        assert damerau_levenshtein(["a", "b"], ["a", "b"]) == 0

    def test_substitution(self) -> None:
        assert damerau_levenshtein(["a", "b"], ["a", "x"]) == 1

    def test_adjacent_transposition_is_one_edit(self) -> None:
        assert damerau_levenshtein(["a", "b"], ["b", "a"]) == 1

    def test_insertion(self) -> None:
        assert damerau_levenshtein(["a", "c"], ["a", "b", "c"]) == 1

    def test_classic_kitten_sitting(self) -> None:
        assert damerau_levenshtein(list("kitten"), list("sitting")) == 3


class TestTibetanDamerau:
    def test_subjoined_consonant_change_is_one_edit(self) -> None:
        # བཀྲ (subjoined KA) -> བགྲ (subjoined GA): one grapheme substitution.
        assert tibetan_damerau("བཀྲ", "བགྲ") == 1

    def test_dropping_whole_subjoined_stack_is_one_edit(self) -> None:
        assert tibetan_damerau("བཀྲ", "བཀ") == 1

    def test_vowel_sign_change_is_one_edit(self) -> None:
        # ཀི (vowel I) -> ཀུ (vowel U): one grapheme substitution.
        assert tibetan_damerau("ཀི", "ཀུ") == 1

    def test_tibetan_transposition(self) -> None:
        assert tibetan_damerau("བཀ", "ཀབ") == 1

    def test_ascii_delegates_to_codepoints(self) -> None:
        assert tibetan_damerau("abc", "axc") == 1
        assert tibetan_damerau("kitten", "sitting") == 3

    def test_identical_is_zero(self) -> None:
        assert tibetan_damerau("བཀྲ་ཤིས", "བཀྲ་ཤིས") == 0
