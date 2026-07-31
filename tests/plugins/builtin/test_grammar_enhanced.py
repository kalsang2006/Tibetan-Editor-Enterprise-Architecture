"""Enhanced unit and integration tests for Enterprise Tibetan Grammar Checker."""

import pytest

from teea.ai.engines import DummyInferenceEngine
from teea.engine import TEEAEngine
from teea.nlp.collocation import CollocationDatabase
from teea.nlp.sanskrit import SanskritTransliterationValidator
from teea.nlp.verb_lexicon import Transitivity, VerbLexicon
from teea.plugins.builtin.grammar import GrammarCheckerPlugin


@pytest.fixture
def grammar_plugin() -> GrammarCheckerPlugin:
    return GrammarCheckerPlugin()


def test_collocation_database_loading() -> None:
    cdb = CollocationDatabase()
    assert cdb.get_collocation_score("ང་", "ཡིན་") > 0.8
    assert cdb.get_collocation_score("ཆོས་སྒོར", "བོད་") < 0.2


def test_malapropism_bod_vs_bdag() -> None:
    cdb = CollocationDatabase()
    context = ["ང་", "ཆོས་སྒོར", "བོད་", "ཡིན"]
    assert cdb.is_malapropism(context, "བོད་")
    replacements = cdb.suggest_semantic_replacement(context, "བོད་")
    assert "བདག" in replacements[0] or "བདག" in replacements[1] if len(replacements) > 1 else "བདག" in replacements[0]


def test_sanskrit_validator() -> None:
    sv = SanskritTransliterationValidator()
    assert sv.is_valid_sanskrit("ཀརྨ")
    assert not sv.is_valid_sanskrit("ཀསྨ")
    assert sv.get_final_consonant_sanskrit("ཀརྨ") == "མ"


def test_verb_lexicon() -> None:
    vl = VerbLexicon()
    info = vl.get_verb_info("བལྟས")
    assert info is not None
    assert info.transitivity == Transitivity.TRANS
    assert info.tense == "past"


def test_e2e_grammar_checker_malapropism_pipeline() -> None:
    engine = TEEAEngine(ai_engine=DummyInferenceEngine())
    res = engine.analyze("དེ་རིང་ང་ཆོས་སྒོར་བོདག་ཡིནན།")

    suggestions = res.suggestions
    assert any("Structural Error" in s.message or "Malapropism" in s.message or "Correction" in s.message for s in suggestions)
    
    # Verify patch replacement
    replacements = [op.replacement for op in res.patch.operations if op.replacement]
    assert len(replacements) >= 1
