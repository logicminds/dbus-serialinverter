"""Test 020: Solis.test_connection() does not call get_settings()."""
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


def _make_solis_with_product_model(model_register_value):
    client = mock.MagicMock()
    client.is_socket_open.return_value = True
    client.read_input_registers.return_value = mock.MagicMock(
        **{"isError.return_value": False, "registers": [model_register_value]}
    )
    s = Solis.__new__(Solis)
    Inverter.__init__(s, port="/dev/null", baudrate=9600, slave=1)
    s.type = "Solis"
    s.client = client
    return s


# ── test_connection() does not call get_settings() ────────────────────────────

def test_test_connection_does_not_call_get_settings():
    """test_connection() must return True/False without calling get_settings()."""
    s = _make_solis_with_product_model(224)
    get_settings_calls = []
    s.get_settings = lambda: get_settings_calls.append(1) or True
    result = s.test_connection()
    assert result is True
    assert len(get_settings_calls) == 0, (
        "test_connection() must not call get_settings() (todo 009)"
    )


def test_startup_sequence_calls_get_settings_exactly_once():
    """Full startup: test_connection() + get_settings() = exactly 1 get_settings call."""
    s = _make_solis_with_product_model(224)
    # Override get_settings to count calls (and return True)
    call_count = [0]
    original = Solis.get_settings

    def counting(self):
        call_count[0] += 1
        return original(self)

    s.get_settings = lambda: counting(s)

    s.test_connection()   # must NOT call get_settings internally
    s.get_settings()      # setup_vedbus() calls it once

    assert call_count[0] == 1, (
        f"Expected get_settings() called exactly once, got {call_count[0]}"
    )


def test_test_connection_returns_false_for_wrong_model():
    s = _make_solis_with_product_model(999)  # not 224
    result = s.test_connection()
    assert result is False


def test_test_connection_returns_false_on_read_failure():
    client = mock.MagicMock()
    client.is_socket_open.return_value = True
    client.read_input_registers.return_value = mock.MagicMock(
        **{"isError.return_value": True, "registers": []}
    )
    s = Solis.__new__(Solis)
    Inverter.__init__(s, port="/dev/null", baudrate=9600, slave=1)
    s.type = "Solis"
    s.client = client
    result = s.test_connection()
    assert result is False


if __name__ == "__main__":
    test_test_connection_does_not_call_get_settings()
    test_startup_sequence_calls_get_settings_exactly_once()
    test_test_connection_returns_false_for_wrong_model()
    test_test_connection_returns_false_on_read_failure()
    print("All 020 tests passed.")
