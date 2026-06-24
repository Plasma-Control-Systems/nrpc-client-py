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
    _scaled_signed_adc_voltage,
    _uint32,
    _uint32_values,
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


class _AsyncSingleAdcBackend(AsyncLCardBackend):
    ADC_INPUT_MODES = (LCardAdcInputMode.DIFFERENTIAL,)
    ADC_INPUT_MODE_LIMITS: dict[LCardAdcInputMode, int] | None = None
    ADC_INPUT_RANGES = (10.0,)
    ADC_RANGE_SHIFT = 6
    ADC_RESOLUTION_BITS = 16
    ADC_VOLTAGE_DIVISOR = 0x8000

    def _adc_channel_spec(
        self,
        channel: int,
        input_mode: LCardAdcInputMode,
        input_range: float | None = None,
    ) -> int:
        input_mode = LCardAdcInputMode(input_mode)
        if input_mode not in self.ADC_INPUT_MODES:
            raise ValueError(
                f"{self.board.name} does not support {input_mode.name.lower()} ADC input"
            )
        if self.ADC_INPUT_MODE_LIMITS is not None:
            maximum = self.ADC_INPUT_MODE_LIMITS[input_mode]
            if not 0 <= channel <= maximum:
                raise ValueError(
                    f"{self.board.name} {input_mode.name.lower()} ADC channel "
                    f"must be between 0 and {maximum}"
                )
        return (
            _uint32(channel, "channel")
            | input_mode.value
            | self._adc_range_bits(input_range)
        )

    def _adc_range_bits(self, input_range: float | None) -> int:
        if input_range is None:
            return 0
        try:
            index = self.ADC_INPUT_RANGES.index(float(input_range))
        except ValueError as exc:
            allowed = ", ".join(str(value) for value in self.ADC_INPUT_RANGES)
            raise ValueError(
                f"{self.board.name} input_range must be one of: {allowed}"
            ) from exc
        return index << self.ADC_RANGE_SHIFT

    def _adc_input_range(self, input_range: float | None) -> float:
        if input_range is None:
            return self.ADC_INPUT_RANGES[0]
        self._adc_range_bits(input_range)
        return float(input_range)

    def _adc_mode(
        self, channel: int, input_mode: LCardAdcInputMode
    ) -> int:
        _ = channel, input_mode
        return 0

    async def adc_sample(
        self,
        channel: int,
        *,
        input_mode: LCardAdcInputMode = LCardAdcInputMode.DIFFERENTIAL,
        input_range: float | None = None,
        rate: float = 0.0,
        timeout: int = 0,
    ) -> int:
        channel_spec = self._adc_channel_spec(channel, input_mode, input_range)
        result = await self._io_async(
            LCardAsyncOperation.ADC_INPUT,
            channel_count=1,
            channels=[channel_spec],
            rate=rate,
            mode=self._adc_mode(channel_spec, input_mode),
            timeout=timeout,
        )
        return result.data[0]

    async def adc_voltage(
        self,
        channel: int,
        *,
        input_mode: LCardAdcInputMode = LCardAdcInputMode.DIFFERENTIAL,
        input_range: float | None = None,
        rate: float = 0.0,
        timeout: int = 0,
    ) -> float:
        return _scaled_signed_adc_voltage(
            await self.adc_sample(
                channel,
                input_mode=input_mode,
                input_range=input_range,
                rate=rate,
                timeout=timeout,
            ),
            self._adc_input_range(input_range),
            self.ADC_RESOLUTION_BITS,
            self.ADC_VOLTAGE_DIVISOR,
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


class AsyncL791Backend(_AsyncSingleAdcBackend):
    BOARD_TYPES = (LCardBoardType.L791,)
    ADC_INPUT_RANGES = (10.0, 5.0, 2.5, 1.25, 0.625, 0.312, 0.156, 0.078)
    ADC_RESOLUTION_BITS = 14
    ADC_VOLTAGE_DIVISOR = 8192.0

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
    ADC_INPUT_MODE_LIMITS = {
        LCardAdcInputMode.DIFFERENTIAL: 15,
        LCardAdcInputMode.ZERO: 15,
        LCardAdcInputMode.SINGLE_ENDED: 15,
    }
    ADC_INPUT_RANGES = (10.0, 2.5, 0.625, 0.15625)
    ADC_RESOLUTION_BITS = 14
    ADC_VOLTAGE_DIVISOR = 8000.0


class AsyncE140Backend(_AsyncSingleDacBackend, _AsyncSingleAdcBackend):
    BOARD_TYPES = (LCardBoardType.E140,)
    ADC_INPUT_MODES = (
        LCardAdcInputMode.DIFFERENTIAL,
        LCardAdcInputMode.ZERO,
        LCardAdcInputMode.SINGLE_ENDED,
    )
    ADC_INPUT_MODE_LIMITS = {
        LCardAdcInputMode.DIFFERENTIAL: 15,
        LCardAdcInputMode.ZERO: 31,
        LCardAdcInputMode.SINGLE_ENDED: 31,
    }
    ADC_INPUT_RANGES = (10.0, 2.5, 0.625, 0.15625)
    ADC_RESOLUTION_BITS = 14
    ADC_VOLTAGE_DIVISOR = 8000.0

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
    ADC_INPUT_RANGES = (5.0, 1.6, 0.5, 0.16)
    ADC_RESOLUTION_BITS = 12
    ADC_VOLTAGE_DIVISOR = 2000.0

    async def write_dac(self, value: int, *, timeout: int = 0) -> None:
        if not 0 <= value <= 0xFF:
            raise ValueError("E154 DAC value must be between 0 and 255")
        await self._io_async(
            LCardAsyncOperation.DAC_OUTPUT,
            channel_count=1,
            data=[value],
            timeout=timeout,
        )


class _AsyncE2010AdcBackend(_AsyncSingleAdcBackend):
    ADC_INPUT_MASK_SIGNAL_0_3V = 0x0400
    ADC_INPUT_MASK_SIGNAL_1_3V = 0x0200
    ADC_INPUT_MASK_SIGNAL_2_3V = 0x1000
    ADC_INPUT_MASK_SIGNAL_3_3V = 0x0800
    _ADC_SIGNAL_BITS = (
        ADC_INPUT_MASK_SIGNAL_0_3V,
        ADC_INPUT_MASK_SIGNAL_1_3V,
        ADC_INPUT_MASK_SIGNAL_2_3V,
        ADC_INPUT_MASK_SIGNAL_3_3V,
    )
    _ADC_RANGE_BITS = (
        (0x0008, 0x0010),
        (0x0002, 0x0004),
        (0x8000, 0x0100),
        (0x2000, 0x4000),
    )
    _ADC_RANGE_VALUES = (3.0, 1.0, 0.3)
    _ADC_KNOWN_MASK = (
        ADC_INPUT_MASK_SIGNAL_0_3V
        | ADC_INPUT_MASK_SIGNAL_1_3V
        | ADC_INPUT_MASK_SIGNAL_2_3V
        | ADC_INPUT_MASK_SIGNAL_3_3V
        | 0x0008
        | 0x0010
        | 0x0002
        | 0x0004
        | 0x8000
        | 0x0100
        | 0x2000
        | 0x4000
    )

    def _adc_channel_spec(
        self, channel: int, input_mode: LCardAdcInputMode
    ) -> int:
        if input_mode != LCardAdcInputMode.DIFFERENTIAL:
            raise ValueError("E2010 ADC input mode is configured by adc_input_mask")
        if not 0 <= channel <= 3:
            raise ValueError("channel must be between 0 and 3")
        return channel

    @classmethod
    def _adc_input_range_from_mask(cls, channel: int, adc_input_mask: int) -> float:
        one_volt_bit, point_three_volt_bit = cls._ADC_RANGE_BITS[channel]
        if adc_input_mask & point_three_volt_bit:
            return cls._ADC_RANGE_VALUES[2]
        if adc_input_mask & one_volt_bit:
            return cls._ADC_RANGE_VALUES[1]
        return cls._ADC_RANGE_VALUES[0]

    @classmethod
    def _validate_adc_input_mask(cls, channel: int, adc_input_mask: int) -> int:
        adc_input_mask = _uint32(adc_input_mask, "adc_input_mask")
        if adc_input_mask & ~cls._ADC_KNOWN_MASK:
            raise ValueError("adc_input_mask contains unsupported E2010 bits")
        if (adc_input_mask & cls._ADC_SIGNAL_BITS[channel]) == 0:
            raise ValueError(
                "adc_input_mask must enable the selected E2010 ADC channel"
            )
        for index, range_bits in enumerate(cls._ADC_RANGE_BITS):
            if sum(1 for bit in range_bits if adc_input_mask & bit) > 1:
                raise ValueError(
                    f"adc_input_mask selects more than one range for channel {index}"
                )
        return adc_input_mask

    async def adc_sample(
        self,
        channel: int,
        *,
        input_mode: LCardAdcInputMode = LCardAdcInputMode.DIFFERENTIAL,
        adc_input_mask: int | None = None,
        rate: float = 0.0,
        timeout: int = 0,
    ) -> int:
        channel_spec = self._adc_channel_spec(channel, input_mode)
        if adc_input_mask is None:
            adc_input_mask = self._ADC_SIGNAL_BITS[channel_spec]
        result = await self._io_async(
            LCardAsyncOperation.ADC_INPUT,
            channel_count=1,
            channels=[channel_spec],
            rate=rate,
            mode=self._validate_adc_input_mask(channel_spec, adc_input_mask),
            timeout=timeout,
        )
        return result.data[0]

    async def adc_voltage(
        self,
        channel: int,
        *,
        input_mode: LCardAdcInputMode = LCardAdcInputMode.DIFFERENTIAL,
        adc_input_mask: int | None = None,
        input_range: float | None = None,
        rate: float = 0.0,
        timeout: int = 0,
    ) -> float:
        channel_spec = self._adc_channel_spec(channel, input_mode)
        if adc_input_mask is None:
            adc_input_mask = self._ADC_SIGNAL_BITS[channel_spec]
        adc_input_mask = self._validate_adc_input_mask(
            channel_spec, adc_input_mask
        )
        if input_range is None:
            input_range = self._adc_input_range_from_mask(
                channel_spec, adc_input_mask
            )
        return _scaled_signed_adc_voltage(
            await self.adc_sample(
                channel,
                input_mode=input_mode,
                adc_input_mask=adc_input_mask,
                rate=rate,
                timeout=timeout,
            ),
            input_range,
            14,
            8000.0,
        )


class AsyncE2010Backend(_AsyncSingleDacBackend, _AsyncE2010AdcBackend):
    BOARD_TYPES = (LCardBoardType.E2010, LCardBoardType.E2010B)


class AsyncE310Backend(AsyncLCardBackend):
    BOARD_TYPES = (LCardBoardType.E310,)


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
