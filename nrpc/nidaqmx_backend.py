from __future__ import annotations

import math
from enum import IntEnum
from typing import TYPE_CHECKING, Iterable

from .client import DataType, TypedValue

if TYPE_CHECKING:
    from .client import NrpcClient

NIDAQMX_CREATE_AI_VOLTAGE = 64
NIDAQMX_CREATE_AI_THERMOCOUPLE = 65
NIDAQMX_CREATE_AO_VOLTAGE = 66
NIDAQMX_CREATE_DI = 67
NIDAQMX_CREATE_DO = 68
NIDAQMX_START = 69
NIDAQMX_READ_ANALOG = 70
NIDAQMX_WRITE_ANALOG = 71
NIDAQMX_READ_DIGITAL = 72
NIDAQMX_WRITE_DIGITAL = 73
NIDAQMX_CLOSE = 74

MAX_SAMPLES_PER_CALL = 1024 * 1024


class NidaqmxChannelType(IntEnum):
    ANALOG_INPUT = 0
    ANALOG_OUTPUT = 1
    DIGITAL_INPUT = 2
    DIGITAL_OUTPUT = 3


class NidaqmxTerminalConfig(IntEnum):
    DEFAULT = -1
    RSE = 10083
    NRSE = 10078
    DIFFERENTIAL = 10106
    PSEUDODIFFERENTIAL = 12529


class NidaqmxThermocoupleType(IntEnum):
    B = 10047
    E = 10055
    J = 10072
    K = 10073
    N = 10077
    R = 10082
    S = 10085
    T = 10086


class NidaqmxCjcSource(IntEnum):
    BUILT_IN = 10200
    CONSTANT_VALUE = 10116
    CHANNEL = 10113


def _channel(value: str, name: str = "physical_channel") -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{name} must not be empty")
    return value


def _range(minimum: float, maximum: float) -> tuple[float, float]:
    minimum, maximum = float(minimum), float(maximum)
    if not math.isfinite(minimum) or not math.isfinite(maximum) or minimum >= maximum:
        raise ValueError("minimum and maximum must be finite and minimum must be less than maximum")
    return minimum, maximum


def _count(value: int) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or not 1 <= value <= MAX_SAMPLES_PER_CALL:
        raise ValueError(f"sample_count must be between 1 and {MAX_SAMPLES_PER_CALL}")
    return value


def _values(value: object, kind: type, operation: str) -> list:
    if isinstance(value, kind) and not isinstance(value, bool):
        return [value]
    if isinstance(value, list) and all(isinstance(item, kind) and not isinstance(item, bool) for item in value):
        return value
    raise RuntimeError(f"NI-DAQmx {operation} returned invalid data")


def _write_values(values: Iterable, digital: bool) -> list:
    result = list(values)
    if not 1 <= len(result) <= MAX_SAMPLES_PER_CALL:
        raise ValueError(f"values must contain between 1 and {MAX_SAMPLES_PER_CALL} samples")
    if digital:
        if any(not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= 0xFFFFFFFF for value in result):
            raise ValueError("digital values must be uint32 integers")
    else:
        if any(isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)) for value in result):
            raise ValueError("analog values must be finite numbers")
        result = [float(value) for value in result]
    return result


def _grouping(value: bool) -> bool:
    if not isinstance(value, bool):
        raise ValueError("one_channel_for_all_lines must be a bool")
    return value


class NidaqmxTask:
    """Client proxy for one server-side NI-DAQmx task."""

    def __init__(self, client: NrpcClient, handle: int, channel_type: NidaqmxChannelType):
        self._client = client
        self._handle = handle
        self._channel_type = channel_type
        self._closed = False

    @classmethod
    def create_ai_voltage(cls, client: NrpcClient, physical_channel: str, minimum: float = -10.0,
                          maximum: float = 10.0, *, terminal: NidaqmxTerminalConfig = NidaqmxTerminalConfig.DEFAULT,
                          timeout: int = 5000) -> NidaqmxTask:
        minimum, maximum = _range(minimum, maximum)
        return cls._create(client, NIDAQMX_CREATE_AI_VOLTAGE, NidaqmxChannelType.ANALOG_INPUT,
                           [_channel(physical_channel), TypedValue(DataType.FLOAT64, minimum),
                            TypedValue(DataType.FLOAT64, maximum), TypedValue(DataType.INT32, NidaqmxTerminalConfig(terminal).value)], timeout)

    @classmethod
    def create_ai_thermocouple(cls, client: NrpcClient, physical_channel: str, minimum: float, maximum: float,
                               thermocouple_type: NidaqmxThermocoupleType, *,
                               cjc_source: NidaqmxCjcSource = NidaqmxCjcSource.BUILT_IN,
                               cjc_value: float = 25.0, cjc_channel: str = "", timeout: int = 5000) -> NidaqmxTask:
        minimum, maximum = _range(minimum, maximum)
        source = NidaqmxCjcSource(cjc_source)
        if source == NidaqmxCjcSource.CHANNEL:
            _channel(cjc_channel, "cjc_channel")
        if not math.isfinite(float(cjc_value)):
            raise ValueError("cjc_value must be finite")
        return cls._create(client, NIDAQMX_CREATE_AI_THERMOCOUPLE, NidaqmxChannelType.ANALOG_INPUT,
                           [_channel(physical_channel), TypedValue(DataType.FLOAT64, minimum), TypedValue(DataType.FLOAT64, maximum),
                            TypedValue(DataType.INT32, NidaqmxThermocoupleType(thermocouple_type).value),
                            TypedValue(DataType.INT32, source.value), TypedValue(DataType.FLOAT64, float(cjc_value)), cjc_channel], timeout)

    @classmethod
    def create_ao_voltage(cls, client: NrpcClient, physical_channel: str, minimum: float = -10.0,
                          maximum: float = 10.0, *, timeout: int = 5000) -> NidaqmxTask:
        minimum, maximum = _range(minimum, maximum)
        return cls._create(client, NIDAQMX_CREATE_AO_VOLTAGE, NidaqmxChannelType.ANALOG_OUTPUT,
                           [_channel(physical_channel), TypedValue(DataType.FLOAT64, minimum), TypedValue(DataType.FLOAT64, maximum)], timeout)

    @classmethod
    def create_digital_input(cls, client: NrpcClient, lines: str, *, one_channel_for_all_lines: bool = True,
                             timeout: int = 5000) -> NidaqmxTask:
        return cls._create(client, NIDAQMX_CREATE_DI, NidaqmxChannelType.DIGITAL_INPUT,
                           [_channel(lines, "lines"), _grouping(one_channel_for_all_lines)], timeout)

    @classmethod
    def create_digital_output(cls, client: NrpcClient, lines: str, *, one_channel_for_all_lines: bool = True,
                              timeout: int = 5000) -> NidaqmxTask:
        return cls._create(client, NIDAQMX_CREATE_DO, NidaqmxChannelType.DIGITAL_OUTPUT,
                           [_channel(lines, "lines"), _grouping(one_channel_for_all_lines)], timeout)

    @classmethod
    def _create(cls, client: NrpcClient, function: int, channel_type: NidaqmxChannelType,
                args: list, timeout: int) -> NidaqmxTask:
        values = client.call(function, args, timeout=timeout)
        if len(values) != 1 or not isinstance(values[0], int) or isinstance(values[0], bool):
            raise RuntimeError("NI-DAQmx task creation returned an invalid handle")
        return cls(client, values[0], channel_type)

    @property
    def handle(self) -> int:
        return self._handle

    @property
    def channel_type(self) -> NidaqmxChannelType:
        return self._channel_type

    def start(self, *, timeout: int = 0) -> None:
        self._call(NIDAQMX_START, timeout=timeout)

    def read(self, sample_count: int = 1, *, timeout: int = 0) -> list[float] | list[int]:
        if self._channel_type == NidaqmxChannelType.ANALOG_INPUT:
            return self.read_analog(sample_count, timeout=timeout)
        if self._channel_type == NidaqmxChannelType.DIGITAL_INPUT:
            return self.read_digital(sample_count, timeout=timeout)
        raise RuntimeError("NI-DAQmx output tasks cannot be read")

    def write(self, values: Iterable[float] | Iterable[int], *, timeout: int = 0) -> int:
        if self._channel_type == NidaqmxChannelType.ANALOG_OUTPUT:
            return self.write_analog(values, timeout=timeout)
        if self._channel_type == NidaqmxChannelType.DIGITAL_OUTPUT:
            return self.write_digital(values, timeout=timeout)
        raise RuntimeError("NI-DAQmx input tasks cannot be written")

    def read_analog(self, sample_count: int = 1, *, timeout: int = 0) -> list[float]:
        self._require(NidaqmxChannelType.ANALOG_INPUT)
        values = self._call(NIDAQMX_READ_ANALOG, TypedValue(DataType.UINT32, _count(sample_count)), timeout=timeout)
        if len(values) != 1:
            raise RuntimeError("NI-DAQmx analog read returned invalid data")
        return _values(values[0], float, "analog read")

    def write_analog(self, values: Iterable[float], *, timeout: int = 0) -> int:
        self._require(NidaqmxChannelType.ANALOG_OUTPUT)
        return self._write(NIDAQMX_WRITE_ANALOG, TypedValue(DataType.FLOAT64, _write_values(values, False)), timeout)

    def read_digital(self, sample_count: int = 1, *, timeout: int = 0) -> list[int]:
        self._require(NidaqmxChannelType.DIGITAL_INPUT)
        values = self._call(NIDAQMX_READ_DIGITAL, TypedValue(DataType.UINT32, _count(sample_count)), timeout=timeout)
        if len(values) != 1:
            raise RuntimeError("NI-DAQmx digital read returned invalid data")
        return _values(values[0], int, "digital read")

    def write_digital(self, values: Iterable[int], *, timeout: int = 0) -> int:
        self._require(NidaqmxChannelType.DIGITAL_OUTPUT)
        return self._write(NIDAQMX_WRITE_DIGITAL, TypedValue(DataType.UINT32, _write_values(values, True)), timeout)

    def _write(self, function: int, values: TypedValue, timeout: int) -> int:
        result = self._call(function, values, timeout=timeout)
        if len(result) != 1 or not isinstance(result[0], int) or isinstance(result[0], bool):
            raise RuntimeError("NI-DAQmx write returned an invalid sample count")
        return result[0]

    def _call(self, function: int, *args: object, timeout: int) -> list:
        self._ensure_open()
        return self._client.call(function, [TypedValue(DataType.UINT64, self._handle), *args], timeout=timeout)

    def _require(self, expected: NidaqmxChannelType) -> None:
        self._ensure_open()
        if self._channel_type != expected:
            raise RuntimeError(f"operation requires an {expected.name.lower().replace('_', ' ')} task")

    def close(self, *, timeout: int = 0) -> None:
        if self._closed:
            return
        self._call(NIDAQMX_CLOSE, timeout=timeout)
        self._closed = True

    def _ensure_open(self) -> None:
        if self._closed:
            raise RuntimeError("NI-DAQmx task is closed")

    def __enter__(self) -> NidaqmxTask:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
