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
