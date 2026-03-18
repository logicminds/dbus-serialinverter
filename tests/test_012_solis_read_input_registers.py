"""Test 012: Solis.read_input_registers() data type handling and error paths."""
import sys
import os
import types
import logging
import unittest.mock as mock

for mod in ["dbus", "gi", "gi.repository", "gi.repository.GLib",
            "pymodbus", "pymodbus.client", "pymodbus.constants", "pymodbus.payload"]:
    sys.modules.setdefault(mod, types.ModuleType(mod))

_payload = sys.modules["pymodbus.payload"]
if not hasattr(_payload, "BinaryPayloadDecoder"):
    class _FakeDecoder:
        def __init__(self, v=0): self._v = v
        def decode_16bit_uint(self): return int(self._v)
        def decode_32bit_uint(self): return int(self._v)
        def decode_32bit_float(self): return float(self._v)
        def decode_string(self, n): return b"teststr "
    class _FakeBPD:
        @classmethod
        def fromRegisters(cls, regs, endian): return _FakeDecoder(regs[0] if regs else 0)
    _payload.BinaryPayloadDecoder = _FakeBPD

_constants = sys.modules["pymodbus.constants"]
if not hasattr(_constants, "Endian"):
    _constants.Endian = type("Endian", (), {"Big": 0})()

sys.modules["pymodbus.client"].ModbusSerialClient = mock.MagicMock

utils_stub = sys.modules.setdefault("utils", types.ModuleType("utils"))
if not hasattr(utils_stub, "logger"):
    utils_stub.logger = logging.getLogger("test")
for _attr, _val in [
    ("INVERTER_TYPE", "Solis"), ("INVERTER_MAX_AC_POWER", 800.0),
    ("INVERTER_PHASE", "L1"), ("INVERTER_POLL_INTERVAL", 1000), ("INVERTER_POSITION", 1),
]:
    if not hasattr(utils_stub, _attr):
        setattr(utils_stub, _attr, _val)

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "etc", "dbus-serialinverter"))

if "inverter" in sys.modules and not hasattr(sys.modules["inverter"], "Inverter"):
    del sys.modules["inverter"]

from inverter import Inverter
from solis import Solis


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_result(registers, is_error=False):
    r = mock.MagicMock()
    r.isError.return_value = is_error
    r.registers = registers
    return r


def _make_error_result():
    return _make_result([], is_error=True)


def _make_solis_with_client(client):
    s = Solis.__new__(Solis)
    Inverter.__init__(s, port="/dev/null", baudrate=9600, slave=1)
    s.type = "Solis"
    s.max_ac_power = 800.0
    s.phase = "L1"
    s.client = client
    return s


# ── Data type handling ────────────────────────────────────────────────────────

def test_u16_decode_with_scale():
    client = mock.MagicMock()
    client.connect.return_value = True
    client.read_input_registers.return_value = _make_result([500])
    s = _make_solis_with_client(client)
    success, val = s.read_input_registers(3035, 1, "u16", 0.1, 1)
    assert success is True
    assert abs(val - 50.0) < 0.01  # 500 * 0.1 = 50.0


def test_u32_decode():
    client = mock.MagicMock()
    client.connect.return_value = True
    client.read_input_registers.return_value = _make_result([1000])
    s = _make_solis_with_client(client)
    success, val = s.read_input_registers(3004, 2, "u32", 1, 0)
    assert success is True
    assert val == 1000


def test_float_decode():
    client = mock.MagicMock()
    client.connect.return_value = True
    client.read_input_registers.return_value = _make_result([230])
    s = _make_solis_with_client(client)
    success, val = s.read_input_registers(3035, 2, "float", 1, 2)
    assert success is True
    assert isinstance(val, float)


def test_string_decode_raises_type_error():
    """
    The 'string' data_type path in read_input_registers is broken in production:
    decode_string() returns bytes, and round(bytes * scale, digits) raises TypeError.
    This documents the known limitation — the string path is dead code in solis.py
    (serial reads use client.read_input_registers directly, not this helper).
    """
    client = mock.MagicMock()
    client.connect.return_value = True
    client.read_input_registers.return_value = _make_result([0])
    s = _make_solis_with_client(client)
    try:
        s.read_input_registers(3000, 4, "string", 1, 0)
        assert False, "Should raise TypeError (bytes cannot be scaled)"
    except TypeError:
        pass  # expected — string data_type is dead code in production


def test_unsupported_data_type_returns_false():
    client = mock.MagicMock()
    client.connect.return_value = True
    client.read_input_registers.return_value = _make_result([0])
    s = _make_solis_with_client(client)
    success, val = s.read_input_registers(3035, 1, "invalid_type", 1, 0)
    assert success is False
    assert val == 0


# ── Connection and error paths ────────────────────────────────────────────────

def test_connection_failure_returns_false():
    client = mock.MagicMock()
    client.connect.return_value = False
    s = _make_solis_with_client(client)
    success, val = s.read_input_registers(3035, 1, "u16", 1, 0)
    assert success is False
    assert val == 0


def test_register_error_response_returns_false():
    client = mock.MagicMock()
    client.connect.return_value = True
    client.read_input_registers.return_value = _make_error_result()
    s = _make_solis_with_client(client)
    success, val = s.read_input_registers(3035, 1, "u16", 1, 0)
    assert success is False
    assert val == 0


# ── write_registers error paths ───────────────────────────────────────────────

def test_write_registers_returns_false_on_connection_failure():
    client = mock.MagicMock()
    client.connect.return_value = False
    s = _make_solis_with_client(client)
    result = s.write_registers(3051, 5000)
    assert result is False


def test_write_registers_returns_false_on_error_response():
    client = mock.MagicMock()
    client.connect.return_value = True
    client.write_registers.return_value = _make_error_result()
    s = _make_solis_with_client(client)
    result = s.write_registers(3051, 5000)
    assert result is False


def test_write_registers_returns_true_on_success():
    client = mock.MagicMock()
    client.connect.return_value = True
    client.write_registers.return_value = _make_result([0])
    s = _make_solis_with_client(client)
    result = s.write_registers(3051, 5000)
    assert result is True


if __name__ == "__main__":
    test_u16_decode_with_scale()
    test_u32_decode()
    test_float_decode()
    test_string_decode()
    test_unsupported_data_type_returns_false()
    test_connection_failure_returns_false()
    test_register_error_response_returns_false()
    test_write_registers_returns_false_on_connection_failure()
    test_write_registers_returns_false_on_error_response()
    test_write_registers_returns_true_on_success()
    print("All 012 tests passed.")
