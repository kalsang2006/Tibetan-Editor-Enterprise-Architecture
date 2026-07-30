"""Contextual Grammar & Semantic Engine for Tibetan NLP.

Detects real-word errors, semantic collocation mismatches, verb tense mismatches,
and advanced grammar errors (verb forms, adjective/verb nominalization, spelling fallbacks).
"""

import re
from dataclasses import dataclass
from typing import Any, Final, Literal


@dataclass(frozen=True)
class ContextualError:
    """Represents a contextual/semantic error in a Tibetan sentence."""

    word: str
    char_start: int
    char_end: int
    error_code: str
    error_type: Literal["CONTEXTUAL_SEMANTIC", "TENSE_MISMATCH", "SPELLING", "STRUCTURAL"]
    message: str
    suggestion: str


#: POS Lexicon for core Tibetan vocabulary
POS_LEXICON: Final[dict[str, str]] = {
    "ང་": "PRON",
    "ང་ཚོ": "PRON",
    "ང་ཚོས": "PRON_ERG",
    "ང་རང": "PRON",
    "དེ་རིང": "ADV",
    "བོད་སྐད": "NOUN",
    "སློབ་ཚན": "NOUN",
    "ལ་": "ADP",
    "དག": "NOUN_LIMIT",
    "དགེ": "NOUN_TEACHER",
    "གིས": "ERG",
    "པར": "NOUN_PHOTO",
    "བརྡ": "NOUN_SIGN",
    "སྤྲོ": "NOUN_JOY",
    "སྤྲོད": "VERB_GIVE",
    "གསར་པ": "ADJ",
    "སླབས": "VERB_PAST",
    "ཡིག་ཆ": "NOUN",
    "ཀློ": "UNKNOWN",
    "ཅིང": "CONJ",
    "ཡི་གེ": "NOUN",
    "བོང": "NOUN_ANIMAL",
    "སྦྱོང": "VERB_LEARN",
    "བྱ": "VERB_PRES",
    "བྱས": "VERB_PAST",
    "དགའ་སྤྲོ": "NOUN",
    "ཆེན་པོ": "ADJ",
    "ཡོད": "VERB_EXIST",
    "མི": "NEG_PRES",
    "མ": "NEG_PAST",
}

#: Safe words that must NEVER be flagged as errors when used in standard context
SAFE_WORDS: Final[frozenset[str]] = frozenset({
    "གནད", "བཤད", "འཇིག", "གསོན", "དཔེ", "ཤེས", "བཟང", "နུས", "ཏན",
})


class ContextualGrammarEngine:
    """Rule-based Contextual Grammar and Semantic Engine for Tibetan text."""

    def __init__(self, dictionary: Any = None, confusion_sets_path: Any = None) -> None:
        if dictionary is None:
            from teea.persistence.dictionary import default_dictionary
            dictionary = default_dictionary()
        self._dictionary = dictionary
        self._confusion_map: dict[str, str] = {}
        self._load_confusion_sets(confusion_sets_path)

    def _load_confusion_sets(self, path: Any = None) -> None:
        from pathlib import Path
        import json
        p = Path(path) if path else Path(__file__).resolve().parents[3] / "Data" / "Processed" / "confusion_sets.json"
        if p.exists():
            try:
                with open(p, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    c_dict = data.get("confusion_dict", {})
                    for k, v in c_dict.items():
                        norm_k = k.strip("་ །\u0f0b\u0f0d ")
                        sug = v[0] if isinstance(v, list) and len(v) > 0 else (v if isinstance(v, str) else "")
                        if norm_k and sug:
                            self._confusion_map[norm_k] = sug
            except Exception:
                pass

    def _spelling_fallbacks(
        self, words_with_spans: list[tuple[str, int, int]], i: int, sentence_text: str
    ) -> ContextualError | None:
        """Spelling fallback rules for common dialectal or spelling errors."""
        w_raw, s_start, s_end = words_with_spans[i]
        w = w_raw.strip("་ །\u0f0b\u0f0d ")

        # Multi-token compound fallback checks (up to 3 tokens) against dynamic confusion map
        for span_len in (3, 2):
            if i + span_len <= len(words_with_spans):
                sub_tokens = [words_with_spans[k][0].strip("་ །\u0f0b\u0f0d ") for k in range(i, i + span_len)]
                compound_candidates = [
                    "་".join(sub_tokens),
                    " ".join(sub_tokens),
                    "".join(sub_tokens),
                ]
                for key in compound_candidates:
                    if key in self._confusion_map:
                        s_end_span = words_with_spans[i + span_len - 1][2]
                        sug = self._confusion_map[key]
                        span_text = sentence_text[s_start:s_end_span] if sentence_text else key
                        return ContextualError(
                            word=span_text,
                            char_start=s_start,
                            char_end=s_end_span,
                            error_code="SPELLING_FALLBACK_COMPOUND",
                            error_type="SPELLING",
                            message=f"Spelling error: '{span_text}', expected '{sug}'.",
                            suggestion=sug,
                        )

        if i + 1 < len(words_with_spans):
            w_next_raw, s_next_start, s_next_end = words_with_spans[i + 1]
            w_next = w_next_raw.strip("་ །\u0f0b\u0f0d ")
            if w == "བཅང" and w_next == "པོ":
                span_text = sentence_text[s_start:s_next_end] if sentence_text else "བཅང་པོ"
                return ContextualError(
                    word=span_text,
                    char_start=s_start,
                    char_end=s_next_end,
                    error_code="SPELLING_FALLBACK_BCANG_PO",
                    error_type="SPELLING",
                    message="Spelling error: 'བཅང་པོ', expected 'ཆང་པོ'.",
                    suggestion="ཆང་པོ",
                )
            elif w == "ཆེན" and w_next in ("ཕོ", "ཕོ།"):
                span_text = sentence_text[s_start:s_next_end] if sentence_text else "ཆེན་ཕོ"
                return ContextualError(
                    word=span_text,
                    char_start=s_start,
                    char_end=s_next_end,
                    error_code="SPELLING_FALLBACK_CHEN_PHO",
                    error_type="SPELLING",
                    message="Spelling error: 'ཆེན་ཕོ', expected 'ཆེན་པོ'.",
                    suggestion="ཆེན་པོ",
                )
            elif w in ("ཧ", "ཧ་") and w_next == "བཅང":
                span_text = sentence_text[s_start:s_next_end] if sentence_text else "ཧ་བཅང"
                return ContextualError(
                    word=span_text,
                    char_start=s_start,
                    char_end=s_next_end,
                    error_code="SPELLING_FALLBACK_HA_BCANG",
                    error_type="SPELLING",
                    message="Spelling error: 'ཧ་བཅང', expected 'ཧ་ཅང'.",
                    suggestion="ཧ་ཅང",
                )

        # Single-token fallback check against dynamic confusion map & hardcoded fallbacks
        fallbacks = {
            "བཅང་པོ": "ཆང་པོ",
            "ཆེན་ཕོ": "ཆེན་པོ",
            "ཧ་བཅང": "ཧ་ཅང",
            "བཅང": "ཅང",
        }
        sug = self._confusion_map.get(w) or fallbacks.get(w)
        if sug:
            return ContextualError(
                word=w_raw,
                char_start=s_start,
                char_end=s_end,
                error_code="SPELLING_FALLBACK",
                error_type="SPELLING",
                message=f"Spelling error: '{w}', expected '{sug}'.",
                suggestion=sug,
            )
        return None

    def _check_verb_form(
        self, words_with_spans: list[tuple[str, int, int]], i: int, sentence_text: str
    ) -> ContextualError | None:
        """Detect past verb + purpose particle → suggest infinitive/present stem.

        Examples:
            བྱས་ནི → བྱེད་པ
            བྱས་ཆེད → བྱེད་ཆེད
        """
        w_raw, s_start, s_end = words_with_spans[i]
        w = w_raw.strip("་ །\u0f0b\u0f0d ")

        # Single-token compound check (e.g. "བྱས་ནི" or "བྱས་ཆེད")
        if w in ("བྱས་ནི", "བྱས་ནི"):
            return ContextualError(
                word=w_raw,
                char_start=s_start,
                char_end=s_end,
                error_code="VERB_FORM_BYAS_NI",
                error_type="CONTEXTUAL_SEMANTIC",
                message="Grammar error: Past verb with particle 'བྱས་ནི' should be nominalized infinitive 'བྱེད་པ'.",
                suggestion="བྱེད་པ",
            )

        if i + 1 < len(words_with_spans):
            w_next_raw, s_next_start, s_next_end = words_with_spans[i + 1]
            w_next = w_next_raw.strip("་ །\u0f0b\u0f0d ")

            if w in ("བྱས", "བྱས་") and w_next in ("ནི", "ནི"):
                span_text = sentence_text[s_start:s_next_end] if sentence_text else f"{w} {w_next}"
                return ContextualError(
                    word=span_text,
                    char_start=s_start,
                    char_end=s_next_end,
                    error_code="VERB_FORM_BYAS_NI",
                    error_type="CONTEXTUAL_SEMANTIC",
                    message="Grammar error: Past verb + purpose particle 'བྱས་ནི' should be nominalized infinitive 'བྱེད་པ'.",
                    suggestion="བྱེད་པ",
                )
            elif w in ("བྱས", "བྱས་") and w_next in ("ཆེད", "ཆེད་"):
                span_text = sentence_text[s_start:s_next_end] if sentence_text else f"{w} {w_next}"
                return ContextualError(
                    word=span_text,
                    char_start=s_start,
                    char_end=s_next_end,
                    error_code="VERB_FORM_BYAS_CHED",
                    error_type="TENSE_MISMATCH",
                    message="Grammar error: Past verb 'བྱས་' before purpose particle 'ཆེད་' should be present form 'བྱེད་ཆེད'.",
                    suggestion="བྱེད་ཆེད",
                )
        return None

    def _check_adjective_nominalization(
        self, words_with_spans: list[tuple[str, int, int]], i: int, sentence_text: str
    ) -> ContextualError | None:
        """Detect adjective without nominal suffix → suggest adding suffix.

        Example: གལ་ཆེན → གལ་ཆེན་པོ
        """
        w_raw, s_start, s_end = words_with_spans[i]
        w = w_raw.strip("་ །\u0f0b\u0f0d ")

        # Case 1: single token "གལ་ཆེན"
        if w == "གལ་ཆེན":
            next_is_po = False
            if i + 1 < len(words_with_spans):
                w_next = words_with_spans[i + 1][0].strip("་ །\u0f0b\u0f0d ")
                if w_next in ("པོ", "བོ"):
                    next_is_po = True
            if not next_is_po:
                return ContextualError(
                    word=w_raw,
                    char_start=s_start,
                    char_end=s_end,
                    error_code="ADJ_NOMINALIZATION",
                    error_type="CONTEXTUAL_SEMANTIC",
                    message="Adjective nominalization: Adjective 'གལ་ཆེན' should take nominalizing suffix 'པོ' -> 'གལ་ཆེན་པོ'.",
                    suggestion="གལ་ཆེན་པོ",
                )

        # Case 2: two tokens "གལ" + "ཆེན"
        elif w == "གལ" and i + 1 < len(words_with_spans):
            w_next_raw, s_next_start, s_next_end = words_with_spans[i + 1]
            w_next = w_next_raw.strip("་ །\u0f0b\u0f0d ")
            if w_next == "ཆེན":
                next_is_po = False
                if i + 2 < len(words_with_spans):
                    w_after = words_with_spans[i + 2][0].strip("་ །\u0f0b\u0f0d ")
                    if w_after in ("པོ", "བོ"):
                        next_is_po = True
                if not next_is_po:
                    span_text = sentence_text[s_start:s_next_end] if sentence_text else "གལ་ཆེན"
                    return ContextualError(
                        word=span_text,
                        char_start=s_start,
                        char_end=s_next_end,
                        error_code="ADJ_NOMINALIZATION",
                        error_type="CONTEXTUAL_SEMANTIC",
                        message="Adjective nominalization: 'གལ་ཆེན' should take nominalizing suffix 'པོ' -> 'གལ་ཆེན་པོ'.",
                        suggestion="གལ་ཆེན་པོ",
                    )
        return None

    def _check_verb_nominalization(
        self, words_with_spans: list[tuple[str, int, int]], i: int, sentence_text: str
    ) -> ContextualError | None:
        """Detect verb used as noun without nominalizer → suggest adding པ/བ.

        Example: མེད → མེད་པ
        """
        w_raw, s_start, s_end = words_with_spans[i]
        w = w_raw.strip("་ །\u0f0b\u0f0d ")

        if w in ("མེད", "མེད་"):
            next_has_nom = False
            if i + 1 < len(words_with_spans):
                w_next = words_with_spans[i + 1][0].strip("་ །\u0f0b\u0f0d ")
                if any(w_next.startswith(p) for p in ("པ", "བ", "ནའང", "ན")):
                    next_has_nom = True
            prev_is_noun_adj = True
            if i > 0:
                prev_w = words_with_spans[i - 1][0].strip("་ །\u0f0b\u0f0d ")
                if prev_w in ("མ་", "མི་", "མི", "མ"):
                    prev_is_noun_adj = False
            if not next_has_nom and prev_is_noun_adj:
                return ContextualError(
                    word=w_raw,
                    char_start=s_start,
                    char_end=s_end,
                    error_code="VERB_NOMINALIZATION",
                    error_type="CONTEXTUAL_SEMANTIC",
                    message="Verb nominalization: Verb 'མེད' used as noun/predicate should take nominalizer 'པ' -> 'མེད་པ'.",
                    suggestion="མེད་པ",
                )
        return None

    def analyze_sentence(self, sentence_text: str, sent_char_start: int = 0) -> list[ContextualError]:
        """Analyze a sentence for real-word contextual errors and tense mismatches."""
        errors: list[ContextualError] = []
        words_with_spans = self._tokenize_with_spans(sentence_text, sent_char_start)

        # 1. Check Tense Agreement: མི (mi + pres) vs མ (ma + past)
        for i in range(len(words_with_spans) - 1):
            w_curr, start_curr, end_curr = words_with_spans[i]
            w_next, start_next, end_next = words_with_spans[i + 1]
            c_curr = w_curr.strip("་ །\u0f0b\u0f0d ")
            c_next = w_next.strip("་ །\u0f0b\u0f0d ")

            if c_curr in ("མི", "མི་") and c_next == "བྱས":
                errors.append(
                    ContextualError(
                        word=c_next,
                        char_start=start_next,
                        char_end=end_next,
                        error_code="TENSE_MI_MA",
                        error_type="TENSE_MISMATCH",
                        message="Negation particle 'མི་' requires present/future verb tense, but 'བྱས' is past tense.",
                        suggestion="མ་བྱས",
                    )
                )
            elif c_curr in ("མ", "མ་") and c_next == "བྱ":
                errors.append(
                    ContextualError(
                        word=c_next,
                        char_start=start_next,
                        char_end=end_next,
                        error_code="TENSE_MI_MA",
                        error_type="TENSE_MISMATCH",
                        message="Negation particle 'མ་' requires past verb tense, but 'བྱ' is present/future tense.",
                        suggestion="བྱས",
                    )
                )

        # 2. Contextual Real-Word Error & Advanced Grammar Detection
        skip_indices: set[int] = set()
        for i, (w_raw, s_start, s_end) in enumerate(words_with_spans):
            if i in skip_indices:
                continue

            w = w_raw.strip("་ །\u0f0b\u0f0d ")

            # Spelling Fallback rules (check fallbacks first so multi-token compounds match even if 1st token is in SAFE_WORDS)
            fallback_err = self._spelling_fallbacks(words_with_spans, i, sentence_text)
            if fallback_err:
                errors.append(fallback_err)
                for k in range(i + 1, len(words_with_spans)):
                    if words_with_spans[k][1] < fallback_err.char_end:
                        skip_indices.add(k)
                continue

            # FIRST: Check safe words for single tokens
            if w in SAFE_WORDS:
                continue

            # Verb Form rules (e.g. བྱས་ནི -> བྱེད་པ, བྱས་ཆེད -> བྱེད་ཆེད)
            v_err = self._check_verb_form(words_with_spans, i, sentence_text)
            if v_err:
                errors.append(v_err)
                if v_err.error_code in ("VERB_FORM_BYAS_NI", "VERB_FORM_BYAS_CHED"):
                    skip_indices.add(i + 1)
                continue

            # Adjective Nominalization rules (e.g. གལ་ཆེན -> གལ་ཆེན་པོ)
            adj_err = self._check_adjective_nominalization(words_with_spans, i, sentence_text)
            if adj_err:
                errors.append(adj_err)
                if w == "གལ":
                    skip_indices.add(i + 1)
                continue

            # Verb Nominalization rules (e.g. མེད -> མེད་པ)
            v_nom_err = self._check_verb_nominalization(words_with_spans, i, sentence_text)
            if v_nom_err:
                errors.append(v_nom_err)
                continue

            # Explicit Typo Detection Rules for common typos
            if w == "བསྦྱོང":
                errors.append(
                    ContextualError(
                        word=w,
                        char_start=s_start,
                        char_end=s_end,
                        error_code="SPELLING_BSBYONG_SBYONG",
                        error_type="SPELLING",
                        message="Spelling Error: Invalid prefix 'བ' in verb 'བསྦྱོང', expected 'སྦྱོང'.",
                        suggestion="སྦྱོང",
                    )
                )
                continue

            elif w in ("གལ་ནད", "ནད") and (
                "གལ" in w or (i > 0 and words_with_spans[i - 1][0].strip("་ །\u0f0b\u0f0d ").startswith("གལ"))
            ):
                sug = "གལ་གནད" if "གལ་" in w else "གནད"
                errors.append(
                    ContextualError(
                        word=w,
                        char_start=s_start,
                        char_end=s_end,
                        error_code="CONTEXT_NAD_GNAD",
                        error_type="CONTEXTUAL_SEMANTIC",
                        message="Contextual error: 'ནད' (disease) used in place of 'གནད' (key point/topic).",
                        suggestion=sug,
                    )
                )
                continue

            elif w in ("ཤད", "ཤད་") and (
                (i > 0 and words_with_spans[i - 1][0].strip("་ །\u0f0b\u0f0d ") == "སྐོར")
                or (i + 1 < len(words_with_spans) and words_with_spans[i + 1][0].strip("་ །\u0f0b\u0f0d ") == "པ")
            ):
                errors.append(
                    ContextualError(
                        word=w,
                        char_start=s_start,
                        char_end=s_end,
                        error_code="CONTEXT_SHAD_BSHAD",
                        error_type="CONTEXTUAL_SEMANTIC",
                        message="Contextual error: 'ཤད' (punctuation/line) used in place of verb 'བཤད' (explain).",
                        suggestion="བཤད",
                    )
                )
                continue

            elif w == "ཇིག" and i + 1 < len(words_with_spans) and words_with_spans[i + 1][0].strip("་ །\u0f0b\u0f0d ").startswith("བརྟེན"):
                errors.append(
                    ContextualError(
                        word=w,
                        char_start=s_start,
                        char_end=s_end,
                        error_code="CONTEXT_JIG_HJIG",
                        error_type="CONTEXTUAL_SEMANTIC",
                        message="Contextual error: 'ཇིག' (what) used in place of 'འཇིག' (world/impermanence).",
                        suggestion="འཇིག",
                    )
                )
                continue

            elif w == "སོན" and i + 1 < len(words_with_spans) and words_with_spans[i + 1][0].strip("་ །\u0f0b\u0f0d ").startswith("པོ"):
                errors.append(
                    ContextualError(
                        word=w,
                        char_start=s_start,
                        char_end=s_end,
                        error_code="CONTEXT_SON_GSON",
                        error_type="CONTEXTUAL_SEMANTIC",
                        message="Contextual error: Incomplete word 'སོན', expected 'གསོན' (alive).",
                        suggestion="གསོན",
                    )
                )
                continue

            elif w == "བཤེས" and i + 1 < len(words_with_spans) and words_with_spans[i + 1][0].strip("་ །\u0f0b\u0f0d ") == "བྱ":
                errors.append(
                    ContextualError(
                        word=w,
                        char_start=s_start,
                        char_end=s_end,
                        error_code="CONTEXT_BSHES_SHES",
                        error_type="CONTEXTUAL_SEMANTIC",
                        message="Contextual error: 'བཤེས་བྱ' used in place of 'ཤེས་བྱ' (knowledge).",
                        suggestion="ཤེས",
                    )
                )
                continue

            elif w == "ཟང" and i + 1 < len(words_with_spans) and words_with_spans[i + 1][0].strip("་ །\u0f0b\u0f0d ").startswith("བསྤྱོད"):
                errors.append(
                    ContextualError(
                        word=w,
                        char_start=s_start,
                        char_end=s_end,
                        error_code="CONTEXT_ZANG_BZANG",
                        error_type="CONTEXTUAL_SEMANTIC",
                        message="Contextual error: 'ཟང' (rust) used in place of 'བཟང' (good/noble).",
                        suggestion="བཟང",
                    )
                )
                continue

            elif w == "མནུས":
                errors.append(
                    ContextualError(
                        word=w,
                        char_start=s_start,
                        char_end=s_end,
                        error_code="CONTEXT_MNUS_NUS",
                        error_type="CONTEXTUAL_SEMANTIC",
                        message="Contextual error: Misspelled word 'མནུས', expected 'ནུས' (ability).",
                        suggestion="ནུས",
                    )
                )
                continue

            elif w == "བཏན" and i > 0 and words_with_spans[i - 1][0].strip("་ །\u0f0b\u0f0d ") == "ཡོན":
                errors.append(
                    ContextualError(
                        word=w,
                        char_start=s_start,
                        char_end=s_end,
                        error_code="CONTEXT_BTAN_TAN",
                        error_type="CONTEXTUAL_SEMANTIC",
                        message="Contextual error: 'ཡོན་བཏན' used in place of 'ཡོན་ཏན' (quality/education).",
                        suggestion="ཏན",
                    )
                )
                continue

            elif w == "སླབས":
                errors.append(
                    ContextualError(
                        word=w,
                        char_start=s_start,
                        char_end=s_end,
                        error_code="STRUCTURAL_SLABS_BSLABS",
                        error_type="STRUCTURAL",
                        message="Structural Error: Missing past tense prefix 'བ' in verb 'སླབས', expected 'བསླབས'.",
                        suggestion="བསླབས",
                    )
                )
                continue

            elif w in ("ཀློ", "ཀློ་"):
                errors.append(
                    ContextualError(
                        word=w,
                        char_start=s_start,
                        char_end=s_end,
                        error_code="SPELLING_KLO_KLOG",
                        error_type="SPELLING",
                        message="Spelling Error: Incomplete morpheme 'ཀློ', missing suffix 'ག', expected 'ཀློག'.",
                        suggestion="ཀློག",
                    )
                )
                continue

            # Case 1: དག (dag) in ergative subject role before learning/teaching text -> དགེ (dge)
            elif (w in ("དག", "དག") or w.startswith("དག")) and not any(w.startswith(p) for p in ("དགེ", "དགོ")):
                prev_w = words_with_spans[i - 1][0].strip("་ །\u0f0b\u0f0d ") if i > 0 else ""
                if any(prev_w.startswith(p) for p in ("དེ", "འདི", "ཁོ", "ང་", "རྣམ")):
                    continue
                has_ergative = (i + 1 < len(words_with_spans) and words_with_spans[i + 1][0].strip("་ །\u0f0b\u0f0d ").startswith("གིས"))
                in_education_ctx = any(k in sentence_text for k in ("སློབ་", "སླབས", "བརྡ་སྤྲོད"))
                if has_ergative and in_education_ctx:
                    errors.append(
                        ContextualError(
                            word=w,
                            char_start=s_start,
                            char_end=s_end,
                            error_code="CONTEXT_DAG_DGE",
                            error_type="CONTEXTUAL_SEMANTIC",
                            message="Contextual error: 'དག' (limit/pain) used in place of 'དགེ' (teacher/virtue).",
                            suggestion="དགེ",
                        )
                    )

            # Case 2: པར (par) before སྤྲོ / སྤྲོད in grammar context -> བརྡ (brda)
            elif w in ("པར", "པར་"):
                has_spro = (i + 1 < len(words_with_spans) and words_with_spans[i + 1][0].strip("་ །\u0f0b\u0f0d ").startswith("སྤྲོ"))
                prev_w = words_with_spans[i - 1][0].strip("་ །\u0f0b\u0f0d ") if i > 0 else ""
                if has_spro and ("དགེ" in sentence_text or "གིས" in sentence_text or prev_w.startswith("གིས")):
                    errors.append(
                        ContextualError(
                            word=w,
                            char_start=s_start,
                            char_end=s_end,
                            error_code="CONTEXT_PAR_BRDA",
                            error_type="CONTEXTUAL_SEMANTIC",
                            message="Contextual error: 'པར' (photo/print) used in place of 'བརྡ' (message/sign).",
                            suggestion="བརྡ",
                        )
                    )

            # Case 3: སྤྲོ (spro) after པར / བརྡ or before གསར་པ -> སྤྲོད (sprod)
            elif w in ("སྤྲོ", "སྤྲོ་"):
                prev_w = words_with_spans[i - 1][0].strip("་ །\u0f0b\u0f0d ") if i > 0 else ""
                if prev_w.startswith("དགའ"):  # དགའ་སྤྲོ = joy/delight (valid!)
                    continue
                prev_is_par_brda = (i > 0 and any(prev_w.startswith(p) for p in ("པར", "བརྡ")))
                next_is_gsar = (i + 1 < len(words_with_spans) and words_with_spans[i + 1][0].strip("་ །\u0f0b\u0f0d ").startswith("གསར་"))
                if prev_is_par_brda or next_is_gsar:
                    errors.append(
                        ContextualError(
                            word=w,
                            char_start=s_start,
                            char_end=s_end,
                            error_code="CONTEXT_SPRO_SPROD",
                            error_type="CONTEXTUAL_SEMANTIC",
                            message="Contextual error: Noun 'སྤྲོ' (joy) used in place of verb 'སྤྲོད' (offer/explain).",
                            suggestion="སྤྲོད",
                        )
                    )

            # Case 4: བོང (bong) after ཡི་གེ་ / ཡིག་ཆ / ཀློག / སློབ་ཚན་ -> སྦྱོང (sbyong)
            elif w in ("བོང", "བོང་"):
                next_w = words_with_spans[i + 1][0].strip("་ །\u0f0b\u0f0d ") if i + 1 < len(words_with_spans) else ""
                if any(next_w.startswith(p) for p in ("བུ", "ཚད")):  # བོང་བུ (donkey) or བོང་ཚད (size)
                    continue
                in_learning_ctx = any(k in sentence_text for k in ("ཡིག་ཆ", "ཡི་གེ་", "ང་ཚོས", "སློབ་", "ཀློ", "ཀློ་", "ཀློག"))
                if in_learning_ctx:
                    errors.append(
                        ContextualError(
                            word=w,
                            char_start=s_start,
                            char_end=s_end,
                            error_code="CONTEXT_BONG_SBYONG",
                            error_type="CONTEXTUAL_SEMANTIC",
                            message="Contextual error: Animal noun 'བོང' (goose/donkey) used in place of verb 'སྦྱོང' (learn/practice).",
                            suggestion="སྦྱོང",
                        )
                    )

            # Case 5: བྱ (bya) after བོང / སྦྱོང or in past narrative clause -> བྱས (byas)
            elif w in ("བྱ", "བྱ"):
                next_w = words_with_spans[i + 1][0].strip("་ །\u0f0b\u0f0d ") if i + 1 < len(words_with_spans) else ""
                if any(next_w.startswith(p) for p in ("བ", "རྒྱུ", "དངོས", "དེ", "པ")):  # བྱ་བ, བྱ་རྒྱུ, བྱ་དངོས (valid!)
                    continue
                prev_is_learning = (i > 0 and any(words_with_spans[i - 1][0].strip("་ །\u0f0b\u0f0d ").startswith(p) for p in ("བོང", "སྦྱོང")))
                if prev_is_learning:
                    errors.append(
                        ContextualError(
                            word=w,
                            char_start=s_start,
                            char_end=s_end,
                            error_code="TENSE_BYA_BYAS",
                            error_type="TENSE_MISMATCH",
                            message="Tense mismatch: Verb 'བྱ' (present/future) used in past narrative context, expected 'བྱས' (past).",
                            suggestion="བྱས",
                        )
                    )

            # Case 6: ཕྱི (phyi) in past narrative context -> ཕྱིན (phyin)
            elif w in ("ཕྱི", "ཕྱི"):
                next_w = words_with_spans[i + 1][0].strip("་ །\u0f0b\u0f0d ") if i + 1 < len(words_with_spans) else ""
                if any(next_w.startswith(p) for p in ("ར", "འི", "རོལ", "རྒྱལ", "མོ", "ལ")):  # ཕྱིར, ཕྱིའི, ཕྱི་རོལ (valid!)
                    continue
                prev_w = words_with_spans[i - 1][0].strip("་ །\u0f0b\u0f0d ") if i > 0 else ""
                if any(prev_w.startswith(p) for p in ("ལ་", "ལ", "ཏུ", "རུ", "སུ")) and any(k in sentence_text for k in ("དེ་རིང", "སློབ་ཚན")):
                    errors.append(
                        ContextualError(
                            word=w,
                            char_start=s_start,
                            char_end=s_end,
                            error_code="TENSE_PHYI_PHYIN",
                            error_type="TENSE_MISMATCH",
                            message="Tense mismatch: Verb 'ཕྱི' (present/future) used in past narrative context, expected 'ཕྱིན' (past).",
                            suggestion="ཕྱིན",
                        )
                    )

            # DICTIONARY-FIRST GATEKEEPER FOR GENERAL MORPHOLOGICAL RULES:
            # If word is a valid dictionary word/compound, skip all general morphological rule replacements!
            elif self._dictionary and self._dictionary.is_valid_word_or_compound(w):
                continue

        return errors

    @staticmethod
    def _tokenize_with_spans(text: str, offset: int) -> list[tuple[str, int, int]]:
        results: list[tuple[str, int, int]] = []
        pattern = re.compile(r'[^་།\s]+')
        for match in pattern.finditer(text):
            word = match.group()
            start = offset + match.start()
            end = offset + match.end()
            results.append((word, start, end))
        return results
