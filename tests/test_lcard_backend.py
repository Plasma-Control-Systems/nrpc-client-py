import unittest

from nrpc import (
    DataType,
    E140Backend,
    E2010Backend,
    E310Backend,
    E440Backend,
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
    LCARD_ADC_FRAME,
    LCARD_IO_ASYNC,
    LCARD_LOAD_BIOS,
    LCARD_OPEN,
    LCARD_SLOT_INFO,
)


class FakeClient:
    def __init__(self):
        self.calls = []
        self.board = LCardBoardType.E140
        self.io_data = None

    def call(self, function, args=(), timeout=0):
        self.calls.append((function, list(args), timeout))
        if function == LCARD_OPEN:
            self.board = LCardBoardType(args[1].value)
            return [73]
        if function == LCARD_SLOT_INFO:
            return [[self.board.value, 23, 5]]
        if function == LCARD_IO_ASYNC:
            count = args[4].value
            if self.io_data is not None:
                return [1250.0, self.io_data[:count]]
            return [1250.0, list(range(101, 101 + count))]
        if function == LCARD_ADC_FRAME:
            count = args[1].value * args[3].value
            if self.io_data is not None:
                return [2000.0, args[1].value, args[3].value, self.io_data[:count]]
            return [2000.0, args[1].value, args[3].value, list(range(count))]
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
                4,
                input_mode=LCardAdcInputMode.SINGLE_ENDED,
                rate=1000.0,
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
            single_ended_adc_args[2],
            TypedValue(DataType.FLOAT64, 1000.0),
        )
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
        self.assertFalse(hasattr(e310, "adc_sample"))
        self.assertFalse(hasattr(e310, "write_dac"))

        e2010 = LCardBackend.open(client, LCardBoardType.E2010)
        self.assertIsInstance(e2010, E2010Backend)
        self.assertEqual(e2010.adc_sample(0), 101)

        pci_a = LCardBackend.open(client, LCardBoardType.PCI_A)
        self.assertIsInstance(pci_a, L780Backend)
        self.assertFalse(hasattr(pci_a, "configure_ttl"))

        with self.assertRaises(ValueError):
            l791.adc_sample(0, input_mode=LCardAdcInputMode.SINGLE_ENDED)

    def test_invalid_values_are_rejected_locally(self):
        client = FakeClient()
        with self.assertRaises(ValueError):
            LCardBackend.open(client, LCardBoardType.E310, -1)
        self.assertEqual(client.calls, [])

        backend = LCardBackend.open(client, LCardBoardType.E310)
        self.assertFalse(hasattr(backend, "read_adc"))

    def test_e140_and_e440_adc_line_limits_are_mode_specific(self):
        client = FakeClient()
        e140 = LCardBackend.open(client, LCardBoardType.E140)
        self.assertIsInstance(e140, E140Backend)
        e140.adc_sample(31, input_mode=LCardAdcInputMode.SINGLE_ENDED)
        self.assertEqual(
            client.calls[-1][1][5],
            TypedValue(
                DataType.UINT32,
                [31 | LCardAdcInputMode.SINGLE_ENDED],
            ),
        )
        with self.assertRaises(ValueError):
            e140.adc_sample(16, input_mode=LCardAdcInputMode.DIFFERENTIAL)

        e440 = LCardBackend.open(client, LCardBoardType.E440)
        self.assertIsInstance(e440, E440Backend)
        e440.adc_sample(15, input_mode=LCardAdcInputMode.SINGLE_ENDED)
        with self.assertRaises(ValueError):
            e440.adc_sample(16, input_mode=LCardAdcInputMode.SINGLE_ENDED)

    def test_e2010_adc_limits_and_per_channel_default_masks(self):
        client = FakeClient()
        e2010 = LCardBackend.open(client, LCardBoardType.E2010)

        e2010.adc_sample(2)
        self.assertEqual(client.calls[-1][1][5], TypedValue(DataType.UINT32, [2]))
        self.assertEqual(client.calls[-1][1][3], TypedValue(DataType.UINT32, 0x1000))

        e2010.adc_sample(1, adc_input_mask=0x0202)
        self.assertEqual(client.calls[-1][1][3], TypedValue(DataType.UINT32, 0x0202))

        with self.assertRaises(ValueError):
            e2010.adc_sample(4)
        with self.assertRaises(ValueError):
            e2010.adc_sample(0, adc_input_mask=0x0200)
        with self.assertRaises(ValueError):
            e2010.adc_sample(0, adc_input_mask=0x0400 | 0x0008 | 0x0010)
        with self.assertRaises(ValueError):
            e2010.adc_sample(0, adc_input_mask=0x0400 | 0x0001)

    def test_adc_voltage_converts_counts_with_board_ranges(self):
        client = FakeClient()
        client.io_data = [4000]
        e140 = LCardBackend.open(client, LCardBoardType.E140)
        self.assertAlmostEqual(e140.adc_voltage(3, input_range=2.5), 1.25)
        self.assertEqual(client.calls[-1][1][5], TypedValue(DataType.UINT32, [3 | 64]))

        client.io_data = [1000]
        e154 = LCardBackend.open(client, LCardBoardType.E154)
        self.assertAlmostEqual(e154.adc_voltage(2, input_range=1.6), 0.8)
        self.assertEqual(client.calls[-1][1][5], TypedValue(DataType.UINT32, [2 | 64]))

        client.io_data = [4096]
        l791 = LCardBackend.open(client, LCardBoardType.L791)
        self.assertAlmostEqual(l791.adc_voltage(1, input_range=5.0), 2.5)
        self.assertEqual(client.calls[-1][1][5], TypedValue(DataType.UINT32, [1 | 64]))

        client.io_data = [4000]
        e2010 = LCardBackend.open(client, LCardBoardType.E2010)
        self.assertAlmostEqual(
            e2010.adc_voltage(1, adc_input_mask=0x0202),
            0.5,
        )
        self.assertEqual(client.calls[-1][1][3], TypedValue(DataType.UINT32, 0x0202))

        with self.assertRaises(ValueError):
            e140.adc_voltage(0, input_range=1.0)

    def test_adc_voltage_frame_uses_stream_frame_call(self):
        client = FakeClient()
        client.io_data = [0, 4000, 0, 0]
        e440 = LCardBackend.open(client, LCardBoardType.E440)

        frame = e440.adc_voltage_frame(
            channel_count=2,
            sample_rate=400.0,
            samples_per_channel=2,
            start_channel=0,
            end_channel=1,
            mode=LCardAdcInputMode.SINGLE_ENDED,
            auto_init=True,
            timeout=3000,
        )

        self.assertEqual(frame.rate, 2000.0)
        self.assertEqual(frame.channel_count, 2)
        self.assertEqual(frame.samples_per_channel, 2)
        self.assertEqual(frame.data, [0.0, 5.0, 0.0, 0.0])
        self.assertEqual(client.calls[-1][0], LCARD_ADC_FRAME)
        self.assertEqual(client.calls[-1][2], 3000)
        self.assertEqual(client.calls[-1][1][1], TypedValue(DataType.UINT32, 2))
        self.assertEqual(
            client.calls[-1][1][6],
            TypedValue(DataType.UINT32, LCardAdcInputMode.SINGLE_ENDED),
        )
        self.assertEqual(client.calls[-1][1][7], TypedValue(DataType.BOOL, True))

        with self.assertRaises(ValueError):
            e440.adc_voltage_frame(
                channel_count=2,
                sample_rate=400.0,
                samples_per_channel=65537,
                start_channel=0,
                end_channel=1,
            )
