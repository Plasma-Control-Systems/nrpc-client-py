#!/usr/bin/env python3
"""Send a SCPI query through the nRPC TCP backend."""

import argparse

from nrpc import NrpcClient, TcpBackend


def scpi_query(tcp: TcpBackend, command: str, timeout: int) -> str:
    """Send one newline-delimited SCPI query and return its response."""

    request = command.encode("ascii") + b"\n"
    written = tcp.write(request, timeout=timeout)
    if written != len(request):
        raise RuntimeError(f"short TCP write: {written} of {len(request)} bytes")
    return tcp.read_until(b"\n", timeout=timeout).decode("ascii").rstrip()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--nrpc-host", default="127.0.0.1")
    parser.add_argument("--nrpc-port", type=int, default=9000)
    parser.add_argument("--device-host", required=True)
    parser.add_argument("--device-port", type=int, default=5025)
    parser.add_argument("--command", default="*IDN?")
    parser.add_argument("--timeout", type=int, default=1000)
    arguments = parser.parse_args()

    with NrpcClient(arguments.nrpc_host, arguments.nrpc_port) as client:
        with client.open_tcp_backend(
            arguments.device_host,
            arguments.device_port,
            timeout=arguments.timeout,
        ) as tcp:
            response = scpi_query(tcp, arguments.command, arguments.timeout)

    print(response)


if __name__ == "__main__":
    main()

