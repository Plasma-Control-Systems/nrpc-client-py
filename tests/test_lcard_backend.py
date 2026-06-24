import unittest

from nrpc import (
    DataType,
    E140Backend,
    E2010Backend,
    E310Backend,
    L780Backend,
    L791Backend,
    LCardAdcInputMode,
    LCardBackend,
    LCardBoardType,
    LCardSlotInfo,
    TypedValue,
)
from nrpc.lcard_backend import (
    LCARD_CLOSE,
    LCARD_IO_ASYNC,
    LCARD_LOAD_BIOS,
    LCARD_OPEN,
    LCARD_SLOT_INFO,
)


class FakeClient:
    def __init__(self):
        self.calls = []
        self.board = LCardBoardType.E140

    def call(self, function, args=(), timeout=0):
        self.calls.append((function, list(args), timeout))
        if function == LCARD_OPEN:
            self.board = LCardBoardType(args[1].value)
            return [73]
        if function == LCARD_SLOT_INFO:
            return [[self.board.value, 23, 5]]
        if function == LCARD_IO_ASYNC:
            count = args[4].value
            return [1250.0, list(range(101, 101 + count))]
        if function in (LCARD_LOAD_BIOS, LCARD_CLOSE):
            return []
        raise AssertionError(function)


class LCardBackendTests(unittest.TestCase):
    def test_e140_helpers_and_board_identity(self):
        client = FakeClient()
        with LCardBackend.open(
            client, LCardBoardType.E140, 2, timeout=100
        ) as backend:
            self.assertIsInstance(backend, E140Backend)
            self.assertEqual(
                backend.slot_info(timeout=200),
                LCardSlotInfo(LCardBoardType.E140, 23, 5),
            )
            self.assertEqual(backend.adc_sample(4), 101)
            backend.adc_sample(
                4, input_mode=LCardAdcInputMode.SINGLE_ENDED
            )
            backend.write_dac(1, 123)
            backend.write_dac_pair(100, 200)
            backend.load_bios("updated.bio")

        open_args = client.calls[0][1]
        self.assertEqual(open_args[0], TypedValue(DataType.UINT32, 2))
        self.assertEqual(
            open_args[1],
            TypedValue(DataType.UINT32, LCardBoardType.E140.value),
        )
        self.assertEqual(open_args[2], "")
        default_adc_args = client.calls[2][1]
        self.assertEqual(default_adc_args[5], TypedValue(DataType.UINT32, [4]))
        single_ended_adc_args = client.calls[3][1]
        self.assertEqual(
            single_ended_adc_args[5],
            TypedValue(DataType.UINT32, [4 | LCardAdcInputMode.SINGLE_ENDED]),
        )
        self.assertEqual(client.calls[-1][0], LCARD_CLOSE)

    def test_explicit_bios_path_overrides_server_auto_load(self):
        client = FakeClient()
        LCardBackend.open(client, LCardBoardType.E140, bios="e140.bio")

        self.assertEqual(client.calls[0][1][2], "e140.bio")

    def test_device_specific_classes_expose_distinct_helpers(self):
        client = FakeClient()
        l791 = LCardBackend.open(client, LCardBoardType.L791)
        self.assertIsInstance(l791, L791Backend)
        l791.write_dac_pair(0, 10, 1, 20)

        e310 = LCardBackend.open(client, LCardBoardType.E310)
        self.assertIsInstance(e310, E310Backend)
        e310.configure_adc(0x30, external_start=True)
        self.assertEqual(e310.read_adc(), (101, 102, 103, 104))
        self.assertFalse(hasattr(e310, "write_dac"))

        e2010 = LCardBackend.open(client, LCardBoardType.E2010)
        self.assertIsInstance(e2010, E2010Backend)
        self.assertFalse(hasattr(e2010, "adc_sample"))

        pci_a = LCardBackend.open(client, LCardBoardType.PCI_A)
        self.assertIsInstance(pci_a, L780Backend)
        with self.assertRaises(RuntimeError):
            pci_a.configure_ttl(1)

        with self.assertRaises(ValueError):
            l791.adc_sample(0, input_mode=LCardAdcInputMode.SINGLE_ENDED)

    def test_invalid_values_are_rejected_locally(self):
        client = FakeClient()
        with self.assertRaises(ValueError):
            LCardBackend.open(client, LCardBoardType.E310, -1)
        self.assertEqual(client.calls, [])

        backend = LCardBackend.open(client, LCardBoardType.E310)
        with self.assertRaises(ValueError):
            backend.configure_adc(0x01)
