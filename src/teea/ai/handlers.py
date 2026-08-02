"""AI endpoint handlers for the TEEA assistant.

Each handler is a callable that accepts a request mapping and yields
SSE frames (dicts with ``kind`` and associated fields).  The HTTP bridge
in :mod:`teea.transport.http_server` wraps these as HTTP+SSE responses,
and the add-in consumes them through the same ``StreamFrame`` protocol.

The methods map
---------------
:data:`AI_ENDPOINT_METHODS` maps every method the add-in's Assistant tab
calls to the handler that serves it.  It is the single source of truth
that ``addin/src/taskpane/types/ipc.ts`` mirrors as ``AI_METHOD_PATHS``.

Cancellation
------------
``ai.cancel`` sets a generation-wide cancellation flag keyed by
``request_id`` so a streaming handler can notice and stop early.
The add-in sends ``ai.cancel`` when the user presses Stop.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Generator
from typing import Any

HandlerFn = Callable[[dict[str, Any], str], Generator[dict[str, Any], None, None]]

_DEFAULT_TOKEN_COUNT = 20
_TOKEN_INTERVAL = 0.05

_cancelled: dict[str, bool] = {}
_cancel_lock = threading.Lock()


def _is_cancelled(request_id: str) -> bool:
    with _cancel_lock:
        return _cancelled.get(request_id, False)


def _set_cancelled(request_id: str) -> None:
    with _cancel_lock:
        _cancelled[request_id] = True


def _cleanup(request_id: str) -> None:
    with _cancel_lock:
        _cancelled.pop(request_id, None)


def _stream_tokens(
    text: str,
    request_id: str,
    prefix: str = "",
    token_count: int = _DEFAULT_TOKEN_COUNT,
) -> Generator[dict[str, Any], None, None]:
    """Yield SSE token frames, checking cancellation between each."""
    tokens = (prefix + " " + text).split()
    if not tokens:
        tokens = ["(no", "text", "provided)"]

    for i, token in enumerate(tokens):
        if _is_cancelled(request_id):
            yield {"kind": "cancelled"}
            return
        yield {"kind": "token", "token": token + " "}
        time.sleep(_TOKEN_INTERVAL)
        if i >= token_count:
            break

    yield {"kind": "done"}
    _cleanup(request_id)


def handle_explain(
    params: dict[str, Any],
    request_id: str,
) -> Generator[dict[str, Any], None, None]:
    """Explain the grammar of text using mock AI."""
    text = params.get("text", "")
    yield from _stream_tokens(text, request_id, prefix="[Mock] Grammar explanation (will be integrated with Monlam AI)")


def handle_summarize(
    params: dict[str, Any],
    request_id: str,
) -> Generator[dict[str, Any], None, None]:
    """Summarize text using mock AI."""
    text = params.get("text", "")
    yield from _stream_tokens(text, request_id, prefix="[Mock] Summary (will be integrated with Monlam AI)")


def handle_cancel(
    params: dict[str, Any],
    request_id: str,
) -> Generator[dict[str, Any], None, None]:
    """Cancel a running generation by its request_id."""
    target = params.get("request_id", request_id)
    _set_cancelled(target)
    yield {"kind": "done"}
    _cleanup(target)


def handle_translate(
    params: dict[str, Any],
    request_id: str,
) -> Generator[dict[str, Any], None, None]:
    """Mock translation: echo the text with a prefix showing target language."""
    text = params.get("text", "")
    target = params.get("target_lang", "en")
    yield from _stream_tokens(text, request_id, prefix=f"[Mock] Translation to {target} (will be integrated with Monlam AI)")


def handle_ocr(
    params: dict[str, Any],
    request_id: str,
) -> Generator[dict[str, Any], None, None]:
    """Mock OCR: return placeholder extracted text."""
    prefix = "[Mock] Extracted text from image via OCR (will be integrated with Monlam AI)"
    text = params.get("text", "Sample OCR output")
    if "image_url" in params:
        text = f"OCR of {params['image_url']}: placeholder"
    elif "image_data" in params:
        text = "OCR from base64 image data: placeholder"
    yield from _stream_tokens(text, request_id, prefix=prefix, token_count=10)


def handle_stt(
    params: dict[str, Any],
    request_id: str,
) -> Generator[dict[str, Any], None, None]:
    """Mock speech-to-text: return placeholder transcription."""
    prefix = "[Mock] Transcription from STT (will be integrated with Monlam AI)"
    text = params.get("text", "Sample transcription")
    if "audio_url" in params:
        text = f"STT of {params['audio_url']}: placeholder"
    elif "audio_data" in params:
        text = "STT from base64 audio data: placeholder"
    yield from _stream_tokens(text, request_id, prefix=prefix, token_count=10)


AI_ENDPOINT_METHODS: dict[str, HandlerFn] = {
    "ai.explain": handle_explain,
    "ai.summarize": handle_summarize,
    "ai.cancel": handle_cancel,
    "ai.translate": handle_translate,
    "ai.ocr": handle_ocr,
    "ai.stt": handle_stt,
}

__all__ = [
    "AI_ENDPOINT_METHODS",
    "HandlerFn",
    "handle_cancel",
    "handle_explain",
    "handle_ocr",
    "handle_stt",
    "handle_summarize",
    "handle_translate",
]