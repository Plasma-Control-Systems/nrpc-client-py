from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import TYPE_CHECKING, Iterable

from .client import DataType, TypedValue

if TYPE_CHECKING:
    from .client import NrpcClient

LCARD_OPEN = 48
LCARD_IO_ASYNC = 49
LCARD_SLOT_INFO = 50
LCARD_LOAD_BIOS = 51
LCARD_CLOSE = 52
LCARD_ADC_FRAME = 53


class LCardBoardType(IntEnum):
    """Native LCard board types reported by ``GetSlotParam``."""

    PCI_A = 5
    PCI_B = 6
    PCI_C = 14
    L791 = 19
    E440 = 30
    E140 = 31
    E2010 = 32
    E154 = 38
    E2010B = 39
    E310 = 77


class _LCardIoOperation(IntEnum):
    ADC_CONFIG = 3
    TTL_CONFIG = 4
    DAC_CONFIG = 5
    ADC_INPUT = 6
    TTL_INPUT = 7
    TTL_OUTPUT = 8
    DAC_OUTPUT = 9
    FREQUENCY_INPUT = 10


class LCardAdcInputMode(IntEnum):
    """ADC input channel mode bits used by E140/E440 channel specs."""

    DIFFERENTIAL = 0
    ZERO = 16
    SINGLE_ENDED = 32


@dataclass(frozen=True)
class LCardSlotInfo:
    board_type: LCardBoardType
    dsp_type: int
    irq: int


@dataclass(frozen=True)
class _LCardIoResult:
    rate: float
    data: list[int]


@dataclass(frozen=True)
class LCardAdcFrame:
    rate: float
    channel_count: int
    samples_per_channel: int
    data: list[float]


def _positive_float(value: float, name: str) -> float:
    value = float(value)
    if value <= 0:
        raise ValueError(f"{name} must be positive")
    return value


def _signed_adc_voltage(code: int, input_range: float) -> float:
    return _scaled_signed_adc_voltage(code, input_range, 16, 0x8000)


def _scaled_signed_adc_voltage(
    code: int, input_range: float, bits: int, divisor: float
) -> float:
    input_range = _positive_float(input_range, "input_range")
    mask = (1 << bits) - 1
    sign = 1 << (bits - 1)
    raw = code & mask
    if raw >= sign:
        raw -= 1 << bits
    return raw * input_range / divisor


def _uint32_values(values: Iterable[int], name: str) -> list[int]:
    result = list(values)
    if len(result) > 128:
        raise ValueError(f"{name} supports at most 128 values")
    if any(not 0 <= value <= 0xFFFFFFFF for value in result):
        raise ValueError(f"{name} values must be between 0 and 4294967295")
    return result


def _uint32(value: int, name: str) -> int:
    if not 0 <= value <= 0xFFFFFFFF:
        raise ValueError(f"{name} must be between 0 and 4294967295")
    return value


def _decode_uint32_values(value: object, operation: str) -> list[int]:
    if isinstance(value, int):
        return [value]
    if isinstance(value, list) and all(isinstance(item, int) for item in value):
        return value
    raise RuntimeError(f"LCard {operation} returned invalid uint32 data")


class LCardBackend:
    """Base proxy shared by all supported LCard board families."""

    BOARD_TYPES: tuple[LCardBoardType, ...] = ()

    def __init__(self, client: NrpcClient, handle: int, board: LCardBoardType):
        self._client = client
        self._handle = handle
        self._board = board
        self._closed = False

    @classmethod
    def open(
        cls,
        client: NrpcClient,
        board: LCardBoardType,
        slot: int = 0,
        *,
        bios: str = "",
        timeout: int = 5000,
    ) -> LCardBackend:
        """Open a board, letting the server auto-load BIOS when ``bios`` is empty."""

        board = LCardBoardType(board)
        _uint32(slot, "slot")
        backend_type = _BACKEND_TYPES[board]
        values = client.call(
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
        return backend_type(client, values[0], board)

    @property
    def handle(self) -> int:
        return self._handle

    @property
    def board(self) -> LCardBoardType:
        return self._board

    def slot_info(self, *, timeout: int = 0) -> LCardSlotInfo:
        self._ensure_open()
        values = self._client.call(
            LCARD_SLOT_INFO,
            [TypedValue(DataType.UINT64, self._handle)],
            timeout=timeout,
        )
        if len(values) != 1:
            raise RuntimeError("LCard slot info returned invalid data")
        data = _decode_uint32_values(values[0], "slot info")
        if len(data) != 3:
            raise RuntimeError("LCard slot info returned invalid data")
        board = LCardBoardType(data[0])
        if board != self._board:
            raise RuntimeError("LCard slot board type changed unexpectedly")
        return LCardSlotInfo(board, data[1], data[2])

    def load_bios(self, path: str, *, timeout: int = 0) -> None:
        self._ensure_open()
        if not path:
            raise ValueError("path must not be empty")
        self._client.call(
            LCARD_LOAD_BIOS,
            [TypedValue(DataType.UINT64, self._handle), path],
            timeout=timeout,
        )

    def _io(
        self,
        operation: _LCardIoOperation,
        *,
        channel_count: int = 0,
        channels: Iterable[int] = (),
        data: Iterable[int] = (),
        rate: float = 0.0,
        mode: int = 0,
        timeout: int = 0,
    ) -> _LCardIoResult:
        self._ensure_open()
        channels = _uint32_values(channels, "channels")
        data = _uint32_values(data, "data")
        _uint32(channel_count, "channel_count")
        _uint32(mode, "mode")
        values = self._client.call(
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
        return _LCardIoResult(
            values[0], _decode_uint32_values(values[1], "IoAsync")
        )

    def _adc_frame(
        self,
        *,
        channel_count: int,
        sample_rate: float,
        samples_per_channel: int,
        start_channel: int,
        end_channel: int,
        mode: int,
        auto_init: bool = True,
        timeout: int = 0,
    ) -> tuple[float, int, int, list[int]]:
        self._ensure_open()
        channel_count = _uint32(channel_count, "channel_count")
        samples_per_channel = _uint32(samples_per_channel, "samples_per_channel")
        start_channel = _uint32(start_channel, "start_channel")
        end_channel = _uint32(end_channel, "end_channel")
        mode = _uint32(mode, "mode")
        sample_rate = _positive_float(sample_rate, "sample_rate")
        values = self._client.call(
            LCARD_ADC_FRAME,
            [
                TypedValue(DataType.UINT64, self._handle),
                TypedValue(DataType.UINT32, channel_count),
                TypedValue(DataType.FLOAT64, sample_rate),
                TypedValue(DataType.UINT32, samples_per_channel),
                TypedValue(DataType.UINT32, start_channel),
                TypedValue(DataType.UINT32, end_channel),
                TypedValue(DataType.UINT32, mode),
                TypedValue(DataType.BOOL, bool(auto_init)),
            ],
            timeout=timeout,
        )
        if (
            len(values) != 4
            or not isinstance(values[0], float)
            or not isinstance(values[1], int)
            or not isinstance(values[2], int)
        ):
            raise RuntimeError("LCard ADC frame returned invalid data")
        data = _decode_uint32_values(values[3], "ADC frame")
        if len(data) != values[1] * values[2]:
            raise RuntimeError("LCard ADC frame returned invalid data")
        return values[0], values[1], values[2], data

    def close(self, *, timeout: int = 0) -> None:
        if self._closed:
            return
        self._client.call(
            LCARD_CLOSE,
            [TypedValue(DataType.UINT64, self._handle)],
            timeout=timeout,
        )
        self._closed = True

    def __enter__(self) -> LCardBackend:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _ensure_open(self) -> None:
        if self._closed:
            raise RuntimeError("LCard backend is closed")


class _SingleAdcBackend(LCardBackend):
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
        input_range = _positive_float(input_range, "input_range")
        try:
            index = self.ADC_INPUT_RANGES.index(input_range)
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
        return input_range

    def _adc_mode(
        self, channel: int, input_mode: LCardAdcInputMode
    ) -> int:
        _ = channel, input_mode
        return 0

    def adc_sample(
        self,
        channel: int,
        *,
        input_mode: LCardAdcInputMode = LCardAdcInputMode.DIFFERENTIAL,
        input_range: float | None = None,
        rate: float = 0.0,
        timeout: int = 0,
    ) -> int:
        channel_spec = self._adc_channel_spec(channel, input_mode, input_range)
        result = self._io(
            _LCardIoOperation.ADC_INPUT,
            channel_count=1,
            channels=[channel_spec],
            rate=rate,
            mode=self._adc_mode(channel_spec, input_mode),
            timeout=timeout,
        )
        return result.data[0]

    def adc_voltage(
        self,
        channel: int,
        *,
        input_mode: LCardAdcInputMode = LCardAdcInputMode.DIFFERENTIAL,
        input_range: float | None = None,
        rate: float = 0.0,
        timeout: int = 0,
    ) -> float:
        return _scaled_signed_adc_voltage(
            self.adc_sample(
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

    def adc_voltage_frame(
        self,
        *,
        channel_count: int,
        sample_rate: float,
        samples_per_channel: int,
        start_channel: int,
        end_channel: int,
        mode: LCardAdcInputMode = LCardAdcInputMode.DIFFERENTIAL,
        auto_init: bool = True,
        timeout: int = 0,
    ) -> LCardAdcFrame:
        if self.board not in (LCardBoardType.E140, LCardBoardType.E440):
            raise ValueError(
                f"{self.board.name} does not support ADC voltage frames"
            )
        channel_count = _uint32(channel_count, "channel_count")
        samples_per_channel = _uint32(samples_per_channel, "samples_per_channel")
        start_channel = _uint32(start_channel, "start_channel")
        end_channel = _uint32(end_channel, "end_channel")
        mode = LCardAdcInputMode(mode)
        if channel_count == 0 or samples_per_channel == 0:
            raise ValueError("ADC voltage frame requires channels and samples")
        if end_channel < start_channel:
            raise ValueError("end_channel must not be before start_channel")
        if channel_count != end_channel - start_channel + 1:
            raise ValueError(
                "channel_count must match start_channel and end_channel"
            )
        if channel_count * samples_per_channel > 131072:
            raise ValueError("ADC voltage frames support at most 131072 elements")
        for channel in range(start_channel, end_channel + 1):
            self._adc_channel_spec(channel, mode, None)
        rate, channels, samples, data = self._adc_frame(
            channel_count=channel_count,
            sample_rate=sample_rate,
            samples_per_channel=samples_per_channel,
            start_channel=start_channel,
            end_channel=end_channel,
            mode=mode.value,
            auto_init=auto_init,
            timeout=timeout,
        )
        input_range = self._adc_input_range(None)
        volts = [
            _scaled_signed_adc_voltage(
                value,
                input_range,
                self.ADC_RESOLUTION_BITS,
                self.ADC_VOLTAGE_DIVISOR,
            )
            for value in data
        ]
        return LCardAdcFrame(rate, channels, samples, volts)


class _SingleDacBackend(LCardBackend):
    DAC_MAX = 0xFFF
    DAC_CHANNELS = 2

    def write_dac(
        self, channel: int, value: int, *, timeout: int = 0
    ) -> None:
        if not 0 <= channel < self.DAC_CHANNELS:
            raise ValueError(
                f"channel must be between 0 and {self.DAC_CHANNELS - 1}"
            )
        if not 0 <= value <= self.DAC_MAX:
            raise ValueError(f"value must be between 0 and {self.DAC_MAX}")
        self._io(
            _LCardIoOperation.DAC_OUTPUT,
            channel_count=1,
            data=[value],
            mode=channel,
            timeout=timeout,
        )


class L780Backend(_SingleDacBackend, _SingleAdcBackend):
    BOARD_TYPES = (
        LCardBoardType.PCI_A,
        LCardBoardType.PCI_B,
        LCardBoardType.PCI_C,
    )


class L791Backend(_SingleAdcBackend):
    BOARD_TYPES = (LCardBoardType.L791,)
    ADC_INPUT_RANGES = (10.0, 5.0, 2.5, 1.25, 0.625, 0.312, 0.156, 0.078)
    ADC_RESOLUTION_BITS = 14
    ADC_VOLTAGE_DIVISOR = 8192.0

    def write_dac_pair(
        self,
        channel_a: int,
        value_a: int,
        channel_b: int,
        value_b: int,
        *,
        timeout: int = 0,
    ) -> None:
        for channel in (channel_a, channel_b):
            if not 0 <= channel <= 3:
                raise ValueError("L791 DAC channels must be between 0 and 3")
        for value in (value_a, value_b):
            if not 0 <= value <= 0xFFF:
                raise ValueError("L791 DAC values must be between 0 and 4095")
        self._io(
            _LCardIoOperation.DAC_OUTPUT,
            channel_count=2,
            channels=[channel_a, channel_b],
            data=[value_a, value_b],
            timeout=timeout,
        )


class E440Backend(_SingleDacBackend, _SingleAdcBackend):
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


class E140Backend(_SingleDacBackend, _SingleAdcBackend):
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

    def write_dac_pair(
        self, value_a: int, value_b: int, *, timeout: int = 0
    ) -> None:
        for value in (value_a, value_b):
            if not 0 <= value <= 0xFFFF:
                raise ValueError("E140 dual DAC values must fit uint16")
        self._io(
            _LCardIoOperation.DAC_OUTPUT,
            channel_count=1,
            data=[value_a, value_b],
            mode=2,
            timeout=timeout,
        )


class E154Backend(_SingleAdcBackend):
    BOARD_TYPES = (LCardBoardType.E154,)
    ADC_INPUT_RANGES = (5.0, 1.6, 0.5, 0.16)
    ADC_RESOLUTION_BITS = 12
    ADC_VOLTAGE_DIVISOR = 2000.0

    def write_dac(self, value: int, *, timeout: int = 0) -> None:
        if not 0 <= value <= 0xFF:
            raise ValueError("E154 DAC value must be between 0 and 255")
        self._io(
            _LCardIoOperation.DAC_OUTPUT,
            channel_count=1,
            data=[value],
            timeout=timeout,
        )


class _E2010AdcBackend(_SingleAdcBackend):
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

    def _adc_mode(
        self, channel: int, input_mode: LCardAdcInputMode
    ) -> int:
        _ = channel, input_mode
        return self._ADC_SIGNAL_BITS[channel]

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

    def adc_sample(
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
            adc_input_mask = self._adc_mode(channel_spec, input_mode)
        result = self._io(
            _LCardIoOperation.ADC_INPUT,
            channel_count=1,
            channels=[channel_spec],
            rate=rate,
            mode=self._validate_adc_input_mask(channel_spec, adc_input_mask),
            timeout=timeout,
        )
        return result.data[0]

    def adc_voltage(
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
            adc_input_mask = self._adc_mode(channel_spec, input_mode)
        adc_input_mask = self._validate_adc_input_mask(
            channel_spec, adc_input_mask
        )
        if input_range is None:
            input_range = self._adc_input_range_from_mask(
                channel_spec, adc_input_mask
            )
        return _scaled_signed_adc_voltage(
            self.adc_sample(
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

    def adc_voltage_frame(
        self,
        *,
        channel_count: int,
        sample_rate: float,
        samples_per_channel: int,
        start_channel: int,
        end_channel: int,
        mode: int | None = None,
        auto_init: bool = True,
        timeout: int = 0,
    ) -> LCardAdcFrame:
        channel_count = _uint32(channel_count, "channel_count")
        samples_per_channel = _uint32(samples_per_channel, "samples_per_channel")
        start_channel = _uint32(start_channel, "start_channel")
        end_channel = _uint32(end_channel, "end_channel")
        if channel_count == 0 or samples_per_channel == 0:
            raise ValueError("ADC voltage frame requires channels and samples")
        if end_channel < start_channel:
            raise ValueError("end_channel must not be before start_channel")
        if channel_count != end_channel - start_channel + 1:
            raise ValueError(
                "channel_count must match start_channel and end_channel"
            )
        if channel_count * samples_per_channel > 131072:
            raise ValueError("ADC voltage frames support at most 131072 elements")
        for channel in range(start_channel, end_channel + 1):
            self._adc_channel_spec(channel, LCardAdcInputMode.DIFFERENTIAL)
        if mode is None:
            mode = 0
            for channel in range(start_channel, end_channel + 1):
                mode |= self._ADC_SIGNAL_BITS[channel]
        for channel in range(start_channel, end_channel + 1):
            self._validate_adc_input_mask(channel, mode)
        rate, channels, samples, data = self._adc_frame(
            channel_count=channel_count,
            sample_rate=sample_rate,
            samples_per_channel=samples_per_channel,
            start_channel=start_channel,
            end_channel=end_channel,
            mode=mode,
            auto_init=auto_init,
            timeout=timeout,
        )
        ranges = [
            self._adc_input_range_from_mask(channel, mode)
            for channel in range(start_channel, end_channel + 1)
        ]
        volts = [
            _scaled_signed_adc_voltage(value, ranges[index % channels], 14, 8000.0)
            for index, value in enumerate(data)
        ]
        return LCardAdcFrame(rate, channels, samples, volts)


class E2010Backend(_SingleDacBackend, _E2010AdcBackend):
    BOARD_TYPES = (LCardBoardType.E2010, LCardBoardType.E2010B)


class E310Backend(LCardBackend):
    BOARD_TYPES = (LCardBoardType.E310,)


_BACKEND_TYPES: dict[LCardBoardType, type[LCardBackend]] = {}
for _backend_type in (
    L780Backend,
    L791Backend,
    E440Backend,
    E140Backend,
    E154Backend,
    E2010Backend,
    E310Backend,
):
    for _board_type in _backend_type.BOARD_TYPES:
        _BACKEND_TYPES[_board_type] = _backend_type
