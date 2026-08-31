import unittest
from unittest.mock import Mock

from nrpc import NrpcClient, ProtocolError, ServerInfo


class DiscoveryTests(unittest.TestCase):
    def client_with_response(self, response):
        client = object.__new__(NrpcClient)
        client.call = Mock(return_value=response)
        return client

    def test_get_server_info_returns_typed_metadata(self):
        client = self.client_with_response(
            ["1.0.0", 1, "linux", "x86_64", [0, 1, 2, 16, 17]]
        )

        info = client.get_server_info(timeout=250)

        self.assertEqual(
            info,
            ServerInfo("1.0.0", 1, "linux", "x86_64", (0, 1, 2, 16, 17)),
        )
        client.call.assert_called_once_with(2, timeout=250)

    def test_get_server_info_rejects_malformed_shape(self):
        malformed = [
            [],
            ["1.0.0", 1, "linux", "x86_64", 2],
            ["1.0.0", 1, "darwin", "arm64", [0, 2]],
            ["1.0.0", 1, "linux", "x86_64", [2, 0]],
            ["1.0.0", 1, "linux", "x86_64", [0, 1]],
            ["1.0.0", True, "linux", "x86_64", [0, 2]],
        ]
        for response in malformed:
            with self.subTest(response=response):
                with self.assertRaises(ProtocolError):
                    self.client_with_response(response).get_server_info()


if __name__ == "__main__":
    unittest.main()
