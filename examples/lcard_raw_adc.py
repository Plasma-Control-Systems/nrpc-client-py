"""Open an LCard device and read raw ADC codes."""

import argparse

from nrpc import LcardAdcChannel, NrpcClient


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--nrpc-host", default="127.0.0.1")
    parser.add_argument("--nrpc-port", type=int, default=9000)
    parser.add_argument("--slot", type=int, default=0)
    parser.add_argument("--firmware")
    parser.add_argument("--channel", type=int, default=0)
    parser.add_argument("--range", type=float, default=10.0, dest="full_scale")
    parser.add_argument("--rate-khz", type=float, default=100.0)
    parser.add_argument("--timeout", type=int, default=5000)
    args = parser.parse_args()

    with NrpcClient(args.nrpc_host, args.nrpc_port) as client:
        with client.open_lcard(
            args.slot, firmware_path=args.firmware, timeout=args.timeout
        ) as device:
            channel = LcardAdcChannel(args.channel, args.full_scale)
            print(device.info)
            print("single:", device.read_adc(channel, timeout=args.timeout))
            frame = device.read_adc_frame(
                [channel], rate_khz=args.rate_khz, timeout=args.timeout
            )
            print("frame:", frame.codes, "actual rate (kHz):", frame.actual_rate_khz)


if __name__ == "__main__":
    main()
