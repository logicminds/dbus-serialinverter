"""Test 039: Samlex read_status_data() — per-register error branches.

Covers the individual `error = True` paths (samlex.py lines 155, 163, 170,
176, 182, 189, 195, 201, 226) that were missed because test_033 only fails
REG_AC_OUT_VOLTAGE, which is the first register read.  Each test below fails
exactly one register while all others succeed, exercising the corresponding
`else: error = True` branch.
"""
import sys
import os
import types
import logging
import configparser
import unittest.mock as mock


for _mod in ["dbus", "gi", "gi.repository", "gi.repository.GLib",
             "pymodbus", "pymodbus.client", "pymodbus.constants", "pymodbus.payload"]:
    sys.modules.setdefault(_mod, types.ModuleType(_mod))

sys.modules["pymodbus.client"].ModbusSerialClient = mock.MagicMock
sys.modules["pymodbus.constants"].Endian = type("Endian", (), {"Big": 0})()
if not hasattr(sys.modules["pymodbus.payload"], "BinaryPayloadDecoder"):
    sys.modules["pymodbus.payload"].BinaryPayloadDecoder = mock.MagicMock

utils_stub = sys.modules.setdefault("utils", types.ModuleType("utils"))
if not hasattr(utils_stub, "logger"):
    utils_stub.logger = logging.getLogger("test")
for _attr, _val in [
    ("INVERTER_TYPE", "Samlex"), ("INVERTER_MAX_AC_POWER", 4000.0),
    ("INVERTER_PHASE", "L1"), ("INVERTER_POLL_INTERVAL", 1000), ("INVERTER_POSITION", 1),
]:
    if not hasattr(utils_stub, _attr):
        setattr(utils_stub, _attr, _val)

_DRIVER_DIR = os.path.join(os.path.dirname(__file__), "..", "etc", "dbus-serialinverter")
if _DRIVER_DIR not in sys.path:
    sys.path.insert(0, _DRIVER_DIR)

if "inverter" in sys.modules and not hasattr(sys.modules["inverter"], "Inverter"):
    del sys.modules["inverter"]

from inverter import Inverter
from samlex import Samlex, REQUIRED_SAMLEX_REGISTERS


# ── Register map (same layout as test_033) ────────────────────────────────────

_REG_MAP = {key: 100 + i for i, key in enumerate(REQUIRED_SAMLEX_REGISTERS)}
_SCALES = {
    "SCALE_AC_OUT_VOLTAGE": "0.1",
    "SCALE_AC_OUT_CURRENT": "0.01",
    "SCALE_AC_OUT_POWER":   "1.0",
    "SCALE_DC_VOLTAGE":     "0.1",
    "SCALE_DC_CURRENT":     "0.01",
    "SCALE_AC_IN_VOLTAGE":  "0.1",
    "SCALE_AC_IN_CURRENT":  "0.01",
}


def _make_config():
    cfg = configparser.ConfigParser()
    cfg.add_section("SAMLEX_REGISTERS")
    for key, addr in _REG_MAP.items():
        cfg.set("SAMLEX_REGISTERS", key, _SCALES.get(key, str(addr)))
    return cfg


def _make_client(fail_address):
    """Client that fails reads at exactly one register address."""
    def _effect(address=0, count=1, slave=1):
        res = mock.MagicMock()
        if address == fail_address:
            res.isError.return_value = True
            res.registers = []
        else:
            res.isError.return_value = False
            res.registers = [1]  # non-zero so status logic picks 'Running'
        return res

    client = mock.MagicMock()
    client.is_socket_open.return_value = True
    client.read_input_registers.side_effect = _effect
    return client


def _make_samlex(fail_reg_key):
    s = Samlex.__new__(Samlex)
    Inverter.__init__(s, port="/dev/null", baudrate=9600, slave=1)
    s.type = "Samlex"
    s.energy_data["dc"]["charge_state"] = None
    s.client = _make_client(_REG_MAP[fail_reg_key])
    utils_stub.config = _make_config()
    return s


# ── Per-register failure tests ────────────────────────────────────────────────
# Each test fails exactly one register; read_status_data() must return False.

def test_false_when_ac_out_current_fails():
    """Line 155: error=True when REG_AC_OUT_CURRENT read fails."""
    s = _make_samlex("REG_AC_OUT_CURRENT")
    assert s.read_status_data() is False


def test_false_when_ac_out_power_fails():
    """Line 163: error=True when REG_AC_OUT_POWER read fails."""
    s = _make_samlex("REG_AC_OUT_POWER")
    assert s.read_status_data() is False


def test_false_when_dc_voltage_fails():
    """Line 170: error=True when REG_DC_VOLTAGE read fails."""
    s = _make_samlex("REG_DC_VOLTAGE")
    assert s.read_status_data() is False


def test_false_when_dc_current_fails():
    """Line 176: error=True when REG_DC_CURRENT read fails."""
    s = _make_samlex("REG_DC_CURRENT")
    assert s.read_status_data() is False


def test_false_when_soc_fails():
    """Line 182: error=True when REG_SOC read fails."""
    s = _make_samlex("REG_SOC")
    assert s.read_status_data() is False


def test_false_when_ac_in_voltage_fails():
    """Line 189: error=True when REG_AC_IN_VOLTAGE read fails."""
    s = _make_samlex("REG_AC_IN_VOLTAGE")
    assert s.read_status_data() is False


def test_false_when_ac_in_current_fails():
    """Line 195: error=True when REG_AC_IN_CURRENT read fails."""
    s = _make_samlex("REG_AC_IN_CURRENT")
    assert s.read_status_data() is False


def test_false_when_ac_in_connected_fails():
    """Line 201: error=True when REG_AC_IN_CONNECTED read fails."""
    s = _make_samlex("REG_AC_IN_CONNECTED")
    assert s.read_status_data() is False


def test_false_when_charge_state_fails():
    """Line 226: error=True when REG_CHARGE_STATE read fails."""
    s = _make_samlex("REG_CHARGE_STATE")
    assert s.read_status_data() is False


# ── Partial failure: other fields still populated ────────────────────────────

def test_ac_voltage_populated_despite_later_failure():
    """A failure in a later register does not clobber an earlier successful read."""
    s = _make_samlex("REG_CHARGE_STATE")  # only the last register fails
    s.read_status_data()
    # AC voltage should have been populated from REG_AC_OUT_VOLTAGE (register 100)
    assert s.energy_data["L1"]["ac_voltage"] is not None


if __name__ == "__main__":
    test_false_when_ac_out_current_fails()
    test_false_when_ac_out_power_fails()
    test_false_when_dc_voltage_fails()
    test_false_when_dc_current_fails()
    test_false_when_soc_fails()
    test_false_when_ac_in_voltage_fails()
    test_false_when_ac_in_current_fails()
    test_false_when_ac_in_connected_fails()
    test_false_when_charge_state_fails()
    test_ac_voltage_populated_despite_later_failure()
    print("All 039 tests passed.")
