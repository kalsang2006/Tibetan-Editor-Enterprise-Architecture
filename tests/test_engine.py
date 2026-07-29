"""Tests for the TEEAEngine facade."""

from __future__ import annotations

from teea.engine import TEEAEngine
from teea.fusion import UnifiedSuggestions


def test_engine_initialization() -> None:
    engine = TEEAEngine()
    assert engine.version == "1.0.0"
    assert engine.dictionary is not None


def test_engine_health() -> None:
    engine = TEEAEngine()
    h = engine.health()
    assert h["status"] == "ok"
    assert h["version"] == "1.0.0"
    assert h["ai_active"] is True
    assert h["vocabulary_size"] > 0
    assert len(h["plugins_loaded"]) > 0


def test_engine_diagnose() -> None:
    engine = TEEAEngine()
    d = engine.diagnose()
    assert d["version"] == "1.0.0"
    assert "settings" in d
    assert d["dictionary_size"] > 0
    assert d["plugins"]["count"] > 0


def test_engine_analyze_empty() -> None:
    engine = TEEAEngine()
    unified = engine.analyze("")
    assert isinstance(unified, UnifiedSuggestions)
    assert len(unified.suggestions) == 0


def test_engine_analyze_sample_tibetan() -> None:
    engine = TEEAEngine()
    unified = engine.analyze("མངོན་སུམ")
    assert isinstance(unified, UnifiedSuggestions)
    assert len(unified.suggestions) > 0


def test_engine_rewrite() -> None:
    engine = TEEAEngine()
    res = engine.rewrite("བཀྲ་ཤིས་བདེ་ལེགས", template="formal")
    assert res == "བཀྲ་ཤིས་བདེ་ལེགས"
