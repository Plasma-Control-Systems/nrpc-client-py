import unittest

from nrpc import (
    DataType, NidaqmxChannelType, NidaqmxCjcSource, NidaqmxTask,
    NidaqmxTerminalConfig, NidaqmxThermocoupleType, TypedValue,
)
from nrpc.nidaqmx_backend import (
    NIDAQMX_CLOSE, NIDAQMX_CREATE_AI_THERMOCOUPLE,
    NIDAQMX_CREATE_AI_VOLTAGE, NIDAQMX_CREATE_DO, NIDAQMX_READ_ANALOG,
    NIDAQMX_START, NIDAQMX_WRITE_DIGITAL,
)


class FakeClient:
    def __init__(self):
        self.calls = []

    def call(self, function, args=(), timeout=0):
        self.calls.append((function, list(args), timeout))
        if function in (NIDAQMX_CREATE_AI_VOLTAGE, NIDAQMX_CREATE_AI_THERMOCOUPLE, NIDAQMX_CREATE_DO):
            return [91]
        if function == NIDAQMX_READ_ANALOG:
            return [[21.25, 22.5]]
        if function == NIDAQMX_WRITE_DIGITAL:
            return [len(args[1].value)]
        if function in (NIDAQMX_START, NIDAQMX_CLOSE):
            return []
        raise AssertionError(function)


class NidaqmxBackendTests(unittest.TestCase):
    def test_voltage_input_lifecycle_and_arguments(self):
        client = FakeClient()
        with NidaqmxTask.create_ai_voltage(
            client, "Dev1/ai0", -5, 5,
            terminal=NidaqmxTerminalConfig.DIFFERENTIAL, timeout=100,
        ) as task:
            self.assertEqual(task.channel_type, NidaqmxChannelType.ANALOG_INPUT)
            task.start(timeout=200)
            self.assertEqual(task.read(2, timeout=300), [21.25, 22.5])
        args = client.calls[0][1]
        self.assertEqual(args[1], TypedValue(DataType.FLOAT64, -5.0))
        self.assertEqual(args[3], TypedValue(DataType.INT32, 10106))
        self.assertEqual(client.calls[-1][0], NIDAQMX_CLOSE)
        with self.assertRaises(RuntimeError):
            task.start()

    def test_thermocouple_and_digital_output(self):
        client = FakeClient()
        NidaqmxTask.create_ai_thermocouple(
            client, "Dev1/ai1", -100, 500, NidaqmxThermocoupleType.K,
            cjc_source=NidaqmxCjcSource.CHANNEL, cjc_channel="Dev1/ai7",
        )
        tc_args = client.calls[0][1]
        self.assertEqual(tc_args[3], TypedValue(DataType.INT32, 10073))
        self.assertEqual(tc_args[4], TypedValue(DataType.INT32, 10113))
        output = NidaqmxTask.create_digital_output(client, "Dev1/port0")
        self.assertEqual(output.write([1, 2, 3]), 3)
        self.assertEqual(client.calls[-1][1][1], TypedValue(DataType.UINT32, [1, 2, 3]))
        with self.assertRaises(RuntimeError):
            output.read()

    def test_invalid_configuration_is_rejected_locally(self):
        client = FakeClient()
        with self.assertRaises(ValueError):
            NidaqmxTask.create_ai_voltage(client, "", 10, -10)
        with self.assertRaises(ValueError):
            NidaqmxTask.create_ai_thermocouple(
                client, "Dev1/ai0", -10, 10, NidaqmxThermocoupleType.K,
                cjc_source=NidaqmxCjcSource.CHANNEL,
            )
        self.assertEqual(client.calls, [])


if __name__ == "__main__":
    unittest.main()
