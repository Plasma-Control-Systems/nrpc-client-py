#!/usr/bin/env python3
"""Send a SCPI query through the nRPC serial backend."""

import argparse

from nrpc import NrpcClient, SerialBackend, SerialParity


def scpi_query(
    serial: SerialBackend, command: str, timeout: int
) -> str:
    """Send one newline-delimited SCPI query and return its response."""

    request = command.encode("ascii") + b"\n"
    written = serial.write(request, timeout=timeout)
    if written != len(request):
        raise RuntimeError(
            f"short serial write: {written} of {len(request)} bytes"
        )
    return serial.read_until(b"\n", timeout=timeout).decode("ascii").rstrip()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--nrpc-host", default="127.0.0.1")
    parser.add_argument("--nrpc-port", type=int, default=9000)
    parser.add_argument("--port", required=True, help="COM port or device path")
    parser.add_argument("--baud-rate", type=int, default=9600)
    parser.add_argument(
        "--parity",
        choices=["none", "odd", "even", "mark", "space"],
        default="none",
    )
    parser.add_argument("--command", default="*IDN?")
    parser.add_argument("--timeout", type=int, default=1000)
    arguments = parser.parse_args()

    parity = SerialParity[arguments.parity.upper()]
    with NrpcClient(arguments.nrpc_host, arguments.nrpc_port) as client:
        with client.open_serial_backend(
            arguments.port,
            baud_rate=arguments.baud_rate,
            parity=parity,
            timeout=arguments.timeout,
        ) as serial:
            response = scpi_query(
                serial, arguments.command, arguments.timeout
            )
    print(response)


if __name__ == "__main__":
    main()

