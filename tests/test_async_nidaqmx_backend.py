import unittest

from nrpc import AsyncNidaqmxTask, DataType, NidaqmxChannelType, TypedValue
from nrpc.nidaqmx_backend import (
    NIDAQMX_CLOSE, NIDAQMX_CREATE_DI, NIDAQMX_READ_DIGITAL, NIDAQMX_START,
)


class FakeAsyncClient:
    def __init__(self):
        self.calls = []

    async def call(self, function, args=(), timeout=0):
        self.calls.append((function, list(args), timeout))
        if function == NIDAQMX_CREATE_DI:
            return [17]
        if function == NIDAQMX_READ_DIGITAL:
            return [[0x5A]]
        if function in (NIDAQMX_START, NIDAQMX_CLOSE):
            return []
        raise AssertionError(function)


class AsyncNidaqmxBackendTests(unittest.IsolatedAsyncioTestCase):
    async def test_async_digital_input_lifecycle(self):
        client = FakeAsyncClient()
        async with await AsyncNidaqmxTask.create_digital_input(
            client, "Dev1/port0", timeout=100
        ) as task:
            self.assertEqual(task.channel_type, NidaqmxChannelType.DIGITAL_INPUT)
            await task.start()
            self.assertEqual(await task.read(1, timeout=250), [0x5A])
        self.assertEqual(client.calls[2][1][1], TypedValue(DataType.UINT32, 1))
        self.assertEqual(client.calls[-1][0], NIDAQMX_CLOSE)


if __name__ == "__main__":
    unittest.main()
