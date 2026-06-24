import unittest

from nrpc import (
    AsyncE2010Backend,
    AsyncLCardBackend,
    AsyncSerialBackend,
    AsyncTcpBackend,
    DataType,
    AsyncE310Backend,
    SerialFlowControl,
    SerialParity,
    TypedValue,
)
from nrpc.lcard_backend import (
    LCARD_CLOSE,
    LCARD_IO_ASYNC,
    LCARD_OPEN,
    LCardAdcInputMode,
    LCardBoardType,
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
        self.io_data = None

    async def call(self, function, args=(), timeout=0):
        self.calls.append((function, list(args), timeout))
        if function in (TCP_OPEN, SERIAL_OPEN, LCARD_OPEN):
            return [77]
        if function in (TCP_WRITE, SERIAL_WRITE):
            return [len(args[1])]
        if function in (TCP_READ, SERIAL_READ):
            return [self.reads.pop(0)]
        if function in (TCP_CLOSE, SERIAL_CLOSE):
            return []
        if function == LCARD_IO_ASYNC:
            count = args[4].value
            if self.io_data is not None:
                return [1000.0, self.io_data[:count]]
            return [1000.0, list(range(42, 42 + count))]
        if function == LCARD_CLOSE:
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

    async def test_lcard_backend_runs_async_io_and_closes(self):
        client = FakeAsyncClient()
        async with await AsyncLCardBackend.open(
            client, LCardBoardType.E310, 3, timeout=100
        ) as backend:
            self.assertIsInstance(backend, AsyncE310Backend)
            self.assertFalse(hasattr(backend, "read_adc"))

        self.assertEqual(
            client.calls[0][1][0], TypedValue(DataType.UINT32, 3)
        )
        self.assertEqual(
            client.calls[0][1][1],
            TypedValue(DataType.UINT32, LCardBoardType.E310.value),
        )
        self.assertEqual(client.calls[0][1][2], "")
        self.assertEqual(client.calls[-1][0], LCARD_CLOSE)

    async def test_lcard_e2010_adc_stream_helper(self):
        client = FakeAsyncClient()
        backend = await AsyncLCardBackend.open(client, LCardBoardType.E2010)

        self.assertIsInstance(backend, AsyncE2010Backend)
        self.assertEqual(await backend.adc_sample(0), 42)
        self.assertEqual(client.calls[1][1][3], TypedValue(DataType.UINT32, 0x0400))
        self.assertEqual(await backend.adc_sample(3), 42)
        self.assertEqual(client.calls[2][1][3], TypedValue(DataType.UINT32, 0x0800))
        with self.assertRaises(ValueError):
            await backend.adc_sample(3, adc_input_mask=0x0400)
        client.io_data = [4000]
        self.assertAlmostEqual(
            await backend.adc_voltage(1, adc_input_mask=0x0202),
            0.5,
        )

    async def test_lcard_adc_input_mode_is_encoded_in_channel(self):
        client = FakeAsyncClient()
        backend = await AsyncLCardBackend.open(client, LCardBoardType.E140)

        await backend.adc_sample(
            2, input_mode=LCardAdcInputMode.SINGLE_ENDED, rate=1000.0
        )

        self.assertEqual(
            client.calls[1][1][2],
            TypedValue(DataType.FLOAT64, 1000.0),
        )
        self.assertEqual(
            client.calls[1][1][5],
            TypedValue(DataType.UINT32, [2 | LCardAdcInputMode.SINGLE_ENDED]),
        )
        with self.assertRaises(ValueError):
            await backend.adc_sample(16, input_mode=LCardAdcInputMode.DIFFERENTIAL)
        client.io_data = [4000]
        self.assertAlmostEqual(
            await backend.adc_voltage(
                2,
                input_mode=LCardAdcInputMode.SINGLE_ENDED,
                input_range=2.5,
            ),
            1.25,
        )
        self.assertEqual(
            client.calls[-1][1][5],
            TypedValue(
                DataType.UINT32,
                [2 | LCardAdcInputMode.SINGLE_ENDED | 64],
            ),
        )
