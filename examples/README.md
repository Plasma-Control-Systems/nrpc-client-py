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

On Windows, inspect slot `0` and read one asynchronous ADC sample:

```powershell
python examples/lcard_device.py `
  --nrpc-port 9000 `
  --board E140 `
  --slot 0 `
  --adc-channel 0
```

Pass a BIOS or PLD path when the board requires one, and optionally exercise
TTL or DAC output:

```powershell
python examples/lcard_device.py `
  --board E140 `
  --bios C:\LCard\BIOS\L761.bio `
  --ttl-output 0xA525 `
  --dac-output 123
```

The nRPC server must be built on Windows with the LCard backend enabled and
the matching lcomp/wlcomp installation available.
