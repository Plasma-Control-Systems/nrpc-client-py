import ssl
import unittest
from unittest.mock import Mock, patch

from nrpc import NrpcClient


class TlsClientTests(unittest.TestCase):
    @patch("nrpc.client.socket.create_connection")
    def test_sync_client_wraps_connection_with_tls(self, create_connection):
        connection = Mock()
        tls_socket = Mock()
        context = Mock(spec=ssl.SSLContext)
        create_connection.return_value = connection
        context.wrap_socket.return_value = tls_socket

        client = NrpcClient(
            "127.0.0.1",
            9000,
            ssl_context=context,
            server_hostname="nrpc.example.com",
        )

        context.wrap_socket.assert_called_once_with(
            connection, server_hostname="nrpc.example.com"
        )
        tls_socket.settimeout.assert_called_once_with(None)
        client.close()

    @patch("nrpc.client.socket.create_connection")
    def test_sync_client_closes_socket_when_tls_handshake_fails(
        self, create_connection
    ):
        connection = Mock()
        context = Mock(spec=ssl.SSLContext)
        create_connection.return_value = connection
        context.wrap_socket.side_effect = ssl.SSLError("handshake failed")

        with self.assertRaises(ssl.SSLError):
            NrpcClient("localhost", 9000, ssl_context=context)

        connection.close.assert_called_once_with()

    def test_server_hostname_requires_tls(self):
        with self.assertRaises(ValueError):
            NrpcClient("localhost", 9000, server_hostname="localhost")


if __name__ == "__main__":
    unittest.main()
