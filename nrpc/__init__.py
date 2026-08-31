"""Public API for the synchronous nRPC Python client."""
from .client import (
    DataType,
    NrpcClient,
    NrpcError,
    NrpcValue,
    ProtocolError,
    RemoteError,
    TypedValue,
)
from .nidaqmx_backend import (
    NidaqmxChannelType,
    NidaqmxCjcSource,
    NidaqmxTask,
    NidaqmxTerminalConfig,
    NidaqmxThermocoupleType,
)
from .lcard_backend import (
    LcardAdcChannel,
    LcardAdcFrame,
    LcardAdcInputMode,
    LcardAdcTrigger,
    LcardAdcTriggerMode,
    LcardAdcVoltageFrame,
    LcardCapability,
    LcardDacWriteResult,
    LcardDevice,
    LcardDeviceInfo,
)
from .serial_backend import (
    SerialBackend,
    SerialFlowControl,
    SerialParity,
)
from .tcp_backend import TcpBackend
from .protocols import (
    ByteTransport,
    ModbusError,
    ModbusException,
    ModbusProtocolError,
    ModbusRtuClient,
    ModbusTcpClient,
    ProtocolSession,
    ProtocolTransaction,
    ProtocolTransportError,
)

__version__ = "1.0.0"

__all__ = [
    "__version__",
    "ByteTransport",
    "DataType",
    "NrpcClient",
    "NrpcError",
    "NrpcValue",
    "NidaqmxChannelType",
    "NidaqmxCjcSource",
    "NidaqmxTask",
    "NidaqmxTerminalConfig",
    "NidaqmxThermocoupleType",
    "LcardAdcChannel",
    "LcardAdcFrame",
    "LcardAdcInputMode",
    "LcardAdcTrigger",
    "LcardAdcTriggerMode",
    "LcardAdcVoltageFrame",
    "LcardCapability",
    "LcardDacWriteResult",
    "LcardDevice",
    "LcardDeviceInfo",
    "ModbusError",
    "ModbusException",
    "ModbusProtocolError",
    "ModbusRtuClient",
    "ModbusTcpClient",
    "ProtocolError",
    "ProtocolSession",
    "ProtocolTransaction",
    "ProtocolTransportError",
    "RemoteError",
    "SerialBackend",
    "SerialFlowControl",
    "SerialParity",
    "TypedValue",
    "TcpBackend",
]
