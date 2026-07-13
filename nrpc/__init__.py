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
from .serial_backend import (
    SerialBackend,
    SerialFlowControl,
    SerialParity,
)
from .tcp_backend import TcpBackend

__version__ = "0.1.0"

__all__ = [
    "__version__",
    "DataType",
    "NrpcClient",
    "NrpcError",
    "NrpcValue",
    "NidaqmxChannelType",
    "NidaqmxCjcSource",
    "NidaqmxTask",
    "NidaqmxTerminalConfig",
    "NidaqmxThermocoupleType",
    "ProtocolError",
    "RemoteError",
    "SerialBackend",
    "SerialFlowControl",
    "SerialParity",
    "TypedValue",
    "TcpBackend",
]
