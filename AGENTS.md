# nRPC Python Client Agent Guide

## Scope and source of truth

This file applies to the entire `nrpc-client` repository. The distribution is `nrpc-client`; users import the dependency-free, typed `nrpc` package on Python 3.10 or newer. It is a synchronous nRPC 0.1.0 client.

Use `SPEC.md` as the authoritative wire-protocol definition, `nrpc/__init__.py` as the authoritative public export list, implementation modules for signatures and validation, `README.md`/`examples/` for supported usage, and tests for edge cases. The sibling `../nrpc-server` repository owns the C++ peer and built-in backend implementations. Any change to function indices, argument order/types, result shapes, errors, or timeout behavior must be synchronized across both repositories.

Do not add a runtime dependency without a strong reason. Do not reintroduce an async API: the public contract is intentionally synchronous and `tests/test_public_api.py` asserts that no `Async*` symbols are exported.

## Architecture

`nrpc/client.py` contains the wire codec, errors, `TypedValue`, and `NrpcClient`. `NrpcClient` opens one persistent socket, optionally wraps it with a caller-supplied `ssl.SSLContext`, and serializes calls with a `threading.Lock`. nRPC 0.1.0 allows one in-flight request per connection; callers needing concurrency must use separate `NrpcClient` instances.

Backend modules are thin typed proxies over numeric RPC functions:

| Module | Proxy | Function indices |
| --- | --- | --- |
| `tcp_backend.py` | `TcpBackend` | `16..19` open/write/read/close |
| `serial_backend.py` | `SerialBackend` | `32..35` open/write/read/close |
| `nidaqmx_backend.py` | `NidaqmxTask` | `64..74` task creation and I/O |
| `lcard_backend.py` | `LcardDevice` | `80..85` device/ADC/DAC operations |

The proxies validate inputs locally, use explicit `TypedValue`s for fixed-width wire fields, validate response count and Python types, and implement context managers. TCP and serial `read_until` maintain a local excess-byte buffer. Closing proxies and clients is idempotent; server-side resources are also released if the connection drops.

### Wire invariants

- Requests and responses use 16-byte headers; variable-table entries are 16 bytes; all multibyte numbers are network byte order.
- Magic is `0xF0`, version `0x01`, at most 255 variables, and the default accepted payload limit is 16 MiB.
- Reserved bytes must be zero. Strings are UTF-8 with a trailing NUL. Bool payload bytes must be exactly 0 or 1.
- Plain values infer as: `None -> NULL`, `bool -> BOOL`, `int -> INT64`, `float -> FLOAT64`, `str -> STRING`, bytes-like -> `BYTES`.
- Use `TypedValue(DataType.X, value)` for every fixed-width number, numeric/bool array, or otherwise exact wire type. Numeric response arrays decode to `list`; a one-element numeric value decodes to a scalar. Bytes and strings remain bytes and str.
- `timeout` is an unsigned 32-bit server-operation timeout in milliseconds. Zero means no operation timeout. For nonzero calls, the client socket deadline is the requested timeout plus one second of transport margin; the prior socket timeout is restored afterward.
- Never silently accept trailing payload, invalid counts/sizes, reserved bits, unknown data types, malformed strings/bools, mismatched function indices, or oversized payloads. Raise `ProtocolError`.

## Public API

Only symbols exported by `nrpc.__all__` are public:

- Core: `NrpcClient`, `DataType`, `TypedValue`, `NrpcValue`, `NrpcError`, `ProtocolError`, `RemoteError`, `__version__`.
- TCP/serial: `TcpBackend`, `SerialBackend`, `SerialParity`, `SerialFlowControl`.
- NI-DAQmx: `NidaqmxTask`, `NidaqmxChannelType`, `NidaqmxTerminalConfig`, `NidaqmxThermocoupleType`, `NidaqmxCjcSource`.
- LCard: `LcardDevice`, `LcardDeviceInfo`, `LcardCapability`, `LcardAdcChannel`, `LcardAdcInputMode`, `LcardAdcFrame`, `LcardDacWriteResult`.

Core signatures:

```python
NrpcClient(host, port, *, connect_timeout=10.0, max_payload_size=16*1024*1024,
           ssl_context=None, server_hostname=None)
client.call(function_index, args=(), timeout=0) -> list[Any]
client.close() -> None
```

`RemoteError` represents a server/backend error and exposes `code`, `function_index`, `status`, `detail`, `description`, and `function_name`. Keep `_FUNCTION_NAMES` and `_ERROR_DESCRIPTIONS` synchronized with the server. Transport failures remain the relevant socket/SSL exception; malformed peer data raises `ProtocolError`.

Preferred factories and proxy methods:

| Factory | Important proxy operations |
| --- | --- |
| `open_tcp_backend(host, port, timeout=5000)` | `write`, `read`, `read_until`, `close` |
| `open_serial_backend(port, baud_rate=9600, data_bits=8, parity=NONE, stop_bits=1, flow_control=NONE, timeout=5000)` | `write`, `read`, `read_until`, `close` |
| `create_nidaqmx_ai_voltage(...)`, `create_nidaqmx_ai_thermocouple(...)`, `create_nidaqmx_ao_voltage(...)`, `create_nidaqmx_digital_input(...)`, `create_nidaqmx_digital_output(...)` | `start`, typed `read`/`write`, `close` |
| `open_lcard(slot, firmware_path=None, timeout=5000)` | `info`, `read_adc`, `read_adc_frame`, `write_dac`, `write_dac_frames`, `close` |

NI-DAQmx is hosted by a Windows server loading `nicaiu.dll`; this Python package remains platform-independent. LCard similarly runs behind the server's WLCOMP/LComp adapter and returns raw hardware codes. Do not add client-side voltage conversion without an explicit new API contract.

## Usage examples

Install for development and run the full unit suite from this repository:

```sh
python -m pip install --editable .
python -m unittest discover -s tests -v
```

### Basic typed RPC

```python
from nrpc import DataType, NrpcClient, TypedValue

with NrpcClient("127.0.0.1", 9000) as client:
    values = client.call(
        0,
        [
            TypedValue(DataType.UINT32, [1, 2, 3]),
            "hello",
            b"\x00\x01",
            True,
        ],
        timeout=1000,
    )
    print(values)
```

The sample server's function `0` echoes values. Function `1` expects exactly one network-order `uint32` millisecond duration:

```python
client.call(1, [TypedValue(DataType.UINT32, 50)], timeout=500)
```

### Verified TLS

```python
import ssl
from nrpc import NrpcClient

tls = ssl.create_default_context(cafile="server.crt")
with NrpcClient(
    "192.0.2.20", 9000,
    ssl_context=tls,
    server_hostname="nrpc.example.com",
) as client:
    print(client.call(0, ["hello over TLS"], timeout=1000))
```

Passing `server_hostname` without `ssl_context` is invalid. TLS verification policy belongs to the supplied context; examples should use verification, not an unverified context.

### TCP or serial SCPI

```python
from nrpc import NrpcClient, SerialParity

with NrpcClient("127.0.0.1", 9000) as client:
    with client.open_tcp_backend("192.0.2.10", 5025, timeout=1000) as tcp:
        assert tcp.write("*IDN?\n", timeout=1000) == 6
        print(tcp.read_until(b"\n", timeout=1000).decode("ascii").rstrip())

    with client.open_serial_backend(
        "COM7", baud_rate=115200, parity=SerialParity.NONE, timeout=1000
    ) as serial:
        serial.write(b"*IDN?\n", timeout=1000)
        print(serial.read_until(b"\n", timeout=1000))
```

SCPI is application logic, not part of the proxies. Check short writes. `read_until` includes the terminator and buffers bytes after it for the next read.

### NI-DAQmx voltage input

```python
from nrpc import NidaqmxTerminalConfig, NrpcClient

with NrpcClient("127.0.0.1", 9000) as client:
    with client.create_nidaqmx_ai_voltage(
        "Dev1/ai0", -10.0, 10.0,
        terminal=NidaqmxTerminalConfig.DIFFERENTIAL,
        timeout=1000,
    ) as task:
        task.start(timeout=1000)
        samples = task.read(10, timeout=1000)
```

Input tasks may be read and output tasks written. The proxy rejects operations that do not match the task's channel type. Sample arrays are limited to 1,048,576 values per call.

### LCard raw ADC

```python
from nrpc import LcardAdcChannel, NrpcClient

with NrpcClient("127.0.0.1", 9000) as client:
    with client.open_lcard(0, firmware_path=r"C:\LCard\L780.bio") as device:
        channel = LcardAdcChannel(0, range=10.0)
        code = device.read_adc(channel, timeout=1000)
        frame = device.read_adc_frame([channel], rate_khz=100.0, timeout=1000)
        print(device.info, code, frame.codes, frame.actual_rate_khz)
```

Use `LcardAdcChannel.raw(logical_code)` only for an existing vendor logical-channel code. ADC frames allow 1..128 channels. Finite DAC output requires equal-length DAC0/DAC1 uint16 arrays and reports actual normalized rate.

Complete CLI programs are in `examples/basic_rpc.py`, `tls_rpc.py`, `tcp_scpi.py`, `serial_scpi.py`, `nidaqmx_voltage_input.py`, and `lcard_raw_adc.py`.

## Development and tests

Code should remain compatible with Python 3.10, fully typed, standard-library-only, and formatted consistently with the existing modules. Prefer local validation before any network call and clear `ValueError`/`TypeError` messages. Validate remote result shape even when the server is trusted. Use context managers in examples and tests so server resources close deterministically.

Tests use `unittest` and require no external packages:

```sh
python -m unittest discover -s tests -v
python -m unittest tests.test_codec -v
python -m unittest tests.test_tcp_backend -v
```

Backend unit tests use fake clients and should assert exact function index, argument `DataType`, value, and timeout. TLS tests mock socket wrapping. Codec tests should cover valid round trips and malformed frames. `test_public_api.py` must be updated deliberately for public exports.

End-to-end behavior is exercised from the sibling server's CTest suite. Configure that server with `-DNRPC_PYTHON_CLIENT_SOURCE_DIR=<this repository>` and run the `integration.*` tests. Hardware-specific client changes need fake-driver/unit coverage at minimum; state clearly when NI/LCard hardware was unavailable.

## Change checklist

- Keep `SPEC.md` identical in meaning to the server copy when protocol behavior changes.
- Update `nrpc/__init__.py`, `__all__`, documentation, and public API tests together for exported symbols.
- Preserve exact fixed-width `TypedValue` encoding in every backend request and strict response-shape checks.
- Preserve per-connection call serialization, timeout restoration, buffering behavior, and idempotent cleanup.
- Update server handlers/constants and the client's readable function/error maps with any backend contract change.
- Add focused unit tests, run the full client suite, and run applicable sibling-server integration tests.
