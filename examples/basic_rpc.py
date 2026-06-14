#!/usr/bin/env python3
"""Call the sample server's echo backend."""

import argparse

from nrpc import DataType, NrpcClient, TypedValue


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9000)
    parser.add_argument("--timeout", type=int, default=1000)
    arguments = parser.parse_args()

    request = [
        TypedValue(DataType.UINT32, [1, 2, 3]),
        "hello from Python",
        b"\x00\x01\x02",
        True,
    ]
    with NrpcClient(arguments.host, arguments.port) as client:
        response = client.call(0, request, timeout=arguments.timeout)

    print(f"response: {response!r}")


if __name__ == "__main__":
    main()

