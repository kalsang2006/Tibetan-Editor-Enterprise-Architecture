"""TEEA tokenization module (TiBERT-backed).

Public API:

* :class:`Tokenizer` — the abstraction downstream code depends on.
* :class:`TiBERTTokenizer` — the concrete TiBERT-backed implementation.
* :class:`TextNormalizer` — Unicode normalization (pipeline Stage 2).
* :class:`SyllableSegmenter` — tsheg-based syllable segmentation.
* Domain models: :class:`EncodedText`, :class:`Token`, :class:`Syllable`.
* The exception hierarchy rooted at :class:`TokenizationError`.

Typical usage::

    from teea.core import load_settings, configure_logging
    from teea.nlp.tokenization import TiBERTTokenizer

    settings = load_settings()
    configure_logging(level=settings.log_level, json_output=settings.log_json)
    tokenizer = TiBERTTokenizer(settings.tokenization)

    encoded = tokenizer.encode("བཀྲ་ཤིས་བདེ་ལེགས།")
    ids = encoded.ids
"""

from __future__ import annotations

from teea.nlp.tokenization.exceptions import (
    DetokenizationError,
    EmptyInputError,
    InputNotStringError,
    InputTooLongError,
    NormalizationError,
    OffsetAlignmentError,
    TokenizationError,
    TokenizerLoadError,
    TokenizerNotInitializedError,
)
from teea.nlp.tokenization.interfaces import Tokenizer
from teea.nlp.tokenization.models import EncodedText, Syllable, Token
from teea.nlp.tokenization.normalization import TextNormalizer
from teea.nlp.tokenization.syllable import SyllableSegmenter
from teea.nlp.tokenization.tibert import (
    BackendLoader,
    BackendTokenizer,
    TiBERTTokenizer,
    default_tibert_loader,
)

__all__ = [
    "BackendLoader",
    "BackendTokenizer",
    "DetokenizationError",
    "EmptyInputError",
    "EncodedText",
    "InputNotStringError",
    "InputTooLongError",
    "NormalizationError",
    "OffsetAlignmentError",
    "Syllable",
    "SyllableSegmenter",
    "TextNormalizer",
    "TiBERTTokenizer",
    "Token",
    "TokenizationError",
    "Tokenizer",
    "TokenizerLoadError",
    "TokenizerNotInitializedError",
    "default_tibert_loader",
]