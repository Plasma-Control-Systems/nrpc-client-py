from __future__ import annotations

from enum import IntEnum
from typing import TYPE_CHECKING

from .client import DataType, TypedValue

if TYPE_CHECKING:
    from .client import NrpcClient

GPIO_OPEN = 48
GPIO_READ = 49
GPIO_WRITE = 50
GPIO_CLOSE = 51


class GpioDirection(IntEnum):
    """Direction of a GPIO line requested by the server."""

    INPUT = 0
    OUTPUT = 1


class GpioLine:
    """Client proxy for one libgpiod line owned by the nRPC server."""

    def __init__(
        self,
        client: NrpcClient,
        chip: str,
        offset: int,
        direction: GpioDirection = GpioDirection.INPUT,
        *,
        initial_value: bool = False,
        active_low: bool = False,
        consumer: str = "nrpc-server",
        timeout: int = 5000,
    ):
        if not chip:
            raise ValueError("chip must not be empty")
        if not 0 <= offset <= 0xFFFFFFFF:
            raise ValueError("offset must be between 0 and 4294967295")
        direction = GpioDirection(direction)
        if not isinstance(initial_value, bool):
            raise TypeError("initial_value must be bool")
        if not isinstance(active_low, bool):
            raise TypeError("active_low must be bool")
        if not consumer:
            raise ValueError("consumer must not be empty")

        self._client = client
        self._direction = direction
        self._closed = False
        values = client.call(
            GPIO_OPEN,
            [
                chip,
                TypedValue(DataType.UINT32, offset),
                TypedValue(DataType.UINT8, direction.value),
                TypedValue(DataType.BOOL, initial_value),
                TypedValue(DataType.BOOL, active_low),
                consumer,
            ],
            timeout=timeout,
        )
        if len(values) != 1 or not isinstance(values[0], int):
            raise RuntimeError("GPIO open returned an invalid handle")
        self._handle = values[0]

    @property
    def handle(self) -> int:
        """Server-side handle scoped to this nRPC connection."""

        return self._handle

    @property
    def direction(self) -> GpioDirection:
        return self._direction

    def read(self, *, timeout: int = 0) -> bool:
        """Read the logical line value."""

        self._ensure_open()
        values = self._client.call(
            GPIO_READ,
            [TypedValue(DataType.UINT64, self._handle)],
            timeout=timeout,
        )
        if len(values) != 1 or not isinstance(values[0], bool):
            raise RuntimeError("GPIO read returned an invalid value")
        return values[0]

    def write(self, value: bool, *, timeout: int = 0) -> None:
        """Set the logical value of an output line."""

        self._ensure_open()
        if self._direction != GpioDirection.OUTPUT:
            raise RuntimeError("cannot write to a GPIO input")
        if not isinstance(value, bool):
            raise TypeError("value must be bool")
        values = self._client.call(
            GPIO_WRITE,
            [
                TypedValue(DataType.UINT64, self._handle),
                TypedValue(DataType.BOOL, value),
            ],
            timeout=timeout,
        )
        if values:
            raise RuntimeError("GPIO write returned unexpected values")

    def close(self, *, timeout: int = 0) -> None:
        """Release the remote line. Calling this repeatedly is safe."""

        if self._closed:
            return
        values = self._client.call(
            GPIO_CLOSE,
            [TypedValue(DataType.UINT64, self._handle)],
            timeout=timeout,
        )
        if values:
            raise RuntimeError("GPIO close returned unexpected values")
        self._closed = True

    def __enter__(self) -> GpioLine:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _ensure_open(self) -> None:
        if self._closed:
            raise RuntimeError("GPIO line is closed")
