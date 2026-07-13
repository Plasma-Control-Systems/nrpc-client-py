from __future__ import annotations

import math
from dataclasses import dataclass
from enum import IntEnum, IntFlag
from typing import TYPE_CHECKING, Iterable, Sequence

from .client import DataType, TypedValue

if TYPE_CHECKING:
    from .client import NrpcClient

LCARD_OPEN = 80
LCARD_READ_ADC = 81
LCARD_READ_ADC_FRAME = 82
LCARD_WRITE_DAC = 83
LCARD_WRITE_DAC_FRAMES = 84
LCARD_CLOSE = 85

MAX_ADC_CHANNELS = 128
MAX_DAC_FRAMES = 262144


class LcardCapability(IntFlag):
    READ_ADC = 1 << 0
    READ_ADC_FRAME = 1 << 1
    WRITE_DAC = 1 << 2
    WRITE_DAC_FRAMES = 1 << 3


class LcardAdcInputMode(IntEnum):
    DIFFERENTIAL = 0
    COMMON_GROUND = 1
    ZERO = 2


@dataclass(frozen=True)
class LcardAdcChannel:
    """Portable ADC selector or an advanced vendor logical channel code."""

    channel: int
    range: float = 10.0
    mode: LcardAdcInputMode = LcardAdcInputMode.DIFFERENTIAL
    is_raw: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.channel, int) or isinstance(self.channel, bool) or not 0 <= self.channel <= 0xFFFFFFFF:
            raise ValueError("channel must be a uint32 integer")
        if not self.is_raw and (not math.isfinite(float(self.range)) or float(self.range) <= 0):
            raise ValueError("range must be a positive finite full-scale value")
        try:
            mode = LcardAdcInputMode(self.mode)
        except ValueError as error:
            raise ValueError("invalid ADC input mode") from error
        object.__setattr__(self, "range", float(self.range))
        object.__setattr__(self, "mode", mode)

    @classmethod
    def raw(cls, logical_code: int) -> LcardAdcChannel:
        return cls(logical_code, range=1.0, is_raw=True)


@dataclass(frozen=True)
class LcardDeviceInfo:
    board_type: int
    board_name: str
    revision: int
    dac_present: bool
    capabilities: LcardCapability

    def supports(self, capability: LcardCapability) -> bool:
        return bool(self.capabilities & capability)


@dataclass(frozen=True)
class LcardAdcFrame:
    codes: list[int]
    actual_rate_khz: float


@dataclass(frozen=True)
class LcardDacWriteResult:
    frames_written: int
    actual_rate_khz: float


def _channels(values: Sequence[LcardAdcChannel] | Iterable[LcardAdcChannel]) -> tuple[list[LcardAdcChannel], list[TypedValue]]:
    channels = list(values)
    if not 1 <= len(channels) <= MAX_ADC_CHANNELS or not all(isinstance(value, LcardAdcChannel) for value in channels):
        raise ValueError(f"channels must contain 1 to {MAX_ADC_CHANNELS} LcardAdcChannel values")
    return channels, [
        TypedValue(DataType.BOOL, [value.is_raw for value in channels]),
        TypedValue(DataType.UINT32, [value.channel for value in channels]),
        TypedValue(DataType.FLOAT64, [value.range for value in channels]),
        TypedValue(DataType.UINT8, [value.mode.value for value in channels]),
    ]


def _rate(value: float, name: str) -> float:
    result = float(value)
    if not math.isfinite(result) or result <= 0:
        raise ValueError(f"{name} must be positive and finite")
    return result


def _codes(values: Iterable[int], name: str) -> list[int]:
    result = list(values)
    if not 1 <= len(result) <= MAX_DAC_FRAMES:
        raise ValueError(f"{name} must contain 1 to {MAX_DAC_FRAMES} codes")
    if any(not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= 0xFFFF for value in result):
        raise ValueError(f"{name} values must be uint16 integers")
    return result


class LcardDevice:
    """Client proxy owning one server-side LCard device."""

    def __init__(self, client: NrpcClient, handle: int, info: LcardDeviceInfo):
        self._client = client
        self._handle = handle
        self._info = info
        self._closed = False

    @classmethod
    def open(cls, client: NrpcClient, slot: int, firmware_path: str | None = None,
             *, timeout: int = 5000) -> LcardDevice:
        if not isinstance(slot, int) or isinstance(slot, bool) or not 0 <= slot <= 0xFFFFFFFF:
            raise ValueError("slot must be a uint32 integer")
        if firmware_path is not None and not isinstance(firmware_path, str):
            raise ValueError("firmware_path must be a string or None")
        values = client.call(LCARD_OPEN, [
            TypedValue(DataType.UINT32, slot), firmware_path or "",
        ], timeout=timeout)
        if (len(values) != 6 or not isinstance(values[0], int) or isinstance(values[0], bool)
                or not isinstance(values[1], int) or not isinstance(values[2], str)
                or not isinstance(values[3], int) or not isinstance(values[4], bool)
                or not isinstance(values[5], int)):
            raise RuntimeError("LCard open returned invalid device metadata")
        info = LcardDeviceInfo(values[1], values[2], values[3], values[4], LcardCapability(values[5]))
        return cls(client, values[0], info)

    @property
    def handle(self) -> int:
        return self._handle

    @property
    def info(self) -> LcardDeviceInfo:
        return self._info

    def read_adc(self, channel: LcardAdcChannel, *, timeout: int = 5000) -> int:
        self._ensure_open()
        _, arguments = _channels([channel])
        values = self._client.call(LCARD_READ_ADC, [
            TypedValue(DataType.UINT64, self._handle), *arguments,
        ], timeout=timeout)
        if len(values) != 1 or not isinstance(values[0], int) or isinstance(values[0], bool):
            raise RuntimeError("LCard ADC read returned invalid data")
        return values[0]

    def read_adc_frame(self, channels: Sequence[LcardAdcChannel] | Iterable[LcardAdcChannel],
                       rate_khz: float = 100.0, *, timeout: int = 5000) -> LcardAdcFrame:
        self._ensure_open()
        requested, arguments = _channels(channels)
        values = self._client.call(LCARD_READ_ADC_FRAME, [
            TypedValue(DataType.UINT64, self._handle), *arguments,
            TypedValue(DataType.FLOAT64, _rate(rate_khz, "rate_khz")),
        ], timeout=timeout)
        if (len(values) != 2 or not isinstance(values[0], list)
                or len(values[0]) != len(requested)
                or any(not isinstance(code, int) or isinstance(code, bool) for code in values[0])
                or not isinstance(values[1], float)):
            raise RuntimeError("LCard ADC frame returned invalid data")
        return LcardAdcFrame(values[0], values[1])

    def write_dac(self, channel: int, code: int, *, timeout: int = 5000) -> None:
        self._ensure_open()
        if not isinstance(channel, int) or isinstance(channel, bool) or not 0 <= channel <= 1:
            raise ValueError("DAC channel must be 0 or 1")
        if not isinstance(code, int) or isinstance(code, bool) or not 0 <= code <= 0xFFFF:
            raise ValueError("DAC code must be a uint16 integer")
        values = self._client.call(LCARD_WRITE_DAC, [
            TypedValue(DataType.UINT64, self._handle),
            TypedValue(DataType.UINT8, channel),
            TypedValue(DataType.UINT16, code),
        ], timeout=timeout)
        if values:
            raise RuntimeError("LCard DAC write returned invalid data")

    def write_dac_frames(self, dac0: Iterable[int], dac1: Iterable[int],
                         frame_rate_khz: float, *, timeout: int = 5000) -> LcardDacWriteResult:
        self._ensure_open()
        values0, values1 = _codes(dac0, "dac0"), _codes(dac1, "dac1")
        if len(values0) != len(values1):
            raise ValueError("dac0 and dac1 must have equal lengths")
        values = self._client.call(LCARD_WRITE_DAC_FRAMES, [
            TypedValue(DataType.UINT64, self._handle),
            TypedValue(DataType.UINT16, values0),
            TypedValue(DataType.UINT16, values1),
            TypedValue(DataType.FLOAT64, _rate(frame_rate_khz, "frame_rate_khz")),
        ], timeout=timeout)
        if (len(values) != 2 or not isinstance(values[0], int) or isinstance(values[0], bool)
                or not isinstance(values[1], float)):
            raise RuntimeError("LCard DAC frame write returned invalid data")
        return LcardDacWriteResult(values[0], values[1])

    def close(self, *, timeout: int = 5000) -> None:
        if self._closed:
            return
        values = self._client.call(LCARD_CLOSE, [TypedValue(DataType.UINT64, self._handle)], timeout=timeout)
        if values:
            raise RuntimeError("LCard close returned invalid data")
        self._closed = True

    def _ensure_open(self) -> None:
        if self._closed:
            raise RuntimeError("LCard device is closed")

    def __enter__(self) -> LcardDevice:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
