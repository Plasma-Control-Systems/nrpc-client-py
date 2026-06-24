#!/usr/bin/env python3
"""Read configurable ADC voltage channels from an LCard E14-440."""

import argparse
from dataclasses import dataclass

from nrpc import E440Backend, LCardAdcInputMode, LCardBoardType, NrpcClient


ADC_INPUT_MODES = {
    "diff": LCardAdcInputMode.DIFFERENTIAL,
    "differential": LCardAdcInputMode.DIFFERENTIAL,
    "single": LCardAdcInputMode.SINGLE_ENDED,
    "single-ended": LCardAdcInputMode.SINGLE_ENDED,
    "zero": LCardAdcInputMode.ZERO,
}


@dataclass(frozen=True)
class ChannelConfig:
    line: int
    input_mode: LCardAdcInputMode
    input_range: float | None


def parse_channel(value: str) -> ChannelConfig:
    """Parse LINE[:MODE[:RANGE]], for example 0:single-ended:2.5."""

    parts = value.split(":")
    if not 1 <= len(parts) <= 3:
        raise argparse.ArgumentTypeError(
            "channel must be LINE[:MODE[:RANGE]]"
        )
    try:
        line = int(parts[0], 0)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("channel line must be an integer") from exc

    mode = LCardAdcInputMode.DIFFERENTIAL
    if len(parts) >= 2 and parts[1]:
        try:
            mode = ADC_INPUT_MODES[parts[1].lower()]
        except KeyError as exc:
            allowed = ", ".join(sorted(ADC_INPUT_MODES))
            raise argparse.ArgumentTypeError(
                f"mode must be one of: {allowed}"
            ) from exc

    input_range = None
    if len(parts) == 3 and parts[2]:
        try:
            input_range = float(parts[2])
        except ValueError as exc:
            raise argparse.ArgumentTypeError(
                "input range must be a floating-point voltage"
            ) from exc

    return ChannelConfig(line, mode, input_range)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--nrpc-host", default="127.0.0.1")
    parser.add_argument("--nrpc-port", type=int, default=9000)
    parser.add_argument("--slot", type=int, default=0)
    parser.add_argument(
        "--bios",
        default="",
        help="override the server's automatic BIOS lookup",
    )
    parser.add_argument(
        "--channel",
        action="append",
        type=parse_channel,
        required=True,
        help=(
            "ADC channel as LINE[:MODE[:RANGE]], for example "
            "0:differential:10 or 3:single-ended:2.5; repeat for more channels"
        ),
    )
    parser.add_argument("--timeout", type=int, default=1000)
    arguments = parser.parse_args()

    with NrpcClient(arguments.nrpc_host, arguments.nrpc_port) as client:
        with client.open_lcard_backend(
            LCardBoardType.E440,
            arguments.slot,
            bios=arguments.bios,
            timeout=arguments.timeout,
        ) as device:
            if not isinstance(device, E440Backend):
                raise RuntimeError(f"slot contains {device.board.name}, not E440")

            info = device.slot_info(timeout=arguments.timeout)
            print(
                f"board_type={info.board_type.name} "
                f"dsp_type={info.dsp_type} irq={info.irq}"
            )

            for channel in arguments.channel:
                volts = device.adc_voltage(
                    channel.line,
                    input_mode=channel.input_mode,
                    input_range=channel.input_range,
                    timeout=arguments.timeout,
                )
                range_text = (
                    "default"
                    if channel.input_range is None
                    else f"{channel.input_range:g} V"
                )
                print(
                    f"adc[{channel.line}] "
                    f"{channel.input_mode.name.lower()} "
                    f"range={range_text}: {volts:g} V"
                )


if __name__ == "__main__":
    main()
