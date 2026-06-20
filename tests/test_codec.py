import struct
import unittest

from nrpc.client import (
    DataType,
    NrpcClient,
    ProtocolError,
    RemoteError,
    TypedValue,
    _encode_request,
)


class CodecTests(unittest.TestCase):
    def test_remote_error_includes_readable_details(self):
        error = RemoteError(5003, 64)

        self.assertEqual(error.code, 5003)
        self.assertEqual(error.function_index, 64)
        self.assertEqual(error.status, 1)
        self.assertEqual(error.description, "NI-DAQmx task creation failed")
        self.assertIn("create NI-DAQmx analog voltage input task", str(error))
        self.assertIn("status 1, error code 5003", str(error))

    def test_unknown_remote_error_has_readable_fallback(self):
        error = RemoteError(9999, 250)

        self.assertIn("unregistered nRPC function", str(error))
        self.assertIn("unknown remote backend error", str(error))

    def test_builtin_server_error_includes_server_defined_meaning(self):
        error = RemoteError(3, 1)

        self.assertEqual(error.function_name, "sleep")
        self.assertEqual(
            error.description, "sleep expects one uint32 duration"
        )

    def test_request_uses_network_byte_order(self):
        packet = _encode_request(
            7, [TypedValue(DataType.UINT32, 0x11223344), "ok"], 0x01020304
        )
        self.assertEqual(packet[:4], bytes([0xF0, 1, 7, 2]))
        self.assertEqual(packet[8:12], b"\x01\x02\x03\x04")
        self.assertEqual(packet[-7:-3], b"\x11\x22\x33\x44")
        self.assertEqual(packet[-3:], b"ok\0")

    def test_response_payload_decodes_all_categories(self):
        table = b"".join(
            [
                struct.pack("!B3xII4x", DataType.INT16, 4, 2),
                struct.pack("!B3xII4x", DataType.BOOL, 2, 2),
                struct.pack("!B3xII4x", DataType.STRING, 3, 3),
            ]
        )
        payload = table + struct.pack("!2h", -1, 2) + b"\x01\x00ok\0"
        self.assertEqual(
            NrpcClient._decode_payload(3, payload),
            [[-1, 2], [True, False], "ok"],
        )

    def test_trailing_payload_is_rejected(self):
        with self.assertRaises(ProtocolError):
            NrpcClient._decode_payload(0, b"x")

    def test_nonzero_variable_reserved_bytes_are_rejected(self):
        payload = struct.pack("!B3sII4s", DataType.BYTES, b"\0\0\x01", 0, 0, b"\0" * 4)
        with self.assertRaises(ProtocolError):
            NrpcClient._decode_payload(1, payload)


if __name__ == "__main__":
    unittest.main()
