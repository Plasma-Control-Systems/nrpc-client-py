#!/usr/bin/env python3
"""Inspect an LCard device and perform simple asynchronous I/O."""

import argparse

from nrpc import (
    E140Backend,
    E154Backend,
    E2010Backend,
    E440Backend,
    L780Backend,
    L791Backend,
    LCardAdcInputMode,
    LCardBoardType,
    NrpcClient,
)


ADC_INPUT_MODES = {
    "differential": LCardAdcInputMode.DIFFERENTIAL,
    "single-ended": LCardAdcInputMode.SINGLE_ENDED,
    "zero": LCardAdcInputMode.ZERO,
}


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
        help="override the server's automatic BIOS or PLD lookup",
    )
    parser.add_argument("--adc-channel", type=integer, default=0)
    parser.add_argument(
        "--adc-input-mode",
        choices=tuple(ADC_INPUT_MODES),
        default="differential",
        help="ADC input mode for E140/E440",
    )
    parser.add_argument(
        "--adc-input-range",
        type=float,
        help="ADC voltage range; when omitted the client uses the board default",
    )
    parser.add_argument(
        "--e2010-adc-input-mask",
        type=integer,
        help="optional E20-10 ADC input mask; defaults to signal input on the selected channel",
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

            if isinstance(device, E2010Backend):
                sample_kwargs = {}
                if arguments.e2010_adc_input_mask is not None:
                    sample_kwargs["adc_input_mask"] = arguments.e2010_adc_input_mask
                sample = device.adc_voltage(
                    arguments.adc_channel,
                    input_range=arguments.adc_input_range,
                    timeout=arguments.timeout,
                    **sample_kwargs,
                )
                print(f"adc[{arguments.adc_channel}]={sample:g} V")
            elif isinstance(
                device, (L780Backend, L791Backend, E440Backend, E140Backend, E154Backend)
            ):
                sample = device.adc_voltage(
                    arguments.adc_channel,
                    input_mode=ADC_INPUT_MODES[arguments.adc_input_mode],
                    input_range=arguments.adc_input_range,
                    timeout=arguments.timeout,
                )
                print(f"adc[{arguments.adc_channel}]={sample:g} V")
            else:
                print("ADC stream sampling is not supported")

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
