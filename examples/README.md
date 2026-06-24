# Examples

Build and start the sample server from the separate `nrpc-server` repository
before running these programs:

```sh
cmake -S ../nrpc-server -B ../nrpc-server/build -DCMAKE_BUILD_TYPE=Debug
cmake --build ../nrpc-server/build -j
../nrpc-server/build/nrpc_server 9000
```

## Basic RPC

Calls function `0`, the sample echo backend:

```sh
python examples/basic_rpc.py --port 9000
```

The asynchronous client can call the same backend without blocking the event
loop:

```sh
python examples/async_rpc.py --port 9000
```

## TLS RPC

Start a TLS-only server with its certificate and private key:

```sh
../nrpc-server/build/nrpc_server 9000 \
  --tls-cert server.crt \
  --tls-key server.key
```

Then call the echo backend using the certificate as the trust anchor. Specify
the name in the certificate when connecting through a different host or IP:

```sh
python examples/tls_rpc.py \
  --port 9000 \
  --ca-cert server.crt \
  --server-hostname nrpc.example.com
```

## TCP and SCPI

Routes `*IDN?` through the server-side TCP backend to a SCPI device:

```sh
python examples/tcp_scpi.py \
  --nrpc-port 9000 \
  --device-host 192.0.2.10 \
  --device-port 5025
```

To use the repository's mock power supply:

```sh
python ../nrpc-server/tests/mock_scpi_power_supply.py --port 5025
python examples/tcp_scpi.py \
  --nrpc-port 9000 \
  --device-host 127.0.0.1 \
  --device-port 5025
```

## Serial and SCPI

Routes `*IDN?` through a serial port opened by the nRPC server:

```sh
python examples/serial_scpi.py \
  --nrpc-port 9000 \
  --port /dev/ttyUSB0 \
  --baud-rate 115200
```

On Windows, use a port name such as `COM7`.

## LCard Device

On Windows, inspect slot `0` and read one ADC voltage sample:

```powershell
python examples/lcard_device.py `
  --nrpc-port 9000 `
  --board E140 `
  --slot 0 `
  --adc-channel 0 `
  --adc-input-mode single-ended `
  --adc-input-range 2.5
```

The Windows server loads a matching BIOS or PLD file automatically from the
default LCard BIOS directory when one is present. Pass `--bios` only to
override that lookup, and optionally exercise DAC output:

```powershell
python examples/lcard_device.py `
  --board E140 `
  --bios C:\LCard\BIOS\L761.bio `
  --dac-output 123
```

The nRPC server must be built on Windows with the LCard backend enabled and
the matching lcomp/wlcomp installation available.

## E14-440 ADC Channels

Read several E14-440 ADC channels with per-channel input mode and voltage
range:

```powershell
python examples/e440_adc_channels.py `
  --nrpc-port 9000 `
  --slot 0 `
  --channel 0:differential:10 `
  --channel 1:single-ended:2.5 `
  --channel 2:zero:0.625
```

Each `--channel` value is `LINE[:MODE[:RANGE]]`. Supported modes are
`differential`, `single-ended`, and `zero`; supported E14-440 ranges are
`10`, `2.5`, `0.625`, and `0.15625` volts.

## NI-DAQmx Voltage Input

On the Windows machine hosting the nRPC server, install the NI-DAQmx runtime
and connect a device exposed as `Dev1`. Read ten differential voltage samples
from analog input `ai0` with:

```powershell
python examples/nidaqmx_voltage_input.py `
  --nrpc-host 127.0.0.1 `
  --nrpc-port 9000 `
  --channel Dev1/ai0 `
  --minimum -10 `
  --maximum 10 `
  --terminal DIFFERENTIAL `
  --samples 10 `
  --timeout 1000
```

The server must be built with `NRPC_ENABLE_NIDAQMX_BACKEND=ON`. Device and
channel names can be confirmed in NI Measurement & Automation Explorer.
