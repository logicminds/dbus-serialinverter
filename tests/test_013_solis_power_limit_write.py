"""Test 013: Solis power limit write triggers only when the active limit differs."""
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

def _make_solis(active_limit_percent, desired_limit_watts=None, max_ac_power=800.0):
    """
    active_limit_percent: what register 3049 reports (e.g. 50 → 50% → 400W active)
    desired_limit_watts: what energy_data['overall']['power_limit'] is set to
                         (defaults to same as active, so no write should fire)
    """
    active_limit_watts = max_ac_power * (active_limit_percent / 100)
    if desired_limit_watts is None:
        desired_limit_watts = active_limit_watts

    s = Solis.__new__(Solis)
    Inverter.__init__(s, port="/dev/null", baudrate=9600, slave=1)
    s.type = "Solis"
    s.max_ac_power = max_ac_power
    s.phase = "L1"
    s.energy_data["overall"]["power_limit"] = desired_limit_watts
    s.energy_data["overall"]["active_power_limit"] = active_limit_watts

    def _patched_read(address, count, data_type, scale, digits):
        if address == 3049:
            # Register 3049 stores percent*100 (e.g. 5000 for 50%).
            # read_input_registers applies scale=0.01, returning the percent (50.0).
            # read_status_data then does: power_limit_watts = max_ac * (int(percent)/100).
            # We return the percent directly so the caller's arithmetic works correctly.
            return True, float(active_limit_percent)
        return True, round(0 * scale, digits)

    s.read_input_registers = _patched_read
    return s


# ── Write triggered when limit changed ────────────────────────────────────────

def test_write_triggered_when_power_limit_changes():
    # Active: 50% (400W), desired: 100% (800W)
    s = _make_solis(active_limit_percent=50, desired_limit_watts=800.0)
    write_mock = mock.MagicMock(return_value=True)
    s.write_registers = write_mock
    s.read_status_data()
    assert write_mock.call_count == 1, "write_registers must be called when limit changed"


def test_write_value_is_correct_percentage_times_100():
    # Active: 50% (400W), desired: 100% (800W) → write 100*100 = 10000
    s = _make_solis(active_limit_percent=50, desired_limit_watts=800.0)
    write_mock = mock.MagicMock(return_value=True)
    s.write_registers = write_mock
    s.read_status_data()
    written_value = write_mock.call_args[0][1]
    assert written_value == 10000, f"Expected 10000, got {written_value}"


def test_write_value_for_half_power():
    # Active: 100%, desired: 50% (400W) → write 50*100 = 5000
    s = _make_solis(active_limit_percent=100, desired_limit_watts=400.0)
    write_mock = mock.MagicMock(return_value=True)
    s.write_registers = write_mock
    s.read_status_data()
    written_value = write_mock.call_args[0][1]
    assert written_value == 5000, f"Expected 5000, got {written_value}"


# ── No write when limit unchanged ─────────────────────────────────────────────

def test_write_not_triggered_when_limit_unchanged():
    # Active: 100% (800W), desired: 100% (800W) — same
    s = _make_solis(active_limit_percent=100, desired_limit_watts=800.0)
    write_mock = mock.MagicMock(return_value=True)
    s.write_registers = write_mock
    s.read_status_data()
    assert write_mock.call_count == 0, "write_registers must NOT be called when limit unchanged"


# ── Clamping: written value always in [0, 10000] ─────────────────────────────

def test_write_value_clamped_when_desired_exceeds_max():
    # Desired 9999W >> max_ac_power=800W → clamped to 100% → 10000
    s = _make_solis(active_limit_percent=50, desired_limit_watts=9999.0)
    write_mock = mock.MagicMock(return_value=True)
    s.write_registers = write_mock
    s.read_status_data()
    written_value = write_mock.call_args[0][1]
    assert 0 <= written_value <= 10000, f"Written value {written_value} out of [0, 10000]"
    assert written_value == 10000


def test_write_value_clamped_when_desired_is_negative():
    # Desired -500W → clamped to 0% → 0
    s = _make_solis(active_limit_percent=50, desired_limit_watts=-500.0)
    write_mock = mock.MagicMock(return_value=True)
    s.write_registers = write_mock
    s.read_status_data()
    written_value = write_mock.call_args[0][1]
    assert written_value == 0, f"Expected 0, got {written_value}"


if __name__ == "__main__":
    test_write_triggered_when_power_limit_changes()
    test_write_value_is_correct_percentage_times_100()
    test_write_value_for_half_power()
    test_write_not_triggered_when_limit_unchanged()
    test_write_value_clamped_when_desired_exceeds_max()
    test_write_value_clamped_when_desired_is_negative()
    print("All 013 tests passed.")
