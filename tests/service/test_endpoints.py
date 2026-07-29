"""Tests for FastAPI service endpoints."""

from __future__ import annotations

from fastapi.testclient import TestClient

from teea.engine import TEEAEngine
from teea.service.app import create_app


def test_health_endpoint() -> None:
    engine = TEEAEngine()
    app = create_app(engine=engine)
    client = TestClient(app)

    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["version"] == "1.0.0"
    assert data["ai_active"] is True
    assert data["vocabulary_size"] > 0


def test_analyze_endpoint() -> None:
    engine = TEEAEngine()
    app = create_app(engine=engine)
    client = TestClient(app)

    response = client.post("/analyze", json={"text": "མངོན་སུམ"})
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert data["char_count"] == 8
    assert len(data["suggestions"]) > 0
    assert "latency_ms" in data


def test_legacy_ipc_endpoint() -> None:
    engine = TEEAEngine()
    app = create_app(engine=engine)
    client = TestClient(app)

    payload = {
        "method": "analysis.run",
        "params": {"text": "མངོན་སུམ"},
        "request_id": "test-req-1",
    }
    response = client.post("/api/analysis/run", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert data["request_id"] == "test-req-1"
    assert "suggestions" in data["result"]


def test_ai_rewrite_endpoint() -> None:
    engine = TEEAEngine()
    app = create_app(engine=engine)
    client = TestClient(app)

    response = client.post("/ai/rewrite", json={"text": "བཀྲ་ཤིས་བདེ་ལེགས", "template": "formal"})
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert data["output"] == "བཀྲ་ཤིས་བདེ་ལེགས"


def test_metrics_endpoint() -> None:
    engine = TEEAEngine()
    app = create_app(engine=engine)
    client = TestClient(app)

    # Perform one analyze request first to update metrics
    client.post("/analyze", json={"text": "test"})

    response = client.get("/metrics")
    assert response.status_code == 200
    data = response.json()
    assert data["requests_total"] >= 1
    assert "avg_latency_ms" in data
    assert "uptime_seconds" in data


def test_ui_static_route() -> None:
    engine = TEEAEngine()
    app = create_app(engine=engine)
    client = TestClient(app)

    response = client.get("/ui")
    assert response.status_code == 200
    assert "<title>TEEA — Tibetan AI Engine Test Workbench</title>" in response.text
