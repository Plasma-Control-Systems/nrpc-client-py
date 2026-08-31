from __future__ import annotations

from enum import IntEnum
from typing import TYPE_CHECKING

from .client import DataType, TypedValue

if TYPE_CHECKING:
    from .client import NrpcClient

SPI_OPEN = 52
SPI_TRANSFER = 53
SPI_CLOSE = 54


class SpiMode(IntEnum):
    """SPI clock polarity and phase mode."""

    MODE_0 = 0
    MODE_1 = 1
    MODE_2 = 2
    MODE_3 = 3


class SpiDevice:
    """Client proxy for one Linux spidev device owned by the server."""

    def __init__(
        self,
        client: NrpcClient,
        device: str,
        *,
        mode: SpiMode = SpiMode.MODE_0,
        max_speed_hz: int = 1_000_000,
        bits_per_word: int = 8,
        lsb_first: bool = False,
        timeout: int = 5000,
    ):
        if not device:
            raise ValueError("device must not be empty")
        mode = SpiMode(mode)
        if not 1 <= max_speed_hz <= 0xFFFFFFFF:
            raise ValueError("max_speed_hz must be between 1 and 4294967295")
        if not 1 <= bits_per_word <= 0xFF:
            raise ValueError("bits_per_word must be between 1 and 255")
        if not isinstance(lsb_first, bool):
            raise TypeError("lsb_first must be bool")

        self._client = client
        self._closed = False
        values = client.call(
            SPI_OPEN,
            [
                device,
                TypedValue(DataType.UINT8, mode.value),
                TypedValue(DataType.UINT32, max_speed_hz),
                TypedValue(DataType.UINT8, bits_per_word),
                TypedValue(DataType.BOOL, lsb_first),
            ],
            timeout=timeout,
        )
        if len(values) != 1 or not isinstance(values[0], int):
            raise RuntimeError("SPI open returned an invalid handle")
        self._handle = values[0]

    @property
    def handle(self) -> int:
        """Server-side handle scoped to this nRPC connection."""

        return self._handle

    def transfer(
        self,
        data: bytes | bytearray | memoryview,
        *,
        speed_hz: int | None = None,
        delay_us: int = 0,
        cs_change: bool = False,
        timeout: int = 0,
    ) -> bytes:
        """Perform one full-duplex transfer and return the received bytes."""

        self._ensure_open()
        if not isinstance(data, (bytes, bytearray, memoryview)):
            raise TypeError("data must be bytes-like")
        transmitted = bytes(data)
        if not transmitted:
            raise ValueError("data must not be empty")
        transfer_speed = 0 if speed_hz is None else speed_hz
        if not 0 <= transfer_speed <= 0xFFFFFFFF:
            raise ValueError("speed_hz must be between 0 and 4294967295")
        if not 0 <= delay_us <= 0xFFFF:
            raise ValueError("delay_us must be between 0 and 65535")
        if not isinstance(cs_change, bool):
            raise TypeError("cs_change must be bool")

        values = self._client.call(
            SPI_TRANSFER,
            [
                TypedValue(DataType.UINT64, self._handle),
                transmitted,
                TypedValue(DataType.UINT32, transfer_speed),
                TypedValue(DataType.UINT16, delay_us),
                TypedValue(DataType.BOOL, cs_change),
            ],
            timeout=timeout,
        )
        if len(values) != 1 or not isinstance(values[0], bytes):
            raise RuntimeError("SPI transfer returned invalid data")
        if len(values[0]) != len(transmitted):
            raise RuntimeError("SPI transfer returned an invalid byte count")
        return values[0]

    def close(self, *, timeout: int = 0) -> None:
        """Release the remote device. Calling this repeatedly is safe."""

        if self._closed:
            return
        values = self._client.call(
            SPI_CLOSE,
            [TypedValue(DataType.UINT64, self._handle)],
            timeout=timeout,
        )
        if values:
            raise RuntimeError("SPI close returned unexpected values")
        self._closed = True

    def __enter__(self) -> SpiDevice:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _ensure_open(self) -> None:
        if self._closed:
            raise RuntimeError("SPI device is closed")
