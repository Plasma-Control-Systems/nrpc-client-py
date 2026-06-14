from __future__ import annotations

from enum import IntEnum
from typing import TYPE_CHECKING

from .client import DataType, TypedValue

if TYPE_CHECKING:
    from .client import NrpcClient

SERIAL_OPEN = 32
SERIAL_WRITE = 33
SERIAL_READ = 34
SERIAL_CLOSE = 35


class SerialParity(IntEnum):
    """Serial parity modes supported by libserialport."""

    NONE = 0
    ODD = 1
    EVEN = 2
    MARK = 3
    SPACE = 4


class SerialFlowControl(IntEnum):
    """Serial flow-control presets supported by libserialport."""

    NONE = 0
    SOFTWARE = 1
    RTS_CTS = 2
    DTR_DSR = 3


class SerialBackend:
    """Client proxy for a serial port owned by the nRPC server."""

    def __init__(
        self,
        client: NrpcClient,
        port: str,
        *,
        baud_rate: int = 9600,
        data_bits: int = 8,
        parity: SerialParity = SerialParity.NONE,
        stop_bits: int = 1,
        flow_control: SerialFlowControl = SerialFlowControl.NONE,
        timeout: int = 5000,
    ):
        if not port:
            raise ValueError("port must not be empty")
        if not 0 < baud_rate <= 0xFFFFFFFF:
            raise ValueError("baud_rate must be between 1 and 4294967295")
        if not 5 <= data_bits <= 8:
            raise ValueError("data_bits must be between 5 and 8")
        if stop_bits not in (1, 2):
            raise ValueError("stop_bits must be 1 or 2")
        parity = SerialParity(parity)
        flow_control = SerialFlowControl(flow_control)

        self._client = client
        self._buffer = bytearray()
        self._closed = False
        values = client.call(
            SERIAL_OPEN,
            [
                port,
                TypedValue(DataType.UINT32, baud_rate),
                TypedValue(DataType.UINT8, data_bits),
                TypedValue(DataType.UINT8, parity.value),
                TypedValue(DataType.UINT8, stop_bits),
                TypedValue(DataType.UINT8, flow_control.value),
            ],
            timeout=timeout,
        )
        if len(values) != 1 or not isinstance(values[0], int):
            raise RuntimeError("serial backend open returned an invalid handle")
        self._handle = values[0]

    @property
    def handle(self) -> int:
        """Server-side handle identifier scoped to this nRPC connection."""

        return self._handle

    def write(
        self,
        data: bytes | bytearray | memoryview | str,
        *,
        timeout: int = 0,
        encoding: str = "ascii",
    ) -> int:
        """Write data through the remote serial port."""

        self._ensure_open()
        encoded = data.encode(encoding) if isinstance(data, str) else bytes(data)
        values = self._client.call(
            SERIAL_WRITE,
            [TypedValue(DataType.UINT64, self._handle), encoded],
            timeout=timeout,
        )
        if len(values) != 1 or not isinstance(values[0], int):
            raise RuntimeError(
                "serial backend write returned an invalid byte count"
            )
        return values[0]

    def read(self, max_size: int = 4096, *, timeout: int = 0) -> bytes:
        """Read up to ``max_size`` bytes from the remote serial port."""

        self._ensure_open()
        if not 0 < max_size <= 0xFFFFFFFF:
            raise ValueError("max_size must be between 1 and 4294967295")
        if self._buffer:
            result = bytes(self._buffer[:max_size])
            del self._buffer[:max_size]
            return result
        values = self._client.call(
            SERIAL_READ,
            [
                TypedValue(DataType.UINT64, self._handle),
                TypedValue(DataType.UINT32, max_size),
            ],
            timeout=timeout,
        )
        if len(values) != 1 or not isinstance(values[0], bytes):
            raise RuntimeError("serial backend read returned invalid data")
        return values[0]

    def read_until(
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
                raise ValueError("serial response exceeds max_size")
            read_size = min(chunk_size, max_size - len(self._buffer))
            values = self._client.call(
                SERIAL_READ,
                [
                    TypedValue(DataType.UINT64, self._handle),
                    TypedValue(DataType.UINT32, read_size),
                ],
                timeout=timeout,
            )
            if len(values) != 1 or not isinstance(values[0], bytes):
                raise RuntimeError("serial backend read returned invalid data")
            self._buffer.extend(values[0])

    def close(self, *, timeout: int = 0) -> None:
        """Close the remote serial port. Calling this repeatedly is safe."""

        if self._closed:
            return
        self._client.call(
            SERIAL_CLOSE,
            [TypedValue(DataType.UINT64, self._handle)],
            timeout=timeout,
        )
        self._closed = True
        self._buffer.clear()

    def __enter__(self) -> SerialBackend:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _ensure_open(self) -> None:
        if self._closed:
            raise RuntimeError("serial backend is closed")

