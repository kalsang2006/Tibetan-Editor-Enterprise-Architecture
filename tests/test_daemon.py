"""Tests for the TEEA daemon composition root."""

from __future__ import annotations

from teea.daemon import TEEADaemon, create_daemon
from teea.nlp.snapshot import DocumentSnapshot
from teea.plugins.builtin.diagnostics import DocumentDiagnosticsPlugin


def test_create_daemon_defaults() -> None:
    daemon = create_daemon()
    assert isinstance(daemon, TEEADaemon)


def test_daemon_properties() -> None:
    daemon = create_daemon()
    assert daemon.settings is not None
    assert daemon.builder is not None
    assert daemon.plugins is not None
    assert daemon.fusion is not None
    assert daemon.ai_runtime is None
    assert not daemon.is_serving()


def test_daemon_diagnose() -> None:
    daemon = create_daemon()
    diag = daemon.diagnose()
    assert "version" in diag
    assert "settings" in diag
    assert "builder" in diag
    assert "plugins" in diag
    assert "fusion" in diag
    assert "ai_runtime" in diag
    assert "ipc" in diag
    assert not diag["ipc"]["serving"]
    assert not diag["ai_runtime"]["active"]


def test_daemon_diagnose_plugin_count() -> None:
    daemon = create_daemon()
    diag = daemon.diagnose()
    assert diag["plugins"]["count"] == 0
    assert diag["plugins"]["names"] == []
    assert not diag["plugins"]["concurrent"]


def test_daemon_start_stop_no_transport() -> None:
    daemon = create_daemon()
    daemon.start()
    daemon.stop()


def test_daemon_shutdown() -> None:
    daemon = create_daemon()
    daemon.shutdown()


def test_daemon_with_custom_plugins() -> None:
    class CountingPlugin:
        def __init__(self) -> None:
            self.call_count = 0

        @property
        def name(self) -> str:
            return "counter"

        def examine(self, snapshot: DocumentSnapshot) -> list:  # type: ignore[type-arg]
            self.call_count += 1
            return []

    plugin = CountingPlugin()
    daemon = TEEADaemon(plugins=[plugin])
    assert daemon.plugins is not None
    assert "counter" in daemon.plugins.plugins


def test_daemon_diagnose_with_builtin_plugin() -> None:
    plugin = DocumentDiagnosticsPlugin()
    daemon = TEEADaemon(plugins=[plugin])
    diag = daemon.diagnose()
    assert diag["plugins"]["count"] == 1
    assert "teea.diagnostics" in diag["plugins"]["names"]
