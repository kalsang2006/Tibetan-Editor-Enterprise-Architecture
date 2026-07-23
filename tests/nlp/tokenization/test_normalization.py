"""Unit tests for Stage 2 Unicode normalization (:mod:`teea.nlp.tokenization.normalization`).

Normalization sits directly upstream of tokenization, so every guarantee the
tokenizer, the spell checker and the plagiarism pipeline make about spans and
vocabulary coverage rests on this one class. These tests therefore pin down the
contract rather than the implementation:

* the configured :class:`~teea.core.config.NormalizationForm` is the form that
  actually gets applied, and ``.form`` reports it truthfully;
* :meth:`TextNormalizer.normalize` is **idempotent**, verified against the real
  Milarepa corpus rather than invented strings — token spans computed against a
  normalized string are only meaningful if re-normalizing is a no-op;
* real Tibetan content is **never** altered: the corpus and the classical
  lexicon round-trip verbatim under all four forms, and the tsheg/shad survive
  control-stripping because they are ordinary punctuation, not controls;
* the normalizer genuinely canonicalizes — proved with a precomposed/decomposed
  pair *derived from* :mod:`unicodedata` at import time rather than hardcoded,
  so the tests cannot drift out of sync with the Unicode database;
* the documented cleaning switches (``strip_controls``, ``collapse_whitespace``)
  behave exactly as the class docstring promises, including their interaction:
  collapsing subsumes the newline/tab that stripping deliberately preserves.
"""

from __future__ import annotations

import unicodedata

import pytest

from teea.core.config import NormalizationForm, TokenizationSettings
from teea.core.types import (
    LINE_BREAK_CHARS,
    SHAD,
    TIBETAN_BLOCK_END,
    TIBETAN_BLOCK_START,
    TSHEG,
    is_tibetan_char,
    tibetan_ratio,
)
from teea.nlp.tokenization import TextNormalizer
from teea.nlp.tokenization.normalization import _PRESERVED_CONTROLS

ALL_FORMS: tuple[NormalizationForm, ...] = ("NFC", "NFKC", "NFD", "NFKD")
COMPOSING_FORMS: tuple[NormalizationForm, ...] = ("NFC", "NFKC")
DECOMPOSING_FORMS: tuple[NormalizationForm, ...] = ("NFD", "NFKD")
CANONICAL_FORMS: tuple[NormalizationForm, ...] = ("NFC", "NFD")
COMPATIBILITY_FORMS: tuple[NormalizationForm, ...] = ("NFKC", "NFKD")

#: ``(collapse_whitespace, strip_controls)`` — the full switch matrix.
FLAG_COMBINATIONS: tuple[tuple[bool, bool], ...] = (
    (True, True),
    (True, False),
    (False, True),
    (False, False),
)

# Invisible code points are spelled with escapes so the source stays legible and
# cannot be silently mangled by an editor that drops zero-width characters.
ZWSP = "\u200b"  # ZERO WIDTH SPACE (Cf) — endemic in copy-pasted Tibetan
ZWJ = "\u200d"  # ZERO WIDTH JOINER (Cf)
BOM = "\ufeff"  # ZERO WIDTH NO-BREAK SPACE / BOM (Cf)
NBSP = "\u00a0"  # NO-BREAK SPACE (Zs — whitespace, but not a control)
NUL = "\x00"  # NULL (Cc)
UNIT_SEP = "\x1f"  # UNIT SEPARATOR (Cc)


# -- Unicode fixtures derived from the Unicode database -----------------------
# These are *discovered*, not guessed: if the Unicode database ever stops
# exhibiting the properties relied upon here, collection fails loudly instead of
# the suite silently asserting something untrue.


def _find_composable_pair() -> tuple[str, str]:
    """Return a ``(precomposed, decomposed)`` pair that NFC recomposes."""
    for code_point in range(0x00C0, 0x0400):
        precomposed = chr(code_point)
        decomposed = unicodedata.normalize("NFD", precomposed)
        if decomposed != precomposed and unicodedata.normalize("NFC", decomposed) == precomposed:
            return precomposed, decomposed
    raise RuntimeError("Unicode database exposes no canonically composable character")


def _find_tibetan_decomposable() -> tuple[str, str]:
    """Return a Tibetan ``(stack, canonical decomposition)`` pair."""
    for code_point in range(TIBETAN_BLOCK_START, TIBETAN_BLOCK_END + 1):
        stack = chr(code_point)
        decomposed = unicodedata.normalize("NFD", stack)
        if decomposed != stack:
            return stack, decomposed
    raise RuntimeError("Unicode database exposes no decomposable Tibetan character")


def _find_tibetan_compatibility_char() -> tuple[str, str]:
    """Return a Tibetan char whose compatibility form differs from its canonical form."""
    for code_point in range(TIBETAN_BLOCK_START, TIBETAN_BLOCK_END + 1):
        char = chr(code_point)
        folded = unicodedata.normalize("NFKC", char)
        if folded != unicodedata.normalize("NFC", char):
            return char, folded
    raise RuntimeError("Unicode database exposes no Tibetan compatibility character")


PRECOMPOSED, DECOMPOSED = _find_composable_pair()
TIBETAN_STACK, TIBETAN_STACK_DECOMPOSED = _find_tibetan_decomposable()
TIBETAN_COMPAT, TIBETAN_COMPAT_FOLDED = _find_tibetan_compatibility_char()

#: Exercises every form differently: canonical composition *and* a Tibetan
#: character that only the compatibility forms touch.
MIXED_SAMPLE = f"བཀྲ{TSHEG}ཤིས{SHAD}{TIBETAN_COMPAT}{PRECOMPOSED}{DECOMPOSED}"

#: Real Tibetan greeting, used wherever the specific words are irrelevant.
TASHI_DELEK = f"བཀྲ{TSHEG}ཤིས{TSHEG}བདེ{TSHEG}ལེགས{SHAD}"


def _raw(form: NormalizationForm = "NFC") -> TextNormalizer:
    """Build a normalizer that *only* applies the Unicode form (no cleaning)."""
    return TextNormalizer(form=form, collapse_whitespace=False, strip_controls=False)


# -- Configuration ------------------------------------------------------------


def test_default_form_is_nfc() -> None:
    assert TextNormalizer().form == "NFC"


@pytest.mark.parametrize("form", ALL_FORMS)
def test_form_property_reflects_the_configured_form(form: NormalizationForm) -> None:
    assert TextNormalizer(form=form).form == form


@pytest.mark.parametrize("form", ALL_FORMS)
def test_form_tracks_the_settings_value_it_is_built_from(form: NormalizationForm) -> None:
    configured = TokenizationSettings(normalization_form=form)
    assert TextNormalizer(form=configured.normalization_form).form == form


def test_default_settings_select_nfc(settings: TokenizationSettings) -> None:
    normalizer = TextNormalizer(form=settings.normalization_form)
    assert normalizer.form == settings.normalization_form == "NFC"


def test_normalizer_fixture_is_an_nfc_normalizer(normalizer: TextNormalizer) -> None:
    assert normalizer.form == "NFC"


# -- Normalization forms ------------------------------------------------------


@pytest.mark.parametrize("form", ALL_FORMS)
def test_each_form_applies_the_reference_unicode_algorithm(form: NormalizationForm) -> None:
    assert _raw(form).normalize(MIXED_SAMPLE) == unicodedata.normalize(form, MIXED_SAMPLE)


def test_the_four_forms_are_not_interchangeable_on_the_sample() -> None:
    """Guards the parametrized tests above from degenerating into a single case."""
    results = {_raw(form).normalize(MIXED_SAMPLE) for form in ALL_FORMS}
    assert len(results) > 1


@pytest.mark.parametrize("form", ALL_FORMS)
def test_output_is_normalized_under_its_own_form(
    form: NormalizationForm, corpus_sentences: list[str]
) -> None:
    normalizer = TextNormalizer(form=form)
    assert all(unicodedata.is_normalized(form, normalizer.normalize(s)) for s in corpus_sentences)


# -- Canonicalization: precomposed vs decomposed ------------------------------


def test_derived_pair_really_is_a_composition_pair() -> None:
    """State the premise the canonicalization tests rest on, explicitly."""
    assert PRECOMPOSED != DECOMPOSED
    assert len(PRECOMPOSED) == 1
    assert unicodedata.normalize("NFC", DECOMPOSED) == PRECOMPOSED
    assert unicodedata.normalize("NFD", PRECOMPOSED) == DECOMPOSED


@pytest.mark.parametrize("form", COMPOSING_FORMS)
def test_composing_forms_map_both_spellings_to_the_precomposed_form(
    form: NormalizationForm,
) -> None:
    normalizer = _raw(form)
    assert normalizer.normalize(DECOMPOSED) == PRECOMPOSED
    assert normalizer.normalize(PRECOMPOSED) == PRECOMPOSED


@pytest.mark.parametrize("form", DECOMPOSING_FORMS)
def test_decomposing_forms_map_both_spellings_to_the_decomposed_form(
    form: NormalizationForm,
) -> None:
    normalizer = _raw(form)
    assert normalizer.normalize(PRECOMPOSED) == DECOMPOSED
    assert normalizer.normalize(DECOMPOSED) == DECOMPOSED


@pytest.mark.parametrize("form", ALL_FORMS)
def test_normalization_unifies_the_two_spellings_in_context(form: NormalizationForm) -> None:
    """Two byte sequences that render identically must tokenize identically."""
    left = f"བཀྲ{TSHEG}{PRECOMPOSED}{SHAD}"
    right = f"བཀྲ{TSHEG}{DECOMPOSED}{SHAD}"
    normalizer = TextNormalizer(form=form)
    assert left != right
    assert normalizer.normalize(left) == normalizer.normalize(right)


def test_tibetan_stacks_are_composition_exclusions() -> None:
    """Tibetan precomposed stacks decompose under NFC and are never recomposed.

    This is documented Unicode behavior (every Tibetan canonical decomposition
    is a composition exclusion), and it is why the corpus can be simultaneously
    NFC- and NFD-normalized. Both spellings still converge on one form, which is
    the property downstream consumers actually depend on.
    """
    assert TIBETAN_STACK != TIBETAN_STACK_DECOMPOSED
    for form in CANONICAL_FORMS:
        normalizer = _raw(form)
        assert normalizer.normalize(TIBETAN_STACK) == TIBETAN_STACK_DECOMPOSED
        assert normalizer.normalize(TIBETAN_STACK_DECOMPOSED) == TIBETAN_STACK_DECOMPOSED


@pytest.mark.parametrize("form", COMPATIBILITY_FORMS)
def test_compatibility_forms_fold_the_tibetan_compatibility_character(
    form: NormalizationForm,
) -> None:
    assert TIBETAN_COMPAT_FOLDED != TIBETAN_COMPAT
    assert _raw(form).normalize(TIBETAN_COMPAT) == TIBETAN_COMPAT_FOLDED


@pytest.mark.parametrize("form", CANONICAL_FORMS)
def test_canonical_forms_leave_the_tibetan_compatibility_character_alone(
    form: NormalizationForm,
) -> None:
    assert _raw(form).normalize(TIBETAN_COMPAT) == TIBETAN_COMPAT


# -- Idempotence --------------------------------------------------------------


@pytest.mark.parametrize("form", ALL_FORMS)
def test_normalize_is_idempotent_over_the_real_corpus(
    form: NormalizationForm, corpus_sentences: list[str]
) -> None:
    normalizer = TextNormalizer(form=form)
    assert corpus_sentences
    for sentence in corpus_sentences:
        once = normalizer.normalize(sentence)
        assert normalizer.normalize(once) == once


@pytest.mark.parametrize("form", ALL_FORMS)
def test_normalize_is_idempotent_over_the_real_lexicon(
    form: NormalizationForm, lexicon_sample: list[str]
) -> None:
    normalizer = TextNormalizer(form=form)
    assert lexicon_sample
    for entry in lexicon_sample:
        once = normalizer.normalize(entry)
        assert normalizer.normalize(once) == once


@pytest.mark.parametrize(("collapse", "strip"), FLAG_COMBINATIONS)
def test_normalize_is_idempotent_for_every_flag_combination(collapse: bool, strip: bool) -> None:
    normalizer = TextNormalizer(form="NFC", collapse_whitespace=collapse, strip_controls=strip)
    messy = f"  བཀྲ{TSHEG}{ZWSP} ཤིས{SHAD}\n\n\tབདེ{TSHEG}ལེགས{SHAD}  {NUL}"
    once = normalizer.normalize(messy)
    assert normalizer.normalize(once) == once


# Regression guard: control stripping must happen *before* Unicode normalization.
# When it ran afterwards, a stripped format character left the surviving combining
# marks in non-canonical order, so the output was not normalized and the documented
# idempotence guarantee did not hold.
@pytest.mark.parametrize("collapse", [True, False])
def test_stripping_a_blocking_format_char_keeps_output_normalized(collapse: bool) -> None:
    """``normalize`` promises idempotence; a Cf char between combining marks broke it.

    ``TIBETAN VOWEL SIGN U`` (combining class 132) sorts *after* ``TIBETAN VOWEL
    SIGN AA`` (129), so NFC would reorder them — but only when they are adjacent.
    A zero-width space between them (endemic in copy-pasted Tibetan) blocks the
    reorder; stripping it afterwards yields non-NFC text that a second pass then
    rewrites, so spans computed on the first pass do not survive the second.
    """
    text = f"ཀུ{ZWSP}ཱ"
    normalizer = TextNormalizer(form="NFC", collapse_whitespace=collapse, strip_controls=True)
    once = normalizer.normalize(text)
    assert unicodedata.is_normalized("NFC", once)
    assert normalizer.normalize(once) == once


# -- Tibetan content is never altered -----------------------------------------


def test_corpus_sentences_are_already_nfc(corpus_sentences: list[str]) -> None:
    """Establish, via unicodedata, the premise of the round-trip test below."""
    assert corpus_sentences
    assert all(unicodedata.is_normalized("NFC", sentence) for sentence in corpus_sentences)


def test_nfc_round_trips_real_corpus_sentences_verbatim(
    normalizer: TextNormalizer, corpus_sentences: list[str]
) -> None:
    assert [normalizer.normalize(sentence) for sentence in corpus_sentences] == corpus_sentences


@pytest.mark.parametrize("form", ALL_FORMS)
def test_no_form_alters_pure_tibetan_lexicon_entries(
    form: NormalizationForm, lexicon_sample: list[str]
) -> None:
    normalizer = TextNormalizer(form=form)
    assert lexicon_sample
    for entry in lexicon_sample:
        assert tibetan_ratio(entry) == 1.0
        assert normalizer.normalize(entry) == entry


@pytest.mark.parametrize("form", ALL_FORMS)
def test_normalization_keeps_corpus_output_inside_the_tibetan_block(
    form: NormalizationForm, corpus_sentences: list[str]
) -> None:
    normalizer = TextNormalizer(form=form)
    for sentence in corpus_sentences:
        result = normalizer.normalize(sentence)
        assert result
        assert all(is_tibetan_char(char) for char in result)


def test_tsheg_and_shad_are_ordinary_punctuation_not_controls() -> None:
    """Explain why control-stripping structurally cannot touch Tibetan delimiters."""
    for char in (TSHEG, SHAD):
        assert is_tibetan_char(char)
        assert unicodedata.category(char) == "Po"


@pytest.mark.parametrize("form", ALL_FORMS)
def test_tsheg_and_shad_survive_every_form_and_every_cleaning_step(
    form: NormalizationForm,
) -> None:
    normalizer = TextNormalizer(form=form, collapse_whitespace=True, strip_controls=True)
    result = normalizer.normalize(TASHI_DELEK)
    assert result == TASHI_DELEK
    assert result.count(TSHEG) == 3
    assert result.count(SHAD) == 1


# -- Control and format character stripping -----------------------------------


def test_preserved_control_set_is_tab_plus_every_line_break() -> None:
    """Stage 2 must not delete document structure.

    Line breaks are preserved rather than stripped as control characters,
    because sentence segmentation (Stage 4) treats them as boundaries and Word
    encodes a paragraph mark as CR and a manual line break as VT. The set is
    shared with Stage 4 via ``core.types`` so the stages cannot drift apart.
    """
    assert frozenset({"\t"}) | LINE_BREAK_CHARS == _PRESERVED_CONTROLS
    # Regression guard for the specific characters Word emits.
    assert {"\n", "\r", "\v"} <= _PRESERVED_CONTROLS


@pytest.mark.parametrize(
    ("char", "category"),
    [
        (ZWSP, "Cf"),
        (ZWJ, "Cf"),
        (BOM, "Cf"),
        (NUL, "Cc"),
        (UNIT_SEP, "Cc"),
        # The legacy information separators are deliberately NOT line breaks, so
        # Stage 2 is still right to remove them as invalid characters.
        ("\x1c", "Cc"),
        ("\x1e", "Cc"),
    ],
)
def test_strip_controls_removes_cc_and_cf_characters(char: str, category: str) -> None:
    assert unicodedata.category(char) == category
    normalizer = TextNormalizer(form="NFC", collapse_whitespace=False, strip_controls=True)
    polluted = f"བཀྲ{TSHEG}{char}ཤིས{SHAD}"
    assert normalizer.normalize(polluted) == f"བཀྲ{TSHEG}ཤིས{SHAD}"


@pytest.mark.parametrize("preserved", sorted(_PRESERVED_CONTROLS))
def test_preserved_controls_survive_stripping_when_not_collapsing(preserved: str) -> None:
    normalizer = TextNormalizer(form="NFC", collapse_whitespace=False, strip_controls=True)
    polluted = f"བཀྲ{TSHEG}{preserved}{ZWSP}ཤིས{SHAD}"
    assert normalizer.normalize(polluted) == f"བཀྲ{TSHEG}{preserved}ཤིས{SHAD}"


def test_strip_controls_false_leaves_control_characters_intact() -> None:
    normalizer = TextNormalizer(form="NFC", collapse_whitespace=False, strip_controls=False)
    polluted = f"བཀྲ{TSHEG}{ZWSP}{NUL}{BOM}ཤིས{SHAD}"
    assert normalizer.normalize(polluted) == polluted


def test_stripping_controls_does_not_disturb_surrounding_tibetan() -> None:
    normalizer = TextNormalizer(form="NFC", collapse_whitespace=False, strip_controls=True)
    polluted = BOM + TASHI_DELEK.replace(SHAD, f"{ZWSP}{SHAD}")
    assert normalizer.normalize(polluted) == TASHI_DELEK


def test_no_break_space_is_not_a_control_and_survives_stripping() -> None:
    """NBSP is ``Zs``, not ``Cc``/``Cf``, so only whitespace handling may touch it."""
    assert unicodedata.category(NBSP) == "Zs"
    normalizer = TextNormalizer(form="NFC", collapse_whitespace=False, strip_controls=True)
    text = f"བཀྲ{SHAD}{NBSP}ཤིས{SHAD}"
    assert normalizer.normalize(text) == text


# -- Whitespace collapsing ----------------------------------------------------


def test_collapse_reduces_runs_to_a_single_space_and_strips_the_result() -> None:
    normalizer = TextNormalizer(form="NFC", collapse_whitespace=True, strip_controls=False)
    padded = f"   བཀྲ{SHAD}    ཤིས{SHAD}   "
    assert normalizer.normalize(padded) == f"བཀྲ{SHAD} ཤིས{SHAD}"


def test_collapse_also_eliminates_the_preserved_newline_and_tab() -> None:
    r"""Document the interaction between the two cleaning switches.

    ``strip_controls`` deliberately preserves ``\n`` and ``\t``, but
    ``collapse_whitespace`` runs afterwards and folds *every* whitespace run into
    a single space — so with both enabled (the defaults) the preserved
    characters never reach the output.
    """
    layout = f"བཀྲ{SHAD}\n\tཤིས{SHAD}"
    keeping = TextNormalizer(form="NFC", collapse_whitespace=False, strip_controls=True)
    collapsing = TextNormalizer(form="NFC", collapse_whitespace=True, strip_controls=True)
    assert keeping.normalize(layout) == layout
    assert collapsing.normalize(layout) == f"བཀྲ{SHAD} ཤིས{SHAD}"


def test_collapse_folds_non_ascii_whitespace_as_well() -> None:
    """``str.split()`` splits on all Unicode whitespace, so NBSP collapses too."""
    normalizer = TextNormalizer(form="NFC", collapse_whitespace=True, strip_controls=False)
    text = f"བཀྲ{SHAD}{NBSP}{NBSP}ཤིས{SHAD}"
    assert normalizer.normalize(text) == f"བཀྲ{SHAD} ཤིས{SHAD}"


def test_collapse_disabled_preserves_layout_verbatim() -> None:
    normalizer = TextNormalizer(form="NFC", collapse_whitespace=False, strip_controls=False)
    layout = f"  བཀྲ{SHAD}   \n\n  ཤིས{SHAD}  "
    assert normalizer.normalize(layout) == layout


def test_collapse_leaves_tsheg_delimited_structure_untouched() -> None:
    """Tibetan words are delimited by the tsheg, never by spaces."""
    normalizer = TextNormalizer(form="NFC")
    assert normalizer.normalize(f"  {TASHI_DELEK}  ") == TASHI_DELEK


# -- Degenerate input ---------------------------------------------------------


@pytest.mark.parametrize("form", ALL_FORMS)
@pytest.mark.parametrize(("collapse", "strip"), FLAG_COMBINATIONS)
def test_empty_input_returns_empty(form: NormalizationForm, collapse: bool, strip: bool) -> None:
    normalizer = TextNormalizer(form=form, collapse_whitespace=collapse, strip_controls=strip)
    assert normalizer.normalize("") == ""


def test_whitespace_only_input_collapses_to_empty() -> None:
    normalizer = TextNormalizer(form="NFC", collapse_whitespace=True, strip_controls=True)
    assert normalizer.normalize(f"   \n\t   {ZWSP}{NBSP}") == ""


def test_whitespace_only_input_is_preserved_when_collapsing_is_disabled() -> None:
    normalizer = TextNormalizer(form="NFC", collapse_whitespace=False, strip_controls=True)
    whitespace = "  \n\t  "
    assert normalizer.normalize(whitespace) == whitespace


def test_control_only_input_is_stripped_to_empty() -> None:
    normalizer = TextNormalizer(form="NFC", collapse_whitespace=False, strip_controls=True)
    assert normalizer.normalize(f"{ZWSP}{NUL}{BOM}") == ""


def test_single_tsheg_survives_as_meaningful_content() -> None:
    normalizer = TextNormalizer(form="NFC")
    assert normalizer.normalize(TSHEG) == TSHEG


# -- Statelessness ------------------------------------------------------------


def test_repeated_calls_on_different_inputs_do_not_interfere(
    corpus_sentences: list[str],
) -> None:
    normalizer = TextNormalizer(form="NFC")
    inputs = [
        *corpus_sentences[:8],
        "",
        f"   \n\t {ZWSP}   ",
        f"{TSHEG}{NUL}",
        f"  བཀྲ{SHAD}   ཤིས{SHAD}  ",
        MIXED_SAMPLE,
    ]
    # Ground truth: each input normalized by a pristine, single-use normalizer.
    isolated = {text: TextNormalizer(form="NFC").normalize(text) for text in inputs}
    interleaved = [normalizer.normalize(text) for text in inputs * 3]
    assert interleaved == [isolated[text] for text in inputs] * 3


def test_normalizer_carries_no_mutable_state_across_calls(corpus_sentences: list[str]) -> None:
    normalizer = TextNormalizer(form="NFKD", collapse_whitespace=False, strip_controls=False)
    before = dict(vars(normalizer))
    for sentence in corpus_sentences:
        normalizer.normalize(sentence)
    assert dict(vars(normalizer)) == before
    assert normalizer.form == "NFKD"


def test_two_normalizers_with_the_same_config_agree(corpus_sentences: list[str]) -> None:
    first = TextNormalizer(form="NFKC")
    second = TextNormalizer(form="NFKC")
    sample = corpus_sentences[:10]
    assert [first.normalize(s) for s in sample] == [second.normalize(s) for s in sample]
