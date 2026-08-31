import unittest

from nrpc import DataType, SpiDevice, SpiMode, TypedValue
from nrpc.spi_backend import SPI_CLOSE, SPI_OPEN, SPI_TRANSFER


class FakeClient:
    def __init__(self):
        self.calls = []

    def call(self, function, args=(), timeout=0):
        self.calls.append((function, list(args), timeout))
        if function == SPI_OPEN:
            return [0x5350490000000001]
        if function == SPI_TRANSFER:
            return [bytes(byte ^ 0xFF for byte in args[1])]
        if function == SPI_CLOSE:
            return []
        raise AssertionError(function)


class SpiBackendTests(unittest.TestCase):
    def test_open_transfer_and_close(self):
        client = FakeClient()
        with SpiDevice(
            client,
            "/dev/spidev0.0",
            mode=SpiMode.MODE_3,
            max_speed_hz=2_000_000,
            bits_per_word=8,
            timeout=100,
        ) as device:
            received = device.transfer(
                b"\x9f\x00\x00",
                speed_hz=500_000,
                delay_us=10,
                cs_change=True,
                timeout=200,
            )

        self.assertEqual(received, b"\x60\xff\xff")
        open_args = client.calls[0][1]
        self.assertEqual(open_args[1], TypedValue(DataType.UINT8, 3))
        self.assertEqual(open_args[2], TypedValue(DataType.UINT32, 2_000_000))
        transfer_args = client.calls[1][1]
        self.assertEqual(transfer_args[2], TypedValue(DataType.UINT32, 500_000))
        self.assertEqual(transfer_args[3], TypedValue(DataType.UINT16, 10))
        self.assertEqual(transfer_args[4], TypedValue(DataType.BOOL, True))
        self.assertEqual(client.calls[-1][0], SPI_CLOSE)

    def test_default_transfer_speed_uses_open_configuration(self):
        client = FakeClient()
        device = SpiDevice(client, "/dev/spidev0.0")
        device.transfer(b"\x00")
        self.assertEqual(
            client.calls[-1][1][2], TypedValue(DataType.UINT32, 0)
        )

    def test_invalid_configuration_and_transfer_are_rejected_locally(self):
        client = FakeClient()
        with self.assertRaises(ValueError):
            SpiDevice(client, "", max_speed_hz=1)
        with self.assertRaises(ValueError):
            SpiDevice(client, "/dev/spidev0.0", max_speed_hz=0)
        self.assertEqual(client.calls, [])

        device = SpiDevice(client, "/dev/spidev0.0")
        with self.assertRaises(ValueError):
            device.transfer(b"")
        with self.assertRaises(TypeError):
            device.transfer("not bytes")
        self.assertEqual(len(client.calls), 1)


if __name__ == "__main__":
    unittest.main()
