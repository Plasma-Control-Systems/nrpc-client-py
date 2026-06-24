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


class LCardAsyncOperation(IntEnum):
    ADC_CONFIG = 3
    TTL_CONFIG = 4
    DAC_CONFIG = 5
    ADC_INPUT = 6
    TTL_INPUT = 7
    TTL_OUTPUT = 8
    DAC_OUTPUT = 9
    FREQUENCY_INPUT = 10


@dataclass(frozen=True)
class LCardSlotInfo:
    board_type: LCardBoardType
    dsp_type: int
    irq: int


@dataclass(frozen=True)
class LCardAsyncResult:
    rate: float
    data: list[int]


def _positive_float(value: float, name: str) -> float:
    value = float(value)
    if value <= 0:
        raise ValueError(f"{name} must be positive")
    return value


def _signed_adc_voltage(code: int, input_range: float) -> float:
    input_range = _positive_float(input_range, "input_range")
    raw = code & 0xFFFF
    if raw >= 0x8000:
        raw -= 0x10000
    return raw * input_range / 0x8000


def _unsigned_adc_voltage(
    code: int, input_range: float, resolution: int
) -> float:
    input_range = _positive_float(input_range, "input_range")
    if resolution <= 1:
        raise ValueError("resolution must be greater than 1")
    return (code & 0xFFFFFFFF) * input_range / (resolution - 1)


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

    def _io_async(
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
        return LCardAsyncResult(
            values[0], _decode_uint32_values(values[1], "IoAsync")
        )

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


class _TtlBackend(LCardBackend):
    def configure_ttl(self, mode: int, *, timeout: int = 0) -> None:
        self._io_async(
            LCardAsyncOperation.TTL_CONFIG,
            mode=_uint32(mode, "mode"),
            timeout=timeout,
        )

    def read_ttl(self, *, timeout: int = 0) -> int:
        result = self._io_async(
            LCardAsyncOperation.TTL_INPUT,
            channel_count=1,
            timeout=timeout,
        )
        return result.data[0]

    def write_ttl(self, value: int, *, timeout: int = 0) -> None:
        self._io_async(
            LCardAsyncOperation.TTL_OUTPUT,
            channel_count=1,
            data=[_uint32(value, "value")],
            timeout=timeout,
        )


class _SingleAdcBackend(_TtlBackend):
    def adc_sample(self, channel: int, *, timeout: int = 0) -> int:
        result = self._io_async(
            LCardAsyncOperation.ADC_INPUT,
            channel_count=1,
            channels=[_uint32(channel, "channel")],
            timeout=timeout,
        )
        return result.data[0]

    def adc_voltage(
        self,
        channel: int,
        *,
        input_range: float = 10.0,
        timeout: int = 0,
    ) -> float:
        return _signed_adc_voltage(
            self.adc_sample(channel, timeout=timeout), input_range
        )


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
        self._io_async(
            LCardAsyncOperation.DAC_OUTPUT,
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

    def configure_ttl(self, mode: int, *, timeout: int = 0) -> None:
        if self.board != LCardBoardType.PCI_C:
            raise RuntimeError("TTL configuration is supported only by PCI_C")
        super().configure_ttl(mode, timeout=timeout)


class L791Backend(_SingleAdcBackend):
    BOARD_TYPES = (LCardBoardType.L791,)

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
        self._io_async(
            LCardAsyncOperation.DAC_OUTPUT,
            channel_count=2,
            channels=[channel_a, channel_b],
            data=[value_a, value_b],
            timeout=timeout,
        )


class E440Backend(_SingleDacBackend, _SingleAdcBackend):
    BOARD_TYPES = (LCardBoardType.E440,)


class E140Backend(_SingleDacBackend, _SingleAdcBackend):
    BOARD_TYPES = (LCardBoardType.E140,)

    def write_dac_pair(
        self, value_a: int, value_b: int, *, timeout: int = 0
    ) -> None:
        for value in (value_a, value_b):
            if not 0 <= value <= 0xFFFF:
                raise ValueError("E140 dual DAC values must fit uint16")
        self._io_async(
            LCardAsyncOperation.DAC_OUTPUT,
            channel_count=1,
            data=[value_a, value_b],
            mode=2,
            timeout=timeout,
        )


class E154Backend(_SingleAdcBackend):
    BOARD_TYPES = (LCardBoardType.E154,)

    def write_dac(self, value: int, *, timeout: int = 0) -> None:
        if not 0 <= value <= 0xFF:
            raise ValueError("E154 DAC value must be between 0 and 255")
        self._io_async(
            LCardAsyncOperation.DAC_OUTPUT,
            channel_count=1,
            data=[value],
            timeout=timeout,
        )


class E2010Backend(_SingleDacBackend, _TtlBackend):
    BOARD_TYPES = (LCardBoardType.E2010, LCardBoardType.E2010B)


class E310Backend(_TtlBackend):
    BOARD_TYPES = (LCardBoardType.E310,)
    ADC_INPUT_RANGE = 3.3
    ADC_RESOLUTION = 4096

    def configure_adc(
        self, channel_mask: int, *, external_start: bool = False,
        timeout: int = 0
    ) -> None:
        if channel_mask & ~0xF0 or channel_mask == 0:
            raise ValueError("E310 channel_mask must select bits 0x10..0x80")
        self._io_async(
            LCardAsyncOperation.ADC_CONFIG,
            channel_count=channel_mask,
            mode=0x10000 if external_start else 0,
            timeout=timeout,
        )

    def read_adc(self, *, timeout: int = 0) -> tuple[int, int, int, int]:
        result = self._io_async(
            LCardAsyncOperation.ADC_INPUT,
            channel_count=4,
            timeout=timeout,
        )
        if len(result.data) != 4:
            raise RuntimeError("E310 ADC input did not return four channels")
        return result.data[0], result.data[1], result.data[2], result.data[3]

    def read_adc_voltage(
        self,
        *,
        input_range: float = ADC_INPUT_RANGE,
        resolution: int = ADC_RESOLUTION,
        timeout: int = 0,
    ) -> tuple[float, float, float, float]:
        return tuple(
            _unsigned_adc_voltage(code, input_range, resolution)
            for code in self.read_adc(timeout=timeout)
        )

    def configure_ttl(
        self,
        line_mask: int,
        *,
        extended_lines: bool = False,
        timeout: int = 0,
    ) -> None:
        maximum = 0x7FF if extended_lines else 0xFF
        if not 0 <= line_mask <= maximum:
            raise ValueError(f"E310 line_mask must be between 0 and {maximum}")
        self._io_async(
            LCardAsyncOperation.TTL_CONFIG,
            channel_count=line_mask,
            mode=1 if extended_lines else 0,
            timeout=timeout,
        )


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
