from __future__ import annotations

import socket
import ssl
import struct
import threading
from dataclasses import dataclass
from enum import IntEnum
from typing import TYPE_CHECKING, Any, Iterable, Sequence, TypeAlias

if TYPE_CHECKING:
    from .lcard_backend import LCardBackend, LCardBoardType
    from .nidaqmx_backend import (
        NidaqmxCjcSource,
        NidaqmxTask,
        NidaqmxTerminalConfig,
        NidaqmxThermocoupleType,
    )
    from .serial_backend import (
        SerialBackend,
        SerialFlowControl,
        SerialParity,
    )
    from .tcp_backend import TcpBackend

MAGIC = 0xF0
VERSION = 0x01
HEADER_SIZE = 16
VARIABLE_SIZE = 16
MAX_VARIABLES = 255
DEFAULT_MAX_PAYLOAD = 16 * 1024 * 1024

NrpcScalar: TypeAlias = None | bool | int | float | str | bytes


class DataType(IntEnum):
    """nRPC wire-level variable type codes."""
    NULL = 0x00
    INT8 = 0x01
    UINT8 = 0x02
    INT16 = 0x03
    UINT16 = 0x04
    INT32 = 0x05
    UINT32 = 0x06
    INT64 = 0x07
    UINT64 = 0x08
    FLOAT32 = 0x09
    FLOAT64 = 0x10
    BOOL = 0xA0
    STRING = 0xA1
    BYTES = 0xA2


_FORMATS = {
    DataType.INT8: "b",
    DataType.UINT8: "B",
    DataType.INT16: "h",
    DataType.UINT16: "H",
    DataType.INT32: "i",
    DataType.UINT32: "I",
    DataType.INT64: "q",
    DataType.UINT64: "Q",
    DataType.FLOAT32: "f",
    DataType.FLOAT64: "d",
}


class NrpcError(Exception):
    """Base exception for nRPC-specific failures."""

    pass


class ProtocolError(NrpcError):
    """Raised when a peer response violates the nRPC wire protocol."""

    pass


_FUNCTION_NAMES = {
    0: "echo values",
    1: "sleep",
    16: "open TCP connection",
    17: "write to TCP connection",
    18: "read from TCP connection",
    19: "close TCP connection",
    32: "open serial port",
    33: "write to serial port",
    34: "read from serial port",
    35: "close serial port",
    48: "open LCard device",
    49: "perform LCard asynchronous I/O",
    50: "read LCard slot information",
    51: "load LCard BIOS",
    52: "close LCard device",
    53: "read LCard ADC voltage frame",
    64: "create NI-DAQmx analog voltage input task",
    65: "create NI-DAQmx thermocouple input task",
    66: "create NI-DAQmx analog voltage output task",
    67: "create NI-DAQmx digital input task",
    68: "create NI-DAQmx digital output task",
    69: "start NI-DAQmx task",
    70: "read NI-DAQmx analog samples",
    71: "write NI-DAQmx analog samples",
    72: "read NI-DAQmx digital samples",
    73: "write NI-DAQmx digital samples",
    74: "close NI-DAQmx task",
}

_ERROR_DESCRIPTIONS = {
    1: "unknown function index",
    2: "backend raised an exception",
    3: "sleep expects one uint32 duration",
    1001: "nRPC protocol error",
    1002: "request timed out on the server",
    1003: "server response buffer is exhausted",
    1004: "internal server error",
    2001: "invalid TCP arguments",
    2002: "TCP host resolution failed",
    2003: "TCP connection failed",
    2004: "unknown TCP handle",
    2005: "TCP write failed",
    2006: "TCP read failed",
    2007: "TCP operation timed out",
    3001: "invalid serial arguments",
    3002: "serial port open failed",
    3003: "serial port configuration failed",
    3004: "unknown serial port handle",
    3005: "serial port write failed",
    3006: "serial port read failed",
    3007: "serial port operation timed out",
    3008: "unsupported serial port operation",
    4001: "invalid LCard arguments",
    4002: "LCard library could not be loaded",
    4003: "LCard device open failed",
    4004: "unknown LCard handle",
    4005: "LCard operation failed",
    4006: "unsupported LCard operation",
    4007: "LCard operation timed out",
    5001: "invalid NI-DAQmx arguments",
    5002: "NI-DAQmx library could not be loaded",
    5003: "NI-DAQmx task creation failed",
    5004: "unknown NI-DAQmx task handle",
    5005: "NI-DAQmx operation failed",
    5006: "operation is invalid for the NI-DAQmx channel type",
}


class RemoteError(NrpcError):
    """Error returned by a remote nRPC backend."""

    def __init__(
        self,
        code: int,
        function_index: int,
        status: int = 1,
        detail: str | None = None,
    ):
        self.code = code
        self.function_index = function_index
        self.status = status
        self.detail = detail
        self.description = _ERROR_DESCRIPTIONS.get(
            code, "unknown remote backend error"
        )
        self.function_name = _FUNCTION_NAMES.get(
            function_index, "unregistered nRPC function"
        )
        message = (
            f"nRPC function {function_index} ({self.function_name}) failed: "
            f"{self.description}"
        )
        if detail and detail != self.description:
            message += f": {detail}"
        elif detail:
            message += f" ({detail})"
        message += f" (status {status}, error code {code})"
        super().__init__(
            message
        )


@dataclass(frozen=True)
class TypedValue:
    """Value paired with an explicit nRPC wire type.

    Numeric and boolean values may be scalars, lists, or tuples. Strings,
    bytes, and null values follow the constraints of their corresponding wire
    types.
    """

    data_type: DataType
    value: Any


NrpcValue: TypeAlias = NrpcScalar | bytearray | memoryview | TypedValue


@dataclass(frozen=True)
class _EncodedValue:
    data_type: DataType
    count: int
    data: bytes


def _as_sequence(value: Any) -> tuple[Sequence[Any], bool]:
    if isinstance(value, (list, tuple)):
        return value, True
    return (value,), False


def _encode_typed(value: TypedValue) -> _EncodedValue:
    data_type = value.data_type
    raw = value.value
    if data_type == DataType.NULL:
        if raw is not None:
            raise ValueError("NULL value must be None")
        return _EncodedValue(data_type, 0, b"")
    if data_type == DataType.STRING:
        if not isinstance(raw, str):
            raise TypeError("STRING value must be str")
        data = raw.encode("utf-8") + b"\0"
        return _EncodedValue(data_type, len(data), data)
    if data_type == DataType.BYTES:
        data = bytes(raw)
        return _EncodedValue(data_type, len(data), data)

    values, _ = _as_sequence(raw)
    if data_type == DataType.BOOL:
        if not all(isinstance(item, bool) for item in values):
            raise TypeError("BOOL values must contain only bool")
        return _EncodedValue(data_type, len(values), bytes(values))
    try:
        data = struct.pack(f"!{len(values)}{_FORMATS[data_type]}", *values)
    except KeyError as error:
        raise ValueError(f"unsupported nRPC data type: {data_type!r}") from error
    return _EncodedValue(data_type, len(values), data)


def _encode_value(value: Any) -> _EncodedValue:
    if isinstance(value, TypedValue):
        return _encode_typed(value)
    if value is None:
        return _encode_typed(TypedValue(DataType.NULL, None))
    if isinstance(value, bool):
        return _encode_typed(TypedValue(DataType.BOOL, value))
    if isinstance(value, int):
        return _encode_typed(TypedValue(DataType.INT64, value))
    if isinstance(value, float):
        return _encode_typed(TypedValue(DataType.FLOAT64, value))
    if isinstance(value, str):
        return _encode_typed(TypedValue(DataType.STRING, value))
    if isinstance(value, (bytes, bytearray, memoryview)):
        return _encode_typed(TypedValue(DataType.BYTES, value))
    raise TypeError(f"cannot encode {type(value).__name__} as an nRPC value")


def _decode_value(data_type: DataType, count: int, data: bytes) -> Any:
    if data_type == DataType.NULL:
        if count != 0 or data:
            raise ProtocolError("invalid NULL response variable")
        return None
    if data_type == DataType.STRING:
        if count != len(data) or not data.endswith(b"\0"):
            raise ProtocolError("invalid STRING response variable")
        return data[:-1].decode("utf-8")
    if data_type == DataType.BYTES:
        if count != len(data):
            raise ProtocolError("invalid BYTES response variable")
        return data
    if data_type == DataType.BOOL:
        if count != len(data) or any(item not in (0, 1) for item in data):
            raise ProtocolError("invalid BOOL response variable")
        values = tuple(bool(item) for item in data)
    else:
        try:
            item_format = _FORMATS[data_type]
        except KeyError as error:
            raise ProtocolError(f"unknown response data type 0x{data_type:02x}") from error
        item_size = struct.calcsize(item_format)
        if len(data) != count * item_size:
            raise ProtocolError("response element count does not match data size")
        values = struct.unpack(f"!{count}{item_format}", data)
    return values[0] if count == 1 else list(values)


def _encode_request(function_index: int, args: Iterable[Any], timeout: int) -> bytes:
    if not 0 <= function_index <= 255:
        raise ValueError("function_index must be between 0 and 255")
    if not 0 <= timeout <= 0xFFFFFFFF:
        raise ValueError("timeout must be between 0 and 4294967295 ms")
    values = [_encode_value(value) for value in args]
    if len(values) > MAX_VARIABLES:
        raise ValueError("an nRPC request supports at most 255 variables")
    table = bytearray()
    data = bytearray()
    for value in values:
        table.extend(
            struct.pack(
                "!B3xII4x", value.data_type, len(value.data), value.count
            )
        )
        data.extend(value.data)
    payload = bytes(table + data)
    return (
        struct.pack(
            "!BBBBIII",
            MAGIC,
            VERSION,
            function_index,
            len(values),
            len(payload),
            timeout,
            0,
        )
        + payload
    )


class NrpcClient:
    """Persistent synchronous connection to an nRPC server.

    Calls on one client instance are serialized with a lock because nRPC 0.1.0
    permits one in-flight request per TCP connection. Separate instances can be
    used concurrently.
    """

    def __init__(
        self,
        host: str,
        port: int,
        *,
        connect_timeout: float | None = 10.0,
        max_payload_size: int = DEFAULT_MAX_PAYLOAD,
        ssl_context: ssl.SSLContext | None = None,
        server_hostname: str | None = None,
    ):
        """Connect to an nRPC server.

        Args:
            host: Server hostname or IP address.
            port: Server TCP port.
            connect_timeout: Socket connection timeout in seconds.
            max_payload_size: Largest accepted response payload.
            ssl_context: TLS context. When provided, connect using TLS.
            server_hostname: Hostname used for TLS certificate verification and
                SNI. Defaults to ``host``.
        """
        if ssl_context is None and server_hostname is not None:
            raise ValueError("server_hostname requires ssl_context")
        connection = socket.create_connection((host, port), connect_timeout)
        if ssl_context is not None:
            try:
                connection = ssl_context.wrap_socket(
                    connection,
                    server_hostname=(
                        host if server_hostname is None else server_hostname
                    ),
                )
            except BaseException:
                connection.close()
                raise
        self._socket = connection
        self._socket.settimeout(None)
        self._max_payload_size = max_payload_size
        self._lock = threading.Lock()

    def close(self) -> None:
        """Close the nRPC connection. Calling this repeatedly is safe."""

        self._socket.close()

    def __enter__(self) -> NrpcClient:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def call(
        self,
        function_index: int,
        args: Iterable[NrpcValue] = (),
        timeout: int = 0,
    ) -> list[Any]:
        """Invoke a remote function and return its decoded response variables.

        Args:
            function_index: Dispatcher index in the inclusive range 0..255.
            args: Python values or explicit ``TypedValue`` instances.
            timeout: Server-side operation timeout in milliseconds; zero means
                no timeout.

        Raises:
            RemoteError: The remote backend returned an error.
            ProtocolError: The response frame was malformed.
            OSError: The underlying connection failed.
        """
        packet = _encode_request(function_index, args, timeout)
        with self._lock:
            previous_timeout = self._socket.gettimeout()
            self._socket.settimeout(None if timeout == 0 else timeout / 1000.0 + 1.0)
            try:
                self._socket.sendall(packet)
                header = self._recv_exact(HEADER_SIZE)
                status, version, response_index, count, payload_size, error, reserved = (
                    struct.unpack("!BBBBIII", header)
                )
                if version != VERSION:
                    raise ProtocolError(f"unsupported response version {version}")
                if response_index != function_index:
                    raise ProtocolError("response function index does not match request")
                if reserved != 0:
                    raise ProtocolError("response reserved field is not zero")
                if payload_size > self._max_payload_size:
                    raise ProtocolError("response payload exceeds configured limit")
                payload = self._recv_exact(payload_size)
            finally:
                self._socket.settimeout(previous_timeout)
        if status == 1:
            detail = self._decode_error_detail(count, payload)
            raise RemoteError(error, response_index, detail=detail)
        if status != 0:
            raise ProtocolError(f"invalid response status {status}")
        if error != 0:
            raise ProtocolError("successful response contains an error code")
        return self._decode_payload(count, payload)

    def open_tcp_backend(
        self, host: str, port: int, *, timeout: int = 5000
    ) -> "TcpBackend":
        """Open a server-side TCP socket and return its client proxy."""

        from .tcp_backend import TcpBackend

        return TcpBackend(self, host, port, timeout=timeout)

    def open_lcard_backend(
        self,
        board: "LCardBoardType",
        slot: int = 0,
        *,
        bios: str = "",
        timeout: int = 5000,
    ) -> "LCardBackend":
        """Open an LCard device; empty ``bios`` lets the server auto-load it."""

        from .lcard_backend import LCardBackend

        return LCardBackend.open(
            self, board, slot, bios=bios, timeout=timeout
        )

    def create_nidaqmx_ai_voltage(
        self, physical_channel: str, minimum: float = -10.0,
        maximum: float = 10.0, *,
        terminal: "NidaqmxTerminalConfig | None" = None,
        timeout: int = 5000,
    ) -> "NidaqmxTask":
        """Create a server-side NI-DAQmx analog-voltage input task."""
        from .nidaqmx_backend import NidaqmxTask, NidaqmxTerminalConfig

        return NidaqmxTask.create_ai_voltage(
            self, physical_channel, minimum, maximum,
            terminal=NidaqmxTerminalConfig.DEFAULT if terminal is None else terminal,
            timeout=timeout,
        )

    def create_nidaqmx_ai_thermocouple(
        self, physical_channel: str, minimum: float, maximum: float,
        thermocouple_type: "NidaqmxThermocoupleType", *,
        cjc_source: "NidaqmxCjcSource | None" = None,
        cjc_value: float = 25.0, cjc_channel: str = "",
        timeout: int = 5000,
    ) -> "NidaqmxTask":
        """Create a server-side NI-DAQmx thermocouple input task."""
        from .nidaqmx_backend import NidaqmxCjcSource, NidaqmxTask

        return NidaqmxTask.create_ai_thermocouple(
            self, physical_channel, minimum, maximum, thermocouple_type,
            cjc_source=NidaqmxCjcSource.BUILT_IN if cjc_source is None else cjc_source,
            cjc_value=cjc_value, cjc_channel=cjc_channel, timeout=timeout,
        )

    def create_nidaqmx_ao_voltage(
        self, physical_channel: str, minimum: float = -10.0,
        maximum: float = 10.0, *, timeout: int = 5000,
    ) -> "NidaqmxTask":
        """Create a server-side NI-DAQmx analog-voltage output task."""
        from .nidaqmx_backend import NidaqmxTask

        return NidaqmxTask.create_ao_voltage(
            self, physical_channel, minimum, maximum, timeout=timeout
        )

    def create_nidaqmx_digital_input(
        self, lines: str, *, one_channel_for_all_lines: bool = True,
        timeout: int = 5000,
    ) -> "NidaqmxTask":
        """Create a server-side NI-DAQmx digital-input task."""
        from .nidaqmx_backend import NidaqmxTask

        return NidaqmxTask.create_digital_input(
            self, lines, one_channel_for_all_lines=one_channel_for_all_lines,
            timeout=timeout,
        )

    def create_nidaqmx_digital_output(
        self, lines: str, *, one_channel_for_all_lines: bool = True,
        timeout: int = 5000,
    ) -> "NidaqmxTask":
        """Create a server-side NI-DAQmx digital-output task."""
        from .nidaqmx_backend import NidaqmxTask

        return NidaqmxTask.create_digital_output(
            self, lines, one_channel_for_all_lines=one_channel_for_all_lines,
            timeout=timeout,
        )

    def open_serial_backend(
        self,
        port: str,
        *,
        baud_rate: int = 9600,
        data_bits: int = 8,
        parity: "SerialParity | None" = None,
        stop_bits: int = 1,
        flow_control: "SerialFlowControl | None" = None,
        timeout: int = 5000,
    ) -> "SerialBackend":
        """Open a server-side serial port and return its client proxy."""

        from .serial_backend import (
            SerialBackend,
            SerialFlowControl,
            SerialParity,
        )

        return SerialBackend(
            self,
            port,
            baud_rate=baud_rate,
            data_bits=data_bits,
            parity=SerialParity.NONE if parity is None else parity,
            stop_bits=stop_bits,
            flow_control=(
                SerialFlowControl.NONE
                if flow_control is None
                else flow_control
            ),
            timeout=timeout,
        )

    def _recv_exact(self, size: int) -> bytes:
        chunks = bytearray()
        while len(chunks) < size:
            chunk = self._socket.recv(size - len(chunks))
            if not chunk:
                raise ConnectionError("nRPC connection closed before response completed")
            chunks.extend(chunk)
        return bytes(chunks)

    @staticmethod
    def _decode_payload(count: int, payload: bytes) -> list[Any]:
        table_size = count * VARIABLE_SIZE
        if table_size > len(payload):
            raise ProtocolError("truncated response variable table")
        entries: list[tuple[DataType, int, int]] = []
        for offset in range(0, table_size, VARIABLE_SIZE):
            entry = payload[offset : offset + VARIABLE_SIZE]
            type_code, reserved1, data_size, element_count, reserved2 = (
                struct.unpack("!B3sII4s", entry)
            )
            if reserved1 != b"\0\0\0" or reserved2 != b"\0\0\0\0":
                raise ProtocolError(
                    "response variable reserved fields are not zero"
                )
            try:
                data_type = DataType(type_code)
            except ValueError as error:
                raise ProtocolError(
                    f"unknown response data type 0x{type_code:02x}"
                ) from error
            entries.append((data_type, data_size, element_count))

        values: list[Any] = []
        offset = table_size
        for data_type, data_size, element_count in entries:
            end = offset + data_size
            if end > len(payload):
                raise ProtocolError("truncated response variable data")
            values.append(
                _decode_value(data_type, element_count, payload[offset:end])
            )
            offset = end
        if offset != len(payload):
            raise ProtocolError("response payload contains trailing bytes")
        return values

    @staticmethod
    def _decode_error_detail(count: int, payload: bytes) -> str | None:
        if count == 0 and not payload:
            return None
        values = NrpcClient._decode_payload(count, payload)
        if len(values) != 1 or not isinstance(values[0], str):
            raise ProtocolError("error response detail must be a single string")
        return values[0]
