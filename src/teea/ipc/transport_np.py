"""Windows Named Pipe transport: OS-specific Transport implementation.

Implements the :class:`~teea.ipc.interfaces.Transport` protocol over Windows
Named Pipes, providing a cross-process byte channel between the add-in
and the daemon on the same machine.

Usage::

    server_end, client_end = WindowsNamedPipeTransport.pair()
    server.serve(server_end)
    client.connect(client_end)

Thread safety
-------------
All public methods are thread-safe. Each end runs a background reader thread
that reads framed messages from the pipe and delivers them to the registered
receiver. Reader threads use **overlapped (asynchronous) I/O** so that a
:meth:`send` (synchronous write) does not conflict with a pending read on
the same handle.

Implementation notes
--------------------
Named pipe handles are opened with ``FILE_FLAG_OVERLAPPED``. The reader thread
issues overlapped ``ReadFile`` calls and waits on the completion event with a
short timeout to periodically check the ``_closed`` flag.
:meth:`send` performs synchronous ``WriteFile`` (passing ``NULL`` for
*lpOverlapped*), which is permitted on an overlapped handle.
"""

from __future__ import annotations

import contextlib
import struct
import threading
from collections.abc import Callable
from ctypes import (
    POINTER,
    Structure,
    WinDLL,
    byref,
    c_void_p,
    create_string_buffer,
    get_last_error,
    wintypes,
)

from teea.ipc.errors import TransportClosedError

# -- Win32 API bindings -------------------------------------------------------

_kernel32 = WinDLL("kernel32", use_last_error=True)

_kernel32.CreateNamedPipeW.restype = wintypes.HANDLE
_kernel32.CreateNamedPipeW.argtypes = (
    wintypes.LPCWSTR,   # lpName
    wintypes.DWORD,      # dwOpenMode
    wintypes.DWORD,      # dwPipeMode
    wintypes.DWORD,      # nMaxInstances
    wintypes.DWORD,      # nOutBufferSize
    wintypes.DWORD,      # nInBufferSize
    wintypes.DWORD,      # nDefaultTimeOut
    c_void_p,            # lpSecurityAttributes
)

_kernel32.ConnectNamedPipe.restype = wintypes.BOOL
_kernel32.ConnectNamedPipe.argtypes = (wintypes.HANDLE, c_void_p)

_kernel32.DisconnectNamedPipe.restype = wintypes.BOOL
_kernel32.DisconnectNamedPipe.argtypes = (wintypes.HANDLE,)

_kernel32.CreateFileW.restype = wintypes.HANDLE
_kernel32.CreateFileW.argtypes = (
    wintypes.LPCWSTR,   # lpFileName
    wintypes.DWORD,      # dwDesiredAccess
    wintypes.DWORD,      # dwShareMode
    c_void_p,            # lpSecurityAttributes
    wintypes.DWORD,      # dwCreationDisposition
    wintypes.DWORD,      # dwFlagsAndAttributes
    wintypes.HANDLE,     # hTemplateFile
)

_kernel32.WriteFile.restype = wintypes.BOOL
_kernel32.WriteFile.argtypes = (
    wintypes.HANDLE,                 # hFile
    c_void_p,                        # lpBuffer
    wintypes.DWORD,                  # nNumberOfBytesToWrite
    POINTER(wintypes.DWORD),         # lpNumberOfBytesWritten
    c_void_p,                        # lpOverlapped
)

_kernel32.ReadFile.restype = wintypes.BOOL
_kernel32.ReadFile.argtypes = (
    wintypes.HANDLE,                 # hFile
    c_void_p,                        # lpBuffer
    wintypes.DWORD,                  # nNumberOfBytesToRead
    POINTER(wintypes.DWORD),         # lpNumberOfBytesRead
    c_void_p,                        # lpOverlapped
)

_kernel32.CloseHandle.restype = wintypes.BOOL
_kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)

_kernel32.SetNamedPipeHandleState.restype = wintypes.BOOL
_kernel32.SetNamedPipeHandleState.argtypes = (
    wintypes.HANDLE,    # hNamedPipe
    wintypes.LPDWORD,   # lpMode
    c_void_p,           # lpMaxCollectionCount
    c_void_p,           # lpCollectDataTimeout
)

_kernel32.WaitNamedPipeW.restype = wintypes.BOOL
_kernel32.WaitNamedPipeW.argtypes = (wintypes.LPCWSTR, wintypes.DWORD)

_kernel32.FlushFileBuffers.restype = wintypes.BOOL
_kernel32.FlushFileBuffers.argtypes = (wintypes.HANDLE,)

_kernel32.CreateEventW.restype = wintypes.HANDLE
_kernel32.CreateEventW.argtypes = (
    c_void_p,            # lpEventAttributes
    wintypes.BOOL,       # bManualReset
    wintypes.BOOL,       # bInitialState
    wintypes.LPCWSTR,    # lpName
)

_kernel32.WaitForSingleObject.restype = wintypes.DWORD
_kernel32.WaitForSingleObject.argtypes = (wintypes.HANDLE, wintypes.DWORD)

_kernel32.GetOverlappedResult.restype = wintypes.BOOL
_kernel32.GetOverlappedResult.argtypes = (
    wintypes.HANDLE,                 # hFile
    c_void_p,                        # lpOverlapped
    POINTER(wintypes.DWORD),         # lpNumberOfBytesTransferred
    wintypes.BOOL,                   # bWait
)

_kernel32.CancelIoEx.restype = wintypes.BOOL
_kernel32.CancelIoEx.argtypes = (wintypes.HANDLE, c_void_p)

# -- OVERLAPPED structure ------------------------------------------------------


class OVERLAPPED(Structure):
    """Windows ``OVERLAPPED`` structure for asynchronous I/O.

    Layout matches the Win32 declaration on both x86 and x64:
    ``ULONG_PTR`` fields are pointer-sized, ``DWORD`` fields are 32-bit.
    The structure is 32 bytes on x64, 20 bytes on x86.
    """
    _fields_: list[tuple[str, type]] = [  # type: ignore[misc]  # noqa: RUF012
        ("Internal", c_void_p),
        ("InternalHigh", c_void_p),
        ("Offset", wintypes.DWORD),
        ("OffsetHigh", wintypes.DWORD),
        ("hEvent", wintypes.HANDLE),
    ]


# -- Constants ----------------------------------------------------------------

PIPE_ACCESS_DUPLEX = 0x00000003
FILE_FLAG_OVERLAPPED = 0x40000000
PIPE_TYPE_MESSAGE = 0x00000004
PIPE_READMODE_MESSAGE = 0x00000002
PIPE_WAIT = 0x00000000
PIPE_UNLIMITED_INSTANCES = 255

GENERIC_READ = 0x80000000
GENERIC_WRITE = 0x40000000
OPEN_EXISTING = 3

INVALID_HANDLE_VALUE: int = c_void_p(-1).value  # type: ignore[assignment]
WAIT_TIMEOUT = 258
WAIT_OBJECT_0 = 0
ERROR_IO_PENDING = 997
ERROR_MORE_DATA = 234
ERROR_BROKEN_PIPE = 109
ERROR_PIPE_NOT_CONNECTED = 233
ERROR_NO_DATA = 232
ERROR_PIPE_BUSY = 231
ERROR_PIPE_CONNECTED = 535
ERROR_SEM_TIMEOUT = 121

_PIPE_PREFIX = r"\\.\pipe\teea-"
_FRAME_HEADER_FORMAT = "<I"
_FRAME_HEADER_SIZE = 4
_CONNECT_TIMEOUT_SECONDS = 30
_READ_BUF_SIZE = 262144  # 256 KB — covers nearly all IPC messages in one read
_CLOSE_POLL_MS = 100

# -- Utilities ----------------------------------------------------------------


def _pipe_path(name: str) -> str:
    """Prefix *name* with ``\\\\.\\pipe\\teea-``."""
    return _PIPE_PREFIX + name


def _frame_payload(payload: bytes) -> bytes:
    """Prepend 4-byte little-endian length header."""
    return struct.pack(_FRAME_HEADER_FORMAT, len(payload)) + payload


# ---------------------------------------------------------------------------
# Transport
# ---------------------------------------------------------------------------


class WindowsNamedPipeTransport:
    """One end of a Windows Named Pipe channel.

    Satisfies the :class:`~teea.ipc.interfaces.Transport` protocol.
    Construct a connected pair with :meth:`pair`.
    """

    def __init__(
        self,
        handle: int,
        end_name: str,
        *,
        _is_server: bool = False,
    ) -> None:
        self._handle: int = handle
        self._end_name: str = end_name
        self._is_server: bool = _is_server
        self._receiver: Callable[[bytes], None] | None = None
        self._closed: bool = False
        self._lock: threading.Lock = threading.Lock()
        self._reader_thread: threading.Thread | None = None

    # -- factory -----------------------------------------------------------

    @classmethod
    def pair(
        cls,
        pipe_name: str = "ipc",
        *,
        buffer_size: int = 65536,
    ) -> tuple[WindowsNamedPipeTransport, WindowsNamedPipeTransport]:
        """Return a connected ``(server_end, client_end)`` pair.

        Args:
            pipe_name: Short name prefixed with ``\\\\.\\pipe\\teea-``, or
                a full ``\\\\.\\pipe\\...`` path.
            buffer_size: Pipe I/O buffer size.

        Returns:
            (server_end, client_end) with running reader threads.

        Raises:
            RuntimeError: On Win32 API failure.
            TimeoutError: If connection handshake exceeds 30 s.
        """
        full_name = pipe_name if pipe_name.startswith(r"\\.\pipe\\") else _pipe_path(pipe_name)

        # -- server end ----------------------------------------------------
        server_handle = _kernel32.CreateNamedPipeW(
            full_name,
            PIPE_ACCESS_DUPLEX | FILE_FLAG_OVERLAPPED,
            PIPE_TYPE_MESSAGE | PIPE_READMODE_MESSAGE | PIPE_WAIT,
            PIPE_UNLIMITED_INSTANCES,
            buffer_size,
            buffer_size,
            0,
            None,
        )
        if server_handle == INVALID_HANDLE_VALUE:
            err = get_last_error()
            raise RuntimeError(
                f"CreateNamedPipeW failed for '{full_name}': error {err}"
            )

        connect_error: list[int] = [0]
        connect_called: threading.Event = threading.Event()

        def _do_connect() -> None:
            connect_called.set()
            ok = _kernel32.ConnectNamedPipe(server_handle, None)
            if not ok:
                err = get_last_error()
                if err != ERROR_PIPE_CONNECTED:
                    connect_error[0] = err

        connector = threading.Thread(target=_do_connect, daemon=True)
        connector.start()
        connect_called.wait()

        # -- client end ----------------------------------------------------
        ok = _kernel32.WaitNamedPipeW(full_name, 5000)
        if not ok:
            err = get_last_error()
            _kernel32.CloseHandle(server_handle)
            if err in (WAIT_TIMEOUT, ERROR_SEM_TIMEOUT):
                raise TimeoutError(
                    f"Timed out waiting for named pipe '{full_name}'"
                )
            raise RuntimeError(
                f"WaitNamedPipeW failed for '{full_name}': error {err}"
            )

        client_handle = _kernel32.CreateFileW(
            full_name,
            GENERIC_READ | GENERIC_WRITE,
            0,
            None,
            OPEN_EXISTING,
            FILE_FLAG_OVERLAPPED,
            None,
        )
        if client_handle == INVALID_HANDLE_VALUE:
            err = get_last_error()
            if err == ERROR_PIPE_BUSY:
                _kernel32.WaitNamedPipeW(full_name, 10000)
                client_handle = _kernel32.CreateFileW(
                    full_name,
                    GENERIC_READ | GENERIC_WRITE,
                    0,
                    None,
                    OPEN_EXISTING,
                    FILE_FLAG_OVERLAPPED,
                    None,
                )
            if client_handle == INVALID_HANDLE_VALUE:
                err = get_last_error()
                _kernel32.CloseHandle(server_handle)
                raise RuntimeError(
                    f"CreateFileW failed for '{full_name}': error {err}"
                )

        connector.join(timeout=_CONNECT_TIMEOUT_SECONDS)
        if connector.is_alive():
            _kernel32.CloseHandle(server_handle)
            _kernel32.CloseHandle(client_handle)
            raise TimeoutError("ConnectNamedPipe timed out")

        if connect_error[0]:
            _kernel32.CloseHandle(server_handle)
            _kernel32.CloseHandle(client_handle)
            raise RuntimeError(
                f"ConnectNamedPipe failed: error {connect_error[0]}"
            )

        # Set client to message read mode
        mode = wintypes.DWORD(PIPE_READMODE_MESSAGE)
        ok = _kernel32.SetNamedPipeHandleState(
            client_handle, byref(mode), None, None
        )
        if not ok:
            err = get_last_error()
            _kernel32.CloseHandle(server_handle)
            _kernel32.CloseHandle(client_handle)
            raise RuntimeError(
                f"SetNamedPipeHandleState failed: error {err}"
            )

        server_end = cls(server_handle, "server", _is_server=True)
        client_end = cls(client_handle, "client")

        server_end._start_reader()
        client_end._start_reader()

        return server_end, client_end

    # -- reader thread -----------------------------------------------------

    def _start_reader(self) -> None:
        """Start background daemon thread for overlapped reads."""
        if self._reader_thread is not None:
            return
        self._reader_thread = threading.Thread(
            target=self._reader_loop,
            daemon=True,
            name=f"np-reader-{self._end_name}",
        )
        self._reader_thread.start()

    @staticmethod
    def _read_message(
        handle: int,
        event: int,
    ) -> bytes | None:
        """Read one complete framed message from the pipe.

        Performs a single overlapped read for up to ``_READ_BUF_SIZE`` bytes.
        The message frame is ``[4-byte length][payload]``.  If the read
        returns ``ERROR_MORE_DATA`` (message larger than the buffer), the
        remaining bytes are fetched with additional reads.

        Returns:
            The payload bytes, or ``None`` if the pipe was closed or an
            error occurred.
        """
        buf = create_string_buffer(_READ_BUF_SIZE)
        overlapped = OVERLAPPED()
        overlapped.hEvent = event
        read = wintypes.DWORD(0)

        ok = _kernel32.ReadFile(handle, buf, _READ_BUF_SIZE, byref(read), byref(overlapped))

        if not ok:
            err = get_last_error()
            if err == ERROR_IO_PENDING:
                _kernel32.WaitForSingleObject(event, 30000)
                ok = _kernel32.GetOverlappedResult(
                    handle, byref(overlapped), byref(read), False
                )
                if not ok and get_last_error() not in (ERROR_MORE_DATA,):
                    return None
            elif err != ERROR_MORE_DATA:
                return None

        total_read: int = read.value
        if total_read < _FRAME_HEADER_SIZE:
            return None

        length: int = struct.unpack(_FRAME_HEADER_FORMAT, buf.raw[:_FRAME_HEADER_SIZE])[0]
        total_needed: int = _FRAME_HEADER_SIZE + length
        frame_data: list[bytes] = [buf.raw[:total_read]]

        # Read remaining chunks if the message was larger than the buffer
        while total_read < total_needed:
            remaining = total_needed - total_read
            chunk_size = min(remaining, _READ_BUF_SIZE)
            chunk_buf = create_string_buffer(chunk_size)
            chunk_ol = OVERLAPPED()
            chunk_ol.hEvent = event
            chunk_read = wintypes.DWORD(0)

            ok = _kernel32.ReadFile(handle, chunk_buf, chunk_size, byref(chunk_read), byref(chunk_ol))  # noqa: E501
            if not ok:
                err = get_last_error()
                if err == ERROR_IO_PENDING:
                    _kernel32.WaitForSingleObject(event, 30000)
                    _kernel32.GetOverlappedResult(
                        handle, byref(chunk_ol), byref(chunk_read), False
                    )
                elif err != ERROR_MORE_DATA:
                    return None

            if chunk_read.value == 0:
                return None

            frame_data.append(chunk_buf.raw[:chunk_read.value])
            total_read += chunk_read.value

        return b"".join(frame_data)[_FRAME_HEADER_SIZE:total_needed]

    def _reader_loop(self) -> None:
        """Read framed messages from the pipe and deliver to the receiver.

        Uses overlapped (asynchronous) I/O so that a concurrent synchronous
        :meth:`send` is not blocked by the pending read on the same handle.
        """
        event = _kernel32.CreateEventW(None, False, False, None)
        if event == INVALID_HANDLE_VALUE:
            return

        try:
            while True:
                with self._lock:
                    if self._closed:
                        return
                    handle = self._handle

                payload = self._read_message(handle, event)
                if payload is None:
                    break

                with self._lock:
                    receiver = self._receiver
                if receiver is not None:
                    with contextlib.suppress(Exception):
                        receiver(payload)
        finally:
            _kernel32.CloseHandle(event)
            with self._lock:
                self._closed = True

    # -- Transport protocol -------------------------------------------------

    def send(self, payload: bytes) -> None:
        """Deliver *payload* to the peer (synchronous write).

        Raises:
            TransportClosedError: If the pipe is closed.
        """
        framed = _frame_payload(payload)
        with self._lock:
            if self._closed:
                raise TransportClosedError(
                    "The transport is closed.",
                    context={"end": self._end_name},
                )
            handle = self._handle

        written = wintypes.DWORD(0)
        ok = _kernel32.WriteFile(
            handle, framed, len(framed), byref(written), None
        )
        if not ok:
            err = get_last_error()
            self.close()
            raise TransportClosedError(
                f"Write failed on {self._end_name}: error {err}",
                context={"end": self._end_name, "error": err},
            )

    def set_receiver(self, receiver: Callable[[bytes], None]) -> None:
        """Register the callback invoked with each payload the peer sends."""
        with self._lock:
            self._receiver = receiver

    def close(self) -> None:
        """Close the pipe end. Idempotent."""
        with self._lock:
            if self._closed:
                return
            self._closed = True
            handle = self._handle
            self._handle = INVALID_HANDLE_VALUE

        if handle != INVALID_HANDLE_VALUE:
            _kernel32.CancelIoEx(handle, None)
            if self._is_server:
                _kernel32.FlushFileBuffers(handle)
                _kernel32.DisconnectNamedPipe(handle)
            _kernel32.CloseHandle(handle)

    @property
    def is_open(self) -> bool:
        """Whether the pipe end is open."""
        with self._lock:
            return not self._closed

    @property
    def name(self) -> str:
        """Diagnostic label for this end."""
        return self._end_name


__all__ = ["WindowsNamedPipeTransport"]
