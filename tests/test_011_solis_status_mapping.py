"""Test 011: Solis status register → Victron status code mapping."""
import sys
import os
import types
import logging
import unittest.mock as mock

for mod in ["dbus", "gi", "gi.repository", "gi.repository.GLib",
            "pymodbus", "pymodbus.client", "pymodbus.constants", "pymodbus.payload"]:
    sys.modules.setdefault(mod, types.ModuleType(mod))

# Minimal pymodbus stubs (idempotent — conftest may already have set these)
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


# ── Helper: solis instance with read_input_registers patched at method level ──

def _make_solis(register_map=None, success_default=True, value_default=0):
    """
    Build a Solis instance whose read_input_registers is monkey-patched.

    register_map: {address: (success, raw_value)} — overrides for specific registers.
    All other addresses return (success_default, value_default).
    write_registers always succeeds.
    """
    s = Solis.__new__(Solis)
    Inverter.__init__(s, port="/dev/null", baudrate=9600, slave=1)
    s.type = "Solis"
    s.max_ac_power = 800.0
    s.phase = "L1"
    # Set power_limit so the write-path comparison (power_limit_watts != power_limit)
    # doesn't divide None by a float.  0.0 matches what register 3049 returns when
    # value_default=0, so no spurious write is triggered.
    s.energy_data["overall"]["power_limit"] = 0.0
    register_map = register_map or {}

    def _patched_read(address, count, data_type, scale, digits):
        if address in register_map:
            ok, raw = register_map[address]
            if not ok:
                return False, 0
            return True, round(raw * scale, digits)
        if not success_default:
            return False, 0
        return True, round(value_default * scale, digits)

    s.read_input_registers = _patched_read
    s.write_registers = lambda *a, **kw: True
    return s


# ── Status code mapping ───────────────────────────────────────────────────────
# Register 3043: raw Solis status → Victron status code
# 0→0 (Waiting), 1→1 (OpenRun), 2→2 (SoftRun), 3→7 (Generating), else→10 (Fault)

def test_status_0_maps_to_0():
    s = _make_solis(register_map={3043: (True, 0)})
    s.read_status_data()
    assert s.status == 0


def test_status_1_maps_to_1():
    s = _make_solis(register_map={3043: (True, 1)})
    s.read_status_data()
    assert s.status == 1


def test_status_2_maps_to_2():
    s = _make_solis(register_map={3043: (True, 2)})
    s.read_status_data()
    assert s.status == 2


def test_status_3_maps_to_7():
    s = _make_solis(register_map={3043: (True, 3)})
    s.read_status_data()
    assert s.status == 7


def test_status_4_maps_to_10_fault():
    """Values outside 0-3 should map to Victron status 10 (Fault)."""
    s = _make_solis(register_map={3043: (True, 4)})
    s.read_status_data()
    assert s.status == 10


def test_status_255_maps_to_10_fault():
    s = _make_solis(register_map={3043: (True, 255)})
    s.read_status_data()
    assert s.status == 10


def test_status_read_failure_sets_standby():
    """When register 3043 read fails, status must be set to 8 (Standby/Off)."""
    s = _make_solis(register_map={3043: (False, 0)})
    s.read_status_data()
    assert s.status == 8


# ── read_status_data return value ─────────────────────────────────────────────

def test_returns_true_when_all_reads_succeed():
    s = _make_solis()
    result = s.read_status_data()
    assert result is True


def test_returns_false_when_any_read_fails():
    # Fail the overall AC power read
    s = _make_solis(register_map={3004: (False, 0)})
    result = s.read_status_data()
    assert result is False


if __name__ == "__main__":
    test_status_0_maps_to_0()
    test_status_1_maps_to_1()
    test_status_2_maps_to_2()
    test_status_3_maps_to_7()
    test_status_4_maps_to_10_fault()
    test_status_255_maps_to_10_fault()
    test_status_read_failure_sets_standby()
    test_returns_true_when_all_reads_succeed()
    test_returns_false_when_any_read_fails()
    print("All 011 tests passed.")
