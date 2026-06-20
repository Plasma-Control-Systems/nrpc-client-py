#!/usr/bin/env python3
"""Read voltage samples through the server-side NI-DAQmx backend."""

import argparse

from nrpc import NidaqmxTerminalConfig, NrpcClient


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--nrpc-host", default="127.0.0.1")
    parser.add_argument("--nrpc-port", type=int, default=9000)
    parser.add_argument(
        "--channel",
        default="Dev1/ai0",
        help="NI-DAQmx physical channel, for example Dev1/ai0",
    )
    parser.add_argument("--minimum", type=float, default=-10.0)
    parser.add_argument("--maximum", type=float, default=10.0)
    parser.add_argument(
        "--terminal",
        choices=[terminal.name for terminal in NidaqmxTerminalConfig],
        default=NidaqmxTerminalConfig.DEFAULT.name,
    )
    parser.add_argument("--samples", type=int, default=1)
    parser.add_argument("--timeout", type=int, default=1000)
    arguments = parser.parse_args()

    terminal = NidaqmxTerminalConfig[arguments.terminal]
    with NrpcClient(arguments.nrpc_host, arguments.nrpc_port) as client:
        with client.create_nidaqmx_ai_voltage(
            arguments.channel,
            arguments.minimum,
            arguments.maximum,
            terminal=terminal,
            timeout=arguments.timeout,
        ) as task:
            task.start(timeout=arguments.timeout)
            values = task.read(arguments.samples, timeout=arguments.timeout)

    for index, value in enumerate(values):
        print(f"sample[{index}]={value:.9g} V")


if __name__ == "__main__":
    main()
