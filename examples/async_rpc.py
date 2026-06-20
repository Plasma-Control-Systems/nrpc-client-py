#!/usr/bin/env python3
"""Call the sample server's echo backend asynchronously."""

import argparse
import asyncio

from nrpc import AsyncNrpcClient, DataType, TypedValue


async def run(host: str, port: int, timeout: int) -> None:
    request = [
        TypedValue(DataType.UINT32, [1, 2, 3]),
        "hello from async Python",
        b"\x00\x01\x02",
        True,
    ]
    async with AsyncNrpcClient(host, port) as client:
        response = await client.call(0, request, timeout=timeout)

    print(f"response: {response!r}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9000)
    parser.add_argument("--timeout", type=int, default=1000)
    arguments = parser.parse_args()

    asyncio.run(run(arguments.host, arguments.port, arguments.timeout))


if __name__ == "__main__":
    main()
