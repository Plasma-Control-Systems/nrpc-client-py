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

## Modbus TCP

Read holding registers through a TCP connection opened by the nRPC server:

```sh
python examples/modbus_tcp.py \
  --nrpc-port 9000 \
  --device-host 192.0.2.20 \
  --unit-id 1 \
  --address 100 \
  --count 4
```

## Modbus RTU

Read holding registers through a serial port opened by the nRPC server:

```sh
python examples/modbus_rtu.py \
  --nrpc-port 9000 \
  --port /dev/ttyUSB0 \
  --baud-rate 19200 \
  --unit-id 7 \
  --address 0 \
  --count 8
```

The RTU example uses 8 data bits, even parity, and one stop bit. Adjust the
example if the slave uses a different serial configuration.

## GPIO

Read an input line on the Linux server:

```sh
python examples/gpio_control.py --chip /dev/gpiochip0 --offset 17
```

Request an output and set its logical value:

```sh
python examples/gpio_control.py \
  --chip /dev/gpiochip0 \
  --offset 17 \
  --output \
  --value 1
```

Use `gpioinfo` on the server to find the correct offset. Physical header pin
numbers are board-specific and are not accepted directly.

## SPI

Read the JEDEC identifier of an SPI flash attached to the Linux server:

```sh
python examples/spi_flash_id.py --device /dev/spidev0.0 --speed 1000000
```

The server must expose the controller as a spidev device and have read/write
permission for it. The example sends command `0x9f` in SPI mode 0.

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

## LCard Raw ADC

Install LComp on the Windows server and supply a server-local BIOS/PLD path for
boards that require downloadable firmware:

```powershell
python examples/lcard_raw_adc.py `
  --slot 0 `
  --firmware "C:\Program Files (x86)\LCard\LIBRARY\BIOS\L780.bio" `
  --channel 0 `
  --range 10 `
  --timeout 1000
```

Omit `--firmware` for boards with resident firmware. The printed ADC values
are signed raw codes, not volts.
