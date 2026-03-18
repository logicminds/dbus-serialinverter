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


def _make_client(output_type=0, overall_energy_raw=0):
    """
    output_type: 0=single-phase, 1=3-phase (returned as first reg of batch 3002)
    overall_energy_raw: raw register value for 3014 (energy_forwarded * 10)
    """
    def _effect(address=0, count=1, slave=1):
        res = mock.MagicMock()
        res.isError.return_value = False
        if address == 3002:
            # Batch 1: [output_type, unused, ac_power_hi, ac_power_lo]
            res.registers = [output_type, 0, 0, 0]
        elif address == 3014:
            res.registers = [overall_energy_raw] + [0] * (count - 1)
        elif address == 3033:
            # 3-phase V+A batch (6 regs)
            res.registers = [0] * max(count, 6)
        elif address == 3035:
            # single-phase V+A batch (4 regs)
            res.registers = [0] * max(count, 4)
        else:
            res.registers = [0] * max(count, 1)
        return res

    client = mock.MagicMock()
    client.is_socket_open.return_value = True
    client.connect.return_value = True
    client.read_input_registers.side_effect = _effect
    client.write_registers.return_value = mock.MagicMock(**{"isError.return_value": False})
    return client


def _make_solis(output_type=0, overall_energy_raw=0):
    s = Solis.__new__(Solis)
    Inverter.__init__(s, port="/dev/null", baudrate=9600, slave=1)
    s.type = "Solis"
    s.max_ac_power = 800.0
    s.phase = "L1"
    s.energy_data["overall"]["power_limit"] = 0.0
    s.energy_data["overall"]["active_power_limit"] = 0.0
    s.client = _make_client(output_type, overall_energy_raw)
    return s


# ── 3-phase energy_forwarded is None (not 0 or any integer) ──────────────────

def test_3phase_l1_energy_forwarded_is_none():
    s = _make_solis(output_type=1)
    s.read_status_data()
    assert s.energy_data["L1"]["energy_forwarded"] is None, (
        "L1 energy_forwarded must be None in 3-phase mode (not implemented)"
    )


def test_3phase_l2_energy_forwarded_is_none():
    s = _make_solis(output_type=1)
    s.read_status_data()
    assert s.energy_data["L2"]["energy_forwarded"] is None


def test_3phase_l3_energy_forwarded_is_none():
    s = _make_solis(output_type=1)
    s.read_status_data()
    assert s.energy_data["L3"]["energy_forwarded"] is None


def test_3phase_energy_forwarded_not_integer_zero():
    """Specifically guards against the old hardcoded-0 regression."""
    s = _make_solis(output_type=1)
    s.read_status_data()
    for phase in ["L1", "L2", "L3"]:
        val = s.energy_data[phase]["energy_forwarded"]
        assert val != 0, (
            f"{phase} energy_forwarded must not be 0 — use None for 'data unavailable'"
        )


def test_single_phase_energy_forwarded_is_still_populated():
    """Single-phase mode must continue to set energy_forwarded from the overall counter."""
    # overall_energy_raw = 500 → 500 * 0.1 = 50.0 kWh
    s = _make_solis(output_type=0, overall_energy_raw=500)
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
