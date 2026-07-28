"""Tests for the TEEA workflow orchestration module."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from teea.core.types import TextSpan
from teea.fusion import PriorityRankedFusionEngine, Suggestion, SuggestionPriority
from teea.nlp.snapshot import DocumentSnapshot
from teea.workflow import (
    fuse_suggestions,
    load_document,
    normalize_document,
    save_json,
    save_text,
    snapshot_to_dict,
    snapshot_to_text,
)


def test_load_document(tmp_path: Path) -> None:
    text = "བཀྲ་ཤིས་བདེ་ལེགས།"
    file = tmp_path / "test.txt"
    file.write_text(text, encoding="utf-8")
    assert load_document(str(file)) == text


def test_load_document_not_found() -> None:
    with pytest.raises(FileNotFoundError):
        load_document("nonexistent.txt")


def test_normalize_document_unchanged() -> None:
    text = "བཀྲ་ཤིས་བདེ་ལེགས།"
    result = normalize_document(text)
    assert isinstance(result, str)


def test_normalize_document_nfc() -> None:
    text = "བཀྲ་ཤིས་བདེ་ལེགས།"
    result = normalize_document(text, form="NFC")
    assert result == text


def test_save_json(tmp_path: Path) -> None:
    path = str(tmp_path / "out.json")
    result = save_json(path, {"key": "value"})
    assert result == path
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    assert data == {"key": "value"}


def test_save_text(tmp_path: Path) -> None:
    path = str(tmp_path / "out.txt")
    result = save_text(path, "hello")
    assert result == path
    assert Path(path).read_text(encoding="utf-8") == "hello"


def test_snapshot_to_dict_empty() -> None:
    snapshot = DocumentSnapshot(source="")
    result = snapshot_to_dict(snapshot)
    assert result["source"] == ""
    assert result["analyses"] == []


def test_snapshot_to_text_empty() -> None:
    snapshot = DocumentSnapshot(source="")
    text = snapshot_to_text(snapshot)
    assert "Document: 0 chars, 0 sentences" in text


def test_fuse_suggestions_empty() -> None:
    result = fuse_suggestions("hello", [])
    assert len(result.suggestions) == 0


def test_fuse_suggestions_one() -> None:
    suggestion = Suggestion(
        source="test",
        span=TextSpan(char_start=0, char_end=5, byte_start=0, byte_end=5),
        replacement="world",
        score=0.9,
        priority=SuggestionPriority.HIGH,
    )
    result = fuse_suggestions("hello", [suggestion])
    assert len(result.suggestions) == 1
    assert result.suggestions[0].replacement == "world"


def test_fuse_suggestions_with_custom_engine() -> None:
    suggestion = Suggestion(
        source="test",
        span=TextSpan(char_start=0, char_end=5, byte_start=0, byte_end=5),
        replacement="world",
        score=0.9,
        priority=SuggestionPriority.HIGH,
    )
    engine = PriorityRankedFusionEngine(plugin_weights={"test": 0.5})
    result = fuse_suggestions("hello", [suggestion], engine=engine)
    assert len(result.suggestions) == 1
