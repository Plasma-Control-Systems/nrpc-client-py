#!/usr/bin/env python3
"""Read Modbus holding registers through an nRPC TCP backend."""

import argparse

from nrpc import ModbusTcpClient, NrpcClient


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--nrpc-host", default="127.0.0.1")
    parser.add_argument("--nrpc-port", type=int, default=9000)
    parser.add_argument("--device-host", required=True)
    parser.add_argument("--device-port", type=int, default=502)
    parser.add_argument("--unit-id", type=int, default=1)
    parser.add_argument("--address", type=int, default=0)
    parser.add_argument("--count", type=int, default=1)
    parser.add_argument("--timeout", type=int, default=1000)
    args = parser.parse_args()

    with NrpcClient(args.nrpc_host, args.nrpc_port) as client:
        with client.open_tcp_backend(
            args.device_host, args.device_port, timeout=args.timeout
        ) as transport:
            with ModbusTcpClient(transport, unit_id=args.unit_id) as modbus:
                values = modbus.read_holding_registers(
                    args.address, args.count, timeout=args.timeout
                )
                print(values)


if __name__ == "__main__":
    main()
