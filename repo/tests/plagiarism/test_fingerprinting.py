"""Tests for document fingerprint generation."""

from __future__ import annotations

import pytest

from teea.plagiarism.fingerprinting import hash_set, normalize_and_fingerprint
from teea.plagiarism.models import Fingerprint


class TestNormalizeAndFingerprint:
    def test_empty_text_returns_empty_set(self) -> None:
        text, fps = normalize_and_fingerprint("")
        assert text == ""
        assert fps == frozenset()

    def test_short_text_returns_empty_set(self) -> None:
        text, fps = normalize_and_fingerprint("ab")
        assert fps == frozenset()

    def test_normalizes_unicode(self) -> None:
        text, fps = normalize_and_fingerprint("a\u0301b", kgram_size=2, winnow_window=2)
        # NFC normalization combines a+´ → á
        assert "\u00e1" in text

    def test_produces_fingerprints(self) -> None:
        text, fps = normalize_and_fingerprint(
            "the quick brown fox jumps over the lazy dog",
            kgram_size=6,
            winnow_window=4,
        )
        assert len(fps) > 0
        assert all(isinstance(fp, Fingerprint) for fp in fps)

    def test_same_text_produces_same_hashes(self) -> None:
        _, fps1 = normalize_and_fingerprint(
            "hello world this is a test",
            kgram_size=4,
            winnow_window=3,
        )
        _, fps2 = normalize_and_fingerprint(
            "hello world this is a test",
            kgram_size=4,
            winnow_window=3,
        )
        assert fps1 == fps2

    def test_tibetan_text(self) -> None:
        text = "བཀྲ་ཤིས་བདེ་ལེགས།"
        _, fps = normalize_and_fingerprint(text, kgram_size=3)
        assert len(fps) > 0

    def test_hash_set_extraction(self) -> None:
        _, fps = normalize_and_fingerprint(
            "hello world test",
            kgram_size=3,
            winnow_window=2,
        )
        hashes = hash_set(fps)
        assert isinstance(hashes, frozenset)
        assert len(hashes) == len(fps)
        assert all(isinstance(h, int) for h in hashes)

    def test_deterministic_across_calls(self) -> None:
        """Same input always produces identical fingerprints."""
        text = "It was the best of times it was the worst of times"
        _, r1 = normalize_and_fingerprint(text, kgram_size=5, winnow_window=3)
        _, r2 = normalize_and_fingerprint(text, kgram_size=5, winnow_window=3)
        _, r3 = normalize_and_fingerprint(text, kgram_size=5, winnow_window=3)
        assert r1 == r2 == r3

    def test_winnow_window_affects_density(self) -> None:
        text = "a" * 100  # 100 identical chars
        # Small window = more fingerprints
        _, small = normalize_and_fingerprint(text, kgram_size=3, winnow_window=2)
        _, large = normalize_and_fingerprint(text, kgram_size=3, winnow_window=10)
        # Small window should produce more or equal fingerprints
        assert len(small) >= len(large)

    def test_kgram_size_affects_results(self) -> None:
        text = "hello world this is a test document"
        _, small = normalize_and_fingerprint(text, kgram_size=3, winnow_window=3)
        _, large = normalize_and_fingerprint(text, kgram_size=8, winnow_window=3)
        # Smaller k-gram = more hashes before winnowing = potentially more fingerprints
        assert len(small) > 0
        assert len(large) > 0
