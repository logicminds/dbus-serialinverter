"""Test 022: read_status_data() uses batched Modbus reads (≤5 transactions)."""
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


def _make_client(output_type=0):
    """Client that returns output_type in the first register of any 3002 batch."""
    def _effect(address=0, count=1, slave=1):
        res = mock.MagicMock()
        res.isError.return_value = False
        if address == 3002:
            res.registers = [output_type, 0, 0, 0]
        else:
            res.registers = [0] * max(count, 6)
        return res

    client = mock.MagicMock()
    client.is_socket_open.return_value = True
    client.connect.return_value = True
    client.read_input_registers.side_effect = _effect
    client.write_registers.return_value = mock.MagicMock(**{"isError.return_value": False})
    return client


def _make_solis(output_type=0):
    s = Solis.__new__(Solis)
    Inverter.__init__(s, port="/dev/null", baudrate=9600, slave=1)
    s.type = "Solis"
    s.max_ac_power = 800.0
    s.phase = "L1"
    s.energy_data["overall"]["power_limit"] = 0.0
    s.energy_data["overall"]["active_power_limit"] = 0.0
    s.client = _make_client(output_type)
    return s


# ── Transaction count ─────────────────────────────────────────────────────────

def test_single_phase_poll_uses_at_most_5_transactions():
    """Single-phase read_status_data() must issue ≤5 Modbus read transactions."""
    s = _make_solis(output_type=0)
    s.read_status_data()
    count = s.client.read_input_registers.call_count
    assert count <= 5, f"Expected ≤5 transactions, got {count}"


def test_3phase_poll_uses_at_most_5_transactions():
    """3-phase read_status_data() must issue ≤5 Modbus read transactions."""
    s = _make_solis(output_type=1)
    s.read_status_data()
    count = s.client.read_input_registers.call_count
    assert count <= 5, f"Expected ≤5 transactions, got {count}"


# ── Batch 1: output_type + ac_power (3002-3005) ───────────────────────────────

def test_batch1_reads_output_type_and_ac_power_together():
    """Batch 1 must start at address 3002 and read 4 registers."""
    s = _make_solis()
    s.read_status_data()
    calls = s.client.read_input_registers.call_args_list
    batch1 = next((c for c in calls if c.kwargs.get('address') == 3002), None)
    assert batch1 is not None, "Expected a batch read starting at address 3002"
    assert batch1.kwargs['count'] == 4, (
        f"Batch 1 should read 4 registers, got {batch1.kwargs['count']}"
    )


def test_ac_power_decoded_from_batch1():
    """ac_power (u32 at 3004-3005) is decoded from batch 1 at index [2:4]."""
    # registers [output_type=0, unused=0, hi=0, lo=500] → u32 = 500
    def _effect(address=0, count=1, slave=1):
        res = mock.MagicMock()
        res.isError.return_value = False
        if address == 3002:
            # FakeBPD.fromRegisters(regs[2:4]) takes regs[0] of the slice as its value.
            # Put 500 at index [2] so slice [2:4]=[500,0] → FakeDecoder(500) → 500W.
            res.registers = [0, 0, 500, 0]  # output_type=0, unused, ac_power=500W
        else:
            res.registers = [0] * max(count, 6)
        return res

    client = mock.MagicMock()
    client.is_socket_open.return_value = True
    client.read_input_registers.side_effect = _effect

    s = Solis.__new__(Solis)
    Inverter.__init__(s, port="/dev/null", baudrate=9600, slave=1)
    s.type = "Solis"
    s.max_ac_power = 800.0
    s.phase = "L1"
    s.energy_data["overall"]["power_limit"] = 0.0
    s.energy_data["overall"]["active_power_limit"] = 0.0
    s.client = client
    s.read_status_data()
    assert s.energy_data['overall']['ac_power'] == 500


# ── Batch 3 (single-phase): voltage + current (3035-3038) ────────────────────

def test_single_phase_batch3_reads_4_regs_from_3035():
    """Single-phase batch 3 starts at 3035 and reads 4 registers."""
    s = _make_solis(output_type=0)
    s.read_status_data()
    calls = s.client.read_input_registers.call_args_list
    batch3 = next((c for c in calls if c.kwargs.get('address') == 3035), None)
    assert batch3 is not None, "Expected a batch read starting at 3035"
    assert batch3.kwargs['count'] == 4


def test_single_phase_voltage_and_current_from_batch3():
    """Voltage comes from regs[0] and current from regs[3] of the 3035 batch."""
    # 3035 batch: [voltage_raw=2300, 0, 0, current_raw=35]
    # → voltage = 230.0, current = 3.5
    def _effect(address=0, count=1, slave=1):
        res = mock.MagicMock()
        res.isError.return_value = False
        if address == 3002:
            res.registers = [0, 0, 0, 0]   # single-phase, 0W
        elif address == 3035:
            res.registers = [2300, 0, 0, 35]  # V=230.0, A=3.5
        else:
            res.registers = [0] * max(count, 6)
        return res

    client = mock.MagicMock()
    client.is_socket_open.return_value = True
    client.read_input_registers.side_effect = _effect

    s = Solis.__new__(Solis)
    Inverter.__init__(s, port="/dev/null", baudrate=9600, slave=1)
    s.type = "Solis"
    s.max_ac_power = 800.0
    s.phase = "L1"
    s.energy_data["overall"]["power_limit"] = 0.0
    s.energy_data["overall"]["active_power_limit"] = 0.0
    s.client = client
    s.read_status_data()

    assert s.energy_data["L1"]["ac_voltage"] == 230.0
    assert abs(s.energy_data["L1"]["ac_current"] - 3.5) < 0.01


# ── Batch 3 (3-phase): all V+A (3033-3038) ───────────────────────────────────

def test_3phase_batch3_reads_6_regs_from_3033():
    """3-phase batch 3 starts at 3033 and reads 6 registers."""
    s = _make_solis(output_type=1)
    s.read_status_data()
    calls = s.client.read_input_registers.call_args_list
    batch3 = next((c for c in calls if c.kwargs.get('address') == 3033), None)
    assert batch3 is not None, "Expected a batch read starting at 3033"
    assert batch3.kwargs['count'] == 6


def test_3phase_voltages_and_currents_from_batch3():
    """All 6 per-phase values decoded correctly from the 3033 batch."""
    # [L1V=2300, L2V=2310, L3V=2320, L1A=10, L2A=20, L3A=30]
    def _effect(address=0, count=1, slave=1):
        res = mock.MagicMock()
        res.isError.return_value = False
        if address == 3002:
            res.registers = [1, 0, 0, 0]   # 3-phase
        elif address == 3033:
            res.registers = [2300, 2310, 2320, 10, 20, 30]
        else:
            res.registers = [0] * max(count, 6)
        return res

    client = mock.MagicMock()
    client.is_socket_open.return_value = True
    client.read_input_registers.side_effect = _effect

    s = Solis.__new__(Solis)
    Inverter.__init__(s, port="/dev/null", baudrate=9600, slave=1)
    s.type = "Solis"
    s.max_ac_power = 800.0
    s.phase = "L1"
    s.energy_data["overall"]["power_limit"] = 0.0
    s.energy_data["overall"]["active_power_limit"] = 0.0
    s.client = client
    s.read_status_data()

    assert s.energy_data["L1"]["ac_voltage"] == 230.0
    assert s.energy_data["L2"]["ac_voltage"] == 231.0
    assert s.energy_data["L3"]["ac_voltage"] == 232.0
    assert abs(s.energy_data["L1"]["ac_current"] - 1.0) < 0.01
    assert abs(s.energy_data["L2"]["ac_current"] - 2.0) < 0.01
    assert abs(s.energy_data["L3"]["ac_current"] - 3.0) < 0.01


if __name__ == "__main__":
    test_single_phase_poll_uses_at_most_5_transactions()
    test_3phase_poll_uses_at_most_5_transactions()
    test_batch1_reads_output_type_and_ac_power_together()
    test_ac_power_decoded_from_batch1()
    test_single_phase_batch3_reads_4_regs_from_3035()
    test_single_phase_voltage_and_current_from_batch3()
    test_3phase_batch3_reads_6_regs_from_3033()
    test_3phase_voltages_and_currents_from_batch3()
    print("All 022 tests passed.")
