"""Dependency-free Modbus TCP and RTU clients over nRPC byte transports."""

from __future__ import annotations

import struct
import threading
from typing import Sequence

from .transport import ByteTransport, ProtocolSession, ProtocolTransaction

_READ_COILS = 1
_READ_DISCRETE_INPUTS = 2
_READ_HOLDING_REGISTERS = 3
_READ_INPUT_REGISTERS = 4
_WRITE_SINGLE_COIL = 5
_WRITE_SINGLE_REGISTER = 6
_WRITE_MULTIPLE_COILS = 15
_WRITE_MULTIPLE_REGISTERS = 16

_EXCEPTION_DESCRIPTIONS = {
    1: "illegal function",
    2: "illegal data address",
    3: "illegal data value",
    4: "server device failure",
    5: "acknowledge",
    6: "server device busy",
    8: "memory parity error",
    10: "gateway path unavailable",
    11: "gateway target device failed to respond",
}


class ModbusError(Exception):
    """Base exception for Modbus-specific failures."""


class ModbusProtocolError(ModbusError):
    """A Modbus response frame was malformed or did not match its request."""


class ModbusException(ModbusError):
    """Exception response returned by a Modbus server device."""

    def __init__(self, function_code: int, exception_code: int):
        self.function_code = function_code
        self.exception_code = exception_code
        self.description = _EXCEPTION_DESCRIPTIONS.get(
            exception_code, "unknown Modbus exception"
        )
        super().__init__(
            f"Modbus function {function_code} failed: {self.description} "
            f"(exception code {exception_code})"
        )


def _validate_uint16(name: str, value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be int")
    if not 0 <= value <= 0xFFFF:
        raise ValueError(f"{name} must be between 0 and 65535")
    return value


def _validate_unit_id(unit_id: int, *, minimum: int, maximum: int) -> int:
    if isinstance(unit_id, bool) or not isinstance(unit_id, int):
        raise TypeError("unit_id must be int")
    if not minimum <= unit_id <= maximum:
        raise ValueError(
            f"unit_id must be between {minimum} and {maximum}"
        )
    return unit_id


def _validate_count(name: str, count: int, maximum: int) -> int:
    if isinstance(count, bool) or not isinstance(count, int):
        raise TypeError(f"{name} must be int")
    if not 1 <= count <= maximum:
        raise ValueError(f"{name} must be between 1 and {maximum}")
    return count


def _crc16(data: bytes) -> int:
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ (0xA001 if crc & 1 else 0)
    return crc


def _append_crc(data: bytes) -> bytes:
    return data + struct.pack("<H", _crc16(data))


def _pack_coils(values: Sequence[bool]) -> bytes:
    packed = bytearray((len(values) + 7) // 8)
    for index, value in enumerate(values):
        if not isinstance(value, bool):
            raise TypeError("coil values must contain only bool")
        if value:
            packed[index // 8] |= 1 << (index % 8)
    return bytes(packed)


class _ModbusClient:
    def __init__(self, session: ProtocolSession, unit_id: int):
        self._session = session
        self._unit_id = unit_id

    @property
    def unit_id(self) -> int:
        """Modbus server/slave address used by this client."""

        return self._unit_id

    def read_coils(
        self, address: int, count: int, *, timeout: int = 0
    ) -> list[bool]:
        """Read 1..2000 coils (function 01)."""

        return self._read_bits(_READ_COILS, address, count, 2000, timeout)

    def read_discrete_inputs(
        self, address: int, count: int, *, timeout: int = 0
    ) -> list[bool]:
        """Read 1..2000 discrete inputs (function 02)."""

        return self._read_bits(
            _READ_DISCRETE_INPUTS, address, count, 2000, timeout
        )

    def read_holding_registers(
        self, address: int, count: int, *, timeout: int = 0
    ) -> list[int]:
        """Read 1..125 holding registers (function 03)."""

        return self._read_registers(
            _READ_HOLDING_REGISTERS, address, count, timeout
        )

    def read_input_registers(
        self, address: int, count: int, *, timeout: int = 0
    ) -> list[int]:
        """Read 1..125 input registers (function 04)."""

        return self._read_registers(
            _READ_INPUT_REGISTERS, address, count, timeout
        )

    def write_single_coil(
        self, address: int, value: bool, *, timeout: int = 0
    ) -> None:
        """Write one coil (function 05)."""

        address = _validate_uint16("address", address)
        if not isinstance(value, bool):
            raise TypeError("value must be bool")
        encoded_value = 0xFF00 if value else 0x0000
        request = struct.pack("!BHH", _WRITE_SINGLE_COIL, address, encoded_value)
        response = self._request(request, timeout=timeout, write=True)
        self._validate_write_echo(request, response)

    def write_single_register(
        self, address: int, value: int, *, timeout: int = 0
    ) -> None:
        """Write one holding register (function 06)."""

        address = _validate_uint16("address", address)
        value = _validate_uint16("value", value)
        request = struct.pack(
            "!BHH", _WRITE_SINGLE_REGISTER, address, value
        )
        response = self._request(request, timeout=timeout, write=True)
        self._validate_write_echo(request, response)

    def write_multiple_coils(
        self, address: int, values: Sequence[bool], *, timeout: int = 0
    ) -> None:
        """Write 1..1968 coils (function 15)."""

        address = _validate_uint16("address", address)
        if isinstance(values, (str, bytes, bytearray, memoryview)):
            raise TypeError("values must be a sequence of bool")
        count = _validate_count("values length", len(values), 1968)
        packed = _pack_coils(values)
        request = (
            struct.pack(
                "!BHHB", _WRITE_MULTIPLE_COILS, address, count, len(packed)
            )
            + packed
        )
        response = self._request(request, timeout=timeout, write=True)
        self._validate_multiple_write_response(
            _WRITE_MULTIPLE_COILS, address, count, response
        )

    def write_multiple_registers(
        self, address: int, values: Sequence[int], *, timeout: int = 0
    ) -> None:
        """Write 1..123 holding registers (function 16)."""

        address = _validate_uint16("address", address)
        if isinstance(values, (str, bytes, bytearray, memoryview)):
            raise TypeError("values must be a sequence of int")
        count = _validate_count("values length", len(values), 123)
        checked = [_validate_uint16("register value", item) for item in values]
        data = struct.pack(f"!{count}H", *checked)
        request = (
            struct.pack(
                "!BHHB", _WRITE_MULTIPLE_REGISTERS, address, count, len(data)
            )
            + data
        )
        response = self._request(request, timeout=timeout, write=True)
        self._validate_multiple_write_response(
            _WRITE_MULTIPLE_REGISTERS, address, count, response
        )

    def close(self, *, timeout: int = 0) -> None:
        """Close this adapter and its transport if ownership was requested."""

        self._session.close(timeout=timeout)

    def __enter__(self) -> _ModbusClient:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _read_bits(
        self,
        function: int,
        address: int,
        count: int,
        maximum: int,
        timeout: int,
    ) -> list[bool]:
        address = _validate_uint16("address", address)
        count = _validate_count("count", count, maximum)
        request = struct.pack("!BHH", function, address, count)
        response = self._request(request, timeout=timeout, write=False)
        payload = self._response_payload(function, response)
        expected_bytes = (count + 7) // 8
        if len(payload) != expected_bytes + 1 or payload[0] != expected_bytes:
            raise ModbusProtocolError("Modbus bit response has invalid byte count")
        return [
            bool(payload[1 + index // 8] & (1 << (index % 8)))
            for index in range(count)
        ]

    def _read_registers(
        self, function: int, address: int, count: int, timeout: int
    ) -> list[int]:
        address = _validate_uint16("address", address)
        count = _validate_count("count", count, 125)
        request = struct.pack("!BHH", function, address, count)
        response = self._request(request, timeout=timeout, write=False)
        payload = self._response_payload(function, response)
        byte_count = count * 2
        if len(payload) != byte_count + 1 or payload[0] != byte_count:
            raise ModbusProtocolError(
                "Modbus register response has invalid byte count"
            )
        return list(struct.unpack(f"!{count}H", payload[1:]))

    @staticmethod
    def _response_payload(function: int, response: bytes) -> bytes:
        if len(response) == 2 and response[0] == function | 0x80:
            raise ModbusException(function, response[1])
        if not response or response[0] != function:
            actual = "empty" if not response else str(response[0])
            raise ModbusProtocolError(
                f"unexpected Modbus function code {actual}, expected {function}"
            )
        return response[1:]

    @classmethod
    def _validate_write_echo(cls, request: bytes, response: bytes) -> None:
        cls._response_payload(request[0], response)
        if response != request:
            raise ModbusProtocolError("Modbus write response does not echo request")

    @classmethod
    def _validate_multiple_write_response(
        cls,
        function: int,
        address: int,
        count: int,
        response: bytes,
    ) -> None:
        payload = cls._response_payload(function, response)
        if payload != struct.pack("!HH", address, count):
            raise ModbusProtocolError(
                "Modbus multiple-write response does not match request"
            )

    def _request(self, pdu: bytes, *, timeout: int, write: bool) -> bytes:
        raise NotImplementedError


class ModbusTcpClient(_ModbusClient):
    """Modbus TCP client using an nRPC TCP-compatible byte transport."""

    def __init__(
        self,
        transport: ByteTransport,
        *,
        unit_id: int = 1,
        owns_transport: bool = False,
    ):
        super().__init__(
            ProtocolSession(
                transport, max_frame_size=260, owns_transport=owns_transport
            ),
            _validate_unit_id(unit_id, minimum=0, maximum=255),
        )
        self._transaction_id = 0
        self._transaction_id_lock = threading.Lock()

    def _next_transaction_id(self) -> int:
        with self._transaction_id_lock:
            transaction_id = self._transaction_id
            self._transaction_id = (self._transaction_id + 1) & 0xFFFF
            return transaction_id

    def _request(self, pdu: bytes, *, timeout: int, write: bool) -> bytes:
        del write
        transaction_id = self._next_transaction_id()
        request = struct.pack(
            "!HHHB", transaction_id, 0, len(pdu) + 1, self._unit_id
        ) + pdu
        with self._session.transaction(timeout=timeout) as io:
            io.write(request)
            header = io.read_exactly(7)
            response_id, protocol_id, length, unit_id = struct.unpack(
                "!HHHB", header
            )
            if not 2 <= length <= 254:
                raise ModbusProtocolError("Modbus TCP length field is invalid")
            response = io.read_exactly(length - 1)
            if response_id != transaction_id:
                raise ModbusProtocolError(
                    "Modbus TCP transaction identifier does not match request"
                )
            if protocol_id != 0:
                raise ModbusProtocolError("Modbus TCP protocol identifier is not zero")
            if unit_id != self._unit_id:
                raise ModbusProtocolError(
                    "Modbus TCP unit identifier does not match request"
                )
            return response


class ModbusRtuClient(_ModbusClient):
    """Modbus RTU master using an nRPC serial-compatible byte transport."""

    def __init__(
        self,
        transport: ByteTransport,
        *,
        unit_id: int = 1,
        owns_transport: bool = False,
    ):
        super().__init__(
            ProtocolSession(
                transport, max_frame_size=256, owns_transport=owns_transport
            ),
            _validate_unit_id(unit_id, minimum=0, maximum=247),
        )

    def _request(self, pdu: bytes, *, timeout: int, write: bool) -> bytes:
        if self._unit_id == 0 and not write:
            raise ValueError("Modbus RTU broadcast address cannot be used for reads")
        request = _append_crc(bytes((self._unit_id,)) + pdu)
        with self._session.transaction(timeout=timeout) as io:
            io.write(request)
            if self._unit_id == 0:
                if pdu[0] in (
                    _WRITE_MULTIPLE_COILS,
                    _WRITE_MULTIPLE_REGISTERS,
                ):
                    return pdu[:5]
                return pdu
            response = self._read_response(io, pdu[0])
        if _crc16(response) != 0:
            raise ModbusProtocolError("Modbus RTU response CRC is invalid")
        if response[0] != self._unit_id:
            raise ModbusProtocolError(
                "Modbus RTU unit identifier does not match request"
            )
        return response[1:-2]

    @staticmethod
    def _read_response(io: ProtocolTransaction, expected_function: int) -> bytes:
        prefix = io.read_exactly(2)
        function = prefix[1]
        if function == expected_function | 0x80:
            return prefix + io.read_exactly(3)
        if function != expected_function:
            raise ModbusProtocolError(
                f"unexpected Modbus function code {function}, "
                f"expected {expected_function}"
            )
        if function in (
            _READ_COILS,
            _READ_DISCRETE_INPUTS,
            _READ_HOLDING_REGISTERS,
            _READ_INPUT_REGISTERS,
        ):
            byte_count = io.read_exactly(1)
            if byte_count[0] > 250:
                raise ModbusProtocolError(
                    "Modbus RTU response byte count exceeds the protocol limit"
                )
            return prefix + byte_count + io.read_exactly(byte_count[0] + 2)
        if function in (
            _WRITE_SINGLE_COIL,
            _WRITE_SINGLE_REGISTER,
            _WRITE_MULTIPLE_COILS,
            _WRITE_MULTIPLE_REGISTERS,
        ):
            return prefix + io.read_exactly(6)
        raise ModbusProtocolError(f"unsupported Modbus function code {function}")
