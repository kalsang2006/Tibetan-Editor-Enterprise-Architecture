"""Unit tests for :mod:`teea.nlp.tokenization.tibert`.

These tests verify the *orchestration* the TiBERT wrapper is responsible for --
input validation, the normalization boundary, special-token policy, offset
resolution (both the fast tokenizer's native mapping and the slow forward
aligner), truncation policy, unknown-token reporting and failure translation --
without loading the real ~30k-vocabulary TiBERT model.

That is possible because :class:`~teea.nlp.tokenization.tibert.TiBERTTokenizer`
takes its Hugging Face backend through an injected loader. The suite drives the
real wrapper against :class:`~tests.fakes.FakeBackendTokenizer`, which tiles its
input into contiguous tsheg-delimited pieces. Because those pieces exactly tile
the text, every emitted span has a ground truth the tests can check against the
normalized string itself rather than against a hard-coded offset table.

Text under test is real classical Tibetan taken from the Milarepa corpus and
lexicon fixtures, so the assertions exercise multi-byte, multi-codepoint
grapheme clusters rather than ASCII stand-ins.
"""

from __future__ import annotations

import inspect
import sys
import types
from collections.abc import Callable, Mapping, Sequence
from itertools import pairwise
from pathlib import Path
from typing import Any

import pytest

from teea.core.config import TokenizationSettings
from teea.nlp.tokenization.exceptions import (
    DetokenizationError,
    EmptyInputError,
    InputNotStringError,
    InputTooLongError,
    TokenizationError,
    TokenizerLoadError,
)
from teea.nlp.tokenization.interfaces import Tokenizer
from teea.nlp.tokenization.models import EncodedText
from teea.nlp.tokenization.normalization import TextNormalizer
from teea.nlp.tokenization.tibert import (
    BackendLoader,
    BackendTokenizer,
    TiBERTTokenizer,
    _is_continuation,
    _piece_surface,
    default_tibert_loader,
)
from tests.fakes import FakeBackendTokenizer

#: Type of the ``make_tokenizer`` factory fixture from ``tests/conftest.py``.
MakeTokenizer = Callable[..., TiBERTTokenizer]

#: SentencePiece metaspace marker (U+2581). Restated here deliberately so that
#: span ground truth does not depend on the helper under test.
METASPACE = "▁"

#: Special pieces the fake backend models, matching Hugging Face conventions.
CLS_PIECE = "[CLS]"
SEP_PIECE = "[SEP]"

#: The fake exposes a fixed 15-entry vocabulary (5 specials + 10 letters).
FAKE_VOCAB_SIZE = 15


# -- Helpers ----------------------------------------------------------------
def _loader_for(backend: BackendTokenizer) -> BackendLoader:
    """Return a loader that always yields ``backend``."""

    def _load(_: TokenizationSettings) -> BackendTokenizer:
        return backend

    return _load


class _ExplodingBackend(FakeBackendTokenizer):
    """A backend that loads cleanly but fails when asked to tokenize."""

    def __init__(self, error: Exception) -> None:
        super().__init__()
        self.error = error

    def __call__(
        self,
        text: str,
        *,
        add_special_tokens: bool,
        truncation: bool,
        max_length: int,
        return_offsets_mapping: bool,
    ) -> Mapping[str, Any]:
        raise self.error


class _ExplodingDecoder(FakeBackendTokenizer):
    """A backend that tokenizes normally but fails when asked to decode."""

    def __init__(self, error: Exception) -> None:
        super().__init__()
        self.error = error

    def decode(self, ids: Sequence[int], *, skip_special_tokens: bool) -> str:
        raise self.error


def _install_stub_transformers(
    monkeypatch: pytest.MonkeyPatch,
    *,
    result: object = None,
    error: Exception | None = None,
) -> list[tuple[str, dict[str, Any]]]:
    """Replace the lazily imported ``transformers`` module with a stub.

    Keeps :func:`default_tibert_loader` hermetic: no import of the real
    library, no cache lookup and no network access.

    Returns:
        A list that records every ``from_pretrained(source, **kwargs)`` call.
    """
    calls: list[tuple[str, dict[str, Any]]] = []

    class _AutoTokenizer:
        @staticmethod
        def from_pretrained(source: str, **kwargs: Any) -> Any:
            calls.append((source, dict(kwargs)))
            if error is not None:
                raise error
            return result

    module = types.ModuleType("transformers")
    module.AutoTokenizer = _AutoTokenizer  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "transformers", module)
    return calls


def _assert_span_ground_truth(encoded: EncodedText) -> None:
    """Every content token's span must slice its own surface out of the text."""
    normalized = encoded.normalized
    for token in encoded.content_tokens:
        span = token.span
        assert span is not None, f"content token {token.piece!r} has no span"
        expected = token.piece.removeprefix(METASPACE)
        assert normalized[span.char_start : span.char_end] == expected


# -- Piece-surface helpers --------------------------------------------------
@pytest.mark.parametrize(
    ("piece", "expected"),
    [
        (f"{METASPACE}abc", "abc"),
        ("##abc", "abc"),
        ("abc", "abc"),
        (METASPACE, ""),
        (CLS_PIECE, CLS_PIECE),
        (f"a{METASPACE}b", f"a{METASPACE}b"),
    ],
)
def test_piece_surface_strips_only_leading_subword_markers(piece: str, expected: str) -> None:
    assert _piece_surface(piece) == expected


@pytest.mark.parametrize(
    ("piece", "has_any_metaspace", "expected"),
    [
        ("##abc", False, True),
        ("##abc", True, True),
        (f"{METASPACE}abc", True, False),
        ("abc", True, True),
        (f"{METASPACE}abc", False, False),
        ("abc", False, False),
    ],
)
def test_is_continuation_interprets_word_start_markers(
    piece: str, has_any_metaspace: bool, expected: bool
) -> None:
    assert _is_continuation(piece, has_any_metaspace) is expected


# -- Introspection and protocol conformance ---------------------------------
def test_vocab_size_reflects_backend_vocabulary(tokenizer: TiBERTTokenizer) -> None:
    assert tokenizer.vocab_size == FAKE_VOCAB_SIZE


def test_model_id_reflects_configuration(make_tokenizer: MakeTokenizer) -> None:
    settings = TokenizationSettings(model_id="local/TiBERT-test")
    assert make_tokenizer(settings=settings).model_id == "local/TiBERT-test"


def test_tibert_tokenizer_satisfies_tokenizer_protocol(tokenizer: TiBERTTokenizer) -> None:
    assert isinstance(tokenizer, Tokenizer)


def test_fake_backend_satisfies_backend_tokenizer_protocol() -> None:
    assert isinstance(FakeBackendTokenizer(), BackendTokenizer)


# -- Encoding contract ------------------------------------------------------
@pytest.mark.parametrize("index", [0, 7, 23, 41, 59])
def test_encode_keeps_source_and_exposes_normalized(
    tokenizer: TiBERTTokenizer,
    normalizer: TextNormalizer,
    corpus_sentences: list[str],
    index: int,
) -> None:
    raw = f"  {corpus_sentences[index]}\n\n"
    encoded = tokenizer.encode(raw)
    assert encoded.source == raw
    assert encoded.normalized == normalizer.normalize(raw)
    assert encoded.normalized != raw


def test_encode_ids_are_positionally_aligned_with_tokens(
    tokenizer: TiBERTTokenizer, corpus_sentences: list[str]
) -> None:
    encoded = tokenizer.encode(corpus_sentences[2])
    assert encoded.ids == tuple(token.id for token in encoded.tokens)
    assert len(encoded) == len(encoded.tokens) == encoded.num_tokens
    assert encoded.pieces == tuple(token.piece for token in encoded.tokens)


def test_content_token_surfaces_reconstruct_the_normalized_text(
    tokenizer: TiBERTTokenizer, corpus_sentences: list[str]
) -> None:
    encoded = tokenizer.encode(corpus_sentences[5])
    assert "".join(token.text for token in encoded.content_tokens) == encoded.normalized


def test_encode_is_not_truncated_by_default(
    tokenizer: TiBERTTokenizer, corpus_sentences: list[str]
) -> None:
    assert tokenizer.encode(corpus_sentences[0]).was_truncated is False


@pytest.mark.parametrize("index", [0, 3, 11])
def test_continuation_flags_mark_word_internal_pieces(
    tokenizer: TiBERTTokenizer, corpus_sentences: list[str], index: int
) -> None:
    content = tokenizer.encode(corpus_sentences[index]).content_tokens
    assert content[0].is_continuation is False
    assert all(token.is_continuation for token in content[1:])


# -- Special tokens ---------------------------------------------------------
def test_special_tokens_wrap_the_sequence_and_carry_no_span(
    tokenizer: TiBERTTokenizer, corpus_sentences: list[str]
) -> None:
    encoded = tokenizer.encode(corpus_sentences[4], add_special_tokens=True)
    assert encoded.num_special_tokens == 2
    assert encoded.pieces[0] == CLS_PIECE
    assert encoded.pieces[-1] == SEP_PIECE
    specials = [token for token in encoded.tokens if token.is_special]
    assert all(token.span is None for token in specials)
    assert all(token.has_span is False for token in specials)
    assert all(token.is_continuation is False for token in specials)
    assert encoded.num_content_tokens == len(encoded.tokens) - 2


def test_add_special_tokens_false_produces_only_content_tokens(
    tokenizer: TiBERTTokenizer, corpus_sentences: list[str]
) -> None:
    encoded = tokenizer.encode(corpus_sentences[4], add_special_tokens=False)
    assert encoded.num_special_tokens == 0
    assert encoded.content_tokens == encoded.tokens
    assert CLS_PIECE not in encoded.pieces
    assert SEP_PIECE not in encoded.pieces


@pytest.mark.parametrize(
    ("configured", "override", "expected_specials"),
    [
        (True, None, 2),
        (True, False, 0),
        (False, None, 0),
        (False, True, 2),
    ],
)
def test_per_call_add_special_tokens_beats_configured_default(
    make_tokenizer: MakeTokenizer,
    corpus_sentences: list[str],
    configured: bool,
    override: bool | None,
    expected_specials: int,
) -> None:
    settings = TokenizationSettings(add_special_tokens=configured)
    tokenizer = make_tokenizer(settings=settings)
    encoded = tokenizer.encode(corpus_sentences[6], add_special_tokens=override)
    assert encoded.num_special_tokens == expected_specials


# -- Offsets: fast path, slow path, bytes -----------------------------------
@pytest.mark.parametrize("index", [0, 1, 2, 17, 38, 59])
def test_fast_path_spans_match_the_normalized_text(
    make_tokenizer: MakeTokenizer, corpus_sentences: list[str], index: int
) -> None:
    # is_fast=True -> the wrapper consumes the backend's native offset_mapping.
    tokenizer = make_tokenizer(is_fast=True)
    _assert_span_ground_truth(tokenizer.encode(corpus_sentences[index]))


@pytest.mark.parametrize("index", [0, 1, 2, 17, 38, 59])
def test_slow_path_spans_match_the_normalized_text(
    make_tokenizer: MakeTokenizer, corpus_sentences: list[str], index: int
) -> None:
    # is_fast=False -> no offset_mapping, so the forward aligner must recover
    # the same offsets by searching the normalized string.
    tokenizer = make_tokenizer(is_fast=False)
    _assert_span_ground_truth(tokenizer.encode(corpus_sentences[index], add_special_tokens=False))


@pytest.mark.parametrize("index", [0, 9, 26, 55])
def test_fast_and_slow_paths_agree_on_spans(
    make_tokenizer: MakeTokenizer, corpus_sentences: list[str], index: int
) -> None:
    sentence = corpus_sentences[index]
    fast = make_tokenizer(is_fast=True).encode(sentence, add_special_tokens=False)
    slow = make_tokenizer(is_fast=False).encode(sentence, add_special_tokens=False)
    assert fast.pieces == slow.pieces
    assert [token.span for token in fast.tokens] == [token.span for token in slow.tokens]


# -- Regression: special tokens must not poison the forward aligner ----------
# The forward aligner searches the normalized text for each piece's surface. A
# special token's surface ("[CLS]") never occurs in Tibetan text, so searching
# for it fails and latches the `alignment_lost` flag, which used to strip the
# span from every content token that followed. Because `add_special_tokens`
# defaults to True, that silently disabled span mapping on the entire slow path
# -- and with it the add-in's ability to place a suggestion on a Word range.
# The two tests above both pass add_special_tokens=False, so neither can catch
# this; these exercise the default.
@pytest.mark.parametrize("index", [0, 9, 26, 55])
def test_slow_path_keeps_spans_when_special_tokens_are_present(
    make_tokenizer: MakeTokenizer, corpus_sentences: list[str], index: int
) -> None:
    encoded = make_tokenizer(is_fast=False).encode(corpus_sentences[index])

    assert encoded.num_special_tokens == 2
    assert all(token.span is None for token in encoded.tokens if token.is_special)
    # Every content token must still be anchored to the source text.
    assert all(token.span is not None for token in encoded.content_tokens)
    _assert_span_ground_truth(encoded)


@pytest.mark.parametrize("index", [0, 9, 26, 55])
def test_paths_agree_on_spans_with_special_tokens_enabled(
    make_tokenizer: MakeTokenizer, corpus_sentences: list[str], index: int
) -> None:
    sentence = corpus_sentences[index]
    fast = make_tokenizer(is_fast=True).encode(sentence)
    slow = make_tokenizer(is_fast=False).encode(sentence)
    assert [token.span for token in fast.tokens] == [token.span for token in slow.tokens]


@pytest.mark.parametrize("index", [0, 12, 33])
def test_byte_offsets_are_consistent_with_utf8_encoding(
    tokenizer: TiBERTTokenizer, corpus_sentences: list[str], index: int
) -> None:
    encoded = tokenizer.encode(corpus_sentences[index])
    normalized = encoded.normalized
    for token in encoded.content_tokens:
        span = token.span
        assert span is not None
        assert span.byte_start == len(normalized[: span.char_start].encode("utf-8"))
        assert span.byte_end == len(normalized[: span.char_end].encode("utf-8"))
        assert span.byte_length == len(token.text.encode("utf-8"))
        # Tibetan is three bytes per code point, so bytes must exceed chars.
        assert span.byte_length > span.char_length


def test_spans_are_contiguous_and_non_overlapping(
    tokenizer: TiBERTTokenizer, corpus_sentences: list[str]
) -> None:
    encoded = tokenizer.encode(corpus_sentences[8])
    spans = [token.span for token in encoded.content_tokens]
    assert all(span is not None for span in spans)
    bounds = [(span.char_start, span.char_end) for span in spans if span is not None]
    assert bounds[0][0] == 0
    assert bounds[-1][1] == len(encoded.normalized)
    assert all(prev[1] == nxt[0] for prev, nxt in pairwise(bounds))


def test_token_at_char_maps_offsets_back_to_the_covering_token(
    tokenizer: TiBERTTokenizer, corpus_sentences: list[str]
) -> None:
    encoded = tokenizer.encode(corpus_sentences[3])
    for token in encoded.content_tokens:
        span = token.span
        assert span is not None
        assert encoded.token_at_char(span.char_start) is token
        assert encoded.token_at_char(span.char_end - 1) is token
    assert encoded.token_at_char(-1) is None
    assert encoded.token_at_char(len(encoded.normalized)) is None


# -- tokenize ---------------------------------------------------------------
def test_tokenize_returns_raw_pieces_without_special_tokens(
    tokenizer: TiBERTTokenizer, normalizer: TextNormalizer, corpus_sentences: list[str]
) -> None:
    sentence = corpus_sentences[10]
    pieces = tokenizer.tokenize(sentence)
    assert CLS_PIECE not in pieces
    assert SEP_PIECE not in pieces
    # Raw pieces keep the subword marker; stripping it reconstructs the text.
    assert any(piece.startswith(METASPACE) for piece in pieces)
    assert "".join(piece.removeprefix(METASPACE) for piece in pieces) == normalizer.normalize(
        sentence
    )


def test_tokenize_of_a_bare_lexicon_entry_yields_one_piece(
    tokenizer: TiBERTTokenizer, lexicon_sample: list[str]
) -> None:
    # A bare, tsheg-less lexicon headword is a single contiguous run.
    entry = next(item for item in lexicon_sample if item and not (set(item) & {"་", "༌"}))
    assert tokenizer.tokenize(entry) == [f"{METASPACE}{entry}"]


# -- decode -----------------------------------------------------------------
@pytest.mark.parametrize("index", [0, 14, 47])
def test_decode_round_trips_to_the_normalized_text(
    tokenizer: TiBERTTokenizer, corpus_sentences: list[str], index: int
) -> None:
    encoded = tokenizer.encode(corpus_sentences[index])
    assert tokenizer.decode(encoded.ids) == encoded.normalized


def test_decode_can_retain_special_tokens(
    tokenizer: TiBERTTokenizer, corpus_sentences: list[str]
) -> None:
    encoded = tokenizer.encode(corpus_sentences[1], add_special_tokens=True)
    with_specials = tokenizer.decode(encoded.ids, skip_special_tokens=False)
    assert with_specials.startswith(CLS_PIECE)
    assert with_specials.endswith(SEP_PIECE)
    assert encoded.normalized in with_specials


@pytest.mark.parametrize("ids", [123, None, 4.5, "abc", b"ab"])
def test_decode_rejects_non_sequences_and_strings(tokenizer: TiBERTTokenizer, ids: object) -> None:
    with pytest.raises(InputNotStringError) as exc_info:
        tokenizer.decode(ids)  # type: ignore[arg-type]
    assert exc_info.value.context["received_type"] == type(ids).__name__


def test_decode_wraps_backend_failure_as_detokenization_error(
    settings: TokenizationSettings,
) -> None:
    boom = RuntimeError("sentencepiece exploded")
    tokenizer = TiBERTTokenizer(settings, loader=_loader_for(_ExplodingDecoder(boom)))
    with pytest.raises(DetokenizationError) as exc_info:
        tokenizer.decode([1, 2, 3])
    assert exc_info.value.context["num_ids"] == 3
    assert exc_info.value.__cause__ is boom


# -- Input validation -------------------------------------------------------
@pytest.mark.parametrize("value", [123, None, 4.5, ["a"], b"bytes", ("a",)])
def test_encode_rejects_non_string_input(tokenizer: TiBERTTokenizer, value: object) -> None:
    with pytest.raises(InputNotStringError) as exc_info:
        tokenizer.encode(value)  # type: ignore[arg-type]
    assert exc_info.value.context["received_type"] == type(value).__name__


@pytest.mark.parametrize("text", ["", "   ", "\t\n", " \n\t "])
def test_encode_rejects_empty_and_whitespace_only_input(
    tokenizer: TiBERTTokenizer, text: str
) -> None:
    with pytest.raises(EmptyInputError):
        tokenizer.encode(text)


def test_encode_rejects_input_that_normalizes_to_nothing(tokenizer: TiBERTTokenizer) -> None:
    # U+200B is a format character: it survives ``str.strip`` but is removed by
    # the Stage 2 normalizer, so emptiness must be re-checked after normalizing.
    with pytest.raises(EmptyInputError):
        tokenizer.encode("​​")


# -- Truncation -------------------------------------------------------------
def test_encode_raises_when_too_long_and_truncation_not_requested(
    make_tokenizer: MakeTokenizer, corpus_sentences: list[str]
) -> None:
    settings = TokenizationSettings(max_sequence_length=4)
    tokenizer = make_tokenizer(settings=settings)
    with pytest.raises(InputTooLongError) as exc_info:
        tokenizer.encode(corpus_sentences[2], truncate=False)
    context = exc_info.value.context
    assert context["maximum"] == 4
    assert context["produced"] > 4


def test_encode_truncates_on_request_and_reports_it(
    make_tokenizer: MakeTokenizer, corpus_sentences: list[str]
) -> None:
    settings = TokenizationSettings(max_sequence_length=4)
    tokenizer = make_tokenizer(settings=settings)
    encoded = tokenizer.encode(corpus_sentences[2], truncate=True)
    assert encoded.was_truncated is True
    assert len(encoded) == 4
    assert encoded.normalized  # the normalized text is still reported in full
    assert len(encoded.normalized) > 4


def test_short_input_within_the_limit_is_not_truncated(
    make_tokenizer: MakeTokenizer, lexicon_sample: list[str]
) -> None:
    settings = TokenizationSettings(max_sequence_length=64)
    tokenizer = make_tokenizer(settings=settings)
    encoded = tokenizer.encode(lexicon_sample[1], truncate=True)
    assert encoded.was_truncated is False


# -- Unknown tokens ---------------------------------------------------------
def test_encoding_without_unknown_pieces_reports_none(
    tokenizer: TiBERTTokenizer, corpus_sentences: list[str]
) -> None:
    encoded = tokenizer.encode(corpus_sentences[2])
    assert encoded.has_unknown is False
    assert encoded.num_unknown == 0
    assert encoded.unknown_ratio == 0.0


def test_unknown_pieces_are_flagged_and_counted(
    make_tokenizer: MakeTokenizer, corpus_sentences: list[str]
) -> None:
    sentence = corpus_sentences[2]
    # Choose the unknown surface from a piece this text really produces.
    baseline = make_tokenizer().encode(sentence, add_special_tokens=False)
    missing_surface = baseline.content_tokens[3].text

    encoded = make_tokenizer(unk_surface=missing_surface).encode(sentence)
    assert encoded.has_unknown is True
    assert encoded.num_unknown == 1
    assert encoded.unknown_ratio == pytest.approx(encoded.num_unknown / encoded.num_content_tokens)
    assert 0.0 < encoded.unknown_ratio <= 1.0
    unknown = [token for token in encoded.tokens if token.is_unknown]
    assert len(unknown) == 1
    assert missing_surface not in [token.text for token in encoded.content_tokens]


# -- Failure translation ----------------------------------------------------
def test_backend_tokenization_failure_is_wrapped_with_cause(
    settings: TokenizationSettings, corpus_sentences: list[str]
) -> None:
    boom = RuntimeError("backend segfault")
    tokenizer = TiBERTTokenizer(settings, loader=_loader_for(_ExplodingBackend(boom)))
    with pytest.raises(TokenizationError) as exc_info:
        tokenizer.encode(corpus_sentences[0])
    assert type(exc_info.value) is TokenizationError
    assert exc_info.value.__cause__ is boom


def test_backend_tokenization_error_is_propagated_unchanged(
    settings: TokenizationSettings, corpus_sentences: list[str]
) -> None:
    original = InputTooLongError(produced=9_000, maximum=512)
    tokenizer = TiBERTTokenizer(settings, loader=_loader_for(_ExplodingBackend(original)))
    with pytest.raises(InputTooLongError) as exc_info:
        tokenizer.encode(corpus_sentences[0])
    assert exc_info.value is original


def test_loader_failure_propagates_from_the_constructor(
    settings: TokenizationSettings,
) -> None:
    failure = TokenizerLoadError("model directory missing", context={"source": "nowhere"})

    def _failing_loader(_: TokenizationSettings) -> BackendTokenizer:
        raise failure

    with pytest.raises(TokenizerLoadError) as exc_info:
        TiBERTTokenizer(settings, loader=_failing_loader)
    assert exc_info.value is failure


# -- default_tibert_loader --------------------------------------------------
def test_default_loader_converts_load_failure_into_typed_error(
    monkeypatch: pytest.MonkeyPatch, settings: TokenizationSettings
) -> None:
    boom = OSError("offline: cannot reach the model hub")
    _install_stub_transformers(monkeypatch, error=boom)
    with pytest.raises(TokenizerLoadError) as exc_info:
        default_tibert_loader(settings)
    context = exc_info.value.context
    assert context["source"] == settings.model_id
    assert context["cache_dir"] == str(settings.model_cache_dir)
    assert exc_info.value.__cause__ is boom


def test_default_loader_returns_the_backend_and_requests_a_fast_tokenizer(
    monkeypatch: pytest.MonkeyPatch, settings: TokenizationSettings
) -> None:
    backend = FakeBackendTokenizer()
    calls = _install_stub_transformers(monkeypatch, result=backend)
    assert default_tibert_loader(settings) is backend
    source, kwargs = calls[0]
    assert source == settings.model_id
    # Native offset mappings require the fast (Rust) tokenizer.
    assert kwargs["use_fast"] is True
    assert kwargs["trust_remote_code"] is settings.trust_remote_code
    assert kwargs["cache_dir"] == str(settings.model_cache_dir)


def test_default_loader_prefers_a_local_model_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    local = tmp_path / "tibert"
    local.mkdir()
    settings = TokenizationSettings(model_local_path=local)
    calls = _install_stub_transformers(monkeypatch, result=FakeBackendTokenizer())
    default_tibert_loader(settings)
    assert calls[0][0] == str(local)


# Regression guard for a defect found only by running the real model: TiBERT's
# published tokenizer_config.json sets do_lower_case=True, which activates BERT's
# accent stripping. That routine deletes every Unicode Mn character, and in
# Tibetan the Mn class holds the vowel signs and subjoined letters -- so བཀྲ
# silently became བཀ and ཤིས became [UNK]. TokenizationSettings.do_lower_case
# existed and defaulted to False, but the loader never passed it through.
# Hermetic on purpose: this must fail in the default suite, without network.
def test_default_loader_disables_lowercasing_and_accent_stripping(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    class _StubAutoTokenizer:
        @staticmethod
        def from_pretrained(source: str, **kwargs: object) -> FakeBackendTokenizer:
            captured.update(kwargs)
            captured["source"] = source
            return FakeBackendTokenizer()

    stub_module = types.ModuleType("transformers")
    stub_module.AutoTokenizer = _StubAutoTokenizer  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "transformers", stub_module)

    default_tibert_loader(TokenizationSettings())

    assert captured["do_lower_case"] is False, "Tibetan is caseless; lowercasing must be off"
    assert captured["strip_accents"] is False, (
        "strip_accents deletes Tibetan vowel signs (Unicode Mn)"
    )


def test_default_loader_forwards_the_configured_lower_casing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The setting is honoured rather than hard-coded."""
    captured: dict[str, object] = {}

    class _StubAutoTokenizer:
        @staticmethod
        def from_pretrained(source: str, **kwargs: object) -> FakeBackendTokenizer:
            captured.update(kwargs)
            return FakeBackendTokenizer()

    stub_module = types.ModuleType("transformers")
    stub_module.AutoTokenizer = _StubAutoTokenizer  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "transformers", stub_module)

    default_tibert_loader(TokenizationSettings(do_lower_case=True))
    assert captured["do_lower_case"] is True


def test_default_loader_is_the_constructor_default() -> None:
    # Guards against silently swapping the production loader for a test double.
    parameter = inspect.signature(TiBERTTokenizer.__init__).parameters["loader"]
    assert parameter.default is default_tibert_loader
