#!/usr/bin/env python3
"""Call the sample server's echo backend over verified TLS."""

import argparse
import ssl

from nrpc import NrpcClient


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9000)
    parser.add_argument(
        "--ca-cert",
        required=True,
        help="CA certificate, or the server certificate when it is self-signed",
    )
    parser.add_argument(
        "--server-hostname",
        help="certificate hostname when it differs from --host",
    )
    parser.add_argument("--timeout", type=int, default=1000)
    arguments = parser.parse_args()

    context = ssl.create_default_context(cafile=arguments.ca_cert)
    with NrpcClient(
        arguments.host,
        arguments.port,
        ssl_context=context,
        server_hostname=arguments.server_hostname,
    ) as client:
        response = client.call(0, ["hello over TLS"], timeout=arguments.timeout)

    print(f"response: {response!r}")


if __name__ == "__main__":
    main()
