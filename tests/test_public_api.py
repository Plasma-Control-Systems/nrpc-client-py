import unittest

import nrpc


class PublicApiTests(unittest.TestCase):
    def test_version_and_typed_exports(self):
        self.assertEqual(nrpc.__version__, "0.1.0")
        self.assertNotIn("AsyncNrpcClient", nrpc.__all__)
        self.assertFalse(any(name.startswith("Async") for name in nrpc.__all__))
        self.assertIn("NrpcValue", nrpc.__all__)
        self.assertIn("LCardAdcInputMode", nrpc.__all__)
        self.assertIn("LCardAdcFrame", nrpc.__all__)
        self.assertIn("LCardBackend", nrpc.__all__)
        self.assertIn("SerialBackend", nrpc.__all__)
        self.assertIn("TcpBackend", nrpc.__all__)
        self.assertFalse(hasattr(nrpc, "AsyncNrpcClient"))


if __name__ == "__main__":
    unittest.main()
