#!/usr/bin/env python3
"""Read or set a GPIO line through an nRPC server using libgpiod."""

import argparse

from nrpc import GpioDirection, NrpcClient


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--nrpc-host", default="127.0.0.1")
    parser.add_argument("--nrpc-port", type=int, default=9000)
    parser.add_argument("--chip", default="/dev/gpiochip0")
    parser.add_argument("--offset", type=int, required=True)
    parser.add_argument("--output", action="store_true")
    parser.add_argument("--value", type=int, choices=(0, 1), default=0)
    parser.add_argument("--active-low", action="store_true")
    parser.add_argument("--timeout", type=int, default=5000)
    arguments = parser.parse_args()

    direction = (
        GpioDirection.OUTPUT if arguments.output else GpioDirection.INPUT
    )
    with NrpcClient(arguments.nrpc_host, arguments.nrpc_port) as client:
        with client.open_gpio_line(
            arguments.chip,
            arguments.offset,
            direction,
            initial_value=bool(arguments.value),
            active_low=arguments.active_low,
            consumer="nrpc-gpio-control",
            timeout=arguments.timeout,
        ) as line:
            if arguments.output:
                line.write(bool(arguments.value), timeout=arguments.timeout)
            print(int(line.read(timeout=arguments.timeout)))


if __name__ == "__main__":
    main()
