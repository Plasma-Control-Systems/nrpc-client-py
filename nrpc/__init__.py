"""Public API for the synchronous and asynchronous nRPC Python client."""

from .async_client import AsyncNrpcClient
from .async_serial_backend import AsyncSerialBackend
from .async_tcp_backend import AsyncTcpBackend
from .client import (
    DataType,
    NrpcClient,
    NrpcError,
    NrpcValue,
    ProtocolError,
    RemoteError,
    TypedValue,
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
    "AsyncNrpcClient",
    "AsyncSerialBackend",
    "AsyncTcpBackend",
    "DataType",
    "NrpcClient",
    "NrpcError",
    "NrpcValue",
    "ProtocolError",
    "RemoteError",
    "SerialBackend",
    "SerialFlowControl",
    "SerialParity",
    "TypedValue",
    "TcpBackend",
]
