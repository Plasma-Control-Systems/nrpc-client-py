import asyncio
import struct
import unittest

from nrpc import AsyncNrpcClient, ProtocolError, RemoteError
from nrpc.client import MAGIC, VERSION


def response(
    function_index: int,
    *,
    status: int = 0,
    count: int = 0,
    payload: bytes = b"",
    error: int = 0,
) -> bytes:
    return struct.pack(
        "!BBBBIII",
        status,
        VERSION,
        function_index,
        count,
        len(payload),
        error,
        0,
    ) + payload


class AsyncClientTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.requests = []

        async def handle(
            reader: asyncio.StreamReader, writer: asyncio.StreamWriter
        ) -> None:
            try:
                while True:
                    header = await reader.readexactly(16)
                    payload_size = struct.unpack("!I", header[4:8])[0]
                    payload = await reader.readexactly(payload_size)
                    self.requests.append(header + payload)
                    function_index = header[2]
                    if function_index == 3:
                        writer.write(response(3, status=1, error=41))
                    elif function_index == 4:
                        writer.write(response(4, payload=b"x"))
                    else:
                        writer.write(response(function_index))
                    await writer.drain()
            except asyncio.IncompleteReadError:
                pass
            finally:
                writer.close()
                await writer.wait_closed()

        self.server = await asyncio.start_server(handle, "127.0.0.1", 0)
        self.port = self.server.sockets[0].getsockname()[1]

    async def asyncTearDown(self):
        self.server.close()
        await self.server.wait_closed()

    async def test_context_manager_connects_and_calls(self):
        async with AsyncNrpcClient("127.0.0.1", self.port) as client:
            self.assertEqual(await client.call(7, ["hello"]), [])

        self.assertEqual(self.requests[0][0], MAGIC)
        self.assertEqual(self.requests[0][2], 7)

    async def test_explicit_connect_and_remote_error(self):
        client = await AsyncNrpcClient.connect("127.0.0.1", self.port)
        try:
            with self.assertRaises(RemoteError) as raised:
                await client.call(3)
            self.assertEqual(raised.exception.code, 41)
        finally:
            await client.close()

    async def test_invalid_payload_is_rejected(self):
        async with AsyncNrpcClient("127.0.0.1", self.port) as client:
            with self.assertRaises(ProtocolError):
                await client.call(4)

