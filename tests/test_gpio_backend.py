import unittest

from nrpc import DataType, GpioDirection, GpioLine, TypedValue
from nrpc.gpio_backend import GPIO_CLOSE, GPIO_OPEN, GPIO_READ, GPIO_WRITE


class FakeClient:
    def __init__(self):
        self.calls = []
        self.value = False

    def call(self, function, args=(), timeout=0):
        self.calls.append((function, list(args), timeout))
        if function == GPIO_OPEN:
            return [0x4750494F00000001]
        if function == GPIO_READ:
            return [self.value]
        if function == GPIO_WRITE:
            self.value = args[1].value
            return []
        if function == GPIO_CLOSE:
            return []
        raise AssertionError(function)


class GpioBackendTests(unittest.TestCase):
    def test_output_line_open_write_read_and_close(self):
        client = FakeClient()
        with GpioLine(
            client,
            "/dev/gpiochip0",
            17,
            GpioDirection.OUTPUT,
            initial_value=False,
            active_low=True,
            consumer="my-service",
            timeout=100,
        ) as line:
            line.write(True, timeout=200)
            self.assertTrue(line.read(timeout=300))

        open_args = client.calls[0][1]
        self.assertEqual(open_args[1], TypedValue(DataType.UINT32, 17))
        self.assertEqual(
            open_args[2], TypedValue(DataType.UINT8, GpioDirection.OUTPUT.value)
        )
        self.assertEqual(open_args[3], TypedValue(DataType.BOOL, False))
        self.assertEqual(open_args[4], TypedValue(DataType.BOOL, True))
        self.assertEqual(client.calls[-1][0], GPIO_CLOSE)

    def test_input_rejects_write_locally(self):
        client = FakeClient()
        line = GpioLine(client, "/dev/gpiochip0", 4)
        with self.assertRaises(RuntimeError):
            line.write(True)
        self.assertEqual(len(client.calls), 1)

    def test_invalid_configuration_is_rejected_locally(self):
        client = FakeClient()
        with self.assertRaises(ValueError):
            GpioLine(client, "", 0)
        with self.assertRaises(ValueError):
            GpioLine(client, "/dev/gpiochip0", -1)
        self.assertEqual(client.calls, [])


if __name__ == "__main__":
    unittest.main()
