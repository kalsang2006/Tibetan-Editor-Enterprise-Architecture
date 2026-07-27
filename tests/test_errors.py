"""Unit tests for the error taxonomy (:mod:`teea.core.errors`) and the
tokenization exception hierarchy."""

from __future__ import annotations

import pytest

from teea.core.errors import (
    ConfigurationError,
    ErrorCode,
    InputValidationError,
    TEEAError,
)
from teea.nlp.tokenization.exceptions import (
    DetokenizationError,
    EmptyInputError,
    InputNotStringError,
    InputTooLongError,
    NormalizationError,
    OffsetAlignmentError,
    TokenizationError,
    TokenizerLoadError,
    TokenizerNotInitializedError,
)


def test_error_codes_are_unique() -> None:
    values = [code.value for code in ErrorCode]
    assert len(values) == len(set(values))


def test_base_error_defaults_to_unknown_code() -> None:
    err = TEEAError("boom")
    assert err.code is ErrorCode.UNKNOWN
    assert err.message == "boom"
    assert err.context == {}


def test_error_to_dict_is_serializable() -> None:
    err = TEEAError("boom", code=ErrorCode.INPUT_INVALID, context={"n": 3})
    payload = err.to_dict()
    assert payload == {
        "error": "TEEAError",
        "code": "TEEA-0002",
        "message": "boom",
        "context": {"n": 3},
    }


def test_error_context_is_copied_not_aliased() -> None:
    source = {"k": 1}
    err = TEEAError("x", context=source)
    source["k"] = 2
    assert err.context == {"k": 1}


def test_error_cause_is_chained() -> None:
    cause = ValueError("root")
    err = TEEAError("wrapped", cause=cause)
    assert err.__cause__ is cause


def test_configuration_error_default_code() -> None:
    assert ConfigurationError("bad").code is ErrorCode.CONFIGURATION_INVALID


def test_input_validation_error_default_code() -> None:
    assert InputValidationError("bad").code is ErrorCode.INPUT_INVALID


@pytest.mark.parametrize(
    ("exc", "expected_code"),
    [
        (TokenizationError("x"), ErrorCode.TOKENIZATION_FAILED),
        (TokenizerLoadError("x"), ErrorCode.TOKENIZER_LOAD_FAILED),
        (TokenizerNotInitializedError("x"), ErrorCode.TOKENIZER_NOT_INITIALIZED),
        (DetokenizationError("x"), ErrorCode.DETOKENIZATION_FAILED),
        (NormalizationError("x"), ErrorCode.NORMALIZATION_FAILED),
        (OffsetAlignmentError("x"), ErrorCode.OFFSET_ALIGNMENT_FAILED),
    ],
)
def test_tokenization_exception_codes(exc: TokenizationError, expected_code: ErrorCode) -> None:
    assert exc.code is expected_code
    assert isinstance(exc, TEEAError)


def test_input_not_string_error_records_type() -> None:
    err = InputNotStringError("int")
    assert err.code is ErrorCode.INPUT_NOT_STRING
    assert err.context["received_type"] == "int"


def test_empty_input_error_message() -> None:
    err = EmptyInputError()
    assert err.code is ErrorCode.INPUT_EMPTY
    assert "empty" in err.message.lower()


def test_input_too_long_error_records_sizes() -> None:
    err = InputTooLongError(produced=600, maximum=512)
    assert err.code is ErrorCode.INPUT_TOO_LONG
    assert err.context == {"produced": 600, "maximum": 512}


def test_exceptions_can_be_caught_as_base_family() -> None:
    with pytest.raises(TokenizationError):
        raise InputTooLongError(produced=1, maximum=0)
    with pytest.raises(TEEAError):
        raise DetokenizationError("x")
