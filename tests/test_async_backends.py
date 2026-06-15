import unittest

from nrpc import (
    AsyncSerialBackend,
    AsyncTcpBackend,
    DataType,
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
from nrpc.tcp_backend import TCP_CLOSE, TCP_OPEN, TCP_READ, TCP_WRITE


class FakeAsyncClient:
    def __init__(self):
        self.calls = []
        self.reads = [b"12.", b"500\nextra\n"]

    async def call(self, function, args=(), timeout=0):
        self.calls.append((function, list(args), timeout))
        if function in (TCP_OPEN, SERIAL_OPEN):
            return [77]
        if function in (TCP_WRITE, SERIAL_WRITE):
            return [len(args[1])]
        if function in (TCP_READ, SERIAL_READ):
            return [self.reads.pop(0)]
        if function in (TCP_CLOSE, SERIAL_CLOSE):
            return []
        raise AssertionError(function)


class AsyncBackendTests(unittest.IsolatedAsyncioTestCase):
    async def test_tcp_backend_buffers_fragmented_data(self):
        client = FakeAsyncClient()
        backend = await AsyncTcpBackend.open(
            client, "power.local", 5025, timeout=100
        )

        await backend.write(b"MEAS:VOLT?\n", timeout=250)
        self.assertEqual(await backend.read_until(timeout=250), b"12.500\n")
        self.assertEqual(await backend.read_until(timeout=250), b"extra\n")
        await backend.close()

        self.assertEqual(
            client.calls[0][1][1], TypedValue(DataType.UINT16, 5025)
        )
        self.assertEqual(client.calls[-1][0], TCP_CLOSE)

    async def test_serial_backend_configuration_and_context_manager(self):
        client = FakeAsyncClient()
        async with await AsyncSerialBackend.open(
            client,
            "COM7",
            baud_rate=115200,
            parity=SerialParity.EVEN,
            flow_control=SerialFlowControl.RTS_CTS,
            timeout=100,
        ) as backend:
            await backend.write(b"MEAS?\n", timeout=250)
            self.assertEqual(
                await backend.read_until(timeout=250), b"12.500\n"
            )

        open_args = client.calls[0][1]
        self.assertEqual(open_args[1], TypedValue(DataType.UINT32, 115200))
        self.assertEqual(
            open_args[3],
            TypedValue(DataType.UINT8, SerialParity.EVEN.value),
        )
        self.assertEqual(client.calls[-1][0], SERIAL_CLOSE)

    async def test_invalid_serial_configuration_is_rejected_locally(self):
        client = FakeAsyncClient()
        with self.assertRaises(ValueError):
            await AsyncSerialBackend.open(client, "COM7", data_bits=9)
        self.assertEqual(client.calls, [])
