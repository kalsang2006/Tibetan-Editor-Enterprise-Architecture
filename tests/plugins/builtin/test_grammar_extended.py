"""Comprehensive unit tests for extended Tibetan grammar, particle agreement,
repeated words, and typography checking.
"""

import pytest

from teea.engine import TEEAEngine
from teea.plugins.builtin.grammar import GrammarCheckerPlugin
from teea.plugins.builtin.typography import TypographyPlugin


def test_genitive_particle_agreement():
    engine = TEEAEngine()

    # 'ང་ ཀྱི' is invalid after open vowel 'ང་' -> should be 'ང་ གི' or 'ང་ ཡི'
    unified = engine.analyze("ང་ ཀྱི དཔེ་ཆ།")
    suggestions = [s for s in unified.suggestions if s.source == "teea.grammar"]
    assert len(suggestions) >= 1
    assert any("Genitive particle agreement error" in s.message for s in suggestions)


def test_ergative_particle_agreement():
    engine = TEEAEngine()

    # 'དགེ་རྒན་ གིས' is invalid after final 'ན' -> should be 'དགེ་རྒན་ གྱིས'
    unified = engine.analyze("དགེ་རྒན་ གིས བཤད་པ།")
    suggestions = [s for s in unified.suggestions if s.source == "teea.grammar"]
    assert len(suggestions) >= 1
    assert any("Ergative particle agreement error" in s.message for s in suggestions)


def test_interrogative_particle_agreement():
    engine = TEEAEngine()

    # 'ཡོད་ གམ' is invalid after final 'ད' -> should be 'ཡོད་ དམ'
    unified = engine.analyze("ཁྱོད་ ཡོད་ གམ།")
    suggestions = [s for s in unified.suggestions if s.source == "teea.grammar"]
    assert len(suggestions) >= 1
    assert any("Interrogative particle agreement error" in s.message for s in suggestions)


def test_sentence_final_particle_agreement():
    engine = TEEAEngine()

    # 'ཡོད་ གོ' is invalid after final 'ད' -> should be 'ཡོད་ དོ'
    unified = engine.analyze("ང་ ཡོད་ གོ")
    suggestions = [s for s in unified.suggestions if s.source == "teea.grammar"]
    assert len(suggestions) >= 1
    assert any("Sentence-final particle agreement error" in s.message for s in suggestions)


def test_duplicate_repeated_words():
    engine = TEEAEngine()

    # 'ང་ ང་' is duplicate repeated word
    unified = engine.analyze("ང་ ང་ བོད་སྐད་ སྦྱོང་གི་ཡོད།")
    suggestions = [s for s in unified.suggestions if s.source == "teea.grammar"]
    assert len(suggestions) >= 1
    assert any("Duplicate repeated word detected" in s.message for s in suggestions)


def test_duplicate_tsheg_spacing():
    engine = TEEAEngine()

    # 'བཀྲ་shis' with duplicate tshegs 'བཀྲ་་ཤིས'
    unified = engine.analyze("བཀྲ་་ཤིས།")
    suggestions = [s for s in unified.suggestions if s.source == "teea.typography"]
    assert len(suggestions) >= 1
    assert any("Duplicate tsheg" in s.message for s in suggestions)
