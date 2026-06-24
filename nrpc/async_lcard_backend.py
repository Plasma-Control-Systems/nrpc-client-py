from __future__ import annotations

from typing import TYPE_CHECKING, Iterable

from .client import DataType, TypedValue
from .lcard_backend import (
    LCARD_CLOSE,
    LCARD_IO_ASYNC,
    LCARD_OPEN,
    LCardAdcInputMode,
    LCardAsyncOperation,
    LCardAsyncResult,
    LCardBoardType,
    _decode_uint32_values,
    _signed_adc_voltage,
    _uint32,
    _uint32_values,
    _unsigned_adc_voltage,
)

if TYPE_CHECKING:
    from .async_client import AsyncNrpcClient


class AsyncLCardBackend:
    BOARD_TYPES: tuple[LCardBoardType, ...] = ()

    def __init__(
        self, client: AsyncNrpcClient, handle: int, board: LCardBoardType
    ):
        self._client = client
        self._handle = handle
        self._board = board
        self._closed = False

    @classmethod
    async def open(
        cls,
        client: AsyncNrpcClient,
        board: LCardBoardType,
        slot: int = 0,
        *,
        bios: str = "",
        timeout: int = 5000,
    ) -> AsyncLCardBackend:
        """Open a board, letting the server auto-load BIOS when ``bios`` is empty."""

        board = LCardBoardType(board)
        _uint32(slot, "slot")
        values = await client.call(
            LCARD_OPEN,
            [
                TypedValue(DataType.UINT32, slot),
                TypedValue(DataType.UINT32, board.value),
                bios,
            ],
            timeout=timeout,
        )
        if len(values) != 1 or not isinstance(values[0], int):
            raise RuntimeError("LCard backend open returned an invalid handle")
        return _ASYNC_BACKEND_TYPES[board](client, values[0], board)

    @property
    def handle(self) -> int:
        return self._handle

    @property
    def board(self) -> LCardBoardType:
        return self._board

    async def _io_async(
        self,
        operation: LCardAsyncOperation,
        *,
        channel_count: int = 0,
        channels: Iterable[int] = (),
        data: Iterable[int] = (),
        rate: float = 0.0,
        mode: int = 0,
        timeout: int = 0,
    ) -> LCardAsyncResult:
        self._ensure_open()
        channels = _uint32_values(channels, "channels")
        data = _uint32_values(data, "data")
        _uint32(channel_count, "channel_count")
        _uint32(mode, "mode")
        values = await self._client.call(
            LCARD_IO_ASYNC,
            [
                TypedValue(DataType.UINT64, self._handle),
                TypedValue(DataType.UINT32, operation.value),
                TypedValue(DataType.FLOAT64, rate),
                TypedValue(DataType.UINT32, mode),
                TypedValue(DataType.UINT32, channel_count),
                TypedValue(DataType.UINT32, channels),
                TypedValue(DataType.UINT32, data),
            ],
            timeout=timeout,
        )
        if len(values) != 2 or not isinstance(values[0], float):
            raise RuntimeError("LCard IoAsync returned invalid data")
        return LCardAsyncResult(
            values[0], _decode_uint32_values(values[1], "IoAsync")
        )

    async def close(self, *, timeout: int = 0) -> None:
        if self._closed:
            return
        await self._client.call(
            LCARD_CLOSE,
            [TypedValue(DataType.UINT64, self._handle)],
            timeout=timeout,
        )
        self._closed = True

    async def __aenter__(self) -> AsyncLCardBackend:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.close()

    def _ensure_open(self) -> None:
        if self._closed:
            raise RuntimeError("LCard backend is closed")


class _AsyncTtlBackend(AsyncLCardBackend):
    async def configure_ttl(self, mode: int, *, timeout: int = 0) -> None:
        await self._io_async(
            LCardAsyncOperation.TTL_CONFIG, mode=_uint32(mode, "mode"),
            timeout=timeout
        )

    async def read_ttl(self, *, timeout: int = 0) -> int:
        result = await self._io_async(
            LCardAsyncOperation.TTL_INPUT,
            channel_count=1,
            timeout=timeout,
        )
        return result.data[0]

    async def write_ttl(self, value: int, *, timeout: int = 0) -> None:
        await self._io_async(
            LCardAsyncOperation.TTL_OUTPUT,
            channel_count=1,
            data=[_uint32(value, "value")],
            timeout=timeout,
        )


class _AsyncSingleAdcBackend(_AsyncTtlBackend):
    ADC_INPUT_MODES = (LCardAdcInputMode.DIFFERENTIAL,)

    def _adc_channel_spec(
        self, channel: int, input_mode: LCardAdcInputMode
    ) -> int:
        input_mode = LCardAdcInputMode(input_mode)
        if input_mode not in self.ADC_INPUT_MODES:
            raise ValueError(
                f"{self.board.name} does not support {input_mode.name.lower()} ADC input"
            )
        return _uint32(channel, "channel") | input_mode.value

    async def adc_sample(
        self,
        channel: int,
        *,
        input_mode: LCardAdcInputMode = LCardAdcInputMode.DIFFERENTIAL,
        timeout: int = 0,
    ) -> int:
        result = await self._io_async(
            LCardAsyncOperation.ADC_INPUT,
            channel_count=1,
            channels=[self._adc_channel_spec(channel, input_mode)],
            timeout=timeout,
        )
        return result.data[0]

    async def adc_voltage(
        self,
        channel: int,
        *,
        input_mode: LCardAdcInputMode = LCardAdcInputMode.DIFFERENTIAL,
        input_range: float = 10.0,
        timeout: int = 0,
    ) -> float:
        return _signed_adc_voltage(
            await self.adc_sample(
                channel, input_mode=input_mode, timeout=timeout
            ),
            input_range,
        )


class _AsyncSingleDacBackend(AsyncLCardBackend):
    async def write_dac(
        self, channel: int, value: int, *, timeout: int = 0
    ) -> None:
        if not 0 <= channel <= 1:
            raise ValueError("channel must be 0 or 1")
        if not 0 <= value <= 0xFFF:
            raise ValueError("value must be between 0 and 4095")
        await self._io_async(
            LCardAsyncOperation.DAC_OUTPUT,
            channel_count=1,
            data=[value],
            mode=channel,
            timeout=timeout,
        )


class AsyncL780Backend(_AsyncSingleDacBackend, _AsyncSingleAdcBackend):
    BOARD_TYPES = (
        LCardBoardType.PCI_A,
        LCardBoardType.PCI_B,
        LCardBoardType.PCI_C,
    )

    async def configure_ttl(self, mode: int, *, timeout: int = 0) -> None:
        if self.board != LCardBoardType.PCI_C:
            raise RuntimeError("TTL configuration is supported only by PCI_C")
        await super().configure_ttl(mode, timeout=timeout)


class AsyncL791Backend(_AsyncSingleAdcBackend):
    BOARD_TYPES = (LCardBoardType.L791,)

    async def write_dac_pair(
        self, channel_a: int, value_a: int, channel_b: int, value_b: int,
        *, timeout: int = 0
    ) -> None:
        if any(not 0 <= channel <= 3 for channel in (channel_a, channel_b)):
            raise ValueError("L791 DAC channels must be between 0 and 3")
        if any(not 0 <= value <= 0xFFF for value in (value_a, value_b)):
            raise ValueError("L791 DAC values must be between 0 and 4095")
        await self._io_async(
            LCardAsyncOperation.DAC_OUTPUT,
            channel_count=2,
            channels=[channel_a, channel_b],
            data=[value_a, value_b],
            timeout=timeout,
        )


class AsyncE440Backend(_AsyncSingleDacBackend, _AsyncSingleAdcBackend):
    BOARD_TYPES = (LCardBoardType.E440,)
    ADC_INPUT_MODES = (
        LCardAdcInputMode.DIFFERENTIAL,
        LCardAdcInputMode.ZERO,
        LCardAdcInputMode.SINGLE_ENDED,
    )


class AsyncE140Backend(_AsyncSingleDacBackend, _AsyncSingleAdcBackend):
    BOARD_TYPES = (LCardBoardType.E140,)
    ADC_INPUT_MODES = (
        LCardAdcInputMode.DIFFERENTIAL,
        LCardAdcInputMode.ZERO,
        LCardAdcInputMode.SINGLE_ENDED,
    )

    async def write_dac_pair(
        self, value_a: int, value_b: int, *, timeout: int = 0
    ) -> None:
        if any(not 0 <= value <= 0xFFFF for value in (value_a, value_b)):
            raise ValueError("E140 dual DAC values must fit uint16")
        await self._io_async(
            LCardAsyncOperation.DAC_OUTPUT,
            channel_count=1,
            data=[value_a, value_b],
            mode=2,
            timeout=timeout,
        )


class AsyncE154Backend(_AsyncSingleAdcBackend):
    BOARD_TYPES = (LCardBoardType.E154,)

    async def write_dac(self, value: int, *, timeout: int = 0) -> None:
        if not 0 <= value <= 0xFF:
            raise ValueError("E154 DAC value must be between 0 and 255")
        await self._io_async(
            LCardAsyncOperation.DAC_OUTPUT,
            channel_count=1,
            data=[value],
            timeout=timeout,
        )


class AsyncE2010Backend(_AsyncSingleDacBackend, _AsyncTtlBackend):
    BOARD_TYPES = (LCardBoardType.E2010, LCardBoardType.E2010B)


class AsyncE310Backend(_AsyncTtlBackend):
    BOARD_TYPES = (LCardBoardType.E310,)
    ADC_INPUT_RANGE = 3.3
    ADC_RESOLUTION = 4096

    async def configure_adc(
        self, channel_mask: int, *, external_start: bool = False,
        timeout: int = 0
    ) -> None:
        if channel_mask & ~0xF0 or channel_mask == 0:
            raise ValueError("E310 channel_mask must select bits 0x10..0x80")
        await self._io_async(
            LCardAsyncOperation.ADC_CONFIG,
            channel_count=channel_mask,
            mode=0x10000 if external_start else 0,
            timeout=timeout,
        )

    async def read_adc(self, *, timeout: int = 0) -> tuple[int, int, int, int]:
        result = await self._io_async(
            LCardAsyncOperation.ADC_INPUT,
            channel_count=4,
            timeout=timeout,
        )
        if len(result.data) != 4:
            raise RuntimeError("E310 ADC input did not return four channels")
        return result.data[0], result.data[1], result.data[2], result.data[3]

    async def read_adc_voltage(
        self,
        *,
        input_range: float = ADC_INPUT_RANGE,
        resolution: int = ADC_RESOLUTION,
        timeout: int = 0,
    ) -> tuple[float, float, float, float]:
        return tuple(
            _unsigned_adc_voltage(code, input_range, resolution)
            for code in await self.read_adc(timeout=timeout)
        )

    async def configure_ttl(
        self, line_mask: int, *, extended_lines: bool = False,
        timeout: int = 0
    ) -> None:
        maximum = 0x7FF if extended_lines else 0xFF
        if not 0 <= line_mask <= maximum:
            raise ValueError(f"E310 line_mask must be between 0 and {maximum}")
        await self._io_async(
            LCardAsyncOperation.TTL_CONFIG,
            channel_count=line_mask,
            mode=1 if extended_lines else 0,
            timeout=timeout,
        )


_ASYNC_BACKEND_TYPES: dict[LCardBoardType, type[AsyncLCardBackend]] = {}
for _backend_type in (
    AsyncL780Backend,
    AsyncL791Backend,
    AsyncE440Backend,
    AsyncE140Backend,
    AsyncE154Backend,
    AsyncE2010Backend,
    AsyncE310Backend,
):
    for _board_type in _backend_type.BOARD_TYPES:
        _ASYNC_BACKEND_TYPES[_board_type] = _backend_type
