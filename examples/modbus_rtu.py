#!/usr/bin/env python3
"""Read Modbus holding registers through an nRPC serial backend."""

import argparse

from nrpc import ModbusRtuClient, NrpcClient, SerialParity


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--nrpc-host", default="127.0.0.1")
    parser.add_argument("--nrpc-port", type=int, default=9000)
    parser.add_argument("--port", required=True)
    parser.add_argument("--baud-rate", type=int, default=9600)
    parser.add_argument("--unit-id", type=int, default=1)
    parser.add_argument("--address", type=int, default=0)
    parser.add_argument("--count", type=int, default=1)
    parser.add_argument("--timeout", type=int, default=1000)
    args = parser.parse_args()

    with NrpcClient(args.nrpc_host, args.nrpc_port) as client:
        with client.open_serial_backend(
            args.port,
            baud_rate=args.baud_rate,
            data_bits=8,
            parity=SerialParity.EVEN,
            stop_bits=1,
            timeout=args.timeout,
        ) as transport:
            with ModbusRtuClient(transport, unit_id=args.unit_id) as modbus:
                values = modbus.read_holding_registers(
                    args.address, args.count, timeout=args.timeout
                )
                print(values)


if __name__ == "__main__":
    main()
