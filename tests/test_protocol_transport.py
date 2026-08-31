import unittest
import threading

from nrpc import ProtocolSession, ProtocolTransportError


class FakeTransport:
    def __init__(self, reads=(), *, short_write=False):
        self.reads = [bytes(item) for item in reads]
        self.writes = []
        self.timeouts = []
        self.short_write = short_write
        self.close_count = 0

    def write(self, data, *, timeout=0):
        encoded = bytes(data)
        self.writes.append(encoded)
        self.timeouts.append(timeout)
        return len(encoded) - 1 if self.short_write else len(encoded)

    def read(self, max_size, *, timeout=0):
        self.timeouts.append(timeout)
        if not self.reads:
            return b""
        chunk = self.reads.pop(0)
        result, remainder = chunk[:max_size], chunk[max_size:]
        if remainder:
            self.reads.insert(0, remainder)
        return result

    def close(self, *, timeout=0):
        self.close_count += 1
        self.timeouts.append(timeout)


class ProtocolSessionTests(unittest.TestCase):
    def test_transaction_handles_fragmented_reads_and_one_deadline(self):
        transport = FakeTransport([b"a", b"bc", b"def"])
        session = ProtocolSession(transport, max_frame_size=16)

        with session.transaction(timeout=100) as transaction:
            transaction.write(b"request")
            self.assertEqual(transaction.read_exactly(6), b"abcdef")

        self.assertTrue(all(0 < timeout <= 100 for timeout in transport.timeouts))

    def test_short_write_is_rejected(self):
        session = ProtocolSession(
            FakeTransport(short_write=True), max_frame_size=16
        )
        with self.assertRaises(ProtocolTransportError):
            with session.transaction() as transaction:
                transaction.write(b"request")

    def test_read_limit_and_empty_read_are_rejected(self):
        session = ProtocolSession(FakeTransport(), max_frame_size=4)
        with session.transaction() as transaction:
            with self.assertRaises(ValueError):
                transaction.read_exactly(5)
            with self.assertRaises(ConnectionError):
                transaction.read_exactly(1)

    def test_transport_ownership_and_idempotent_close(self):
        borrowed = FakeTransport()
        session = ProtocolSession(borrowed, max_frame_size=16)
        session.close()
        session.close()
        self.assertEqual(borrowed.close_count, 0)

        owned = FakeTransport()
        session = ProtocolSession(
            owned, max_frame_size=16, owns_transport=True
        )
        session.close(timeout=25)
        session.close(timeout=25)
        self.assertEqual(owned.close_count, 1)
        self.assertEqual(owned.timeouts, [25])

    def test_closed_session_rejects_transactions(self):
        session = ProtocolSession(FakeTransport(), max_frame_size=16)
        session.close()
        with self.assertRaises(RuntimeError):
            with session.transaction():
                pass

    def test_timeout_includes_waiting_for_another_transaction(self):
        session = ProtocolSession(FakeTransport(), max_frame_size=16)
        result = []

        def contend():
            try:
                with session.transaction(timeout=10):
                    result.append("acquired")
            except TimeoutError:
                result.append("timed out")

        with session.transaction():
            thread = threading.Thread(target=contend)
            thread.start()
            thread.join(timeout=1)
        thread.join(timeout=1)

        self.assertEqual(result, ["timed out"])


if __name__ == "__main__":
    unittest.main()
