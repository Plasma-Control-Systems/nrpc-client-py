# nRPC Python Client

`nrpc-client` is the synchronous and asynchronous Python client library for
nRPC 0.1.0. It is dependency-free, typed, and supports Python 3.10 or newer on
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

## Async RPC

The asyncio interface uses the same values and exceptions as the synchronous
client:

```python
import asyncio

from nrpc import AsyncNrpcClient


async def main() -> None:
    async with AsyncNrpcClient("127.0.0.1", 9000) as client:
        response = await client.call(0, ["hello"], timeout=1000)
        print(response)


asyncio.run(main())
```

For explicit lifecycle management, use
`client = await AsyncNrpcClient.connect(...)` and `await client.close()`.

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

The asynchronous equivalent is opened and used with `await`:

```python
async with AsyncNrpcClient("127.0.0.1", 9000) as client:
    async with await client.open_tcp_backend("192.0.2.10", 5025) as tcp:
        await tcp.write(b"*IDN?\n", timeout=1000)
        response = await tcp.read_until(b"\n", timeout=1000)
```

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

`AsyncNrpcClient.open_serial_backend` returns an `AsyncSerialBackend` with
async `write`, `read`, `read_until`, and `close` methods.

## LCard Backend

On a Windows server built with the LCard lcomp/wlcomp backend,
`LCardBackend` opens a board by slot and provides the wrapper's common
asynchronous ADC, TTL, and DAC operations:

```python
from nrpc import E140Backend, LCardBoardType, NrpcClient

with NrpcClient("127.0.0.1", 9000) as client:
    with client.open_lcard_backend(
        LCardBoardType.E140, slot=0, bios="e140"
    ) as device:
        assert isinstance(device, E140Backend)
        info = device.slot_info()
        sample = device.adc_sample(0)
        device.write_ttl(0xA525)
        print(info, sample)
```

The requested board type is checked against the physical slot. The returned
proxy is device-specific: `L780Backend`, `L791Backend`, `E440Backend`,
`E140Backend`, `E154Backend`, `E2010Backend`, or `E310Backend`. Their helper
sets reflect the vendor implementations; for example, E2010 has no
asynchronous ADC sample helper, E310 reads four configured ADC channels, and
L791 writes DAC values as a channel pair. The asynchronous client returns the
matching `Async...Backend` class with awaited helpers.

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
and digital inputs and outputs. `AsyncNrpcClient` provides the same factories;
its task operations are awaited. Tasks are cleared on close or disconnect.

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
