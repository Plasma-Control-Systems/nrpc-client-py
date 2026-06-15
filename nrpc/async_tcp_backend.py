from __future__ import annotations

from typing import TYPE_CHECKING

from .client import DataType, TypedValue
from .tcp_backend import TCP_CLOSE, TCP_OPEN, TCP_READ, TCP_WRITE

if TYPE_CHECKING:
    from .async_client import AsyncNrpcClient


class AsyncTcpBackend:
    """Async client proxy for a TCP socket owned by the nRPC server."""

    def __init__(self, client: AsyncNrpcClient, handle: int):
        self._client = client
        self._handle = handle
        self._buffer = bytearray()
        self._closed = False

    @classmethod
    async def open(
        cls,
        client: AsyncNrpcClient,
        host: str,
        port: int,
        *,
        timeout: int = 5000,
    ) -> AsyncTcpBackend:
        if not 0 <= port <= 65535:
            raise ValueError("port must be between 0 and 65535")
        values = await client.call(
            TCP_OPEN,
            [host, TypedValue(DataType.UINT16, port)],
            timeout=timeout,
        )
        if len(values) != 1 or not isinstance(values[0], int):
            raise RuntimeError("TCP backend open returned an invalid handle")
        return cls(client, values[0])

    @property
    def handle(self) -> int:
        """Server-side handle identifier scoped to this nRPC connection."""

        return self._handle

    async def write(
        self,
        data: bytes | bytearray | memoryview | str,
        *,
        timeout: int = 0,
        encoding: str = "ascii",
    ) -> int:
        """Write all data through the remote TCP socket."""

        self._ensure_open()
        encoded = data.encode(encoding) if isinstance(data, str) else bytes(data)
        values = await self._client.call(
            TCP_WRITE,
            [TypedValue(DataType.UINT64, self._handle), encoded],
            timeout=timeout,
        )
        if len(values) != 1 or not isinstance(values[0], int):
            raise RuntimeError("TCP backend write returned an invalid byte count")
        return values[0]

    async def read(self, max_size: int = 4096, *, timeout: int = 0) -> bytes:
        """Read up to ``max_size`` bytes from the remote TCP socket."""

        self._ensure_open()
        if not 0 < max_size <= 0xFFFFFFFF:
            raise ValueError("max_size must be between 1 and 4294967295")
        if self._buffer:
            result = bytes(self._buffer[:max_size])
            del self._buffer[:max_size]
            return result
        return await self._read_remote(max_size, timeout)

    async def read_until(
        self,
        terminator: bytes = b"\n",
        *,
        max_size: int = 1024 * 1024,
        chunk_size: int = 4096,
        timeout: int = 0,
    ) -> bytes:
        """Read through and including ``terminator``, buffering excess bytes."""

        self._ensure_open()
        if not terminator:
            raise ValueError("terminator must not be empty")
        while True:
            end = self._buffer.find(terminator)
            if end >= 0:
                end += len(terminator)
                result = bytes(self._buffer[:end])
                del self._buffer[:end]
                return result
            if len(self._buffer) >= max_size:
                raise ValueError("TCP response exceeds max_size")
            read_size = min(chunk_size, max_size - len(self._buffer))
            self._buffer.extend(await self._read_remote(read_size, timeout))

    async def close(self, *, timeout: int = 0) -> None:
        """Close the remote TCP socket. Calling this repeatedly is safe."""

        if self._closed:
            return
        await self._client.call(
            TCP_CLOSE,
            [TypedValue(DataType.UINT64, self._handle)],
            timeout=timeout,
        )
        self._closed = True
        self._buffer.clear()

    async def __aenter__(self) -> AsyncTcpBackend:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.close()

    async def _read_remote(self, max_size: int, timeout: int) -> bytes:
        values = await self._client.call(
            TCP_READ,
            [
                TypedValue(DataType.UINT64, self._handle),
                TypedValue(DataType.UINT32, max_size),
            ],
            timeout=timeout,
        )
        if len(values) != 1 or not isinstance(values[0], bytes):
            raise RuntimeError("TCP backend read returned invalid data")
        return values[0]

    def _ensure_open(self) -> None:
        if self._closed:
            raise RuntimeError("TCP backend is closed")
