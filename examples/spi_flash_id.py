#!/usr/bin/env python3
"""Read a JEDEC ID from an SPI flash through an nRPC Linux server."""

import argparse

from nrpc import NrpcClient, SpiMode


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--nrpc-host", default="127.0.0.1")
    parser.add_argument("--nrpc-port", type=int, default=9000)
    parser.add_argument("--device", default="/dev/spidev0.0")
    parser.add_argument("--speed", type=int, default=1_000_000)
    parser.add_argument("--timeout", type=int, default=5000)
    arguments = parser.parse_args()

    with NrpcClient(arguments.nrpc_host, arguments.nrpc_port) as client:
        with client.open_spi_device(
            arguments.device,
            mode=SpiMode.MODE_0,
            max_speed_hz=arguments.speed,
            timeout=arguments.timeout,
        ) as spi:
            response = spi.transfer(b"\x9f\x00\x00\x00", timeout=arguments.timeout)
            print(response[1:].hex(" "))


if __name__ == "__main__":
    main()
