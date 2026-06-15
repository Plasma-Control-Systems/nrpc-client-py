from __future__ import annotations

import asyncio
import struct
from typing import TYPE_CHECKING, Any, Iterable

from .client import (
    DEFAULT_MAX_PAYLOAD,
    HEADER_SIZE,
    VERSION,
    NrpcClient,
    NrpcValue,
    ProtocolError,
    RemoteError,
    _encode_request,
)

if TYPE_CHECKING:
    from .async_serial_backend import (
        AsyncSerialBackend,
    )
    from .async_tcp_backend import AsyncTcpBackend
    from .serial_backend import SerialFlowControl, SerialParity


class AsyncNrpcClient:
    """Persistent asynchronous connection to an nRPC server.

    Calls on one client instance are serialized because nRPC 0.1.0 permits one
    in-flight request per TCP connection. Separate instances can be used
    concurrently.
    """

    def __init__(
        self,
        host: str,
        port: int,
        *,
        connect_timeout: float | None = 10.0,
        max_payload_size: int = DEFAULT_MAX_PAYLOAD,
    ):
        self._host = host
        self._port = port
        self._connect_timeout = connect_timeout
        self._max_payload_size = max_payload_size
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._lock = asyncio.Lock()

    @classmethod
    async def connect(
        cls,
        host: str,
        port: int,
        *,
        connect_timeout: float | None = 10.0,
        max_payload_size: int = DEFAULT_MAX_PAYLOAD,
    ) -> AsyncNrpcClient:
        """Create and connect an asynchronous nRPC client."""

        client = cls(
            host,
            port,
            connect_timeout=connect_timeout,
            max_payload_size=max_payload_size,
        )
        await client._ensure_connected()
        return client

    async def close(self) -> None:
        """Close the nRPC connection. Calling this repeatedly is safe."""

        writer = self._writer
        self._reader = None
        self._writer = None
        if writer is None:
            return
        writer.close()
        try:
            await writer.wait_closed()
        except (ConnectionError, OSError):
            pass

    async def __aenter__(self) -> AsyncNrpcClient:
        await self._ensure_connected()
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.close()

    async def call(
        self,
        function_index: int,
        args: Iterable[NrpcValue] = (),
        timeout: int = 0,
    ) -> list[Any]:
        """Invoke a remote function without blocking the event loop."""

        packet = _encode_request(function_index, args, timeout)
        async with self._lock:
            await self._ensure_connected()
            operation = self._exchange(packet)
            try:
                if timeout == 0:
                    header, payload = await operation
                else:
                    header, payload = await asyncio.wait_for(
                        operation, timeout / 1000.0 + 1.0
                    )
            except BaseException:
                self._discard_connection()
                raise

        status, version, response_index, count, payload_size, error, reserved = (
            struct.unpack("!BBBBIII", header)
        )
        if version != VERSION:
            raise ProtocolError(f"unsupported response version {version}")
        if response_index != function_index:
            raise ProtocolError("response function index does not match request")
        if reserved != 0:
            raise ProtocolError("response reserved field is not zero")
        if status == 1:
            if count != 0 or payload_size != 0:
                raise ProtocolError("error response contains variables")
            raise RemoteError(error, response_index)
        if status != 0:
            raise ProtocolError(f"invalid response status {status}")
        if error != 0:
            raise ProtocolError("successful response contains an error code")
        return NrpcClient._decode_payload(count, payload)

    async def open_tcp_backend(
        self, host: str, port: int, *, timeout: int = 5000
    ) -> "AsyncTcpBackend":
        """Open a server-side TCP socket and return its async client proxy."""

        from .async_tcp_backend import AsyncTcpBackend

        return await AsyncTcpBackend.open(self, host, port, timeout=timeout)

    async def open_serial_backend(
        self,
        port: str,
        *,
        baud_rate: int = 9600,
        data_bits: int = 8,
        parity: "SerialParity | None" = None,
        stop_bits: int = 1,
        flow_control: "SerialFlowControl | None" = None,
        timeout: int = 5000,
    ) -> "AsyncSerialBackend":
        """Open a server-side serial port and return its async client proxy."""

        from .async_serial_backend import AsyncSerialBackend
        from .serial_backend import SerialFlowControl, SerialParity

        return await AsyncSerialBackend.open(
            self,
            port,
            baud_rate=baud_rate,
            data_bits=data_bits,
            parity=SerialParity.NONE if parity is None else parity,
            stop_bits=stop_bits,
            flow_control=(
                SerialFlowControl.NONE
                if flow_control is None
                else flow_control
            ),
            timeout=timeout,
        )

    async def _ensure_connected(self) -> None:
        if self._writer is not None:
            return
        operation = asyncio.open_connection(self._host, self._port)
        if self._connect_timeout is None:
            reader, writer = await operation
        else:
            reader, writer = await asyncio.wait_for(
                operation, self._connect_timeout
            )
        self._reader = reader
        self._writer = writer

    async def _exchange(self, packet: bytes) -> tuple[bytes, bytes]:
        reader = self._reader
        writer = self._writer
        if reader is None or writer is None:
            raise RuntimeError("nRPC client is not connected")
        writer.write(packet)
        await writer.drain()
        try:
            header = await reader.readexactly(HEADER_SIZE)
        except asyncio.IncompleteReadError as error:
            raise ConnectionError(
                "nRPC connection closed before response completed"
            ) from error
        payload_size = struct.unpack("!I", header[4:8])[0]
        if payload_size > self._max_payload_size:
            raise ProtocolError("response payload exceeds configured limit")
        try:
            payload = await reader.readexactly(payload_size)
        except asyncio.IncompleteReadError as error:
            raise ConnectionError(
                "nRPC connection closed before response completed"
            ) from error
        return header, payload

    def _discard_connection(self) -> None:
        writer = self._writer
        self._reader = None
        self._writer = None
        if writer is not None:
            writer.close()
