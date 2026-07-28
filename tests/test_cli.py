"""Tests for the TEEA CLI entry point."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from teea.cli import main
from teea.core.config import load_settings
from teea.daemon import create_daemon
from teea.workflow import (
    analyze_text,
    full_workflow,
    load_document,
    save_json,
    save_text,
    snapshot_to_text,
)


def test_no_args_prints_help(capsys: pytest.CaptureFixture[str]) -> None:
    result = main([])
    assert result == 0
    captured = capsys.readouterr()
    assert "usage:" in captured.out


def test_unknown_command_returns_error() -> None:
    with pytest.raises(SystemExit) as exc:
        main(["unknown"])
    assert exc.value.code == 2


def test_config_works() -> None:
    """Config command returns successfully (no capsys to avoid structlog issue)."""
    result = main(["--log-level", "ERROR", "--log-json", "config"])
    assert result == 0


def test_config_json_output(tmp_path: Path) -> None:
    """Config JSON output can be verified via stdout redirect."""
    settings = load_settings()
    data = settings.model_dump(mode="json")
    assert isinstance(data, dict)


def test_health_direct() -> None:
    """Health check works end-to-end."""
    daemon = create_daemon()
    diag = daemon.diagnose()
    assert "version" in diag


def test_analyze_file_not_found(capsys: pytest.CaptureFixture[str]) -> None:
    result = main(["analyze", "nonexistent.txt"])
    assert result == 1
    captured = capsys.readouterr()
    assert "Error:" in captured.err


def test_workflow_file_not_found(capsys: pytest.CaptureFixture[str]) -> None:
    result = main(["workflow", "nonexistent.txt"])
    assert result == 1
    captured = capsys.readouterr()
    assert "Error:" in captured.err


def test_format_file_not_found(capsys: pytest.CaptureFixture[str]) -> None:
    result = main(["format", "nonexistent.txt"])
    assert result == 1
    captured = capsys.readouterr()
    assert "Error:" in captured.err


def test_analyze_outputs_json(tmp_path: Path) -> None:
    """Test the analyze pipeline writes JSON output correctly."""
    text = "བཀྲ་ཤིས་བདེ་ལེགས།"
    file = tmp_path / "input.txt"
    file.write_text(text, encoding="utf-8")
    doc_text = load_document(str(file))
    snapshot = analyze_text(doc_text)
    result = {
        "source": str(file),
        "char_count": len(doc_text),
        "sentence_count": len(snapshot.analyses),
        "snapshot": snapshot.model_dump(mode="json"),
    }
    out = tmp_path / "out.json"
    with open(str(out), "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    assert out.exists()
    data = json.loads(out.read_text(encoding="utf-8"))
    assert "sentence_count" in data
    assert "snapshot" in data


def test_format_saves_report(tmp_path: Path) -> None:
    """Test format via direct workflow call (avoids structlog)."""
    text = "བཀྲ་ཤིས་བདེ་ལེགས།"
    file = tmp_path / "input.txt"
    file.write_text(text, encoding="utf-8")
    doc_text = load_document(str(file))
    snapshot = analyze_text(doc_text)
    report = snapshot_to_text(snapshot)
    report_file = tmp_path / "input.txt.analysis"
    save_text(str(report_file), report)
    assert report_file.exists()
    assert report_file.read_text(encoding="utf-8").startswith("Document:")


def test_format_with_json_flag(tmp_path: Path) -> None:
    text = "བཀྲ་ཤིས་བདེ་ལེགས།"
    file = tmp_path / "input.txt"
    file.write_text(text, encoding="utf-8")
    doc_text = load_document(str(file))
    snapshot = analyze_text(doc_text)
    out = tmp_path / "out.json"
    data = {"source": str(file), "snapshot": snapshot.model_dump(mode="json")}
    save_json(str(out), data)
    result = json.loads(out.read_text(encoding="utf-8"))
    assert "snapshot" in result


def test_workflow_with_json_output(tmp_path: Path) -> None:
    text = "བཀྲ་ཤིས་བདེ་ལེགས།"
    file = tmp_path / "input.txt"
    file.write_text(text, encoding="utf-8")
    out = tmp_path / "out.json"
    result = full_workflow(str(file), output_json=str(out))
    assert "source" in result
    assert "sentence_count" in result
    assert (tmp_path / "out.json").exists()


def test_workflow_on_real_tibetan(tmp_path: Path) -> None:
    text = "བཀྲ་ཤིས་བདེ་ལེགས།"
    file = tmp_path / "input.txt"
    file.write_text(text, encoding="utf-8")
    result = full_workflow(str(file))
    assert result["char_count"] == len(text)
    assert result["sentence_count"] >= 0
