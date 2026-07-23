"""Adversarial, cross-cutting edge cases for the tokenization module.

Where the sibling modules verify one collaborator each, this module attacks the
*seams*:

* the validators and derived properties of the immutable domain models in
  :mod:`teea.nlp.tokenization.models`, which every downstream stage (morphology,
  POS tagging, the plugin runtime, the suggestion fusion engine) is entitled to
  trust without re-checking;
* the half-open ``[start, end)`` span convention shared with
  :class:`teea.core.types.TextSpan`, which is what makes offsets composable
  across plugin boundaries;
* the text shapes that historically break Tibetan pipelines — astral-plane
  characters, invisible ``Cf`` format characters pasted in from Word or the web,
  mixed script, punctuation-only input, and input that overflows the encoder's
  positional limit.

Two rules govern what is asserted here:

* Model invariants are exercised by constructing the models **directly**, never
  through the tokenizer, so that the validators themselves are under test rather
  than a producer that happens to satisfy them today.
* Behavioural tests assert meaning — offsets address the same characters, no
  invisible character survives into a token span, an unknown ratio is a ratio of
  content — rather than the incidental piece strings a given backend emits.

The fake backend segments at the tsheg and its pieces tile the input exactly, so
``normalized[span]`` is ground truth for every resolved span.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest
from pydantic import BaseModel, ValidationError

from teea.core.config import TokenizationSettings
from teea.core.types import SHAD, TSHEG, TextSpan
from teea.nlp.tokenization import (
    EncodedText,
    SyllableSegmenter,
    TextNormalizer,
    TiBERTTokenizer,
    Token,
)
from teea.nlp.tokenization.exceptions import EmptyInputError, InputTooLongError
from teea.nlp.tokenization.models import Syllable

# Invisible Unicode ``Cf`` (format) characters. Copy-pasted document text is full
# of them and none of them may ever reach the tokenizer or a span.
ZWJ = "‍"
ZWSP = "​"
BOM = "﻿"
SOFT_HYPHEN = "­"
WORD_JOINER = "⁠"
FORMAT_CHARS = (ZWJ, ZWSP, BOM, SOFT_HYPHEN, WORD_JOINER)

# Astral-plane (non-BMP) characters: one code point, two UTF-16 code units.
GRINNING_FACE = "\U0001f600"
TREBLE_CLEF = "\U0001d11e"


# -- Helpers -----------------------------------------------------------------


def _span(char_start: int, char_end: int) -> TextSpan:
    """Build a span whose byte offsets coincide with its char offsets."""
    return TextSpan(
        char_start=char_start,
        char_end=char_end,
        byte_start=char_start,
        byte_end=char_end,
    )


def _token(token_id: int, text: str, span: TextSpan | None = None, **flags: bool) -> Token:
    """Build a token whose piece and surface are identical."""
    return Token(id=token_id, piece=text, text=text, span=span, **flags)


def _special(token_id: int, piece: str) -> Token:
    """Build a special token, which by contract carries no span."""
    return Token(id=token_id, piece=piece, text=piece, span=None, is_special=True)


def _byte_offset(text: str, char_index: int) -> int:
    """UTF-8 byte offset of ``char_index`` in ``text``."""
    return len(text[:char_index].encode("utf-8"))


def _is_subsequence(needle: str, haystack: str) -> bool:
    """Whether every character of ``needle`` occurs, in order, in ``haystack``."""
    remaining = iter(haystack)
    return all(char in remaining for char in needle)


def _assert_spans_are_exact(encoded: EncodedText) -> None:
    """Assert every resolved span addresses exactly the text of its token.

    Also checks that spans are ordered and non-overlapping, that byte offsets are
    genuine UTF-8 offsets into the normalized text, and that special tokens are
    left unanchored.
    """
    text = encoded.normalized
    previous_end = 0
    for token in encoded.tokens:
        if token.is_special:
            assert token.span is None, f"special token {token.piece!r} must not be anchored"
            continue
        span = token.span
        if span is None:
            continue
        assert text[span.char_start : span.char_end] == token.text
        assert span.byte_start == _byte_offset(text, span.char_start)
        assert span.byte_end == _byte_offset(text, span.char_end)
        assert span.char_start >= previous_end, "token spans must not overlap"
        previous_end = span.char_end


def _repeat_until_over(sentences: list[str], minimum: int) -> str:
    """Join corpus sentences until they contain more than ``minimum`` tshegs.

    Each tsheg yields at least one backend piece, so the result is guaranteed to
    encode to more than ``minimum`` tokens. The construction is deterministic:
    sentences are consumed in fixture order.
    """
    parts: list[str] = []
    tshegs = 0
    index = 0
    while tshegs <= minimum:
        sentence = sentences[index % len(sentences)]
        parts.append(sentence)
        tshegs += sentence.count(TSHEG)
        index += 1
    return " ".join(parts)


def _sample_encoded() -> EncodedText:
    """A small but realistic encoding: two specials wrapping three content tokens.

    The unknown token is deliberately *not* marked special, because
    ``unknown_ratio`` is defined as a fraction of content tokens and a token can
    only be counted in that fraction if it is part of the content.
    """
    tokens = (
        _special(1, "[CLS]"),
        _token(100, "ཀ" + TSHEG, _span(0, 2)),
        _token(3, "[UNK]", _span(2, 4), is_unknown=True),
        _token(101, "ཁ" + TSHEG, _span(4, 6)),
        _special(2, "[SEP]"),
    )
    return EncodedText(
        source="ཀ" + TSHEG + "??" + TSHEG + "ཁ" + TSHEG,
        normalized="ཀ" + TSHEG + "??" + TSHEG + "ཁ" + TSHEG,
        tokens=tokens,
        ids=tuple(token.id for token in tokens),
        num_special_tokens=2,
    )


# -- TextSpan bounds ---------------------------------------------------------


@pytest.mark.parametrize(
    ("char_start", "char_end", "byte_start", "byte_end"),
    [
        (5, 2, 0, 6),
        (0, 3, 9, 4),
        (-1, 3, 0, 9),
        (0, 3, -1, 9),
        (-2, -1, 0, 3),
    ],
    ids=[
        "char_end_before_start",
        "byte_end_before_start",
        "negative_char",
        "negative_byte",
        "both",
    ],
)
def test_text_span_rejects_inverted_or_negative_bounds(
    char_start: int, char_end: int, byte_start: int, byte_end: int
) -> None:
    with pytest.raises(ValidationError):
        TextSpan(
            char_start=char_start,
            char_end=char_end,
            byte_start=byte_start,
            byte_end=byte_end,
        )


def test_text_span_allows_a_degenerate_empty_span() -> None:
    span = _span(4, 4)
    assert span.is_empty
    assert span.char_length == 0
    assert span.byte_length == 0


# -- Token invariants --------------------------------------------------------


@pytest.mark.parametrize("span", [None, _span(0, 2)], ids=["unanchored", "anchored"])
def test_token_has_span_reflects_presence_of_a_span(span: TextSpan | None) -> None:
    assert _token(7, "ཀ", span).has_span is (span is not None)


@pytest.mark.parametrize(("is_special", "expected"), [(False, True), (True, False)])
def test_token_is_content_is_the_negation_of_is_special(is_special: bool, expected: bool) -> None:
    assert _token(7, "ཀ", is_special=is_special).is_content is expected


def test_token_rejects_a_negative_vocabulary_id() -> None:
    with pytest.raises(ValidationError):
        Token(id=-1, piece="ཀ", text="ཀ")


# -- Syllable invariants -----------------------------------------------------


@pytest.mark.parametrize("has_tsheg", [True, False])
def test_syllable_with_tsheg_restores_the_delimiter_only_when_present(has_tsheg: bool) -> None:
    syllable = Syllable(text="ཀ", span=_span(0, 1), has_trailing_tsheg=has_tsheg)
    assert syllable.with_tsheg() == ("ཀ" + TSHEG if has_tsheg else "ཀ")


@pytest.mark.parametrize(
    ("text", "expected"),
    [("ཀ", True), ("བཀྲ", True), ("abc", False), ("ཀa", False), ("", False)],
)
def test_syllable_is_tibetan_requires_every_character_in_the_block(
    text: str, expected: bool
) -> None:
    assert Syllable(text=text, span=_span(0, len(text))).is_tibetan is expected


# -- EncodedText construction validators -------------------------------------


@pytest.mark.parametrize(
    "ids",
    [(), (100,), (100, 101, 102)],
    ids=["no_ids", "too_few_ids", "too_many_ids"],
)
def test_encoded_text_rejects_ids_tokens_length_mismatch(ids: tuple[int, ...]) -> None:
    tokens = (_token(100, "ཀ"), _token(101, "ཁ"))
    with pytest.raises(ValidationError, match="length mismatch"):
        EncodedText(source="ཀཁ", normalized="ཀཁ", tokens=tokens, ids=ids)


def test_encoded_text_rejects_ids_not_positionally_aligned_with_tokens() -> None:
    tokens = (_token(100, "ཀ"), _token(101, "ཁ"))
    # Same multiset of ids, wrong order: only a positional check catches this.
    with pytest.raises(ValidationError, match="positionally aligned"):
        EncodedText(source="ཀཁ", normalized="ཀཁ", tokens=tokens, ids=(101, 100))


@pytest.mark.parametrize("declared", [0, 2, 5], ids=["understated", "overstated", "absurd"])
def test_encoded_text_rejects_a_wrong_special_token_count(declared: int) -> None:
    tokens = (_special(1, "[CLS]"), _token(100, "ཀ"))
    with pytest.raises(ValidationError, match="num_special_tokens"):
        EncodedText(
            source="ཀ",
            normalized="ཀ",
            tokens=tokens,
            ids=(1, 100),
            num_special_tokens=declared,
        )


def test_encoded_text_rejects_a_negative_special_token_count() -> None:
    with pytest.raises(ValidationError):
        EncodedText(source="ཀ", normalized="ཀ", num_special_tokens=-1)


def test_encoded_text_accepts_an_empty_encoding() -> None:
    encoded = EncodedText(source="ཀ", normalized="ཀ")
    assert encoded.num_tokens == 0
    assert len(encoded) == 0
    assert encoded.content_tokens == ()
    assert encoded.pieces == ()
    assert encoded.surfaces == ()
    assert encoded.was_truncated is False


# -- EncodedText derived properties ------------------------------------------


def test_encoded_text_exposes_counts_and_projections() -> None:
    encoded = _sample_encoded()
    assert encoded.num_tokens == 5
    assert len(encoded) == encoded.num_tokens
    assert encoded.num_content_tokens == 3
    assert encoded.content_tokens == tuple(t for t in encoded.tokens if not t.is_special)
    assert all(token.is_content for token in encoded.content_tokens)
    assert encoded.pieces == ("[CLS]", "ཀ" + TSHEG, "[UNK]", "ཁ" + TSHEG, "[SEP]")
    assert encoded.surfaces == encoded.pieces
    assert len(encoded.ids) == encoded.num_tokens


def test_num_content_tokens_agrees_with_the_content_projection() -> None:
    encoded = _sample_encoded()
    assert encoded.num_content_tokens == len(encoded.content_tokens)


@pytest.mark.parametrize(
    ("tokens", "expected"),
    [
        ((), 0.0),
        ((_special(1, "[CLS]"), _special(2, "[SEP]")), 0.0),
    ],
    ids=["no_tokens", "only_special_tokens"],
)
def test_unknown_ratio_is_zero_without_content_tokens(
    tokens: tuple[Token, ...], expected: float
) -> None:
    encoded = EncodedText(
        source="ཀ",
        normalized="ཀ",
        tokens=tokens,
        ids=tuple(token.id for token in tokens),
        num_special_tokens=sum(1 for token in tokens if token.is_special),
    )
    assert encoded.unknown_ratio == expected


def test_unknown_ratio_excludes_special_tokens_from_the_denominator() -> None:
    tokens = (
        _special(1, "[CLS]"),
        _token(3, "[UNK]", _span(0, 2), is_unknown=True),
        _token(100, "ཁ" + TSHEG, _span(2, 4)),
        _special(2, "[SEP]"),
    )
    encoded = EncodedText(
        source="??" + TSHEG + "ཁ" + TSHEG,
        normalized="??" + TSHEG + "ཁ" + TSHEG,
        tokens=tokens,
        ids=tuple(token.id for token in tokens),
        num_special_tokens=2,
    )
    # One unknown out of two *content* tokens; counting the specials would give 0.25.
    assert encoded.unknown_ratio == pytest.approx(0.5)


def test_unknown_ratio_of_the_sample_encoding_is_a_content_fraction() -> None:
    assert _sample_encoded().unknown_ratio == pytest.approx(1 / 3)


@pytest.mark.parametrize("num_unknown", [0, 1, 2])
def test_has_unknown_mirrors_num_unknown(num_unknown: int) -> None:
    tokens = tuple(
        _token(100 + index, f"s{index}", is_unknown=index < num_unknown) for index in range(2)
    )
    encoded = EncodedText(
        source="s0s1",
        normalized="s0s1",
        tokens=tokens,
        ids=tuple(token.id for token in tokens),
    )
    assert encoded.num_unknown == num_unknown
    assert encoded.has_unknown is (num_unknown > 0)


# -- token_at_char -----------------------------------------------------------


@pytest.mark.parametrize(
    ("char_index", "expected_piece"),
    [
        (-1, None),
        (0, "first"),
        (2, "first"),
        (3, None),
        (4, None),
        (5, "second"),
        (7, "second"),
        (8, None),
        (10_000, None),
    ],
    ids=[
        "negative",
        "at_start_boundary",
        "inside_first",
        "at_exclusive_end_of_first",
        "in_the_gap",
        "at_start_of_second",
        "inside_second",
        "at_exclusive_end_of_second",
        "far_past_the_end",
    ],
)
def test_token_at_char_respects_the_half_open_convention(
    char_index: int, expected_piece: str | None
) -> None:
    tokens = (
        _special(1, "[CLS]"),
        _token(100, "first", _span(0, 3)),
        _token(101, "second", _span(5, 8)),
    )
    encoded = EncodedText(
        source="abc..def",
        normalized="abc..def",
        tokens=tokens,
        ids=tuple(token.id for token in tokens),
        num_special_tokens=1,
    )
    found = encoded.token_at_char(char_index)
    assert (found.piece if found is not None else None) == expected_piece


def test_token_at_char_never_returns_an_unanchored_token() -> None:
    tokens = (_special(1, "[CLS]"), _token(100, "ཀ", span=None))
    encoded = EncodedText(
        source="ཀ",
        normalized="ཀ",
        tokens=tokens,
        ids=(1, 100),
        num_special_tokens=1,
    )
    assert all(encoded.token_at_char(index) is None for index in range(-1, 3))


# -- Immutability, extra=forbid and value semantics --------------------------

_MODEL_PAYLOADS: list[tuple[type[BaseModel], dict[str, Any]]] = [
    (TextSpan, {"char_start": 0, "char_end": 1, "byte_start": 0, "byte_end": 3}),
    (Token, {"id": 100, "piece": "ཀ", "text": "ཀ"}),
    (Syllable, {"text": "ཀ", "span": _span(0, 1), "has_trailing_tsheg": True}),
    (
        EncodedText,
        {
            "source": "ཀ",
            "normalized": "ཀ",
            "tokens": (_token(100, "ཀ", _span(0, 1)),),
            "ids": (100,),
        },
    ),
]
_MODEL_IDS = ["text_span", "token", "syllable", "encoded_text"]


@pytest.mark.parametrize(("model_type", "payload"), _MODEL_PAYLOADS, ids=_MODEL_IDS)
def test_models_are_frozen(model_type: type[BaseModel], payload: dict[str, Any]) -> None:
    instance = model_type(**payload)
    for field_name, value in payload.items():
        with pytest.raises(ValidationError):
            setattr(instance, field_name, value)


@pytest.mark.parametrize(("model_type", "payload"), _MODEL_PAYLOADS, ids=_MODEL_IDS)
def test_models_forbid_unknown_fields(model_type: type[BaseModel], payload: dict[str, Any]) -> None:
    with pytest.raises(ValidationError, match=r"[Ee]xtra"):
        model_type(**payload, unexpected_backend_field="surprise")


@pytest.mark.parametrize(("model_type", "payload"), _MODEL_PAYLOADS, ids=_MODEL_IDS)
def test_models_are_hashable_value_objects(
    model_type: type[BaseModel], payload: dict[str, Any]
) -> None:
    first = model_type(**payload)
    second = model_type(**payload)
    assert first is not second
    assert first == second
    assert hash(first) == hash(second)
    assert len({first, second}) == 1
    assert {first: "cached"}[second] == "cached"


def test_encoded_texts_differing_in_content_do_not_collide() -> None:
    encoded = _sample_encoded()
    other = EncodedText(
        source=encoded.source,
        normalized=encoded.normalized,
        tokens=encoded.tokens,
        ids=encoded.ids,
        num_special_tokens=encoded.num_special_tokens,
        was_truncated=True,
    )
    assert encoded != other
    assert len({encoded, other}) == 2


# -- Real lexicon entries ----------------------------------------------------


def test_lexicon_entries_normalize_and_segment_without_error(
    lexicon_sample: list[str],
    normalizer: TextNormalizer,
    segmenter: SyllableSegmenter,
) -> None:
    for entry in lexicon_sample:
        normalized = normalizer.normalize(entry)
        assert normalized, f"{entry!r} normalized away entirely"
        syllables = segmenter.segment(normalized)

        if set(normalized) <= {SHAD}:
            # Punctuation is a delimiter, never a syllable in its own right.
            assert syllables == []
            continue

        assert syllables, f"{entry!r} produced no syllables"
        assert syllables[-1].has_trailing_tsheg is normalized.endswith(TSHEG)
        for syllable in syllables:
            span = syllable.span
            assert normalized[span.char_start : span.char_end] == syllable.text
            assert span.byte_start == _byte_offset(normalized, span.char_start)
            assert span.byte_end == _byte_offset(normalized, span.char_end)

        rebuilt = "".join(syllable.with_tsheg() for syllable in syllables)
        if SHAD in normalized:
            assert _is_subsequence(rebuilt, normalized)
        else:
            assert rebuilt == normalized


def test_lexicon_entries_encode_without_loss(
    lexicon_sample: list[str], tokenizer: TiBERTTokenizer
) -> None:
    for entry in lexicon_sample:
        encoded = tokenizer.encode(entry)
        assert encoded.source == entry
        # Lexicon entries are already canonical, so Stage 2 is a no-op on them.
        assert encoded.normalized == entry
        assert "".join(token.text for token in encoded.content_tokens) == entry
        assert encoded.was_truncated is False
        _assert_spans_are_exact(encoded)


# -- Corpus: normalization and segmentation stability ------------------------


def test_segmenting_normalized_corpus_is_faithful_and_stable(
    corpus_sentences: list[str],
    normalizer: TextNormalizer,
    segmenter: SyllableSegmenter,
) -> None:
    for sentence in corpus_sentences:
        normalized = normalizer.normalize(sentence)
        syllables = segmenter.segment(normalized)
        assert syllables

        rebuilt = "".join(syllable.with_tsheg() for syllable in syllables)
        assert _is_subsequence(rebuilt, normalized)

        previous_end = 0
        for syllable in syllables:
            span = syllable.span
            assert syllable.text, "empty syllables are never emitted"
            assert normalized[span.char_start : span.char_end] == syllable.text
            assert span.char_start >= previous_end, "syllable spans must not overlap"
            previous_end = span.char_end

        # Re-normalizing must not move a single offset (value equality suffices).
        assert segmenter.segment(normalizer.normalize(normalized)) == syllables


# -- Mixed script and punctuation-only input ---------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "བཀྲ་ཤིས་ ABC 123",
        "abc123",
        "ཀ་1་a་",
        "2024 ལོ་",
        "ཀ" + TSHEG + "\tཁ" + TSHEG,
    ],
    ids=["tibetan_latin_digits", "ascii_only", "interleaved", "leading_digits", "tabbed"],
)
def test_mixed_script_input_keeps_offsets_exact(text: str, tokenizer: TiBERTTokenizer) -> None:
    encoded = tokenizer.encode(text)
    assert encoded.source == text
    assert encoded.num_content_tokens >= 1
    _assert_spans_are_exact(encoded)


def test_segmenter_returns_non_tibetan_runs_verbatim(segmenter: SyllableSegmenter) -> None:
    syllables = segmenter.segment("ཀ" + TSHEG + "ABC" + TSHEG + "123" + TSHEG)
    assert [syllable.text for syllable in syllables] == ["ཀ", "ABC", "123"]
    assert [syllable.is_tibetan for syllable in syllables] == [True, False, False]
    assert all(syllable.has_trailing_tsheg for syllable in syllables)


@pytest.mark.parametrize(
    "text",
    [SHAD, SHAD * 2, SHAD + "  " + SHAD, SHAD + TSHEG + SHAD + TSHEG],
    ids=["single", "doubled", "spaced", "with_tshegs"],
)
def test_shad_only_input_produces_no_syllables(
    text: str, normalizer: TextNormalizer, segmenter: SyllableSegmenter
) -> None:
    assert segmenter.segment(normalizer.normalize(text)) == []


def test_ascii_punctuation_only_input_is_one_non_tibetan_chunk(
    normalizer: TextNormalizer, segmenter: SyllableSegmenter
) -> None:
    syllables = segmenter.segment(normalizer.normalize("!?."))
    assert [syllable.text for syllable in syllables] == ["!?."]
    assert syllables[0].is_tibetan is False


@pytest.mark.parametrize(
    "text", [SHAD, SHAD * 2, "!?.", "…"], ids=["shad", "shads", "ascii", "ellipsis"]
)
def test_punctuation_only_input_encodes_without_error(
    text: str, tokenizer: TiBERTTokenizer
) -> None:
    encoded = tokenizer.encode(text)
    assert encoded.num_content_tokens >= 1
    assert encoded.has_unknown is False
    _assert_spans_are_exact(encoded)


# -- Astral-plane characters -------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        GRINNING_FACE + TSHEG + "བཀྲ་ཤིས།",
        "ཀ" + TSHEG + GRINNING_FACE * 2 + TSHEG + "ཁ" + TSHEG,
        TREBLE_CLEF + TSHEG + "ཀ" + TSHEG,
        "ཀ" + TSHEG + GRINNING_FACE,
    ],
    ids=["leading_emoji", "embedded_emoji", "musical_symbol", "trailing_emoji"],
)
def test_astral_characters_do_not_corrupt_offsets(text: str, tokenizer: TiBERTTokenizer) -> None:
    encoded = tokenizer.encode(text)
    _assert_spans_are_exact(encoded)


def test_astral_offsets_are_code_point_based_not_utf16(tokenizer: TiBERTTokenizer) -> None:
    encoded = tokenizer.encode(GRINNING_FACE + TSHEG + "ཀ" + TSHEG)
    following = encoded.content_tokens[1]
    assert following.text == "ཀ" + TSHEG
    assert following.span is not None
    # The emoji is a single code point: UTF-16 accounting would say 3, not 2.
    assert following.span.char_start == 2
    assert following.span.byte_start == len((GRINNING_FACE + TSHEG).encode("utf-8"))


# -- Invisible format characters ---------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("བཀྲ" + ZWJ + TSHEG + "ཤིས།", "བཀྲ" + TSHEG + "ཤིས།"),
        (BOM + "ཀ" + TSHEG + "ཁ" + TSHEG, "ཀ" + TSHEG + "ཁ" + TSHEG),
        ("ཀ" + SOFT_HYPHEN + TSHEG + WORD_JOINER + "ཁ" + TSHEG, "ཀ" + TSHEG + "ཁ" + TSHEG),
        ("ཀ" + ZWSP + TSHEG, "ཀ" + TSHEG),
        ("👨" + ZWJ + "👩" + TSHEG + "ཀ" + TSHEG, "👨👩" + TSHEG + "ཀ" + TSHEG),
    ],
    ids=["zwj", "bom", "soft_hyphen_word_joiner", "zwsp", "emoji_zwj_sequence"],
)
def test_format_characters_are_stripped_before_tokenization(
    raw: str, expected: str, tokenizer: TiBERTTokenizer
) -> None:
    encoded = tokenizer.encode(raw)
    assert encoded.source == raw, "the caller's original text is retained verbatim"
    assert encoded.normalized == expected
    assert not any(char in encoded.normalized for char in FORMAT_CHARS)
    for token in encoded.content_tokens:
        assert not any(char in token.text for char in FORMAT_CHARS)
    _assert_spans_are_exact(encoded)


def test_format_characters_do_not_perturb_the_token_sequence(tokenizer: TiBERTTokenizer) -> None:
    clean = "བཀྲ་ཤིས་བདེ་ལེགས།"
    noisy = "".join(
        ["བཀྲ", ZWJ, TSHEG, "ཤིས", ZWSP, TSHEG, BOM, "བདེ", TSHEG, "ལེགས", SOFT_HYPHEN, SHAD]
    )
    from_noisy = tokenizer.encode(noisy)
    from_clean = tokenizer.encode(clean)
    assert from_noisy.normalized == from_clean.normalized
    assert from_noisy.surfaces == from_clean.surfaces
    assert [token.span for token in from_noisy.tokens] == [
        token.span for token in from_clean.tokens
    ]


@pytest.mark.parametrize(
    "text",
    [ZWJ + BOM, ZWSP, SOFT_HYPHEN + WORD_JOINER, " "],
    ids=["zwj_bom", "zwsp", "soft_hyphen_word_joiner", "nbsp"],
)
def test_input_that_normalizes_away_entirely_is_rejected(
    text: str, tokenizer: TiBERTTokenizer
) -> None:
    # These strings are non-empty and (mostly) survive ``str.strip``, so only the
    # post-normalization emptiness check can catch them.
    with pytest.raises(EmptyInputError):
        tokenizer.encode(text)


# -- Offset resolution paths agree -------------------------------------------


def test_alignment_fallback_agrees_with_the_native_offset_mapping(
    make_tokenizer: Callable[..., TiBERTTokenizer],
) -> None:
    text = "ཀ" + TSHEG + GRINNING_FACE + TSHEG + "བཀྲ་ཤིས།"
    # Special tokens are disabled so the comparison isolates the two span
    # resolution strategies for content pieces.
    fast = make_tokenizer(is_fast=True).encode(text, add_special_tokens=False)
    slow = make_tokenizer(is_fast=False).encode(text, add_special_tokens=False)
    assert slow.surfaces == fast.surfaces
    assert [token.span for token in slow.tokens] == [token.span for token in fast.tokens]
    _assert_spans_are_exact(slow)


# -- Length limits -----------------------------------------------------------


def test_overlong_input_is_rejected_when_truncation_is_off(
    corpus_sentences: list[str], settings: TokenizationSettings, tokenizer: TiBERTTokenizer
) -> None:
    text = _repeat_until_over(corpus_sentences, settings.max_sequence_length)
    with pytest.raises(InputTooLongError) as exc_info:
        tokenizer.encode(text)
    context = exc_info.value.context
    assert context["maximum"] == settings.max_sequence_length
    assert context["produced"] > settings.max_sequence_length


def test_overlong_input_is_truncated_on_request(
    corpus_sentences: list[str], settings: TokenizationSettings, tokenizer: TiBERTTokenizer
) -> None:
    text = _repeat_until_over(corpus_sentences, settings.max_sequence_length)
    encoded = tokenizer.encode(text, truncate=True)
    assert encoded.was_truncated is True
    assert len(encoded) == settings.max_sequence_length
    assert len(encoded.ids) == len(encoded.tokens)
    assert encoded.source == text
    _assert_spans_are_exact(encoded)


def test_the_length_limit_follows_the_configured_maximum(
    make_tokenizer: Callable[..., TiBERTTokenizer],
) -> None:
    tight = TokenizationSettings(max_sequence_length=4)
    tokenizer = make_tokenizer(settings=tight)
    with pytest.raises(InputTooLongError) as exc_info:
        tokenizer.encode("བཀྲ་ཤིས་བདེ་ལེགས།")
    assert exc_info.value.context["maximum"] == 4


def test_input_just_within_the_limit_is_accepted(
    make_tokenizer: Callable[..., TiBERTTokenizer],
) -> None:
    tight = TokenizationSettings(max_sequence_length=6)
    tokenizer = make_tokenizer(settings=tight)
    encoded = tokenizer.encode("བཀྲ་ཤིས་བདེ་ལེགས།")
    assert len(encoded) == 6
    assert encoded.was_truncated is False
    assert encoded.num_content_tokens == 4


@pytest.mark.xfail(
    strict=True,
    reason=(
        "TiBERTTokenizer.encode computes 'was_truncated = truncate and len(ids) >= max_len', "
        "so an input that fits exactly is reported as truncated whenever truncate=True. "
        "was_truncated is a data-loss signal, so a false positive is not harmless."
    ),
)
def test_exactly_maximum_length_input_is_not_reported_as_truncated(
    make_tokenizer: Callable[..., TiBERTTokenizer],
) -> None:
    tight = TokenizationSettings(max_sequence_length=6)
    tokenizer = make_tokenizer(settings=tight)
    text = "བཀྲ་ཤིས་བདེ་ལེགས།"
    # Same input, same token sequence; only the truncate flag differs.
    lossless = tokenizer.encode(text)
    permitted = tokenizer.encode(text, truncate=True)
    assert permitted.surfaces == lossless.surfaces, "nothing was actually dropped"
    assert permitted.was_truncated is False
