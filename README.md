# nRPC Python Client

`nrpc-client` is the synchronous Python client library for nRPC 0.1.0. It is
dependency-free, typed, and supports Python 3.10 or newer on
Linux, macOS, and Windows. The protocol definition is included in
[SPEC.md](SPEC.md).

## Install

From this repository:

```sh
python -m pip install .
```

For editable development:

```sh
python -m pip install --editable .
```

The distribution is named `nrpc-client`; the import package is `nrpc`.

## Basic RPC

```python
from nrpc import DataType, NrpcClient, TypedValue

with NrpcClient("127.0.0.1", 9000) as client:
    response = client.call(
        0,
        [
            TypedValue(DataType.UINT32, [1, 2, 3]),
            "hello",
            b"\x00\x01",
        ],
        timeout=1000,
    )
    print(response)
```

Plain Python values map as follows:

| Python | nRPC |
| --- | --- |
| `None` | `null` |
| `bool` | `bool` |
| `int` | `int64` |
| `float` | `float64` |
| `str` | UTF-8 `string` |
| bytes-like | `bytes` |

Use `TypedValue` when the exact numeric type or an array is required.

## TLS

Pass an `ssl.SSLContext` to encrypt the connection and verify the server
certificate:

```python
import ssl

from nrpc import NrpcClient

tls = ssl.create_default_context(cafile="server.crt")
with NrpcClient(
    "127.0.0.1",
    9000,
    ssl_context=tls,
    server_hostname="nrpc.example.com",
) as client:
    print(client.call(0, ["hello over TLS"]))
```

`server_hostname` defaults to the connection host. Supplying it separately is
useful when connecting by IP address to a certificate issued for a DNS name.

## TCP Backend

`TcpBackend` controls a server-side operating-system TCP socket. It is
protocol-neutral:

```python
from nrpc import NrpcClient

with NrpcClient("127.0.0.1", 9000) as client:
    with client.open_tcp_backend("192.0.2.10", 5025, timeout=1000) as tcp:
        tcp.write(b"*IDN?\n", timeout=1000)
        response = tcp.read_until(b"\n", timeout=1000)
        print(response.decode("ascii").rstrip())
```

Instrument protocols such as SCPI belong in application code and are composed
from `write`, `read`, and `read_until`.

## Serial Backend

`SerialBackend` controls a serial port opened by the nRPC server through
libserialport:

```python
from nrpc import NrpcClient, SerialFlowControl, SerialParity

with NrpcClient("127.0.0.1", 9000) as client:
    with client.open_serial_backend(
        "/dev/ttyUSB0",
        baud_rate=115200,
        data_bits=8,
        parity=SerialParity.NONE,
        stop_bits=1,
        flow_control=SerialFlowControl.NONE,
        timeout=1000,
    ) as serial:
        serial.write(b"*IDN?\n", timeout=1000)
        response = serial.read_until(b"\n", timeout=1000)
```

Use port names such as `/dev/ttyUSB0`, `/dev/cu.usbserial-*`, or `COM7`
according to the operating system.

## NI-DAQmx Backend

The Windows nRPC server can host NI-DAQmx tasks while this client remains
platform-independent:

```python
from nrpc import NidaqmxTerminalConfig, NrpcClient

with NrpcClient("127.0.0.1", 9000) as client:
    with client.create_nidaqmx_ai_voltage(
        "Dev1/ai0", terminal=NidaqmxTerminalConfig.DIFFERENTIAL
    ) as task:
        task.start()
        print(task.read(10, timeout=1000))
```

Factories are provided for voltage and thermocouple inputs, voltage outputs,
and digital inputs and outputs. Tasks are cleared on close or disconnect.

## LCard Backend

The Windows server can host LCard devices through the vendor WLCOMP adapter while the Python
client remains platform-independent. ADC and DAC values are raw codes:

```python
from nrpc import LcardAdcChannel, NrpcClient

with NrpcClient("127.0.0.1", 9000) as client:
    with client.open_lcard(0, firmware_path=r"C:\LCard\L780.bio") as device:
        channel = LcardAdcChannel(0, 10.0)
        print(device.info)
        print(device.read_adc(channel, timeout=1000))
        print(device.read_adc_frame([channel], rate_khz=100, timeout=1000))
```

Use `LcardAdcChannel.raw(code)` when an application already has a vendor
logical-channel code. Timed DAC output accepts equal-length DAC0 and DAC1 code
arrays and reports the hardware-normalized frame rate. Handles and active
streams are released on close or client disconnect.

## Errors

- `RemoteError`: the server or backend returned an error. Its message includes
  readable function and error descriptions in addition to the numeric status
  and error code.
- `ProtocolError`: the server response violated the nRPC wire format.
- `ConnectionError`, `TimeoutError`, and other socket errors: transport failure.

`RemoteError.code`, `RemoteError.function_index`, `RemoteError.status`,
`RemoteError.description`, and `RemoteError.function_name` expose the remote
failure details.

See [`examples/`](examples/) for complete command-line programs.

The C++ server is maintained in the separate `nrpc-server` repository.
