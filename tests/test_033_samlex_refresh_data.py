"""Test 033: Samlex read_status_data() — AC/DC/AC-in fields, scaling, status mapping, failure."""
import sys
import os
import types
import logging
import configparser
import unittest.mock as mock

for mod in ["dbus", "gi", "gi.repository", "gi.repository.GLib",
            "pymodbus", "pymodbus.client", "pymodbus.constants", "pymodbus.payload"]:
    sys.modules.setdefault(mod, types.ModuleType(mod))

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

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "etc", "dbus-serialinverter"))

if "inverter" in sys.modules and not hasattr(sys.modules["inverter"], "Inverter"):
    del sys.modules["inverter"]

from inverter import Inverter
from samlex import Samlex, REQUIRED_SAMLEX_REGISTERS

# ── Register map used by tests ────────────────────────────────────────────────
# Assign sequential addresses starting at 100 so each register has a unique address.
_REG_MAP = {key: 100 + i for i, key in enumerate(REQUIRED_SAMLEX_REGISTERS)}
# Scales: voltage=0.1, current=0.01, power=1.0, connected/fault/state=raw
_SCALES = {
    "SCALE_AC_OUT_VOLTAGE": "0.1",
    "SCALE_AC_OUT_CURRENT": "0.01",
    "SCALE_AC_OUT_POWER":   "1.0",
    "SCALE_DC_VOLTAGE":     "0.1",
    "SCALE_DC_CURRENT":     "0.01",
    "SCALE_AC_IN_VOLTAGE":  "0.1",
    "SCALE_AC_IN_CURRENT":  "0.01",
}


def _make_config(extra_scales=None):
    cfg = configparser.ConfigParser()
    cfg.add_section("SAMLEX_REGISTERS")
    for key, addr in _REG_MAP.items():
        if key in _SCALES:
            cfg.set("SAMLEX_REGISTERS", key, _SCALES[key])
        else:
            cfg.set("SAMLEX_REGISTERS", key, str(addr))
    if extra_scales:
        for k, v in extra_scales.items():
            cfg.set("SAMLEX_REGISTERS", k, v)
    return cfg


def _make_client(address_regs=None, fail_addresses=None):
    """Mock client that returns address-specific register values."""
    address_regs = address_regs or {}
    fail_addresses = fail_addresses or set()

    def _effect(address=0, count=1, slave=1):
        res = mock.MagicMock()
        if address in fail_addresses:
            res.isError.return_value = True
            res.registers = []
            return res
        raw = []
        for offset in range(count):
            vals = address_regs.get(address + offset, [0])
            raw.append(vals[0] if vals else 0)
        res.isError.return_value = False
        res.registers = raw
        return res

    client = mock.MagicMock()
    client.is_socket_open.return_value = True
    client.connect.return_value = True
    client.read_input_registers.side_effect = _effect
    return client


def _make_samlex(client, cfg=None):
    s = Samlex.__new__(Samlex)
    Inverter.__init__(s, port="/dev/null", baudrate=9600, slave=1)
    s.type = "Samlex"
    s.energy_data["dc"]["charge_state"] = None
    s.phase = "L1"
    s.max_ac_power = 4000.0
    s.client = client
    utils_stub.config = cfg if cfg is not None else _make_config()
    return s


# ── AC output fields ──────────────────────────────────────────────────────────

def test_ac_voltage_scaled():
    """Raw register 2400 × scale 0.1 → 240.0 V."""
    s = _make_samlex(_make_client(address_regs={_REG_MAP["REG_AC_OUT_VOLTAGE"]: [2400]}))
    s.read_status_data()
    assert s.energy_data["L1"]["ac_voltage"] == 240.0


def test_ac_current_scaled():
    """Raw register 1500 × scale 0.01 → 15.0 A."""
    s = _make_samlex(_make_client(address_regs={_REG_MAP["REG_AC_OUT_CURRENT"]: [1500]}))
    s.read_status_data()
    assert s.energy_data["L1"]["ac_current"] == 15.0


def test_ac_power_propagates_to_overall():
    """AC power is stored on both L1 and overall."""
    s = _make_samlex(_make_client(address_regs={_REG_MAP["REG_AC_OUT_POWER"]: [3600]}))
    s.read_status_data()
    assert s.energy_data["L1"]["ac_power"] == 3600.0
    assert s.energy_data["overall"]["ac_power"] == 3600.0


# ── DC / battery fields ───────────────────────────────────────────────────────

def test_dc_voltage_scaled():
    """Raw register 240 × scale 0.1 → 24.0 V."""
    s = _make_samlex(_make_client(address_regs={_REG_MAP["REG_DC_VOLTAGE"]: [240]}))
    s.read_status_data()
    assert s.energy_data["dc"]["voltage"] == 24.0


def test_dc_current_scaled():
    """Raw register 5000 × scale 0.01 → 50.0 A."""
    s = _make_samlex(_make_client(address_regs={_REG_MAP["REG_DC_CURRENT"]: [5000]}))
    s.read_status_data()
    assert s.energy_data["dc"]["current"] == 50.0


def test_soc_stored():
    s = _make_samlex(_make_client(address_regs={_REG_MAP["REG_SOC"]: [75]}))
    s.read_status_data()
    assert s.energy_data["dc"]["soc"] == 75.0


# ── AC input fields ───────────────────────────────────────────────────────────

def test_ac_in_connected_stored():
    s = _make_samlex(_make_client(address_regs={_REG_MAP["REG_AC_IN_CONNECTED"]: [1]}))
    s.read_status_data()
    assert s.energy_data["ac_in"]["connected"] == 1


def test_ac_in_voltage_scaled():
    s = _make_samlex(_make_client(address_regs={_REG_MAP["REG_AC_IN_VOLTAGE"]: [1200]}))
    s.read_status_data()
    assert s.energy_data["ac_in"]["voltage"] == 120.0


# ── Status / fault mapping ────────────────────────────────────────────────────

def test_status_running_when_fault_zero_and_power_positive():
    """fault=0, ac_power>0 → status 7 (Running)."""
    s = _make_samlex(_make_client(address_regs={
        _REG_MAP["REG_FAULT"]:       [0],
        _REG_MAP["REG_AC_OUT_POWER"]: [1000],
    }))
    s.read_status_data()
    assert s.status == 7


def test_status_standby_when_fault_zero_and_power_zero():
    """fault=0, ac_power=0 → status 8 (Standby)."""
    s = _make_samlex(_make_client(address_regs={
        _REG_MAP["REG_FAULT"]:       [0],
        _REG_MAP["REG_AC_OUT_POWER"]: [0],
    }))
    s.read_status_data()
    assert s.status == 8


def test_status_error_when_fault_nonzero():
    """Any non-zero fault register → status 10 (Error)."""
    s = _make_samlex(_make_client(address_regs={_REG_MAP["REG_FAULT"]: [1]}))
    s.read_status_data()
    assert s.status == 10


def test_status_error_on_fault_register_read_failure():
    """Failed fault register read → status 10."""
    s = _make_samlex(_make_client(fail_addresses={_REG_MAP["REG_FAULT"]}))
    s.read_status_data()
    assert s.status == 10


# ── Failure return value ──────────────────────────────────────────────────────

def test_returns_true_when_all_reads_succeed():
    s = _make_samlex(_make_client())
    assert s.read_status_data() is True


def test_returns_false_when_any_read_fails():
    """A single batch failure must make read_status_data() return False."""
    s = _make_samlex(_make_client(fail_addresses={_REG_MAP["REG_AC_OUT_VOLTAGE"]}))
    assert s.read_status_data() is False


# ── Charge state ──────────────────────────────────────────────────────────────

def test_charge_state_stored():
    s = _make_samlex(_make_client(address_regs={_REG_MAP["REG_CHARGE_STATE"]: [3]}))
    s.read_status_data()
    assert s.energy_data["dc"]["charge_state"] == 3


if __name__ == "__main__":
    test_ac_voltage_scaled()
    test_ac_current_scaled()
    test_ac_power_propagates_to_overall()
    test_dc_voltage_scaled()
    test_dc_current_scaled()
    test_soc_stored()
    test_ac_in_connected_stored()
    test_ac_in_voltage_scaled()
    test_status_running_when_fault_zero_and_power_positive()
    test_status_standby_when_fault_zero_and_power_zero()
    test_status_error_when_fault_nonzero()
    test_status_error_on_fault_register_read_failure()
    test_returns_true_when_all_reads_succeed()
    test_returns_false_when_any_read_fails()
    test_charge_state_stored()
    print("All 033 tests passed.")
