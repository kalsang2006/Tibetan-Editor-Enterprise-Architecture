"""Structural Syllable Validator for Tibetan Orthography.

Validates individual Tibetan syllables against strict classical Tibetan orthographic
structural rules before dictionary or corpus lookup. Enforces hard-fail rules on:
- Double/multiple vowel stacking
- Illegal post-suffixes (second suffix must be ད or ས)
- Illegal prefixes (prefix must be ག, ད, བ, མ, or འ)
- Illegal superfixes (head consonant must be ར, ལ, or ས)
- Illegal subfixes (subjoined consonant must be ྱ, ྲ, ླ, or ྭ)
- Illegal suffixes (suffix must be in ག, ང, ད, ན, བ, མ, འ, ར, ལ, ས)
- Excessive consonant count / gibberish sequences (consonant count > 5 or un-structured repeat)
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final

from pydantic import BaseModel, Field


class StructuralErrorType(StrEnum):
    """Categories of Tibetan structural orthographic violations."""

    DOUBLE_VOWEL = "DOUBLE_VOWEL"
    INVALID_POST_SUFFIX = "INVALID_POST_SUFFIX"
    TOO_MANY_CONSONANTS = "TOO_MANY_CONSONANTS"
    INVALID_PREFIX = "INVALID_PREFIX"
    INVALID_SUPERFIX = "INVALID_SUPERFIX"
    INVALID_SUBFIX = "INVALID_SUBFIX"
    INVALID_SUFFIX = "INVALID_SUFFIX"
    GIBBERISH = "GIBBERISH"


#: Legal Tibetan Prefix Consonants (སྔོན་འཇུག)
PREFIX_CONSONANTS: Final[frozenset[str]] = frozenset({"ག", "ད", "བ", "མ", "འ"})

#: Legal Tibetan Superfix/Head Consonants (མགོ་ཅན)
SUPERFIX_CONSONANTS: Final[frozenset[str]] = frozenset({"ར", "ལ", "ས"})

#: The 30 Basic Tibetan Consonants (གསལ་བྱེད་ 30)
BASE_CONSONANTS: Final[frozenset[str]] = frozenset({
    "ཀ", "ཁ", "ག", "ང",
    "ཅ", "ཆ", "ཇ", "ཉ",
    "ཏ", "ཐ", "ད", "ན",
    "པ", "ཕ", "བ", "མ",
    "ཙ", "ཚ", "ཛ", "ཝ",
    "ཞ", "ཟ", "འ", "ཡ",
    "ར", "ལ", "ཤ", "ཥ", "ས", "ཧ", "ཨ"
})

#: Legal Tibetan Subjoined Consonants (འདོགས་ཅན: yata ྱ, rata ྲ, lata ླ, wazur ྭ)
SUBFIX_CHAR_MAP: Final[dict[str, str]] = {
    "\u0fb1": "ཡ",  # yata ྱ
    "\u0fb2": "ར",  # rata ྲ
    "\u0fb3": "ལ",  # lata ླ
    "\u0f99": "ཝ",  # wazur ྭ
    "\u0fba": "ཝ",  # wazur ྭ
}

#: Subjoined Unicode codepoint mapping (U+0F90 to U+0FBC) -> base consonant string
SUBJOINED_BASE_MAP: Final[dict[str, str]] = {
    "\u0f90": "ཀ", "\u0f91": "ཁ", "\u0f92": "ག", "\u0f93": "ང",
    "\u0f94": "ཅ", "\u0f95": "ཆ", "\u0f96": "ཇ", "\u0f97": "ཉ",
    "\u0f9c": "ཏ", "\u0f9d": "ཐ", "\u0f9e": "ད", "\u0f9f": "ན",
    "\u0fa0": "པ", "\u0fa1": "ཕ", "\u0fa2": "བ", "\u0fa3": "མ",
    "\u0fa4": "ཙ", "\u0fa5": "ཚ", "\u0fa6": "ཛ", "\u0fa8": "ཞ",
    "\u0fa9": "ཟ", "\u0faa": "འ", "\u0fac": "ར", "\u0fad": "ལ",
    "\u0fae": "ཤ", "\u0faf": "ཥ", "\u0fb0": "ས", "\u0fb4": "ཧ",
    "\u0fb7": "ཧ", "\u0fb5": "ཨ"
}

#: Tibetan Vowel Signs (དབྱངས)
VOWEL_SIGNS: Final[frozenset[str]] = frozenset({"\u0f72", "\u0f74", "\u0f7a", "\u0f7c", "\u0f7b", "\u0f7d"})

#: Legal Tibetan Primary Suffix Consonants (རྗེས་འཇུག)
SUFFIX_CONSONANTS: Final[frozenset[str]] = frozenset({"ག", "ང", "ད", "ན", "བ", "མ", "འ", "ར", "ལ", "ས"})

#: Legal Tibetan Post-Suffix Consonants (ཡང་འཇུག - ད and ས only)
POST_SUFFIX_CONSONANTS: Final[frozenset[str]] = frozenset({"ད", "ས"})


class SyllableComponents(BaseModel):
    """Decomposed elements of a Tibetan syllable."""

    prefix: str | None = None
    superfix: str | None = None
    base: str | None = None
    subfix: str | None = None
    vowels: list[str] = Field(default_factory=list)
    suffix: str | None = None
    post_suffix: str | None = None
    raw_consonants: list[str] = Field(default_factory=list)
    subjoined_chars: list[str] = Field(default_factory=list)


class StructuralValidationResult(BaseModel):
    """Result of structural validation for a syllable."""

    syllable: str
    is_valid: bool
    error_type: StructuralErrorType | None = None
    error_description: str | None = None
    suggested_corrections: list[str] = Field(default_factory=list)
    components: SyllableComponents = Field(default_factory=SyllableComponents)


class StructuralValidator:
    """Validator enforcing classical Tibetan orthographic structural rules."""

    def parse_syllable(self, syllable: str) -> SyllableComponents:
        """Decompose a Tibetan syllable into prefix, superfix, base, subfix, vowels, suffix, post-suffix."""
        clean = syllable.rstrip("\u0f0b །")
        if not clean:
            return SyllableComponents()

        vowels = [ch for ch in clean if ch in VOWEL_SIGNS]
        inline_consonants: list[str] = [ch for ch in clean if ch in BASE_CONSONANTS]
        subjoined_chars: list[str] = [ch for ch in clean if ch in SUBJOINED_BASE_MAP or ch in SUBFIX_CHAR_MAP or ("\u0f90" <= ch <= "\u0fbc")]

        comp = SyllableComponents(
            vowels=vowels,
            raw_consonants=inline_consonants,
            subjoined_chars=subjoined_chars,
        )

        if not inline_consonants:
            return comp

        num_c = len(inline_consonants)

        # Check for subfixes (yata ྱ \u0fb1, rata ྲ \u0fb2, lata ླ \u0fb3, wazur ྭ \u0f99/\u0fba, plus subjoined HA \u0fb4/\u0fb7)
        for sub_ch in subjoined_chars:
            if sub_ch in SUBFIX_CHAR_MAP:
                comp.subfix = SUBFIX_CHAR_MAP[sub_ch]
            elif sub_ch in ("\u0fb4", "\u0fb7") and not comp.subfix:
                comp.subfix = SUBJOINED_BASE_MAP[sub_ch]

        # Check for superfix (head consonant ར, ལ, ས followed by a subjoined base consonant)
        if subjoined_chars:
            has_sub_base = any(ch in SUBJOINED_BASE_MAP for ch in subjoined_chars)
            if inline_consonants[0] in SUPERFIX_CONSONANTS and has_sub_base:
                comp.superfix = inline_consonants[0]

        # Single Inline Consonant (e.g. ང་, ད, རྒྱུ, སྒྲུབ)
        if num_c == 1:
            if comp.superfix:
                for sub_ch in subjoined_chars:
                    if sub_ch in SUBJOINED_BASE_MAP:
                        comp.base = SUBJOINED_BASE_MAP[sub_ch]
            else:
                comp.base = inline_consonants[0]
            return comp

        # Two Inline Consonants (e.g. བད, ཡིན, དང, བཀྲ, ཞཀ, ཕྱིཝ, ཀློཀ, པརྷ, དཔེ, དགེ)
        if num_c == 2:
            if vowels or subjoined_chars:
                if inline_consonants[0] in PREFIX_CONSONANTS and subjoined_chars:
                    # e.g. བཀྲ, འགྲོ -> prefix=བ/འ, base=ཀ/ག, subfix=ྲ
                    comp.prefix = inline_consonants[0]
                    comp.base = inline_consonants[1]
                elif inline_consonants[0] in PREFIX_CONSONANTS and vowels and not subjoined_chars:
                    v_idx = clean.find(vowels[0])
                    c2_idx = clean.find(inline_consonants[1])
                    if v_idx != -1 and c2_idx != -1 and v_idx >= c2_idx:
                        # e.g. དཔེ, དགེ, བདེ, མཛེ -> prefix=ད, base=པ (vowel attached to base)
                        comp.prefix = inline_consonants[0]
                        comp.base = inline_consonants[1]
                    else:
                        comp.base = inline_consonants[0]
                        comp.suffix = inline_consonants[1]
                else:
                    # e.g. ཕྱིཝ -> base=ཕ, subfix=ྱ, suffix=ཝ
                    # e.g. ཀློཀ -> base=ཀ, subfix=ླ, suffix=ཀ
                    # e.g. པརྷ -> base=པ, subfix=ཧ, suffix=ར
                    comp.base = inline_consonants[0]
                    comp.suffix = inline_consonants[1]
            elif inline_consonants[1] not in SUFFIX_CONSONANTS:
                # e.g. ཞཀ -> ཞ is treated as invalid prefix because ཀ is not a valid suffix
                comp.prefix = inline_consonants[0]
                comp.base = inline_consonants[1]
            elif inline_consonants[1] in SUFFIX_CONSONANTS:
                comp.base = inline_consonants[0]
                comp.suffix = inline_consonants[1]
            else:
                # Fallback: flag non-suffix second consonant as invalid suffix
                comp.base = inline_consonants[0]
                comp.suffix = inline_consonants[1]
            return comp

        # Three Inline Consonants (e.g. བདག, གསལ, བོདག, དགག, བོངབྱ)
        if num_c == 3:
            first_char_idx = clean.find(inline_consonants[0])
            first_has_vowel = False
            if first_char_idx != -1 and first_char_idx + 1 < len(clean) and clean[first_char_idx + 1] in VOWEL_SIGNS:
                first_has_vowel = True

            if first_has_vowel:
                comp.base = inline_consonants[0]
                comp.suffix = inline_consonants[1]
                comp.post_suffix = inline_consonants[2]
            elif inline_consonants[0] in PREFIX_CONSONANTS:
                comp.prefix = inline_consonants[0]
                if comp.superfix:
                    for sub_ch in subjoined_chars:
                        if sub_ch in SUBJOINED_BASE_MAP:
                            comp.base = SUBJOINED_BASE_MAP[sub_ch]
                    comp.suffix = inline_consonants[2]
                else:
                    comp.base = inline_consonants[1]
                    if inline_consonants[2] == inline_consonants[1]:
                        # e.g. དགག -> prefix=ད, base=ག, post_suffix=ག (double suffix)
                        comp.post_suffix = inline_consonants[2]
                    else:
                        comp.suffix = inline_consonants[2]
            else:
                comp.base = inline_consonants[0]
                comp.suffix = inline_consonants[1]
                comp.post_suffix = inline_consonants[2]
            return comp

        # Four Inline Consonants (e.g. བདགག, བསྒྲུབས)
        if num_c == 4:
            if inline_consonants[0] in PREFIX_CONSONANTS:
                comp.prefix = inline_consonants[0]
                if comp.superfix:
                    for sub_ch in subjoined_chars:
                        if sub_ch in SUBJOINED_BASE_MAP:
                            comp.base = SUBJOINED_BASE_MAP[sub_ch]
                    comp.suffix = inline_consonants[2]
                    comp.post_suffix = inline_consonants[3]
                else:
                    comp.base = inline_consonants[1]
                    comp.suffix = inline_consonants[2]
                    comp.post_suffix = inline_consonants[3]
            else:
                comp.superfix = inline_consonants[0]
                comp.base = inline_consonants[1]
                comp.suffix = inline_consonants[2]
                comp.post_suffix = inline_consonants[3]
            return comp

        return comp

    def validate_syllable(self, syllable: str) -> StructuralValidationResult:
        """Validate a single Tibetan syllable against orthographic hard-fail rules."""
        tsheg = "\u0f0b"
        if tsheg in syllable:
            parts = [p.strip() for p in syllable.split(tsheg) if p.strip()]
            for part in parts:
                res = self.validate_syllable(part)
                if not res.is_valid:
                    res.syllable = syllable
                    return res
            return StructuralValidationResult(syllable=syllable, is_valid=True)

        clean = syllable.rstrip("\u0f0b\u0f0d །")
        if not clean:
            return StructuralValidationResult(syllable=syllable, is_valid=True)

        comp = self.parse_syllable(clean)

        # Rule 1: Double Vowels (HARD FAIL)
        if len(comp.vowels) > 1:
            suggestions = self.suggest_structural_correction(syllable, StructuralErrorType.DOUBLE_VOWEL)
            return StructuralValidationResult(
                syllable=syllable,
                is_valid=False,
                error_type=StructuralErrorType.DOUBLE_VOWEL,
                error_description=f"Double or multiple vowel signs detected in syllable: '{syllable}'",
                suggested_corrections=suggestions,
                components=comp,
            )

        # Rule 2: Consonant Count > 5 or Gibberish Repeat (HARD FAIL)
        raw_c = comp.raw_consonants
        if len(raw_c) >= 3 and len(set(raw_c)) == 1:
            suggestions = [raw_c[0] + "\u0f0b"]
            return StructuralValidationResult(
                syllable=syllable,
                is_valid=False,
                error_type=StructuralErrorType.GIBBERISH,
                error_description=f"Repeated un-structured consonant gibberish detected: '{syllable}'",
                suggested_corrections=suggestions,
                components=comp,
            )

        if len(raw_c) > 5:
            suggestions = self.suggest_structural_correction(syllable, StructuralErrorType.TOO_MANY_CONSONANTS)
            return StructuralValidationResult(
                syllable=syllable,
                is_valid=False,
                error_type=StructuralErrorType.TOO_MANY_CONSONANTS,
                error_description=f"Exceeded maximum consonant count (max 5) in syllable: '{syllable}'",
                suggested_corrections=suggestions,
                components=comp,
            )

        # Rule 3: Check Post-Suffix (Second Suffix) Validity (HARD FAIL)
        if comp.post_suffix is not None and comp.post_suffix not in POST_SUFFIX_CONSONANTS:
                suggestions = self.suggest_structural_correction(syllable, StructuralErrorType.INVALID_POST_SUFFIX)
                return StructuralValidationResult(
                    syllable=syllable,
                    is_valid=False,
                    error_type=StructuralErrorType.INVALID_POST_SUFFIX,
                    error_description=f"Illegal post-suffix consonant '{comp.post_suffix}' (must be 'ད' or 'ས') in syllable: '{syllable}'",
                    suggested_corrections=suggestions,
                    components=comp,
                )

        # Rule 4: Check Prefix Validity (HARD FAIL)
        if comp.prefix is not None and comp.prefix not in PREFIX_CONSONANTS:
                suggestions = self.suggest_structural_correction(syllable, StructuralErrorType.INVALID_PREFIX)
                return StructuralValidationResult(
                    syllable=syllable,
                    is_valid=False,
                    error_type=StructuralErrorType.INVALID_PREFIX,
                    error_description=f"Illegal prefix consonant '{comp.prefix}' (must be in ག, ད, བ, མ, འ) in syllable: '{syllable}'",
                    suggested_corrections=suggestions,
                    components=comp,
                )

        # Rule 5: Check Superfix Validity (HARD FAIL)
        if comp.superfix is not None and comp.superfix not in SUPERFIX_CONSONANTS:
            suggestions = self.suggest_structural_correction(syllable, StructuralErrorType.INVALID_SUPERFIX)
            return StructuralValidationResult(
                syllable=syllable,
                is_valid=False,
                error_type=StructuralErrorType.INVALID_SUPERFIX,
                error_description=f"Illegal superfix head consonant '{comp.superfix}' (must be in ར, ལ, ས) in syllable: '{syllable}'",
                suggested_corrections=suggestions,
                components=comp,
            )

        # Rule 6: Check Subfix Validity (HARD FAIL)
        valid_subfixes = set(SUBFIX_CHAR_MAP.values()) | {"ཧ"}
        if comp.subfix is not None:
            # Subjoined char attached after suffix consonant is illegal (e.g. པརྷ)
            if comp.suffix is not None and comp.subjoined_chars:
                first_sub = comp.subjoined_chars[0]
                suf_idx = clean.rfind(comp.suffix)
                sub_idx = clean.find(first_sub)
                if suf_idx != -1 and sub_idx != -1 and sub_idx > suf_idx:
                    suggestions = self.suggest_structural_correction(syllable, StructuralErrorType.INVALID_SUBFIX)
                    return StructuralValidationResult(
                        syllable=syllable,
                        is_valid=False,
                        error_type=StructuralErrorType.INVALID_SUBFIX,
                        error_description=f"Illegal subjoined consonant '{first_sub}' attached to suffix consonant in syllable: '{syllable}'",
                        suggested_corrections=suggestions,
                        components=comp,
                    )

            if comp.subfix not in valid_subfixes:
                suggestions = self.suggest_structural_correction(syllable, StructuralErrorType.INVALID_SUBFIX)
                return StructuralValidationResult(
                    syllable=syllable,
                    is_valid=False,
                    error_type=StructuralErrorType.INVALID_SUBFIX,
                    error_description=f"Illegal subjoined consonant '{comp.subfix}' (must be in ཡ, ར, ལ, ཝ, ཧ) in syllable: '{syllable}'",
                    suggested_corrections=suggestions,
                    components=comp,
                )

        # Rule 7: Check Suffix Validity (HARD FAIL)
        if comp.suffix is not None and comp.suffix not in SUFFIX_CONSONANTS:
            suggestions = self.suggest_structural_correction(syllable, StructuralErrorType.INVALID_SUFFIX)
            return StructuralValidationResult(
                syllable=syllable,
                is_valid=False,
                error_type=StructuralErrorType.INVALID_SUFFIX,
                error_description=f"Illegal suffix consonant '{comp.suffix}' (must be in ག, ང, ད, ན, བ, མ, འ, ར, ལ, ས) in syllable: '{syllable}'",
                suggested_corrections=suggestions,
                components=comp,
            )

        return StructuralValidationResult(syllable=syllable, is_valid=True, components=comp)

    def validate_text(self, text: str) -> list[StructuralValidationResult]:
        """Validate all syllables in a Tibetan text string."""
        tsheg = "\u0f0b"
        syllables = [s.strip() for s in text.split(tsheg) if s.strip()]
        results: list[StructuralValidationResult] = []
        for syl in syllables:
            res = self.validate_syllable(syl)
            if not res.is_valid:
                results.append(res)
        return results

    def suggest_structural_correction(
        self, syllable: str, error_type: StructuralErrorType
    ) -> list[str]:
        """Generate structurally valid candidate corrections for a broken syllable."""
        clean = syllable.rstrip("\u0f0b །")
        corrections: list[str] = []

        if error_type == StructuralErrorType.DOUBLE_VOWEL:
            seen_vowel = False
            fixed_chars = []
            for ch in clean:
                if ch in VOWEL_SIGNS:
                    if not seen_vowel:
                        fixed_chars.append(ch)
                        seen_vowel = True
                else:
                    fixed_chars.append(ch)
            corrections.append("".join(fixed_chars) + "\u0f0b")

        elif error_type == StructuralErrorType.INVALID_POST_SUFFIX:
            comp = self.parse_syllable(clean)
            raw = comp.raw_consonants
            if len(raw) >= 3:
                valid_base = "".join(raw[:-1])
                if comp.vowels:
                    valid_base = raw[0] + comp.vowels[0] + "".join(raw[1:-1])
                corrections.append(valid_base + "\u0f0b")
                if len(raw) == 3 and "ོ" in clean:
                    corrections.append("བོད་" + "\u0f0b" + raw[-1] + "\u0f0b")

        elif error_type == StructuralErrorType.INVALID_PREFIX:
            comp = self.parse_syllable(clean)
            if comp.raw_consonants:
                corrections.append("".join(comp.raw_consonants[1:]) + "\u0f0b")

        elif error_type == StructuralErrorType.TOO_MANY_CONSONANTS or error_type == StructuralErrorType.GIBBERISH:
            comp = self.parse_syllable(clean)
            if comp.raw_consonants:
                corrections.append(comp.raw_consonants[0] + "\u0f0b")

        return corrections
