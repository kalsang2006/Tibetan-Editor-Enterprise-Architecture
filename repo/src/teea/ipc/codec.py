"""JSON message codec for the Local IPC layer.

The default :class:`~teea.ipc.interfaces.MessageCodec`. Messages are Pydantic
models, so encoding is their JSON dump and decoding is validation; the value of
stating it behind the protocol is that a gRPC transport can substitute a protobuf
codec without the server or client changing.

Decoding is strict. A payload that is not valid JSON, or that is valid JSON but
not a valid message, raises :class:`~teea.ipc.errors.MalformedMessageError`
rather than a bare ``ValidationError``, so a peer sending garbage produces a
typed IPC failure instead of an error no caller is told to catch.
"""

from __future__ import annotations

from pydantic import ValidationError

from teea.ipc.errors import MalformedMessageError
from teea.ipc.models import IpcRequest, IpcResponse


class JsonMessageCodec:
    """Encodes messages as UTF-8 JSON.

    Satisfies the :class:`~teea.ipc.interfaces.MessageCodec` protocol. Stateless
    and safe to share across threads.
    """

    def encode(self, message: IpcRequest | IpcResponse) -> bytes:
        """Serialize ``message`` to UTF-8 JSON bytes."""
        return message.model_dump_json().encode("utf-8")

    def decode_request(self, payload: bytes) -> IpcRequest:
        """Deserialize an :class:`IpcRequest`, or raise."""
        try:
            return IpcRequest.model_validate_json(payload)
        except ValidationError as exc:
            raise MalformedMessageError(
                "The payload is not a valid IPC request.",
                context={"bytes": len(payload)},
                cause=exc,
            ) from exc

    def decode_response(self, payload: bytes) -> IpcResponse:
        """Deserialize an :class:`IpcResponse`, or raise."""
        try:
            return IpcResponse.model_validate_json(payload)
        except ValidationError as exc:
            raise MalformedMessageError(
                "The payload is not a valid IPC response.",
                context={"bytes": len(payload)},
                cause=exc,
            ) from exc


__all__ = ["JsonMessageCodec"]
