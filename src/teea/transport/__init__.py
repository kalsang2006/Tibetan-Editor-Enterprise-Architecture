"""The loopback HTTP boundary between the Word add-in and the runtime layer.

Why this package exists, and why it is not ``teea.ipc``
---------------------------------------------------------
ADR-020 ships ``teea.ipc`` as protocol, routing and lifecycle over an injected
``Transport`` -- one stateful, one-client-at-a-time duplex channel -- and states
its own next step in plain words: "Building a named-pipe or gRPC Transport, and
wiring the add-in to it, is the next step for this boundary. It is an additive
change -- one new class implementing an existing protocol -- not a redesign."

A Word task pane is a sandboxed web page. It can reach a local process over
HTTP or a WebSocket; it cannot open a named pipe. So the transport this
boundary actually needs first is HTTP, and this package is that "next step,"
built the way every prior one was: additive, not a redesign.

``Transport``'s own shape does not fit HTTP, and forcing it to would be the
wrong additive change. Every method the add-in calls is a standalone
request/response exchange, while ``Transport`` models one persistent duplex
channel with a single ``$connect`` handshake per connection; ``IpcServer``
holds exactly one ``_transport`` at a time by design. Squeezing many
concurrent HTTP requests through that one-at-a-time model would either
serialise every request behind whichever one is in flight, or require
inventing a second multiplexing layer underneath it -- which is the redesign
ADR-020 explicitly rules out, not the additive step it asks for.

The correct, additive integration point is one level down: a bridge in this
package calls straight into the runtime-layer collaborators the daemon already
composes (:mod:`teea.nlp.snapshot`, :mod:`teea.plugins`, :mod:`teea.fusion`),
using the exact ``IpcRequest`` / ``IpcResponse`` / ``IpcFault`` wire models
:mod:`teea.ipc.models` already defines, validates and tests -- so nothing on
the wire reveals that no ``IpcServer`` sits behind it. This package therefore
depends on ``teea.core``, the runtime-layer packages a given bridge serves, and
exactly one submodule of ``teea.ipc``: ``teea.ipc.models``, for the wire shapes
alone. It never imports ``teea.ipc.server``, ``teea.ipc.client``,
``teea.ipc.transport`` or ``teea.ipc.codec`` -- the protocol engine and the
byte codec stay ``teea.ipc``'s alone -- and nothing in ``teea.ipc`` imports
this package back. It also never imports ``teea.persistence``: a bridge serves
requests through the collaborators the daemon hands it, never storage
directly. ``tests/test_architecture.py`` pins all of this.

Loopback only
-------------
Every server in this package refuses to bind anywhere but a loopback address.
This is not the ``socket``-import ban ``tests/test_architecture.py`` already
states for ``teea.ipc`` and for network *clients* package-wide (``http.server``
is stdlib and is not one of the forbidden client imports); it is a positive
guarantee in the other direction -- the process never listens where another
machine on the network could reach it.

What ships here today
----------------------
:mod:`analysis_server` bridges the document-analysis pipeline (the ``analyze``
/ ``plugins`` / ``fuse`` handlers :class:`~teea.daemon.TEEADaemon` already
registers on its ``IpcServer``) to one HTTP endpoint.

:mod:`http_server` extends this with AI streaming endpoints (explain,
summarize, cancel) served over SSE (Server-Sent Events), combining both
analysis and AI behind a single loopback HTTP server on a single port.
"""

from __future__ import annotations

from teea.transport.analysis_server import (
    DEFAULT_HOST,
    DEFAULT_PORT,
    LOOPBACK_HOSTS,
    AnalysisHttpServer,
    NotLoopbackError,
    serve_analysis_http,
)
from teea.transport.http_server import (
    AI_PATHS,
    ANALYSIS_METHOD,
    ANALYSIS_PATH,
    TEEAHttpServer,
    serve_http,
)

__all__ = [
    "AI_PATHS",
    "ANALYSIS_METHOD",
    "ANALYSIS_PATH",
    "DEFAULT_HOST",
    "DEFAULT_PORT",
    "LOOPBACK_HOSTS",
    "AnalysisHttpServer",
    "NotLoopbackError",
    "TEEAHttpServer",
    "serve_analysis_http",
    "serve_http",
]