"""Unit tests for tsheg-based syllable segmentation.

Covers :class:`~teea.nlp.tokenization.syllable.SyllableSegmenter` together with
the two behaviours of :class:`~teea.nlp.tokenization.models.Syllable` that only
make sense in the presence of a segmenter: ``is_tibetan`` and ``with_tsheg``.

The centre of gravity of this module is **span ground truth**. Every syllable
claims an exact character span *and* an exact UTF-8 byte span into the source
string, and the rest of the platform — the fusion engine, the IPC boundary and
ultimately the Office.js add-in — trusts those numbers without re-deriving
them. Tibetan code points occupy three UTF-8 bytes, so character offsets and
byte offsets diverge from the very first syllable; a confusion between the two
would be completely invisible in an ASCII-only suite. The span assertions here
are therefore re-derived from the real Milarepa corpus and the real classical
lexicon by slicing the source string (and its UTF-8 encoding) directly, rather
than from hand-written expected numbers.

The remaining sections pin down the delimiter contract: tsheg (both variants)
versus the shad family versus whitespace, what ``has_trailing_tsheg`` means,
that delimiters are never returned as syllables while spans stay absolute, and
the documented scope decision that non-Tibetan runs pass through verbatim.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from itertools import pairwise

import pytest

from teea.core.types import SHAD, TSHEG, TextSpan, is_tibetan_char
from teea.nlp.tokenization import Syllable, SyllableSegmenter

# -- Constants and helpers ---------------------------------------------------

#: Non-breaking tsheg (U+0F0C); a delimiter exactly like the ordinary tsheg.
NON_BREAKING_TSHEG = "༌"

#: The shad family recognised as phrase delimiters: U+0F0D..U+0F12 and U+0F14.
SHAD_FAMILY = ("།", "༎", "༏", "༐", "༑", "༒", "༔")

#: Every character that terminates a syllable without belonging to it.
DELIMITERS = frozenset({TSHEG, NON_BREAKING_TSHEG, *SHAD_FAMILY})

#: The greeting used in the package docstring of ``teea.nlp.tokenization``.
GREETING = "བཀྲ་ཤིས་བདེ་ལེགས།"

#: An independent oracle for "maximal run of non-delimiter characters".
#: Deliberately expressed as a regex rather than a scan, so that it does not
#: reproduce the segmenter's own control flow.
_RUN_PATTERN = re.compile(r"[^་༌།-༒༔\s]+")

#: UTF-8 encodes every Tibetan code point in exactly three bytes.
_TIBETAN_BYTES_PER_CHAR = 3


def _assert_spans_are_ground_truth(text: str, syllables: Sequence[Syllable]) -> None:
    """Assert every span re-slices ``text`` (and its UTF-8 bytes) back to itself."""
    encoded = text.encode("utf-8")
    for syllable in syllables:
        span = syllable.span
        assert text[span.char_start : span.char_end] == syllable.text
        assert encoded[span.byte_start : span.byte_end] == syllable.text.encode("utf-8")
        assert span.char_length == len(syllable.text)
        assert span.byte_length == len(syllable.text.encode("utf-8"))


def _surfaces(syllables: Sequence[Syllable]) -> list[str]:
    """Return just the syllable texts, for readable equality assertions."""
    return [syllable.text for syllable in syllables]


# -- Basic tsheg segmentation ------------------------------------------------


def test_segments_the_package_docstring_greeting(segmenter: SyllableSegmenter) -> None:
    syllables = segmenter.segment(GREETING)
    assert _surfaces(syllables) == ["བཀྲ", "ཤིས", "བདེ", "ལེགས"]
    # The first three are tsheg-terminated; the last is closed by the shad.
    assert [s.has_trailing_tsheg for s in syllables] == [True, True, True, False]
    _assert_spans_are_ground_truth(GREETING, syllables)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("ཀ", ["ཀ"]),
        ("ཀ་", ["ཀ"]),
        ("ཀ་ཁ", ["ཀ", "ཁ"]),
        ("ཀ་ཁ་ག་", ["ཀ", "ཁ", "ག"]),
        ("ཆོས།", ["ཆོས"]),
        ("ཆོས་ཉིད།", ["ཆོས", "ཉིད"]),
        # Leading and repeated delimiters must not manufacture empty syllables.
        ("་ཀ", ["ཀ"]),
        ("ཀ་་ཁ", ["ཀ", "ཁ"]),
        ("ཀ་་་ཁ།།ག", ["ཀ", "ཁ", "ག"]),
    ],
)
def test_tsheg_runs_become_syllables(
    segmenter: SyllableSegmenter, text: str, expected: list[str]
) -> None:
    syllables = segmenter.segment(text)
    assert _surfaces(syllables) == expected
    assert all(syllable.text for syllable in syllables)
    _assert_spans_are_ground_truth(text, syllables)


def test_segmenter_is_stateless_across_calls(segmenter: SyllableSegmenter) -> None:
    first = segmenter.segment(GREETING)
    segmenter.segment("ཡི་གེ་གཞན།")
    # Syllables compare by value, so identical input must give an equal result.
    assert segmenter.segment(GREETING) == first


# -- Span ground truth over the real corpus ----------------------------------


def test_corpus_syllable_text_equals_its_char_span_slice(
    segmenter: SyllableSegmenter, corpus_sentences: list[str]
) -> None:
    assert corpus_sentences, "corpus fixture must not be empty"
    for sentence in corpus_sentences:
        syllables = segmenter.segment(sentence)
        assert syllables, f"expected syllables in {sentence!r}"
        for syllable in syllables:
            span = syllable.span
            assert sentence[span.char_start : span.char_end] == syllable.text


def test_corpus_syllable_text_equals_its_byte_span_slice(
    segmenter: SyllableSegmenter, corpus_sentences: list[str]
) -> None:
    for sentence in corpus_sentences:
        encoded = sentence.encode("utf-8")
        for syllable in segmenter.segment(sentence):
            span = syllable.span
            assert encoded[span.byte_start : span.byte_end] == syllable.text.encode("utf-8")


def test_corpus_byte_offsets_diverge_from_char_offsets(
    segmenter: SyllableSegmenter, corpus_sentences: list[str]
) -> None:
    """Byte offsets must be three times the char offsets for all-Tibetan text."""
    tibetan_only = [
        sentence for sentence in corpus_sentences if all(is_tibetan_char(ch) for ch in sentence)
    ]
    assert tibetan_only, "corpus fixture must contain all-Tibetan sentences"
    diverged = False
    for sentence in tibetan_only:
        for syllable in segmenter.segment(sentence):
            span = syllable.span
            assert span.byte_start == _TIBETAN_BYTES_PER_CHAR * span.char_start
            assert span.byte_end == _TIBETAN_BYTES_PER_CHAR * span.char_end
            diverged = diverged or span.byte_start != span.char_start
    assert diverged, "byte/char divergence was never actually exercised"


def test_corpus_spans_are_non_overlapping_and_increasing(
    segmenter: SyllableSegmenter, corpus_sentences: list[str]
) -> None:
    for sentence in corpus_sentences:
        for previous, current in pairwise(segmenter.segment(sentence)):
            # At least one delimiter always separates two syllables, so the
            # relation is strict, not merely non-overlapping.
            assert previous.span.char_end < current.span.char_start
            assert previous.span.byte_end < current.span.byte_start
            assert previous.span.char_start < current.span.char_start


def test_corpus_gaps_between_spans_are_delimiters_only(
    segmenter: SyllableSegmenter, corpus_sentences: list[str]
) -> None:
    """Spans stay absolute: every character left uncovered is a delimiter."""
    for sentence in corpus_sentences:
        covered = {
            index
            for syllable in segmenter.segment(sentence)
            for index in range(syllable.span.char_start, syllable.span.char_end)
        }
        uncovered = [ch for index, ch in enumerate(sentence) if index not in covered]
        assert all(ch in DELIMITERS or ch.isspace() for ch in uncovered)


def test_corpus_syllables_match_an_independent_regex_oracle(
    segmenter: SyllableSegmenter, corpus_sentences: list[str]
) -> None:
    for sentence in corpus_sentences:
        assert _surfaces(segmenter.segment(sentence)) == _RUN_PATTERN.findall(sentence)


def test_mixed_script_spans_are_hand_verifiable(segmenter: SyllableSegmenter) -> None:
    """A worked example in which character and byte offsets provably disagree."""
    text = "ཀ་abc་ཁ"
    syllables = segmenter.segment(text)
    assert _surfaces(syllables) == ["ཀ", "abc", "ཁ"]
    _assert_spans_are_ground_truth(text, syllables)
    assert [(s.span.char_start, s.span.char_end) for s in syllables] == [(0, 1), (2, 5), (6, 7)]
    # Tibetan characters cost three UTF-8 bytes each, Latin ones cost one.
    assert [(s.span.byte_start, s.span.byte_end) for s in syllables] == [(0, 3), (6, 9), (12, 15)]


# -- The trailing-tsheg flag -------------------------------------------------


@pytest.mark.parametrize(
    ("terminator", "expected"),
    [
        (TSHEG, True),
        (NON_BREAKING_TSHEG, True),
        (SHAD, False),
        ("༔", False),
        (" ", False),
        ("\n", False),
        ("\t", False),
        ("", False),
    ],
    ids=["tsheg", "nb-tsheg", "shad", "gter-shad", "space", "newline", "tab", "end-of-input"],
)
def test_terminator_decides_trailing_tsheg(
    segmenter: SyllableSegmenter, terminator: str, expected: bool
) -> None:
    syllables = segmenter.segment(f"ཆོས{terminator}")
    assert len(syllables) == 1
    assert syllables[0].text == "ཆོས"
    assert syllables[0].has_trailing_tsheg is expected


def test_tsheg_before_a_shad_still_counts_as_tsheg_terminated(
    segmenter: SyllableSegmenter,
) -> None:
    (syllable,) = segmenter.segment("ལེགས་།")
    assert syllable.text == "ལེགས"
    assert syllable.has_trailing_tsheg is True


def test_corpus_trailing_tsheg_matches_the_following_character(
    segmenter: SyllableSegmenter, corpus_sentences: list[str]
) -> None:
    for sentence in corpus_sentences:
        for syllable in segmenter.segment(sentence):
            end = syllable.span.char_end
            follower = sentence[end] if end < len(sentence) else ""
            assert syllable.has_trailing_tsheg is (follower in {TSHEG, NON_BREAKING_TSHEG})


def test_non_breaking_tsheg_delimits_like_an_ordinary_tsheg(
    segmenter: SyllableSegmenter,
) -> None:
    ordinary = segmenter.segment("ཆོས་ཉིད་ཀྱི")
    non_breaking = segmenter.segment(f"ཆོས{NON_BREAKING_TSHEG}ཉིད{NON_BREAKING_TSHEG}ཀྱི")
    # Identical surfaces, spans and flags: the variant is fully equivalent.
    assert non_breaking == ordinary


# -- The shad family ---------------------------------------------------------


@pytest.mark.parametrize("shad", SHAD_FAMILY)
def test_shad_delimits_but_is_never_returned(segmenter: SyllableSegmenter, shad: str) -> None:
    text = f"ཀ{shad}ཁ"
    syllables = segmenter.segment(text)
    assert _surfaces(syllables) == ["ཀ", "ཁ"]
    assert all(shad not in syllable.text for syllable in syllables)
    # The second span skips over the shad rather than shifting back onto it.
    assert [(s.span.char_start, s.span.char_end) for s in syllables] == [(0, 1), (2, 3)]
    assert [(s.span.byte_start, s.span.byte_end) for s in syllables] == [(0, 3), (6, 9)]
    _assert_spans_are_ground_truth(text, syllables)


def test_shad_terminated_syllable_is_not_tsheg_terminated(segmenter: SyllableSegmenter) -> None:
    (syllable,) = segmenter.segment(f"ཀ{SHAD}")
    assert syllable.has_trailing_tsheg is False
    assert syllable.with_tsheg() == "ཀ"


# -- Degenerate input --------------------------------------------------------


def test_empty_string_yields_no_syllables(segmenter: SyllableSegmenter) -> None:
    assert segmenter.segment("") == []


@pytest.mark.parametrize(
    "text",
    [" ", "   ", "\t", "\n", "\r\n", " \t\n "],
    ids=["space", "spaces", "tab", "newline", "crlf", "mixed"],
)
def test_whitespace_only_yields_no_syllables(segmenter: SyllableSegmenter, text: str) -> None:
    assert segmenter.segment(text) == []


@pytest.mark.parametrize(
    "text",
    [TSHEG, NON_BREAKING_TSHEG, TSHEG * 3, SHAD, SHAD * 2, f"{SHAD} {TSHEG}\n", "༔"],
)
def test_delimiter_only_input_yields_no_syllables(segmenter: SyllableSegmenter, text: str) -> None:
    assert segmenter.segment(text) == []


# -- Documented scope: non-Tibetan runs pass through -------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Hello world", ["Hello", "world"]),
        ("TEEA v2", ["TEEA", "v2"]),
        ("ཀ latin ཁ", ["ཀ", "latin", "ཁ"]),
    ],
)
def test_non_tibetan_runs_are_returned_verbatim(
    segmenter: SyllableSegmenter, text: str, expected: list[str]
) -> None:
    syllables = segmenter.segment(text)
    assert _surfaces(syllables) == expected
    _assert_spans_are_ground_truth(text, syllables)


def test_is_tibetan_separates_script_from_non_script(segmenter: SyllableSegmenter) -> None:
    syllables = segmenter.segment("ཆོས་latin་ཉིད")
    assert _surfaces(syllables) == ["ཆོས", "latin", "ཉིད"]
    assert [syllable.is_tibetan for syllable in syllables] == [True, False, True]


def test_corpus_syllables_are_all_tibetan(
    segmenter: SyllableSegmenter, corpus_sentences: list[str]
) -> None:
    for sentence in corpus_sentences:
        assert all(syllable.is_tibetan for syllable in segmenter.segment(sentence))


def test_is_tibetan_is_false_for_an_empty_syllable() -> None:
    empty = Syllable(text="", span=TextSpan(char_start=0, char_end=0, byte_start=0, byte_end=0))
    assert empty.is_tibetan is False


# -- Syllable.with_tsheg -----------------------------------------------------


def test_with_tsheg_restores_the_tsheg_only_when_flagged(segmenter: SyllableSegmenter) -> None:
    tsheg_terminated, shad_terminated = segmenter.segment("ཆོས་ཉིད།")
    assert tsheg_terminated.with_tsheg() == f"ཆོས{TSHEG}"
    assert shad_terminated.with_tsheg() == "ཉིད"


def test_with_tsheg_uses_the_canonical_tsheg_for_the_non_breaking_variant(
    segmenter: SyllableSegmenter,
) -> None:
    """``has_trailing_tsheg`` records *that* a tsheg followed, not which one.

    Reconstruction therefore emits the canonical U+0F0B, as documented on
    :meth:`~teea.nlp.tokenization.models.Syllable.with_tsheg`.
    """
    (syllable,) = segmenter.segment(f"ཆོས{NON_BREAKING_TSHEG}")
    assert syllable.with_tsheg() == f"ཆོས{TSHEG}"


def test_with_tsheg_reproduces_the_source_text_at_the_syllable_span(
    segmenter: SyllableSegmenter, corpus_sentences: list[str]
) -> None:
    """Whatever ``with_tsheg`` returns must really occur at that offset."""
    for sentence in corpus_sentences:
        for syllable in segmenter.segment(sentence):
            assert sentence.startswith(syllable.with_tsheg(), syllable.span.char_start)


def test_with_tsheg_reconstructs_a_phrase_without_its_shad(segmenter: SyllableSegmenter) -> None:
    syllables = segmenter.segment(GREETING)
    assert "".join(syllable.with_tsheg() for syllable in syllables) == GREETING.removesuffix(SHAD)


# -- Real lexicon entries ----------------------------------------------------


def test_bare_single_syllable_entry_yields_exactly_one_syllable(
    segmenter: SyllableSegmenter, lexicon_sample: list[str]
) -> None:
    bare = [entry for entry in lexicon_sample if entry and not DELIMITERS.intersection(entry)]
    assert bare, "lexicon fixture must contain bare (tsheg-less) entries"
    for entry in bare:
        syllables = segmenter.segment(entry)
        assert len(syllables) == 1, f"{entry!r} did not segment to a single syllable"
        (syllable,) = syllables
        assert syllable.text == entry
        assert syllable.has_trailing_tsheg is False
        assert syllable.with_tsheg() == entry
        assert syllable.span.char_start == 0
        assert syllable.span.char_end == len(entry)
        assert syllable.span.byte_start == 0
        assert syllable.span.byte_end == len(entry.encode("utf-8"))


def test_tsheg_terminated_lexicon_entry_round_trips(
    segmenter: SyllableSegmenter, lexicon_sample: list[str]
) -> None:
    terminated = [
        entry
        for entry in lexicon_sample
        if entry.endswith(TSHEG) and not DELIMITERS.intersection(entry[:-1])
    ]
    assert terminated, "lexicon fixture must contain tsheg-terminated entries"
    for entry in terminated:
        (syllable,) = segmenter.segment(entry)
        assert syllable.has_trailing_tsheg is True
        # The tsheg is excluded from the span but restorable from the flag.
        assert syllable.text == entry.removesuffix(TSHEG)
        assert syllable.with_tsheg() == entry
        assert syllable.span.char_end == len(entry) - 1


def test_every_lexicon_entry_has_exact_spans(
    segmenter: SyllableSegmenter, lexicon_sample: list[str]
) -> None:
    assert lexicon_sample, "lexicon fixture must not be empty"
    for entry in lexicon_sample:
        _assert_spans_are_ground_truth(entry, segmenter.segment(entry))


def test_punctuation_only_lexicon_entries_yield_no_syllables(
    segmenter: SyllableSegmenter, lexicon_sample: list[str]
) -> None:
    punctuation_only = [
        entry
        for entry in lexicon_sample
        if entry and all(ch in DELIMITERS or ch.isspace() for ch in entry)
    ]
    assert punctuation_only, "lexicon fixture must contain a bare shad entry"
    for entry in punctuation_only:
        assert segmenter.segment(entry) == []
