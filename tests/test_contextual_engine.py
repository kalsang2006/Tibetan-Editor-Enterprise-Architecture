"""Unit and integration tests for Contextual Grammar & Semantic Engine."""

import pytest
from teea.engine import TEEAEngine
from teea.grammar.contextual_engine import ContextualGrammarEngine
from teea.ai.engines import DummyInferenceEngine
from teea.suggestion_fusion import SuggestionFusionEngine


@pytest.fixture
def contextual_engine() -> ContextualGrammarEngine:
    return ContextualGrammarEngine()


def test_tense_mismatch_mi_byas(contextual_engine: ContextualGrammarEngine) -> None:
    errors = contextual_engine.analyze_sentence("ང་མི་བྱས།")
    assert len(errors) >= 1
    tense_err = [e for e in errors if e.error_code == "TENSE_MI_MA"][0]
    assert tense_err.error_type == "TENSE_MISMATCH"
    assert tense_err.suggestion in ("མ་བྱས", "མི་བྱ")


def test_user_contextual_case_dag(contextual_engine: ContextualGrammarEngine) -> None:
    text = "དག་གིས་པར་སྤྲོ་གསར་པ་སླབས།"
    errors = contextual_engine.analyze_sentence(text)
    dag_err = [e for e in errors if e.word in ("དག", "དག་")][0]
    assert dag_err.error_type == "CONTEXTUAL_SEMANTIC"
    assert dag_err.suggestion == "དགེ"


def test_user_contextual_case_par_spro(contextual_engine: ContextualGrammarEngine) -> None:
    text = "དག་གིས་པར་སྤྲོ་གསར་པ་སླབས།"
    errors = contextual_engine.analyze_sentence(text)
    par_err = [e for e in errors if e.word in ("པར", "པར་")][0]
    assert par_err.error_type == "CONTEXTUAL_SEMANTIC"
    assert par_err.suggestion == "བརྡ"

    spro_err = [e for e in errors if e.word in ("སྤྲོ", "སྤྲོ་")][0]
    assert spro_err.error_type == "CONTEXTUAL_SEMANTIC"
    assert spro_err.suggestion == "སྤྲོད"


def test_user_contextual_case_bong_bya(contextual_engine: ContextualGrammarEngine) -> None:
    text = "ང་ཚོས་ཡིག་ཆ་ཀློ་ཅིང་ཡི་གེ་བོང་བྱ།"
    errors = contextual_engine.analyze_sentence(text)
    bong_err = [e for e in errors if e.word in ("བོང", "བོང་")][0]
    assert bong_err.error_type == "CONTEXTUAL_SEMANTIC"
    assert bong_err.suggestion == "སྦྱོང"

    bya_err = [e for e in errors if e.word in ("བྱ", "བྱ།")][0]
    assert bya_err.error_type in ("TENSE_MISMATCH", "CONTEXTUAL_SEMANTIC")
    assert bya_err.suggestion == "བྱས"


def test_user_target_sentence_4_errors(contextual_engine: ContextualGrammarEngine) -> None:
    text = "དེ་རིང་ང་བོད་སྐད་སློབ་ཚན་ལ་ཕྱི། དགེ་གིས་བརྡ་སྤྲོད་བསླབས། ཀློ་བོང་བྱས།"
    errors = contextual_engine.analyze_sentence(text)

    phyi_err = [e for e in errors if e.word in ("ཕྱི", "ཕྱི།")][0]
    assert phyi_err.error_type == "TENSE_MISMATCH"
    assert phyi_err.suggestion == "ཕྱིན"

    klo_err = [e for e in errors if e.word in ("ཀློ", "ཀློ་")][0]
    assert klo_err.error_type == "SPELLING"
    assert klo_err.suggestion == "ཀློག"

    bong_err = [e for e in errors if e.word in ("བོང", "བོང་")][0]
    assert bong_err.error_type == "CONTEXTUAL_SEMANTIC"
    assert bong_err.suggestion == "སྦྱོང"


def test_slabs_structural_prefix(contextual_engine: ContextualGrammarEngine) -> None:
    text = "དགེ་གིས་བརྡ་སྤྲོད་སླབས།"
    errors = contextual_engine.analyze_sentence(text)
    slabs_err = [e for e in errors if e.word in ("སླབས", "སླབས།")][0]
    assert slabs_err.error_type == "STRUCTURAL"
    assert slabs_err.suggestion == "བསླབས"


def test_e2e_full_paragraph_analysis() -> None:
    engine = TEEAEngine(ai_engine=DummyInferenceEngine())
    text = "དེ་རིང་ང་བོད་སྐད་སློབ་ཚན་ལ་ཕྱི། དག་གིས་པར་སྤྲོ་གསར་པ་སླབས། ང་ཚོས་ཡིག་ཆ་ཀློ་ཅིང་ཡི་གེ་བོང་བྱ། ང་རང་དགའ་སྤྲོ་ཆེན་པོ་ཡོད།"
    unified = engine.analyze(text)

    fusion = SuggestionFusionEngine(engine)
    payload = fusion.format_ui_payload(text, unified)

    assert payload["ok"] is True
    assert len(payload["suggestions"]) >= 4

    edits = [s for s in payload["suggestions"] if s.get("replacement")]
    replacements = {s["replacement"] for s in edits}
    assert "དགེ" in replacements
    assert "བརྡ" in replacements
    assert "སྤྲོད" in replacements
    assert "སྦྱོང" in replacements
    assert "བྱས" in replacements


def test_clean_essay_zero_false_positives(contextual_engine: ContextualGrammarEngine) -> None:
    """Verify clean essay text containing valid target words produces 0 false positive errors."""
    clean_essay = "གནད་དོན་འདི་བཤད་པར་བྱའོ། འཇིག་རྟེན་གསོན་པོའི་དཔེ་དེབ་ཤེས་རིག་བཟང་པོ་འདི་ཡིས་ནུས་པ་གཏན་ཏན་ཐོན་ནོ།"
    errors = contextual_engine.analyze_sentence(clean_essay)
    assert len(errors) == 0

    engine = TEEAEngine(ai_engine=DummyInferenceEngine())
    unified = engine.analyze(clean_essay)
    replacements = [s for s in unified.suggestions if s.replacement is not None]
    assert len(replacements) == 0


def test_user_full_essay_zero_false_positives() -> None:
    """Verify user essay text flags actual typos while keeping correct words untouched."""
    essay_text = (
        "སློབ་བསྦྱོང་གིས་གལ་ནད་སྐོར་ཤད་པ། དེང་འདུས་ཀྱིས་ཇིག་བརྟེན་འདིར་མི་ཚེ་སོན་པོར་གནས་པ་དང་འདུན་སྐྱོད་བྱེད་ཆེ་བསློབ་སྦྱོང་ནི་ཧ་བཅང་གལ་ཆེ་བ་ཞིག་ཡིན། "
        "སློབ་སྦྱོང་ཅེས་པ་ནི་དཔེ་དེབ་ཀྱིས་བཤེས་བྱ་ཁོ་ན་བཙམ་མིན་པར། མི་ཚེའི་ཟང་བསྤྱོད་དང་། མནུས་པ། ཡོན་བཏན་བཅས་ཡོངས་དུ་འཛོམས་པས་ལམ་བུ་ཅིགཡིན། "
        "མིའི་རིག་ལ་ཤེ་ཡོན་མེད་ན་མུན་མནག་ནང་ཏུ་རྒྱུ་བ་དང་འདྲའ་སྟེ། ཤེས་ཡོན་གྱི་ང་ཚོའི་བློ་བགྲོས་ཀྱིས་སྒོ་མོ་ཕྱེ་ཞིང་། བཟང་ངན་དང་། བླང་འདོར་གྱིས་ནས་ཚུལ་འབྱེད་པར་བྱེད། "
        "ལྷག་པར་དུ་ན་ཞོན་ཚོ་དུས་ཚོད་སེར་ལྟར་དུ་བརྩིས་དེ་སློབ་སྦྱོང་ལ་འབད་དགོས་པ་ཡིན། དེ་ཡང་སློབ་སྦྱོང་ལེག་པར་བྱས་ན། རང་ཉིད་ཀྱིས་མི་འཚེ་ཛེས་སྡུག་ལྡན་པ་ཞིག་བསྐྲུན་ཐུབ་པ་མ་ཟད། "
        "སྤྱི་ཚོག་དང་རྒྱལ་འཁབ་ཀྱི་ཞབ་ཞུ་སྒྲུབ་པའི་ནུས་པ་ཡང་ཆེན་པོ་ཐོན་གྱིས་ཡོད། མདོར་ན་སློབ་བྱོང་ནི་མི་ཚེའི་མརྒྱན་ཆ་ཆོག་རུ་གྱུར་པ་ཞིག་ཡིན་པའི། "
        "ང་ཚོས་མནམ་ཡང་སློབ་སྦྱོང་བྱེད་པར་མརྒྱུན་འཆད་མེ་པའི་བད་རྩོན་བྱེས་གོས།"
    )
    ctx_engine = ContextualGrammarEngine()
    errors = ctx_engine.analyze_sentence(essay_text)
    edits = errors

    # Verify target typos were corrected
    replacements = {s.suggestion for s in edits}
    assert "སྦྱོང" in replacements
    assert "གནད" in replacements or "གལ་གནད" in replacements
    assert "བཤད" in replacements
    assert "འཇིག" in replacements
    assert "གསོན" in replacements
    assert "ཤེས" in replacements
    assert "བཟང" in replacements
    assert "ནུས" in replacements
    assert "ཏན" in replacements

    # Verify NONE of the correct target words were changed to incorrect forms
    forbidden_bad_replacements = {"བཤེས", "ཟང", "མནོས", "བཏན", "དཔང", "ཇི", "སོན"}
    for s in edits:
        assert s.suggestion not in forbidden_bad_replacements


def test_essay_zero_false_positives() -> None:
    """Clean Tibetan essay text must produce zero false positive suggestions."""
    essay_text = (
        "སློབ་སྦྱོང་གི་གལ་གནད་སྐོར་བཤད་པ། དེང་དུས་ཀྱི་འཇིག་རྟེན་འདིར་མི་ཚེ་གསོན་པོར་གནས་པ་དང་མདུན་བསྐྱོད་བྱེད་ཆེད་སློབ་སྦྱོང་ནི་ཧ་ཅང་གལ་ཆེ་བ་ཞིག་ཡིན། "
        "སློབ་སྦྱོང་ཞེས་པ་ནི་དཔེ་དེབ་ཀྱི་ཤེས་བྱ་ཁོ་ན་ཙམ་མིན་པར། མི་ཚེའི་བཟང་སྤྱོད་དང་། ནུས་པ། ཡོན་ཏན་བཅས་ཡོངས་སུ་འཛོམས་པའི་ལམ་བུ་ཞིག་ཡིན། "
        "མིའི་རིགས་ལ་ཤེས་ཡོན་མེད་ན་མུན་ནག་ནང་དུ་རྒྱུ་བ་དང་འདྲ་སྟེ། ཤེས་ཡོན་གྱིས་ང་ཚོའི་བློ་གྲོས་ཀྱི་སྒོ་མོ་ཕྱེ་ཞིང་། བཟང་ངན་དང་། བླང་དོར་གྱི་གནས་ཚུལ་འབྱེད་པར་བྱེད། "
        "ལྷག་པར་དུ་ན་གཞོན་ཚོས་དུས་ཚོད་གསེར་ལྟར་དུ་བརྩིས་ཏེ་སློབ་སྦྱོང་ལ་འབད་དགོས་པ་ཡིན། དེ་ཡང་སློབ་སྦྱོང་ལེགས་པར་བྱས་ན། རང་ཉིད་ཀྱི་མི་ཚེ་མཛེས་སྡུག་ལྡན་པ་ཞིག་བསྐྲུན་ཐུབ་པ་མ་ཟད། "
        "སྤྱི་ཚོགས་དང་རྒྱལ་ཁབ་ཀྱི་ཞབས་ཞུ་སྒྲུབ་པའི་ནུས་པ་ཡང་ཆེན་པོ་ཐོན་གྱི་ཡོད། མདོར་ན་སློབ་སྦྱོང་ནི་མི་ཚེའི་རྒྱན་ཆ་མཆོག་ཏུ་གྱུར་པ་ཞིག་ཡིན་པས། "
        "ང་ཚོས་ནམ་ཡང་སློབ་སྦྱོང་བྱེད་པར་རྒྱུན་ཆད་མེད་པའི་འབད་བརྩོན་བྱེད་དགོས།"
    )
    engine = TEEAEngine(ai_engine=DummyInferenceEngine())
    unified = engine.analyze(essay_text)
    text_edits = [s for s in unified.suggestions if s.replacement is not None]
    assert len(text_edits) == 0, f"Expected 0 false positive edits, got {len(text_edits)}: {[s.message for s in text_edits]}"
