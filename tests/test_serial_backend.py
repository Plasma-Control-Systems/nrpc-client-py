import unittest

from nrpc import (
    DataType,
    SerialBackend,
    SerialFlowControl,
    SerialParity,
    TypedValue,
)
from nrpc.serial_backend import (
    SERIAL_CLOSE,
    SERIAL_OPEN,
    SERIAL_READ,
    SERIAL_WRITE,
)


class FakeClient:
    def __init__(self):
        self.calls = []
        self.reads = [b"12.", b"500\nextra\n"]

    def call(self, function, args=(), timeout=0):
        self.calls.append((function, list(args), timeout))
        if function == SERIAL_OPEN:
            return [91]
        if function == SERIAL_WRITE:
            return [len(args[1])]
        if function == SERIAL_READ:
            return [self.reads.pop(0)]
        if function == SERIAL_CLOSE:
            return []
        raise AssertionError(function)


class SerialBackendTests(unittest.TestCase):
    def test_configuration_and_buffered_read(self):
        client = FakeClient()
        backend = SerialBackend(
            client,
            "COM7",
            baud_rate=115200,
            parity=SerialParity.EVEN,
            flow_control=SerialFlowControl.RTS_CTS,
            timeout=100,
        )

        backend.write(b"MEAS?\n", timeout=250)
        self.assertEqual(backend.read_until(timeout=250), b"12.500\n")
        self.assertEqual(backend.read_until(timeout=250), b"extra\n")
        backend.close()

        open_args = client.calls[0][1]
        self.assertEqual(open_args[1], TypedValue(DataType.UINT32, 115200))
        self.assertEqual(
            open_args[3],
            TypedValue(DataType.UINT8, SerialParity.EVEN.value),
        )
        self.assertEqual(
            open_args[5],
            TypedValue(DataType.UINT8, SerialFlowControl.RTS_CTS.value),
        )
        self.assertEqual(client.calls[-1][0], SERIAL_CLOSE)

    def test_invalid_configuration_is_rejected_locally(self):
        client = FakeClient()
        with self.assertRaises(ValueError):
            SerialBackend(client, "COM7", data_bits=9)
        self.assertEqual(client.calls, [])


if __name__ == "__main__":
    unittest.main()
