"""TEEA — Tibetan Editor Enterprise Architecture.

Production-grade Tibetan NLP platform. Provides the full Language Server
pipeline (Stages 02-12), Plugin Runtime, Suggestion Fusion Engine, AI Runtime,
IPC layer, and CLI/daemon entrypoints.

Usage::

    # CLI
    teea analyze document.txt
    teea workflow document.txt -o results.json
    teea health

    # Python
    from teea.daemon import create_daemon
    daemon = create_daemon()
    snapshot = daemon.builder.analyze(normalized_text)
"""

from __future__ import annotations

__version__ = "0.1.0"

__all__ = ["__version__"]
