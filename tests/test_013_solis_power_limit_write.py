"""Test 013: Solis.apply_power_limit() encoding/clamping; read_status_data() never writes."""
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


# ── read_status_data() must never call write_registers() ─────────────────────

def test_read_status_data_never_writes_when_limit_changes():
    """Power limit write is no longer in the read path — read_status_data() is read-only."""
    s = _make_solis(active_limit_percent=50, desired_limit_watts=800.0)
    write_mock = mock.MagicMock(return_value=True)
    s.write_registers = write_mock
    s.read_status_data()
    assert write_mock.call_count == 0, "read_status_data() must not call write_registers()"


def test_read_status_data_never_writes_when_limit_unchanged():
    s = _make_solis(active_limit_percent=100, desired_limit_watts=800.0)
    write_mock = mock.MagicMock(return_value=True)
    s.write_registers = write_mock
    s.read_status_data()
    assert write_mock.call_count == 0


# ── apply_power_limit() encoding and clamping ─────────────────────────────────

def test_apply_power_limit_full_power():
    # 800W of 800W max → 100% → register value 10000
    s = _make_solis(active_limit_percent=50)
    write_mock = mock.MagicMock(return_value=True)
    s.write_registers = write_mock
    s.apply_power_limit(800.0)
    written_value = write_mock.call_args[0][1]
    assert written_value == 10000, f"Expected 10000, got {written_value}"


def test_apply_power_limit_half_power():
    # 400W of 800W max → 50% → register value 5000
    s = _make_solis(active_limit_percent=100)
    write_mock = mock.MagicMock(return_value=True)
    s.write_registers = write_mock
    s.apply_power_limit(400.0)
    written_value = write_mock.call_args[0][1]
    assert written_value == 5000, f"Expected 5000, got {written_value}"


def test_apply_power_limit_clamped_when_desired_exceeds_max():
    # 9999W >> 800W max → clamped to 100% → 10000
    s = _make_solis(active_limit_percent=50)
    write_mock = mock.MagicMock(return_value=True)
    s.write_registers = write_mock
    s.apply_power_limit(9999.0)
    written_value = write_mock.call_args[0][1]
    assert 0 <= written_value <= 10000
    assert written_value == 10000


def test_apply_power_limit_clamped_when_negative():
    # -500W → clamped to 0% → 0
    s = _make_solis(active_limit_percent=50)
    write_mock = mock.MagicMock(return_value=True)
    s.write_registers = write_mock
    s.apply_power_limit(-500.0)
    written_value = write_mock.call_args[0][1]
    assert written_value == 0, f"Expected 0, got {written_value}"


if __name__ == "__main__":
    test_read_status_data_never_writes_when_limit_changes()
    test_read_status_data_never_writes_when_limit_unchanged()
    test_apply_power_limit_full_power()
    test_apply_power_limit_half_power()
    test_apply_power_limit_clamped_when_desired_exceeds_max()
    test_apply_power_limit_clamped_when_negative()
    print("All 013 tests passed.")
