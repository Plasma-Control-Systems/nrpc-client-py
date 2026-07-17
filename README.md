# nRPC Python Client

`nrpc-client` is the typed, synchronous Python client for nRPC 0.1.0. It is
dependency-free, supports Python 3.10 or newer, and runs on Linux, macOS, and
Windows. The client can make arbitrary typed RPC calls and provides high-level
proxies for the server's TCP, serial, NI-DAQmx, and LCard backends.

The distribution is named `nrpc-client`; the import package is `nrpc`. The
authoritative wire definition is [SPEC.md](SPEC.md).

## Features

- persistent synchronous TCP connections with optional verified TLS
- strict nRPC request encoding and response validation
- all nRPC scalar types plus explicitly typed numeric and boolean arrays
- connection-safe serialization of calls from multiple Python threads
- context-managed TCP and serial equipment connections
- typed NI-DAQmx task and LCard device proxies
- readable remote function and error descriptions
- no third-party runtime dependencies

## Documentation map

- This README covers installation, API usage, backend behavior, errors, and
  troubleshooting.
- [SPEC.md](SPEC.md) defines the byte-level nRPC protocol.
- [`examples/`](examples/) contains complete command-line programs.
- [AGENTS.md](AGENTS.md) contains repository conventions for coding agents and
  contributors.
- The sibling `../nrpc-server` repository documents server deployment,
  configuration, built-in function schemas, and native driver requirements.

## Quick start

Install the package from this checkout:

```sh
python -m pip install --editable .
```

Start an nRPC server on the same machine, then call its built-in echo function:

```python
from nrpc import DataType, NrpcClient, TypedValue

with NrpcClient("127.0.0.1", 9000) as client:
    response = client.call(
        0,
        [
            TypedValue(DataType.UINT32, [1, 2, 3]),
            "hello",
            b"\x00\x01",
            True,
        ],
        timeout=1000,
    )

print(response)
```

The sample server registers function `0` as an echo handler. A successful call
confirms that the server is reachable and that framing and typed-value handling
work end to end.

## Installation

From the repository:

```sh
python -m pip install .
```

For editable development:

```sh
python -m pip install --editable .
```

To use the source tree without installing it, run commands from this repository
or put this directory on `PYTHONPATH`. The package has no runtime dependencies.

## Core concepts

### Connections and calls

`NrpcClient` opens one persistent connection immediately during construction.
The server processes one request at a time on each connection. Calls made from
multiple threads through the same client are serialized with a lock; use
multiple client instances when RPCs must execute concurrently.

The client is a context manager. Closing the connection also tells the server
to clean up every TCP socket, serial port, NI-DAQmx task, and LCard device owned
by that connection. Backend proxies are context managers as well, which closes
resources earlier and makes failures easier to localize.

### Timeouts

There are two distinct timeout units:

- `connect_timeout` is a socket connection timeout in seconds.
- `timeout` on `call` and backend methods is the server operation timeout in
  milliseconds. Zero means no requested operation timeout.

For a nonzero operation timeout, the client uses that timeout plus one second
as its local socket deadline. This gives the server time to return its
structured timeout error. The socket's previous timeout is restored after the
call.

### Python and nRPC values

Plain Python values use convenient default wire types:

| Python value | nRPC type | Notes |
| --- | --- | --- |
| `None` | `NULL` | no payload |
| `bool` | `BOOL` | scalar only without `TypedValue` |
| `int` | `INT64` | must fit the signed 64-bit range |
| `float` | `FLOAT64` | IEEE-754 double |
| `str` | `STRING` | UTF-8, NUL-terminated on the wire |
| `bytes`, `bytearray`, `memoryview` | `BYTES` | decoded responses are `bytes` |

Use `TypedValue` whenever a backend expects an exact fixed-width number or an
array:

```python
from nrpc import DataType, TypedValue

arguments = [
    TypedValue(DataType.UINT16, 5025),
    TypedValue(DataType.FLOAT32, [0.0, 1.25, -2.5]),
    TypedValue(DataType.BOOL, [True, False, True]),
]
```

Available `DataType` members are `NULL`, `INT8`, `UINT8`, `INT16`, `UINT16`,
`INT32`, `UINT32`, `INT64`, `UINT64`, `FLOAT32`, `FLOAT64`, `BOOL`, `STRING`,
and `BYTES`. Numeric and boolean response values decode as a scalar when their
element count is one and as a `list` otherwise. Empty numeric arrays decode as
an empty list. Strings and bytes never use scalar/list conversion.

## Core API reference

### `NrpcClient`

```python
NrpcClient(
    host: str,
    port: int,
    *,
    connect_timeout: float | None = 10.0,
    max_payload_size: int = 16 * 1024 * 1024,
    ssl_context: ssl.SSLContext | None = None,
    server_hostname: str | None = None,
)
```

- `host` and `port` identify the nRPC server.
- `connect_timeout=None` disables the connection deadline.
- `max_payload_size` is the largest response body accepted by this client.
- `ssl_context` enables TLS. Certificate verification behavior comes from the
  supplied context.
- `server_hostname` controls TLS SNI and hostname verification and defaults to
  `host`. It is invalid without `ssl_context`.

General RPC call:

```python
client.call(
    function_index: int,
    args: Iterable[NrpcValue] = (),
    timeout: int = 0,
) -> list[Any]
```

The function index and argument schema are application/server contracts. The
index must be in `0..255`, there may be at most 255 arguments, and the timeout
must fit an unsigned 32-bit millisecond value. The return value is always a
list containing the decoded response variables, even if the response has zero
or one variable.

`client.close()` is safe to call repeatedly. Prefer `with NrpcClient(...)` so
the connection closes during exception unwinding.

### `TypedValue`

```python
TypedValue(data_type: DataType, value: Any)
```

`TypedValue` is an immutable pair. Numeric and boolean values may be scalars,
lists, or tuples. `STRING` requires `str`, `BYTES` accepts bytes-compatible
input, and `NULL` requires `None`. Encoding checks the requested representation
and raises `TypeError`, `ValueError`, or `struct.error` for invalid input.

## TLS

Use `ssl.create_default_context` with a trusted CA file. For a self-signed
development server, the server certificate itself may be the CA file:

```python
import ssl

from nrpc import NrpcClient

tls = ssl.create_default_context(cafile="server.crt")
with NrpcClient(
    "192.0.2.20",
    9000,
    ssl_context=tls,
    server_hostname="nrpc.example.com",
) as client:
    print(client.call(0, ["hello over TLS"], timeout=1000))
```

`server_hostname` is useful when connecting by IP address to a certificate
issued for a DNS name. A TLS-enabled server port accepts TLS connections only;
plaintext and TLS clients cannot share the same listener. Avoid disabling
certificate verification outside a controlled diagnostic environment.

## TCP backend

`TcpBackend` controls a socket opened by the nRPC server. The destination is
resolved and reached from the server machine, which is important when the
Python process and equipment live on different networks.

Create one through:

```python
client.open_tcp_backend(host: str, port: int, *, timeout: int = 5000)
    -> TcpBackend
```

Proxy API:

| Member | Behavior |
| --- | --- |
| `handle` | connection-scoped server handle ID |
| `write(data, *, timeout=0, encoding="ascii") -> int` | writes bytes, or encodes a string; returns byte count |
| `read(max_size=4096, *, timeout=0) -> bytes` | reads up to `max_size`, using buffered excess first |
| `read_until(terminator=b"\n", *, max_size=1048576, chunk_size=4096, timeout=0) -> bytes` | reads through the terminator and buffers following bytes |
| `close(*, timeout=0)` | closes the remote socket; repeated calls are safe |

Example SCPI query:

```python
from nrpc import NrpcClient

with NrpcClient("127.0.0.1", 9000) as client:
    with client.open_tcp_backend("192.0.2.10", 5025, timeout=1000) as tcp:
        request = b"*IDN?\n"
        written = tcp.write(request, timeout=1000)
        if written != len(request):
            raise RuntimeError(f"short write: {written}/{len(request)}")
        response = tcp.read_until(b"\n", timeout=1000)
        print(response.decode("ascii").rstrip())
```

The proxy is protocol-neutral: SCPI message formatting, terminators, encoding,
and command/response rules belong to application code. `read_until` includes
the terminator in its result. If buffered data reaches `max_size` without the
terminator, it raises `ValueError`.

## Serial backend

`SerialBackend` controls a native serial port on the server machine. Use OS
names such as `COM7`, `/dev/ttyUSB0`, or `/dev/cu.usbserial-...`.

```python
client.open_serial_backend(
    port: str,
    *,
    baud_rate: int = 9600,
    data_bits: int = 8,
    parity: SerialParity = SerialParity.NONE,
    stop_bits: int = 1,
    flow_control: SerialFlowControl = SerialFlowControl.NONE,
    timeout: int = 5000,
) -> SerialBackend
```

Parity values are `NONE`, `ODD`, `EVEN`, `MARK`, and `SPACE`. Flow-control
values are `NONE`, `SOFTWARE`, `RTS_CTS`, and `DTR_DSR`. The client accepts
5..8 data bits and one or two stop bits. The server returns an unsupported
operation error when the host API cannot represent a valid requested mode;
DTR/DSR flow control and mark/space parity are not portable to every platform.

`SerialBackend` provides the same `handle`, `write`, `read`, `read_until`, and
`close` interface as `TcpBackend`:

```python
from nrpc import NrpcClient, SerialParity

with NrpcClient("127.0.0.1", 9000) as client:
    with client.open_serial_backend(
        "COM7",
        baud_rate=115200,
        data_bits=8,
        parity=SerialParity.NONE,
        stop_bits=1,
        timeout=1000,
    ) as serial:
        serial.write(b"*IDN?\n", timeout=1000)
        print(serial.read_until(b"\n", timeout=1000))
```

## NI-DAQmx backend

NI-DAQmx tasks run inside the Windows server process; the Python client remains
platform-independent. The server loads `nicaiu.dll` at runtime. Creating a task
returns a connection-owned `NidaqmxTask`, which is stopped and cleared on close
or disconnect.

### Task factories

| Client factory | Purpose and key parameters |
| --- | --- |
| `create_nidaqmx_ai_voltage(channel, minimum=-10, maximum=10, *, terminal=DEFAULT, timeout=5000)` | analog voltage input |
| `create_nidaqmx_ai_thermocouple(channel, minimum, maximum, thermocouple_type, *, cjc_source=BUILT_IN, cjc_value=25, cjc_channel="", timeout=5000)` | thermocouple input |
| `create_nidaqmx_ao_voltage(channel, minimum=-10, maximum=10, *, timeout=5000)` | analog voltage output |
| `create_nidaqmx_digital_input(lines, *, one_channel_for_all_lines=True, timeout=5000)` | digital input |
| `create_nidaqmx_digital_output(lines, *, one_channel_for_all_lines=True, timeout=5000)` | digital output |

Terminal configurations are `DEFAULT`, `RSE`, `NRSE`, `DIFFERENTIAL`, and
`PSEUDODIFFERENTIAL`. Thermocouple types are `B`, `E`, `J`, `K`, `N`, `R`, `S`,
and `T`. Cold-junction sources are `BUILT_IN`, `CONSTANT_VALUE`, and `CHANNEL`;
`cjc_channel` is required when `CHANNEL` is selected.

### Task API

| Member | Behavior |
| --- | --- |
| `handle` | server-side task handle |
| `channel_type` | `ANALOG_INPUT`, `ANALOG_OUTPUT`, `DIGITAL_INPUT`, or `DIGITAL_OUTPUT` |
| `start(*, timeout=0)` | explicitly starts the task |
| `read(sample_count=1, *, timeout=0)` | dispatches to analog or digital input read |
| `write(values, *, timeout=0)` | dispatches to analog or digital output write |
| `read_analog`, `write_analog` | type-specific analog operations |
| `read_digital`, `write_digital` | type-specific digital operations |
| `close(*, timeout=0)` | stops and clears the remote task |

Reads and writes accept 1..1,048,576 samples per call. Analog output values
must be finite; digital values must fit `uint32`. The proxy rejects reads from
output tasks, writes to input tasks, and mismatched type-specific methods.

Voltage-input example:

```python
from nrpc import NidaqmxTerminalConfig, NrpcClient

with NrpcClient("127.0.0.1", 9000) as client:
    with client.create_nidaqmx_ai_voltage(
        "Dev1/ai0",
        -10.0,
        10.0,
        terminal=NidaqmxTerminalConfig.DIFFERENTIAL,
        timeout=1000,
    ) as task:
        task.start(timeout=1000)
        samples = task.read(10, timeout=1000)
        print(samples)
```

The implemented API creates on-demand, single-channel tasks. Hardware-timed
sampling and explicit clock configuration are outside the nRPC 0.1.0 subset.

## LCard backend

LCard devices run behind the Windows server's WLCOMP/LComp adapter. The Python
API is platform-independent and intentionally exposes raw ADC and DAC hardware
codes. Convert codes to engineering units in application code using the
board's metrology information.

Open a device by server-local slot:

```python
client.open_lcard(
    slot: int,
    firmware_path: str | None = None,
    *,
    timeout: int = 5000,
) -> LcardDevice
```

Some boards require a server-local firmware path; devices with resident
firmware use `None`. `device.info` is an immutable `LcardDeviceInfo` containing
`board_type`, `board_name`, `revision`, `dac_present`, and `capabilities`. Test a
capability with `device.info.supports(LcardCapability.READ_ADC_FRAME)`.

Portable channel selectors use:

```python
LcardAdcChannel(
    channel: int,
    range: float = 10.0,
    mode: LcardAdcInputMode = LcardAdcInputMode.DIFFERENTIAL,
)
```

Input modes are `DIFFERENTIAL`, `COMMON_GROUND`, and `ZERO`. Advanced
applications that already have a vendor logical-channel code can use
`LcardAdcChannel.raw(code)`.

### Device API

| Method | Result |
| --- | --- |
| `read_adc(channel, *, timeout=5000)` | one signed raw ADC code |
| `read_adc_frame(channels, rate_khz=100, *, timeout=5000)` | `LcardAdcFrame(codes, actual_rate_khz)` |
| `write_dac(channel, code, *, timeout=5000)` | writes one uint16 code to DAC 0 or 1 |
| `write_dac_frames(dac0, dac1, frame_rate_khz, *, timeout=5000)` | `LcardDacWriteResult(frames_written, actual_rate_khz)` |
| `close(*, timeout=5000)` | stops streams and releases the device |

ADC frames accept 1..128 channels. Timed DAC arrays must be equal-length,
contain 1..262,144 uint16 codes each, and describe simultaneous DAC0/DAC1
frames. Capability flags are `READ_ADC`, `READ_ADC_FRAME`, `WRITE_DAC`, and
`WRITE_DAC_FRAMES`; not every board supports every operation.

```python
from nrpc import LcardAdcChannel, NrpcClient

with NrpcClient("127.0.0.1", 9000) as client:
    with client.open_lcard(
        0, firmware_path=r"C:\LCard\L780.bio", timeout=5000
    ) as device:
        channel = LcardAdcChannel(0, range=10.0)
        print(device.info)
        print("single code:", device.read_adc(channel, timeout=1000))
        frame = device.read_adc_frame(
            [channel], rate_khz=100.0, timeout=1000
        )
        print(frame.codes, frame.actual_rate_khz)
```

## Errors

The package defines this nRPC-specific hierarchy:

```text
NrpcError
|- ProtocolError
`- RemoteError
```

- `RemoteError` means the server or backend returned an error response. It
  exposes `code`, `function_index`, `status`, `detail`, `description`, and
  `function_name`.
- `ProtocolError` means the peer response violates nRPC framing or value rules.
- `ValueError`, `TypeError`, and occasionally `struct.error` report invalid
  local input before or during encoding.
- `ConnectionError`, `TimeoutError`, `OSError`, and `ssl.SSLError` report
  transport or TLS failures.
- `RuntimeError` from a backend proxy means a response had an unexpected shape
  or an operation was invalid for that proxy's state/type.

Typical handling:

```python
from nrpc import NrpcClient, ProtocolError, RemoteError

try:
    with NrpcClient("127.0.0.1", 9000) as client:
        result = client.call(42, timeout=1000)
except RemoteError as error:
    print(error.function_index, error.code, error.description, error.detail)
except ProtocolError as error:
    print("invalid nRPC response:", error)
except OSError as error:
    print("connection failed:", error)
```

Server-reserved errors use codes `1001..1004`; TCP uses `2001..2007`, serial
`3001..3008`, NI-DAQmx `5001..5006`, and LCard `6001..6007`. Refer to the server
README for the complete meanings and native runtime requirements.

## Architecture and wire behavior

The call path is deliberately small:

```text
Python values / TypedValue
    -> encode 16-byte header, variable table, and data in network byte order
    -> persistent socket or TLS stream
    -> read and validate exact 16-byte response header
    -> enforce payload limit and read exact payload
    -> decode variables or raise RemoteError
```

`nrpc/client.py` owns the codec, core client, and exception descriptions.
Backend modules translate friendly methods into fixed function indices and
exact `TypedValue` arguments. They validate both caller input and response
shape. `nrpc/__init__.py` is the public export boundary; internal codec helpers
and numeric backend constants are not public API.

nRPC uses network byte order for every multibyte number. Reserved bytes must be
zero, strings must end in NUL, boolean bytes must be zero or one, response
function indices must match their requests, and no trailing payload is allowed.
The client treats violations as `ProtocolError` rather than attempting to
recover a potentially desynchronized persistent connection.

## Examples

The examples accept `--help` and can be run after installing the package:

```sh
python examples/basic_rpc.py --host 127.0.0.1 --port 9000
python examples/tls_rpc.py --ca-cert server.crt --server-hostname nrpc.example.com
python examples/tcp_scpi.py --device-host 192.0.2.10 --device-port 5025
python examples/serial_scpi.py --port COM7 --baud-rate 115200
python examples/nidaqmx_voltage_input.py --channel Dev1/ai0 --samples 10
python examples/lcard_raw_adc.py --slot 0 --channel 0
```

TCP, serial, NI-DAQmx, and LCard examples require the matching server-side
equipment and runtime. The basic echo example only requires the sample server.

## Development and testing

Run the complete dependency-free unit suite from the repository root:

```sh
python -m unittest discover -s tests -v
```

Run a focused module while developing:

```sh
python -m unittest tests.test_codec -v
python -m unittest tests.test_tcp_backend -v
```

The tests cover strict codec behavior, public exports, TLS wrapping, buffered
TCP/serial reads, and NI-DAQmx/LCard request serialization using fake clients.
Cross-repository end-to-end tests live in the server repository and run the
compiled server with this source tree. Configure the server with:

```sh
cmake -S ../nrpc-server -B ../nrpc-server/build \
  -DNRPC_PYTHON_CLIENT_SOURCE_DIR=/absolute/path/to/nrpc-client
cmake --build ../nrpc-server/build --parallel
ctest --test-dir ../nrpc-server/build --output-on-failure
```

## Troubleshooting

### `ModuleNotFoundError: No module named 'nrpc'`

Install this repository with `python -m pip install --editable .`, run from its
root, or set `PYTHONPATH` to the repository root. The package name is `nrpc`,
not `nrpc-client`.

### Connection refused or timed out

Confirm the server is running, the host/port match its listener, and the
firewall allows the connection. `127.0.0.1` refers to the Python machine; use
the server's network address when it is remote.

### TLS fails but plaintext works

Confirm the server listener is TLS-enabled, the CA file trusts its certificate,
and `server_hostname` matches a certificate DNS name. A plaintext listener
cannot complete a TLS handshake, and a TLS listener cannot serve plaintext.

### A TCP or serial device cannot be reached

The backend opens the device from the server machine, not from Python. Test
routing, DNS, serial port names, permissions, and vendor runtimes on the server.
Inspect the `RemoteError.detail` and the server's `nrpc.log`.

### `read_until` never finds the terminator

Verify the instrument's actual line ending and encoding. Some devices use
`\r\n`, `\r`, a binary length prefix, or no terminator. Set the matching
terminator or use `read()` and implement the device framing in application code.

### Calls are unexpectedly sequential

One `NrpcClient` intentionally permits one in-flight request. Open a separate
client connection per concurrent workflow. Do not share a backend handle across
clients because server handles are scoped to the connection that created them.
