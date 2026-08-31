import struct
import unittest

from nrpc import (
    ModbusException,
    ModbusProtocolError,
    ModbusRtuClient,
    ModbusTcpClient,
)


def crc16(data):
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ (0xA001 if crc & 1 else 0)
    return crc


def rtu_frame(unit_id, pdu):
    data = bytes((unit_id,)) + pdu
    return data + struct.pack("<H", crc16(data))


class FakeTransport:
    def __init__(self, response=b"", fragments=()):
        self.reads = list(fragments) or [response]
        self.writes = []
        self.close_count = 0

    def write(self, data, *, timeout=0):
        self.writes.append((bytes(data), timeout))
        return len(data)

    def read(self, max_size, *, timeout=0):
        if not self.reads:
            return b""
        chunk = self.reads.pop(0)
        result, remainder = chunk[:max_size], chunk[max_size:]
        if remainder:
            self.reads.insert(0, remainder)
        return result

    def close(self, *, timeout=0):
        self.close_count += 1


class ModbusTcpTests(unittest.TestCase):
    def test_fragmented_holding_register_read(self):
        response = bytes.fromhex("000000000007010304000a0102")
        transport = FakeTransport(fragments=[response[:3], response[3:8], response[8:]])
        client = ModbusTcpClient(transport, unit_id=1)

        self.assertEqual(
            client.read_holding_registers(0, 2, timeout=100), [10, 258]
        )
        self.assertEqual(
            transport.writes[0][0],
            bytes.fromhex("000000000006010300000002"),
        )
        self.assertTrue(0 < transport.writes[0][1] <= 100)

    def test_coils_are_unpacked_least_significant_bit_first(self):
        response = bytes.fromhex("0000000000050101024d01")
        client = ModbusTcpClient(FakeTransport(response), unit_id=1)
        self.assertEqual(
            client.read_coils(20, 10),
            [True, False, True, True, False, False, True, False, True, False],
        )

    def test_multiple_register_write_and_response_validation(self):
        response = bytes.fromhex("000000000006011000100002")
        transport = FakeTransport(response)
        client = ModbusTcpClient(transport)
        client.write_multiple_registers(16, [0x1234, 0xABCD])
        self.assertEqual(
            transport.writes[0][0],
            bytes.fromhex("00000000000b011000100002041234abcd"),
        )

    def test_multiple_coils_are_packed_least_significant_bit_first(self):
        response = bytes.fromhex("000000000006010f0014000a")
        transport = FakeTransport(response)
        client = ModbusTcpClient(transport)
        client.write_multiple_coils(
            20,
            [True, False, True, True, False, False, True, False, True, False],
        )
        self.assertEqual(
            transport.writes[0][0],
            bytes.fromhex("000000000009010f0014000a024d01"),
        )

    def test_exception_response_is_exposed(self):
        response = bytes.fromhex("000000000003018302")
        client = ModbusTcpClient(FakeTransport(response))
        with self.assertRaises(ModbusException) as caught:
            client.read_holding_registers(0, 1)
        self.assertEqual(caught.exception.exception_code, 2)
        self.assertEqual(caught.exception.function_code, 3)

    def test_mbap_mismatch_is_rejected(self):
        response = bytes.fromhex("0001000000050103020001")
        client = ModbusTcpClient(FakeTransport(response))
        with self.assertRaises(ModbusProtocolError):
            client.read_holding_registers(0, 1)


class ModbusRtuTests(unittest.TestCase):
    def test_register_read_uses_standard_crc_and_parses_response(self):
        response = rtu_frame(1, bytes.fromhex("0304000a0102"))
        transport = FakeTransport(fragments=[response[:2], response[2:3], response[3:]])
        client = ModbusRtuClient(transport, unit_id=1)

        self.assertEqual(client.read_holding_registers(0, 2), [10, 258])
        self.assertEqual(
            transport.writes[0][0], bytes.fromhex("010300000002c40b")
        )

    def test_single_coil_write_validates_echo(self):
        response = rtu_frame(7, bytes.fromhex("050013ff00"))
        transport = FakeTransport(response)
        client = ModbusRtuClient(transport, unit_id=7)
        client.write_single_coil(19, True)
        self.assertEqual(transport.writes[0][0], response)

    def test_broadcast_multiple_write_does_not_read(self):
        transport = FakeTransport()
        client = ModbusRtuClient(transport, unit_id=0)
        client.write_multiple_registers(10, [1, 2])
        self.assertEqual(len(transport.writes), 1)
        self.assertEqual(transport.reads, [b""])
        with self.assertRaises(ValueError):
            client.read_input_registers(0, 1)

    def test_bad_crc_is_rejected(self):
        response = bytearray(rtu_frame(1, bytes.fromhex("03020001")))
        response[-1] ^= 0xFF
        client = ModbusRtuClient(FakeTransport(bytes(response)))
        with self.assertRaises(ModbusProtocolError):
            client.read_holding_registers(0, 1)

    def test_exception_crc_is_checked_before_exception_is_raised(self):
        response = rtu_frame(1, bytes.fromhex("8302"))
        client = ModbusRtuClient(FakeTransport(response))
        with self.assertRaises(ModbusException) as caught:
            client.read_holding_registers(0, 1)
        self.assertEqual(caught.exception.exception_code, 2)


class ModbusValidationTests(unittest.TestCase):
    def test_invalid_arguments_do_not_touch_transport(self):
        transport = FakeTransport()
        client = ModbusTcpClient(transport)
        with self.assertRaises(ValueError):
            client.read_holding_registers(0, 126)
        with self.assertRaises(TypeError):
            client.write_single_register(0, True)
        with self.assertRaises(TypeError):
            client.write_multiple_coils(0, [True, 1])
        self.assertEqual(transport.writes, [])

    def test_adapter_only_closes_owned_transport(self):
        borrowed = FakeTransport()
        ModbusTcpClient(borrowed).close()
        self.assertEqual(borrowed.close_count, 0)

        owned = FakeTransport()
        client = ModbusTcpClient(owned, owns_transport=True)
        client.close()
        client.close()
        self.assertEqual(owned.close_count, 1)


if __name__ == "__main__":
    unittest.main()
