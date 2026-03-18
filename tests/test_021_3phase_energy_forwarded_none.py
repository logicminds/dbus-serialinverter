"""Test 021: In 3-phase mode, energy_forwarded is None (not 0) when unimplemented."""
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


def _make_3phase_solis():
    """Solis in 3-phase mode: read_input_registers returns output_type=1."""
    s = Solis.__new__(Solis)
    Inverter.__init__(s, port="/dev/null", baudrate=9600, slave=1)
    s.type = "Solis"
    s.max_ac_power = 800.0
    s.phase = "L1"
    s.energy_data["overall"]["power_limit"] = 800.0
    s.energy_data["overall"]["active_power_limit"] = 800.0

    def _patched_read(address, count, data_type, scale, digits):
        if address == 3002:
            return True, 1   # output_type=1 → 3-phase
        if address == 3014:
            return True, round(100.0 * scale, digits)  # overall energy_forwarded
        return True, round(0 * scale, digits)

    s.read_input_registers = _patched_read
    s.write_registers = lambda *a, **kw: True
    return s


# ── 3-phase energy_forwarded is None (not 0 or any integer) ──────────────────

def test_3phase_l1_energy_forwarded_is_none():
    s = _make_3phase_solis()
    s.read_status_data()
    assert s.energy_data["L1"]["energy_forwarded"] is None, (
        "L1 energy_forwarded must be None in 3-phase mode (not implemented)"
    )


def test_3phase_l2_energy_forwarded_is_none():
    s = _make_3phase_solis()
    s.read_status_data()
    assert s.energy_data["L2"]["energy_forwarded"] is None


def test_3phase_l3_energy_forwarded_is_none():
    s = _make_3phase_solis()
    s.read_status_data()
    assert s.energy_data["L3"]["energy_forwarded"] is None


def test_3phase_energy_forwarded_not_integer_zero():
    """Specifically guards against the old hardcoded-0 regression."""
    s = _make_3phase_solis()
    s.read_status_data()
    for phase in ["L1", "L2", "L3"]:
        val = s.energy_data[phase]["energy_forwarded"]
        assert val != 0, (
            f"{phase} energy_forwarded must not be 0 — use None for 'data unavailable'"
        )


def test_single_phase_energy_forwarded_is_still_populated():
    """Single-phase mode must continue to set energy_forwarded from the overall counter."""
    s = Solis.__new__(Solis)
    Inverter.__init__(s, port="/dev/null", baudrate=9600, slave=1)
    s.type = "Solis"
    s.max_ac_power = 800.0
    s.phase = "L1"
    s.energy_data["overall"]["power_limit"] = 800.0
    s.energy_data["overall"]["active_power_limit"] = 800.0

    def _patched_read(address, count, data_type, scale, digits):
        if address == 3002:
            return True, 0   # single-phase
        if address == 3014:
            return True, round(50.0 * scale, digits)  # 5.0 kWh
        return True, round(0 * scale, digits)

    s.read_input_registers = _patched_read
    s.write_registers = lambda *a, **kw: True
    s.read_status_data()

    assert s.energy_data["L1"]["energy_forwarded"] is not None
    assert s.energy_data["L1"]["energy_forwarded"] != 0


if __name__ == "__main__":
    test_3phase_l1_energy_forwarded_is_none()
    test_3phase_l2_energy_forwarded_is_none()
    test_3phase_l3_energy_forwarded_is_none()
    test_3phase_energy_forwarded_not_integer_zero()
    test_single_phase_energy_forwarded_is_still_populated()
    print("All 021 tests passed.")
