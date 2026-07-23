"""Test doubles used across the TEEA test suite.

Doubles live in their own package (rather than in ``conftest.py``) so that they
can be imported explicitly by name from any test module, and so that each one is
documented as a faithful stand-in for a specific production collaborator.
"""

from __future__ import annotations

from tests.fakes.fake_backend_tokenizer import FakeBackendTokenizer

__all__ = ["FakeBackendTokenizer"]
