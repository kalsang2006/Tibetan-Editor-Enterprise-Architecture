"""Unit and integration tests for TEEA Structural Syllable Validator."""

import pytest

from teea.ai.engines import DummyInferenceEngine
from teea.engine import TEEAEngine
from teea.nlp.structural_validator import (
    StructuralErrorType,
    StructuralValidator,
)


@pytest.fixture
def validator() -> StructuralValidator:
    return StructuralValidator()


# -----------------------------------------------------------------------------
# MUST FAIL TESTS (STRUCTURAL ERRORS)
# -----------------------------------------------------------------------------

def test_double_vowel(validator: StructuralValidator) -> None:
    res = validator.validate_syllable("གིུ")
    assert not res.is_valid
    assert res.error_type == StructuralErrorType.DOUBLE_VOWEL


def test_invalid_post_suffix(validator: StructuralValidator) -> None:
    res = validator.validate_syllable("བདགག")
    assert not res.is_valid
    assert res.error_type == StructuralErrorType.INVALID_POST_SUFFIX


def test_gibberish(validator: StructuralValidator) -> None:
    res = validator.validate_syllable("ཀཀཀ")
    assert not res.is_valid
    assert res.error_type == StructuralErrorType.GIBBERISH


def test_invalid_prefix(validator: StructuralValidator) -> None:
    res = validator.validate_syllable("ཞཀ")
    assert not res.is_valid
    assert res.error_type == StructuralErrorType.INVALID_PREFIX


def test_invalid_post_suffix_bodg(validator: StructuralValidator) -> None:
    res = validator.validate_syllable("བོདག")
    assert not res.is_valid
    assert res.error_type == StructuralErrorType.INVALID_POST_SUFFIX


def test_double_vowel_with_base(validator: StructuralValidator) -> None:
    res = validator.validate_syllable("གིུ")
    assert not res.is_valid
    assert res.error_type == StructuralErrorType.DOUBLE_VOWEL


def test_triple_vowel(validator: StructuralValidator) -> None:
    res = validator.validate_syllable("གིེོུ")
    assert not res.is_valid
    assert res.error_type == StructuralErrorType.DOUBLE_VOWEL


def test_too_many_consonants(validator: StructuralValidator) -> None:
    res = validator.validate_syllable("ཀཀཀཀཀཀ")
    assert not res.is_valid
    assert res.error_type in (StructuralErrorType.TOO_MANY_CONSONANTS, StructuralErrorType.GIBBERISH)


# -----------------------------------------------------------------------------
# MUST PASS TESTS (STRUCTURALLY VALID)
# -----------------------------------------------------------------------------

def test_valid_bdag(validator: StructuralValidator) -> None:
    res = validator.validate_syllable("བདག")
    assert res.is_valid


def test_valid_bod(validator: StructuralValidator) -> None:
    res = validator.validate_syllable("བོད")
    assert res.is_valid


def test_valid_rgyu(validator: StructuralValidator) -> None:
    res = validator.validate_syllable("རྒྱུ")
    assert res.is_valid


def test_valid_yin(validator: StructuralValidator) -> None:
    res = validator.validate_syllable("ཡིན")
    assert res.is_valid


def test_valid_bsgrubs(validator: StructuralValidator) -> None:
    res = validator.validate_syllable("བསྒྲུབས")
    assert res.is_valid


def test_valid_sgrub(validator: StructuralValidator) -> None:
    res = validator.validate_syllable("སྒྲུབ")
    assert res.is_valid


def test_valid_dang(validator: StructuralValidator) -> None:
    res = validator.validate_syllable("དང")
    assert res.is_valid


def test_valid_gsal(validator: StructuralValidator) -> None:
    res = validator.validate_syllable("གསལ")
    assert res.is_valid


def test_valid_bla(validator: StructuralValidator) -> None:
    res = validator.validate_syllable("བླ")
    assert res.is_valid


def test_valid_smra(validator: StructuralValidator) -> None:
    res = validator.validate_syllable("སྨྲ")
    assert res.is_valid


def test_user_target_case_phyiw(validator: StructuralValidator) -> None:
    res = validator.validate_syllable("ཕྱིཝ")
    assert not res.is_valid
    assert res.error_type == StructuralErrorType.INVALID_SUFFIX


def test_user_target_case_dgag(validator: StructuralValidator) -> None:
    res = validator.validate_syllable("དགག")
    assert not res.is_valid
    assert res.error_type == StructuralErrorType.INVALID_POST_SUFFIX


def test_user_target_case_parh(validator: StructuralValidator) -> None:
    res = validator.validate_syllable("པརྷ")
    assert not res.is_valid
    assert res.error_type == StructuralErrorType.INVALID_SUBFIX


def test_user_target_case_klok(validator: StructuralValidator) -> None:
    res = validator.validate_syllable("ཀློཀ")
    assert not res.is_valid
    assert res.error_type == StructuralErrorType.INVALID_SUFFIX


def test_user_target_case_bongbya(validator: StructuralValidator) -> None:
    res = validator.validate_syllable("བོངབྱ")
    assert not res.is_valid
    assert res.error_type == StructuralErrorType.INVALID_POST_SUFFIX


# -----------------------------------------------------------------------------
# INTEGRATION TEST IN SPELL CHECKER PLUGIN
# -----------------------------------------------------------------------------

def test_spell_checker_integration_structural_validation() -> None:
    engine = TEEAEngine(ai_engine=DummyInferenceEngine())
    res = engine.analyze("དེ་རིང་ང་བོདག་ཡིནན།")

    # Verify that structural errors are caught
    suggestions = res.suggestions
    flagged_words = [s.message for s in suggestions if "teea.spelling" in s.source]
    assert len(flagged_words) >= 2
    assert any("བོདག" in msg for msg in flagged_words)
    assert any("ཡིནན" in msg for msg in flagged_words)

    # Verify document patch replacement contains corrections.
    # When བོདག is followed by ་, the tsheg-dedup fix strips the trailing tsheg
    # from the replacement (བོད instead of བོད་) to avoid creating double tsheg.
    replacements = [op.replacement for op in res.patch.operations if op.replacement]
    assert (
        "བོད་" in replacements
        or "བདག་" in replacements
        or "བོད་ག" in replacements
        or "བདག་" in replacements
        or "བོད" in replacements  # tsheg-dedup: trailing ་ stripped when next char is ་
    )
    assert "ཡིན་" in replacements or "ཡིན" in replacements
