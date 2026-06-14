import unittest

from nrpc import DataType, TcpBackend, TypedValue
from nrpc.tcp_backend import TCP_CLOSE, TCP_OPEN, TCP_READ, TCP_WRITE


class FakeClient:
    def __init__(self):
        self.calls = []
        self.reads = [b"12.", b"500\nextra\n"]

    def call(self, function, args=(), timeout=0):
        self.calls.append((function, list(args), timeout))
        if function == TCP_OPEN:
            return [77]
        if function == TCP_WRITE:
            return [len(args[1])]
        if function == TCP_READ:
            return [self.reads.pop(0)]
        if function == TCP_CLOSE:
            return []
        raise AssertionError(function)


class TcpBackendTests(unittest.TestCase):
    def test_read_until_handles_fragmented_and_buffered_data(self):
        client = FakeClient()
        backend = TcpBackend(client, "power.local", 5025, timeout=100)

        backend.write(b"MEAS:VOLT?\n", timeout=250)
        self.assertEqual(backend.read_until(timeout=250), b"12.500\n")
        self.assertEqual(backend.read_until(timeout=250), b"extra\n")
        backend.close()

        self.assertEqual(client.calls[0][0], TCP_OPEN)
        self.assertEqual(
            client.calls[0][1][1], TypedValue(DataType.UINT16, 5025)
        )
        self.assertEqual(client.calls[1][0], TCP_WRITE)
        self.assertEqual(client.calls[-1][0], TCP_CLOSE)


if __name__ == "__main__":
    unittest.main()
