"""Test 039: Samlex read_status_data() — per-group batch failure coverage.

With group-batch reads (018), Modbus failures occur at the batch start address.
Each test below fails exactly one batch group while all others succeed.
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


# ── Register map (same sequential layout as test_033) ─────────────────────────

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

# Batch group start addresses (min address in each group, matching _read_group logic)
_AC_OUT_START  = min(_REG_MAP[k] for k in ["REG_AC_OUT_VOLTAGE", "REG_AC_OUT_CURRENT", "REG_AC_OUT_POWER"])
_DC_START      = min(_REG_MAP[k] for k in ["REG_DC_VOLTAGE", "REG_DC_CURRENT"])
_AC_IN_START   = min(_REG_MAP[k] for k in ["REG_AC_IN_VOLTAGE", "REG_AC_IN_CURRENT", "REG_AC_IN_CONNECTED"])
_STATUS_START  = min(_REG_MAP[k] for k in ["REG_FAULT", "REG_CHARGE_STATE"])


def _make_config():
    cfg = configparser.ConfigParser()
    cfg.add_section("SAMLEX_REGISTERS")
    for key, addr in _REG_MAP.items():
        cfg.set("SAMLEX_REGISTERS", key, _SCALES.get(key, str(addr)))
    return cfg


def _make_client(fail_batch_start):
    """Client that fails the batch read whose start address equals fail_batch_start."""
    def _effect(address=0, count=1, slave=1):
        res = mock.MagicMock()
        if address == fail_batch_start:
            res.isError.return_value = True
            res.registers = []
        else:
            res.isError.return_value = False
            res.registers = [1] * count  # non-zero → status logic picks 'Running'
        return res

    client = mock.MagicMock()
    client.is_socket_open.return_value = True
    client.read_holding_registers.side_effect = _effect
    return client


def _make_samlex(fail_batch_start):
    s = Samlex.__new__(Samlex)
    Inverter.__init__(s, port="/dev/null", baudrate=9600, slave=1)
    s.type = "Samlex"
    s.energy_data["dc"]["charge_state"] = None
    s.client = _make_client(fail_batch_start)
    utils_stub.config = _make_config()
    return s


# ── Per-group failure tests ───────────────────────────────────────────────────
# Each test fails exactly one batch group; read_status_data() must return False.

def test_false_when_ac_out_group_fails():
    """AC output batch failure → read_status_data() returns False."""
    s = _make_samlex(_AC_OUT_START)
    assert s.read_status_data() is False


def test_false_when_dc_group_fails():
    """DC/battery batch failure → read_status_data() returns False."""
    s = _make_samlex(_DC_START)
    assert s.read_status_data() is False


def test_false_when_ac_in_group_fails():
    """AC input batch failure → read_status_data() returns False."""
    s = _make_samlex(_AC_IN_START)
    assert s.read_status_data() is False


def test_false_when_status_group_fails():
    """Status/fault batch failure → read_status_data() returns False."""
    s = _make_samlex(_STATUS_START)
    assert s.read_status_data() is False


# ── Cross-group isolation ─────────────────────────────────────────────────────

def test_ac_voltage_populated_despite_status_group_failure():
    """A failure in the status batch does not clobber earlier successful AC out batch."""
    s = _make_samlex(_STATUS_START)
    s.read_status_data()
    # AC voltage should have been populated from the AC out batch (address _AC_OUT_START)
    assert s.energy_data["L1"]["ac_voltage"] is not None


if __name__ == "__main__":
    test_false_when_ac_out_group_fails()
    test_false_when_dc_group_fails()
    test_false_when_ac_in_group_fails()
    test_false_when_status_group_fails()
    test_ac_voltage_populated_despite_status_group_failure()
    print("All 039 tests passed.")
