"""TEEA — Tibetan Editor Enterprise Architecture.

Production-grade Tibetan NLP platform. This package currently provides the
foundational ``core`` utilities and the TiBERT-backed ``nlp.tokenization``
module. Additional layers (language server pipeline, AI runtime, plugin
runtime, suggestion fusion, IPC, Office.js add-in) are built on top of these
foundations in subsequent modules.
"""

from __future__ import annotations

__version__ = "0.1.0"

__all__ = ["__version__"]