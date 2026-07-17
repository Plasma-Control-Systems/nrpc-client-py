import unittest

from nrpc import (
    DataType, LcardAdcChannel, LcardAdcInputMode, LcardCapability,
    LcardDevice, TypedValue,
)
from nrpc.lcard_backend import (
    LCARD_CLOSE, LCARD_OPEN, LCARD_READ_ADC, LCARD_READ_ADC_FRAME,
    LCARD_WRITE_DAC, LCARD_WRITE_DAC_FRAMES,
)


class FakeClient:
    def __init__(self):
        self.calls = []
        self.adc_frame_result = [[-1, 2], 99.5]

    def call(self, function, args=(), timeout=0):
        self.calls.append((function, list(args), timeout))
        if function == LCARD_OPEN:
            return [0x4C43, 19, "L791", ord("C"), True, 15]
        if function == LCARD_READ_ADC:
            return [-123]
        if function == LCARD_READ_ADC_FRAME:
            return self.adc_frame_result
        if function == LCARD_WRITE_DAC:
            return []
        if function == LCARD_WRITE_DAC_FRAMES:
            return [len(args[1].value), 12.25]
        if function == LCARD_CLOSE:
            return []
        raise AssertionError(function)


class LcardBackendTests(unittest.TestCase):
    def test_lifecycle_metadata_and_adc(self):
        client = FakeClient()
        with LcardDevice.open(client, 2, "L791.bio", timeout=100) as device:
            self.assertEqual(device.info.board_name, "L791")
            self.assertTrue(device.info.supports(LcardCapability.WRITE_DAC_FRAMES))
            self.assertEqual(device.read_adc(LcardAdcChannel(0, 10.0)), -123)
            frame = device.read_adc_frame([
                LcardAdcChannel(0, 10.0), LcardAdcChannel.raw(0x41)
            ], rate_khz=100.0, timeout=200)
            self.assertEqual(frame.codes, [-1, 2])
            self.assertEqual(frame.actual_rate_khz, 99.5)
        self.assertEqual(client.calls[0][1][0], TypedValue(DataType.UINT32, 2))
        self.assertEqual(client.calls[-1][0], LCARD_CLOSE)
        with self.assertRaises(RuntimeError):
            device.read_adc(LcardAdcChannel(0))

    def test_dac_writes_and_serialization(self):
        client = FakeClient()
        device = LcardDevice.open(client, 0)
        device.write_dac(1, 0xABC)
        result = device.write_dac_frames([1, 2], [3, 4], 12.5)
        self.assertEqual(result.frames_written, 2)
        self.assertEqual(client.calls[-1][1][1], TypedValue(DataType.UINT16, [1, 2]))
        self.assertEqual(client.calls[-1][1][2], TypedValue(DataType.UINT16, [3, 4]))

    def test_single_channel_frame_normalizes_scalar_code(self):
        client = FakeClient()
        client.adc_frame_result = [-17, 1000.0]
        device = LcardDevice.open(client, 0)
        frame = device.read_adc_frame([LcardAdcChannel(0)], rate_khz=1000.0)
        self.assertEqual(frame.codes, [-17])
        self.assertEqual(frame.actual_rate_khz, 1000.0)

    def test_invalid_inputs_are_rejected_locally(self):
        client = FakeClient()
        with self.assertRaises(ValueError):
            LcardDevice.open(client, -1)
        device = LcardDevice.open(client, 0)
        with self.assertRaises(ValueError):
            LcardAdcChannel(0, 0)
        with self.assertRaises(ValueError):
            device.write_dac_frames([1], [2, 3], 10)
        with self.assertRaises(ValueError):
            device.read_adc_frame([], 100)
        with self.assertRaises(ValueError):
            LcardAdcChannel(0, 10, LcardAdcInputMode(99))


if __name__ == "__main__":
    unittest.main()
