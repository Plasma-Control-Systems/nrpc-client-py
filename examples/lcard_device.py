#!/usr/bin/env python3
"""Inspect an LCard device and perform simple asynchronous I/O."""

import argparse

from nrpc import (
    E140Backend,
    E154Backend,
    E310Backend,
    E440Backend,
    L780Backend,
    L791Backend,
    LCardBoardType,
    NrpcClient,
)


def integer(value: str) -> int:
    """Parse decimal or 0x-prefixed command-line integers."""

    return int(value, 0)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--nrpc-host", default="127.0.0.1")
    parser.add_argument("--nrpc-port", type=int, default=9000)
    parser.add_argument(
        "--board",
        choices=[board.name for board in LCardBoardType],
        required=True,
        help="expected board type in the selected slot",
    )
    parser.add_argument("--slot", type=int, default=0)
    parser.add_argument(
        "--bios",
        default="",
        help="optional BIOS or PLD path passed to the LCard driver",
    )
    parser.add_argument("--adc-channel", type=integer, default=0)
    parser.add_argument("--adc-mode", type=integer, default=0)
    parser.add_argument(
        "--ttl-output",
        type=integer,
        help="optional TTL value to write, for example 0xA525",
    )
    parser.add_argument(
        "--dac-output",
        type=integer,
        help="optional asynchronous DAC value to write",
    )
    parser.add_argument("--timeout", type=int, default=1000)
    arguments = parser.parse_args()
    board = LCardBoardType[arguments.board]

    with NrpcClient(arguments.nrpc_host, arguments.nrpc_port) as client:
        with client.open_lcard_backend(
            board,
            arguments.slot,
            bios=arguments.bios,
            timeout=arguments.timeout,
        ) as device:
            info = device.slot_info(timeout=arguments.timeout)
            print(
                f"board_type={info.board_type} "
                f"dsp_type={info.dsp_type} irq={info.irq}"
            )

            if isinstance(
                device,
                (L780Backend, L791Backend, E440Backend, E140Backend, E154Backend),
            ):
                sample = device.adc_sample(
                    arguments.adc_channel, timeout=arguments.timeout
                )
                print(f"adc[{arguments.adc_channel}]={sample}")
            elif isinstance(device, E310Backend):
                device.configure_adc(
                    0xF0,
                    external_start=bool(arguments.adc_mode),
                    timeout=arguments.timeout,
                )
                print(f"adc={device.read_adc(timeout=arguments.timeout)}")
            else:
                print("asynchronous ADC sampling is not supported")

            if arguments.ttl_output is not None:
                device.write_ttl(
                    arguments.ttl_output, timeout=arguments.timeout
                )
                print(f"ttl_output=0x{arguments.ttl_output:x}")

            if arguments.dac_output is not None:
                if isinstance(
                    device, (L780Backend, E440Backend, E140Backend)
                ):
                    device.write_dac(
                        0, arguments.dac_output, timeout=arguments.timeout
                    )
                    print(f"dac[0]={arguments.dac_output}")
                elif isinstance(device, E154Backend):
                    device.write_dac(
                        arguments.dac_output, timeout=arguments.timeout
                    )
                    print(f"dac={arguments.dac_output}")
                else:
                    print("single-value DAC output is not supported")


if __name__ == "__main__":
    main()
