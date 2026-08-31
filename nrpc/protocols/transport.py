"""Reusable synchronous byte-transport infrastructure for device protocols."""

from __future__ import annotations

import threading
import time
from contextlib import contextmanager
from typing import Iterator, Protocol


class ByteTransport(Protocol):
    """Minimal transport implemented by the nRPC TCP and serial proxies."""

    def write(self, data: bytes, *, timeout: int = 0) -> int:
        """Write bytes and return the number accepted by the transport."""

        ...

    def read(self, max_size: int, *, timeout: int = 0) -> bytes:
        """Read up to ``max_size`` bytes."""

        ...

    def close(self, *, timeout: int = 0) -> None:
        """Close the transport."""

        ...


class ProtocolTransportError(Exception):
    """The byte transport could not complete a protocol operation safely."""


class _Deadline:
    def __init__(self, timeout: int):
        if not 0 <= timeout <= 0xFFFFFFFF:
            raise ValueError("timeout must be between 0 and 4294967295 ms")
        self._expires = (
            None if timeout == 0 else time.monotonic() + timeout / 1000.0
        )

    def remaining_ms(self) -> int:
        if self._expires is None:
            return 0
        remaining = self._expires - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("device protocol transaction timed out")
        return max(1, min(0xFFFFFFFF, int(remaining * 1000)))


class ProtocolTransaction:
    """Bounded I/O view valid for one locked protocol transaction."""

    def __init__(
        self,
        transport: ByteTransport,
        deadline: _Deadline,
        max_frame_size: int,
    ):
        self._transport = transport
        self._deadline = deadline
        self._max_frame_size = max_frame_size
        self._bytes_read = 0

    def write(self, data: bytes | bytearray | memoryview) -> None:
        """Write one complete frame, rejecting a short transport write."""

        encoded = bytes(data)
        if len(encoded) > self._max_frame_size:
            raise ValueError("protocol frame exceeds max_frame_size")
        written = self._transport.write(
            encoded, timeout=self._deadline.remaining_ms()
        )
        if not isinstance(written, int) or isinstance(written, bool):
            raise ProtocolTransportError(
                "transport write returned an invalid byte count"
            )
        if written != len(encoded):
            raise ProtocolTransportError(
                f"short transport write: expected {len(encoded)}, wrote {written}"
            )

    def read(self, max_size: int) -> bytes:
        """Read up to ``max_size`` bytes within the transaction limits."""

        if not 0 < max_size <= self._max_frame_size - self._bytes_read:
            raise ValueError("protocol read exceeds max_frame_size")
        data = self._transport.read(
            max_size, timeout=self._deadline.remaining_ms()
        )
        if not isinstance(data, bytes):
            raise ProtocolTransportError("transport read returned non-bytes data")
        if len(data) > max_size:
            raise ProtocolTransportError(
                "transport read returned more bytes than requested"
            )
        self._bytes_read += len(data)
        return data

    def read_exactly(self, size: int) -> bytes:
        """Read exactly ``size`` bytes, accepting fragmented reads."""

        if size < 0:
            raise ValueError("size must not be negative")
        if size > self._max_frame_size - self._bytes_read:
            raise ValueError("protocol read exceeds max_frame_size")
        chunks = bytearray()
        while len(chunks) < size:
            chunk = self.read(size - len(chunks))
            if not chunk:
                raise ConnectionError(
                    "transport closed before the protocol frame completed"
                )
            chunks.extend(chunk)
        return bytes(chunks)


class ProtocolSession:
    """Serializes multi-call protocol transactions over a byte transport.

    A session does not close a caller-owned transport by default. Pass
    ``owns_transport=True`` when the session is responsible for its lifetime.
    """

    def __init__(
        self,
        transport: ByteTransport,
        *,
        max_frame_size: int,
        owns_transport: bool = False,
    ):
        if max_frame_size <= 0:
            raise ValueError("max_frame_size must be positive")
        self._transport = transport
        self._max_frame_size = max_frame_size
        self._owns_transport = owns_transport
        self._lock = threading.RLock()
        self._closed = False

    @property
    def closed(self) -> bool:
        """Whether this protocol session has been closed."""

        return self._closed

    @contextmanager
    def transaction(self, *, timeout: int = 0) -> Iterator[ProtocolTransaction]:
        """Lock the session and expose I/O sharing one end-to-end deadline."""

        deadline = _Deadline(timeout)
        if timeout == 0:
            self._lock.acquire()
            acquired = True
        else:
            acquired = self._lock.acquire(
                timeout=deadline.remaining_ms() / 1000.0
            )
        if not acquired:
            raise TimeoutError(
                "device protocol transaction timed out waiting for the session"
            )
        try:
            if self._closed:
                raise RuntimeError("protocol session is closed")
            yield ProtocolTransaction(
                self._transport, deadline, self._max_frame_size
            )
        finally:
            self._lock.release()

    def close(self, *, timeout: int = 0) -> None:
        """Close the session and, when owned, its underlying transport."""

        with self._lock:
            if self._closed:
                return
            if self._owns_transport:
                self._transport.close(timeout=timeout)
            self._closed = True

    def __enter__(self) -> ProtocolSession:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
