from __future__ import annotations

import math
from typing import TYPE_CHECKING, Iterable

from .client import DataType, TypedValue
from .nidaqmx_backend import (
    NIDAQMX_CLOSE, NIDAQMX_CREATE_AI_THERMOCOUPLE,
    NIDAQMX_CREATE_AI_VOLTAGE, NIDAQMX_CREATE_AO_VOLTAGE,
    NIDAQMX_CREATE_DI, NIDAQMX_CREATE_DO, NIDAQMX_READ_ANALOG,
    NIDAQMX_READ_DIGITAL, NIDAQMX_START, NIDAQMX_WRITE_ANALOG,
    NIDAQMX_WRITE_DIGITAL, NidaqmxChannelType, NidaqmxCjcSource,
    NidaqmxTerminalConfig, NidaqmxThermocoupleType, _channel, _count,
    _grouping, _range, _values, _write_values,
)

if TYPE_CHECKING:
    from .async_client import AsyncNrpcClient


class AsyncNidaqmxTask:
    """Asynchronous client proxy for one server-side NI-DAQmx task."""

    def __init__(self, client: AsyncNrpcClient, handle: int, channel_type: NidaqmxChannelType):
        self._client = client
        self._handle = handle
        self._channel_type = channel_type
        self._closed = False

    @classmethod
    async def create_ai_voltage(cls, client: AsyncNrpcClient, physical_channel: str, minimum: float = -10.0,
                                maximum: float = 10.0, *, terminal: NidaqmxTerminalConfig = NidaqmxTerminalConfig.DEFAULT,
                                timeout: int = 5000) -> AsyncNidaqmxTask:
        minimum, maximum = _range(minimum, maximum)
        return await cls._create(client, NIDAQMX_CREATE_AI_VOLTAGE, NidaqmxChannelType.ANALOG_INPUT,
                                 [_channel(physical_channel), TypedValue(DataType.FLOAT64, minimum), TypedValue(DataType.FLOAT64, maximum),
                                  TypedValue(DataType.INT32, NidaqmxTerminalConfig(terminal).value)], timeout)

    @classmethod
    async def create_ai_thermocouple(cls, client: AsyncNrpcClient, physical_channel: str, minimum: float, maximum: float,
                                     thermocouple_type: NidaqmxThermocoupleType, *,
                                     cjc_source: NidaqmxCjcSource = NidaqmxCjcSource.BUILT_IN,
                                     cjc_value: float = 25.0, cjc_channel: str = "", timeout: int = 5000) -> AsyncNidaqmxTask:
        minimum, maximum = _range(minimum, maximum)
        source = NidaqmxCjcSource(cjc_source)
        if source == NidaqmxCjcSource.CHANNEL:
            _channel(cjc_channel, "cjc_channel")
        if not math.isfinite(float(cjc_value)):
            raise ValueError("cjc_value must be finite")
        return await cls._create(client, NIDAQMX_CREATE_AI_THERMOCOUPLE, NidaqmxChannelType.ANALOG_INPUT,
                                 [_channel(physical_channel), TypedValue(DataType.FLOAT64, minimum), TypedValue(DataType.FLOAT64, maximum),
                                  TypedValue(DataType.INT32, NidaqmxThermocoupleType(thermocouple_type).value), TypedValue(DataType.INT32, source.value),
                                  TypedValue(DataType.FLOAT64, float(cjc_value)), cjc_channel], timeout)

    @classmethod
    async def create_ao_voltage(cls, client: AsyncNrpcClient, physical_channel: str, minimum: float = -10.0,
                                maximum: float = 10.0, *, timeout: int = 5000) -> AsyncNidaqmxTask:
        minimum, maximum = _range(minimum, maximum)
        return await cls._create(client, NIDAQMX_CREATE_AO_VOLTAGE, NidaqmxChannelType.ANALOG_OUTPUT,
                                 [_channel(physical_channel), TypedValue(DataType.FLOAT64, minimum), TypedValue(DataType.FLOAT64, maximum)], timeout)

    @classmethod
    async def create_digital_input(cls, client: AsyncNrpcClient, lines: str, *, one_channel_for_all_lines: bool = True,
                                   timeout: int = 5000) -> AsyncNidaqmxTask:
        return await cls._create(client, NIDAQMX_CREATE_DI, NidaqmxChannelType.DIGITAL_INPUT,
                                 [_channel(lines, "lines"), _grouping(one_channel_for_all_lines)], timeout)

    @classmethod
    async def create_digital_output(cls, client: AsyncNrpcClient, lines: str, *, one_channel_for_all_lines: bool = True,
                                    timeout: int = 5000) -> AsyncNidaqmxTask:
        return await cls._create(client, NIDAQMX_CREATE_DO, NidaqmxChannelType.DIGITAL_OUTPUT,
                                 [_channel(lines, "lines"), _grouping(one_channel_for_all_lines)], timeout)

    @classmethod
    async def _create(cls, client: AsyncNrpcClient, function: int, channel_type: NidaqmxChannelType,
                      args: list, timeout: int) -> AsyncNidaqmxTask:
        values = await client.call(function, args, timeout=timeout)
        if len(values) != 1 or not isinstance(values[0], int) or isinstance(values[0], bool):
            raise RuntimeError("NI-DAQmx task creation returned an invalid handle")
        return cls(client, values[0], channel_type)

    @property
    def handle(self) -> int:
        return self._handle

    @property
    def channel_type(self) -> NidaqmxChannelType:
        return self._channel_type

    async def start(self, *, timeout: int = 0) -> None:
        await self._call(NIDAQMX_START, timeout=timeout)

    async def read(self, sample_count: int = 1, *, timeout: int = 0) -> list[float] | list[int]:
        if self._channel_type == NidaqmxChannelType.ANALOG_INPUT:
            return await self.read_analog(sample_count, timeout=timeout)
        if self._channel_type == NidaqmxChannelType.DIGITAL_INPUT:
            return await self.read_digital(sample_count, timeout=timeout)
        raise RuntimeError("NI-DAQmx output tasks cannot be read")

    async def write(self, values: Iterable[float] | Iterable[int], *, timeout: int = 0) -> int:
        if self._channel_type == NidaqmxChannelType.ANALOG_OUTPUT:
            return await self.write_analog(values, timeout=timeout)
        if self._channel_type == NidaqmxChannelType.DIGITAL_OUTPUT:
            return await self.write_digital(values, timeout=timeout)
        raise RuntimeError("NI-DAQmx input tasks cannot be written")

    async def read_analog(self, sample_count: int = 1, *, timeout: int = 0) -> list[float]:
        self._require(NidaqmxChannelType.ANALOG_INPUT)
        values = await self._call(NIDAQMX_READ_ANALOG, TypedValue(DataType.UINT32, _count(sample_count)), timeout=timeout)
        if len(values) != 1:
            raise RuntimeError("NI-DAQmx analog read returned invalid data")
        return _values(values[0], float, "analog read")

    async def write_analog(self, values: Iterable[float], *, timeout: int = 0) -> int:
        self._require(NidaqmxChannelType.ANALOG_OUTPUT)
        return await self._write(NIDAQMX_WRITE_ANALOG, TypedValue(DataType.FLOAT64, _write_values(values, False)), timeout)

    async def read_digital(self, sample_count: int = 1, *, timeout: int = 0) -> list[int]:
        self._require(NidaqmxChannelType.DIGITAL_INPUT)
        values = await self._call(NIDAQMX_READ_DIGITAL, TypedValue(DataType.UINT32, _count(sample_count)), timeout=timeout)
        if len(values) != 1:
            raise RuntimeError("NI-DAQmx digital read returned invalid data")
        return _values(values[0], int, "digital read")

    async def write_digital(self, values: Iterable[int], *, timeout: int = 0) -> int:
        self._require(NidaqmxChannelType.DIGITAL_OUTPUT)
        return await self._write(NIDAQMX_WRITE_DIGITAL, TypedValue(DataType.UINT32, _write_values(values, True)), timeout)

    async def _write(self, function: int, values: TypedValue, timeout: int) -> int:
        result = await self._call(function, values, timeout=timeout)
        if len(result) != 1 or not isinstance(result[0], int) or isinstance(result[0], bool):
            raise RuntimeError("NI-DAQmx write returned an invalid sample count")
        return result[0]

    async def _call(self, function: int, *args: object, timeout: int) -> list:
        self._ensure_open()
        return await self._client.call(function, [TypedValue(DataType.UINT64, self._handle), *args], timeout=timeout)

    def _require(self, expected: NidaqmxChannelType) -> None:
        self._ensure_open()
        if self._channel_type != expected:
            raise RuntimeError(f"operation requires an {expected.name.lower().replace('_', ' ')} task")

    async def close(self, *, timeout: int = 0) -> None:
        if self._closed:
            return
        await self._call(NIDAQMX_CLOSE, timeout=timeout)
        self._closed = True

    def _ensure_open(self) -> None:
        if self._closed:
            raise RuntimeError("NI-DAQmx task is closed")

    async def __aenter__(self) -> AsyncNidaqmxTask:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.close()
