"""Unit tests for the character-bigram inverted index.

Covers indexing, querying, self-exclusion, short-word handling, and the
recall-first contract (candidates share at least one bigram; the caller
filters by real edit distance).
"""

from __future__ import annotations

from teea.nlp.char_bigram_index import CharBigramIndex


class TestCharBigramIndex:
    def test_size_counts_distinct_words(self) -> None:
        index = CharBigramIndex(["བཀྲ", "བཀྲ", "ཤིས"])
        assert index.size == 2
        assert len(index) == 2

    def test_query_returns_words_sharing_a_bigram(self) -> None:
        index = CharBigramIndex(["བཀྲ", "བགྲ", "ཤིས"])
        candidates = index.query("བཀྲ")
        assert "བགྲ" in candidates  # shares the ྲ-word-end bigram
        assert "ཤིས" not in candidates

    def test_query_never_returns_the_query_word_itself(self) -> None:
        index = CharBigramIndex(["abc", "abd"])
        assert "abc" not in index.query("abc")

    def test_query_ranks_by_number_of_shared_bigrams(self) -> None:
        index = CharBigramIndex(["abcd", "abce", "abef"])
        # "abce" shares two bigrams with "abcd" (ab, bc); "abef" shares one (ab).
        assert index.query("abcd")[0] == "abce"

    def test_short_words_with_no_bigram_overlap_return_nothing(self) -> None:
        index = CharBigramIndex(["ab", "cd"])
        assert index.query("ab") == []

    def test_short_word_matching_on_word_end_sentinel(self) -> None:
        # "ab" vs "xb": the trailing-bigram (word-end sentinel) distinguishes
        # forms that would otherwise share nothing.
        index = CharBigramIndex(["ab", "xb"])
        assert "xb" in index.query("ab")

    def test_query_empty_string_returns_empty(self) -> None:
        index = CharBigramIndex(["abc"])
        assert index.query("") == []
        assert index.query("   ") == []

    def test_add_extends_the_index(self) -> None:
        index = CharBigramIndex(["abc"])
        index.add("abd")
        assert index.size == 2
        assert "abd" in index.query("abc")

    def test_add_is_idempotent(self) -> None:
        index = CharBigramIndex(["abc"])
        index.add("abc")
        assert index.size == 1

    def test_empty_and_blank_words_are_skipped(self) -> None:
        index = CharBigramIndex(["", "   ", "abc"])
        assert index.size == 1
        assert index.query("abc") == []
