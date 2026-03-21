# -*- coding: utf-8 -*-
"""Test 043: All Victron dashboard fields are populated for every scenario.

Covers every energy_data field that maps to a visible D-Bus path:

  AC Output   /Ac/Out/L1/V,I,P      ← L1.ac_voltage/current/power
  AC Input    /Ac/ActiveIn/L1/V,I,P ← ac_in.voltage/current/power
              /Ac/ActiveIn/Connected ← ac_in.connected
  DC/Battery  /Dc/0/Voltage,Current  ← dc.voltage/current
              /Dc/0/Power            ← dc.power   (derived: V×I)
              /Soc                   ← dc.soc
  Charge      /VebusChargeState      ← dc.charge_state
  Status      /State                 ← inverter.status

Each scenario is tested in isolation so regressions are pinpointed immediately.
"""

import sys
import os
import types
import logging
import configparser
import unittest.mock as mock

# ── stub VenusOS / pymodbus packages ─────────────────────────────────────────
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

# ── register map (sequential addresses; same approach as test_033) ─────────────
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


def _raw(eng_val, scale_str):
    """Convert an engineering value to the raw uint16 written to Modbus.

    Negative values are stored as two's complement uint16, matching real
    Modbus hardware behaviour for signed int16 registers.
    """
    raw = round(eng_val / float(scale_str))
    if raw < 0:
        raw = raw & 0xFFFF
    return raw


# ── Scenario register tables ──────────────────────────────────────────────────
# Each scenario maps REG_* keys to the raw uint16 the mock server would return.
# Derived from the same engineering values used in samlex_tcp_server.py.
_SCENARIOS = {
    "normal": {
        "REG_IDENTITY":       16420,
        "REG_AC_IN_CONNECTED": 1,       # 1 = AC input normal
        "REG_FAULT":           0,
        "REG_DC_VOLTAGE":      _raw(26.4,  "0.1"),   # 264
        "REG_DC_CURRENT":      _raw(5.2,   "0.01"),  # 520  (positive = charging)
        "REG_AC_OUT_VOLTAGE":  _raw(120.0, "0.1"),   # 1200
        "REG_AC_OUT_CURRENT":  _raw(8.33,  "0.01"),  # 833
        "REG_AC_OUT_POWER":    _raw(1000.0,"1.0"),   # 1000
        "REG_SOC":             85,
        "REG_CHARGE_STATE":    2,        # Absorption
        "REG_AC_IN_VOLTAGE":   _raw(120.0, "0.1"),   # 1200
        "REG_AC_IN_CURRENT":   _raw(30.17, "0.01"),  # 3017
    },
    "fault": {
        "REG_IDENTITY":       16420,
        "REG_AC_IN_CONNECTED": 1,
        "REG_FAULT":           1,        # non-zero = fault
        "REG_DC_VOLTAGE":      _raw(26.4,  "0.1"),
        "REG_DC_CURRENT":      _raw(5.2,   "0.01"),
        "REG_AC_OUT_VOLTAGE":  _raw(120.0, "0.1"),
        "REG_AC_OUT_CURRENT":  _raw(8.33,  "0.01"),
        "REG_AC_OUT_POWER":    _raw(1000.0,"1.0"),
        "REG_SOC":             85,
        "REG_CHARGE_STATE":    2,
        "REG_AC_IN_VOLTAGE":   _raw(120.0, "0.1"),
        "REG_AC_IN_CURRENT":   _raw(30.17, "0.01"),
    },
    "low_battery": {
        "REG_IDENTITY":       16420,
        "REG_AC_IN_CONNECTED": 1,
        "REG_FAULT":           0,
        "REG_DC_VOLTAGE":      _raw(26.4,  "0.1"),
        "REG_DC_CURRENT":      _raw(20.0,  "0.01"),  # high discharge
        "REG_AC_OUT_VOLTAGE":  _raw(120.0, "0.1"),
        "REG_AC_OUT_CURRENT":  _raw(8.33,  "0.01"),
        "REG_AC_OUT_POWER":    _raw(1000.0,"1.0"),
        "REG_SOC":             15,       # low SOC
        "REG_CHARGE_STATE":    2,
        "REG_AC_IN_VOLTAGE":   _raw(120.0, "0.1"),
        "REG_AC_IN_CURRENT":   _raw(30.17, "0.01"),
    },
    "ac_disconnect": {
        "REG_IDENTITY":       16420,
        "REG_AC_IN_CONNECTED": 3,        # 3 = Inverting
        "REG_FAULT":           0,
        "REG_DC_VOLTAGE":      _raw(26.4,  "0.1"),
        "REG_DC_CURRENT":      _raw(5.2,   "0.01"),
        "REG_AC_OUT_VOLTAGE":  _raw(120.0, "0.1"),
        "REG_AC_OUT_CURRENT":  _raw(8.33,  "0.01"),
        "REG_AC_OUT_POWER":    _raw(1000.0,"1.0"),
        "REG_SOC":             85,
        "REG_CHARGE_STATE":    9,        # 9 = Inverting
        "REG_AC_IN_VOLTAGE":   0,        # 0 V disconnected
        "REG_AC_IN_CURRENT":   0,        # 0 A disconnected
    },
    "heavy_load": {
        "REG_IDENTITY":       16420,
        "REG_AC_IN_CONNECTED": 1,
        "REG_FAULT":           0,
        "REG_DC_VOLTAGE":      _raw(26.4,  "0.1"),
        "REG_DC_CURRENT":      _raw(5.2,   "0.01"),
        "REG_AC_OUT_VOLTAGE":  _raw(120.0, "0.1"),
        "REG_AC_OUT_CURRENT":  _raw(31.7,  "0.01"),
        "REG_AC_OUT_POWER":    _raw(3800.0,"1.0"),
        "REG_SOC":             85,
        "REG_CHARGE_STATE":    2,
        "REG_AC_IN_VOLTAGE":   _raw(120.0, "0.1"),
        "REG_AC_IN_CURRENT":   _raw(30.17, "0.01"),
    },
    "heavy_load_with_input": {
        "REG_IDENTITY":       16420,
        "REG_AC_IN_CONNECTED": 1,
        "REG_FAULT":           0,
        "REG_DC_VOLTAGE":      _raw(26.4,  "0.1"),
        "REG_DC_CURRENT":      _raw(6.0,   "0.01"),  # charging
        "REG_AC_OUT_VOLTAGE":  _raw(120.0, "0.1"),
        "REG_AC_OUT_CURRENT":  _raw(31.7,  "0.01"),
        "REG_AC_OUT_POWER":    _raw(3800.0,"1.0"),
        "REG_SOC":             85,
        "REG_CHARGE_STATE":    2,
        "REG_AC_IN_VOLTAGE":   _raw(120.0, "0.1"),
        "REG_AC_IN_CURRENT":   _raw(33.0,  "0.01"),  # shore > output (powers load + charges battery)
    },
    "heavy_load_battery": {
        "REG_IDENTITY":       16420,
        "REG_AC_IN_CONNECTED": 3,        # 3 = Inverting (no AC input)
        "REG_FAULT":           0,
        "REG_DC_VOLTAGE":      _raw(24.8,   "0.1"),   # sagging under load
        "REG_DC_CURRENT":      _raw(-145.0, "0.01"),   # negative = discharging (two's complement)
        "REG_AC_OUT_VOLTAGE":  _raw(120.0,  "0.1"),
        "REG_AC_OUT_CURRENT":  _raw(29.2,   "0.01"),
        "REG_AC_OUT_POWER":    _raw(3500.0, "1.0"),
        "REG_SOC":             62,
        "REG_CHARGE_STATE":    9,         # 9 = Inverting
        "REG_AC_IN_VOLTAGE":   0,
        "REG_AC_IN_CURRENT":   0,
    },
}


def _make_client(scenario_name):
    regs = _SCENARIOS[scenario_name]
    address_regs = {_REG_MAP[k]: [v] for k, v in regs.items() if k in _REG_MAP}

    def _effect(address=0, count=1, slave=1):
        res = mock.MagicMock()
        raw = [address_regs.get(address + offset, [0])[0] for offset in range(count)]
        res.isError.return_value = False
        res.registers = raw
        return res

    client = mock.MagicMock()
    client.is_socket_open.return_value = True
    client.connect.return_value = True
    client.read_input_registers.side_effect = _effect
    return client


def _run(scenario_name):
    """Return a Samlex instance after one read_status_data() call for the scenario."""
    cfg = _make_config()
    s = Samlex.__new__(Samlex)
    Inverter.__init__(s, port="/dev/null", baudrate=9600, slave=1)
    s.type = "Samlex"
    s.energy_data["dc"]["charge_state"] = None
    s.phase = "L1"
    s.max_ac_power = 4000.0
    s.client = _make_client(scenario_name)
    utils_stub.config = cfg
    s.read_status_data()
    return s


# ── Helper: assert all dashboard fields are populated ─────────────────────────

def _assert_ac_out_populated(s, scenario):
    ed = s.energy_data
    assert ed["L1"]["ac_voltage"] is not None, f"[{scenario}] ac_out voltage is None"
    assert ed["L1"]["ac_current"] is not None, f"[{scenario}] ac_out current is None"
    assert ed["L1"]["ac_power"]   is not None, f"[{scenario}] ac_out power is None"
    assert ed["overall"]["ac_power"] is not None, f"[{scenario}] overall ac_power is None"


def _assert_dc_populated(s, scenario):
    dc = s.energy_data["dc"]
    assert dc["voltage"]      is not None, f"[{scenario}] dc voltage is None"
    assert dc["current"]      is not None, f"[{scenario}] dc current is None"
    assert dc["power"]        is not None, f"[{scenario}] dc power is None"
    assert dc["soc"]          is not None, f"[{scenario}] dc soc is None"
    assert dc["charge_state"] is not None, f"[{scenario}] dc charge_state is None"


def _assert_ac_in_populated(s, scenario):
    ac_in = s.energy_data["ac_in"]
    assert ac_in["voltage"]   is not None, f"[{scenario}] ac_in voltage is None"
    assert ac_in["current"]   is not None, f"[{scenario}] ac_in current is None"
    assert ac_in["power"]     is not None, f"[{scenario}] ac_in power is None"
    assert ac_in["connected"] is not None, f"[{scenario}] ac_in connected is None"


def _assert_status_set(s, scenario):
    assert s.status is not None, f"[{scenario}] status is None"


# ── Normal scenario ───────────────────────────────────────────────────────────

def test_normal_all_fields_populated():
    s = _run("normal")
    _assert_ac_out_populated(s, "normal")
    _assert_dc_populated(s, "normal")
    _assert_ac_in_populated(s, "normal")
    _assert_status_set(s, "normal")


def test_normal_ac_out_values():
    s = _run("normal")
    assert abs(s.energy_data["L1"]["ac_voltage"] - 120.0) < 0.2
    assert s.energy_data["L1"]["ac_power"] == 1000.0
    assert s.energy_data["overall"]["ac_power"] == 1000.0


def test_normal_dc_values():
    s = _run("normal")
    dc = s.energy_data["dc"]
    assert abs(dc["voltage"] - 26.4) < 0.2
    assert dc["current"] > 0, "Battery should be charging (positive current)"
    assert dc["power"] > 0,   "DC power should be positive when charging"
    assert dc["soc"] == 85.0
    assert dc["charge_state"] == 2  # Absorption


def test_normal_dc_power_equals_voltage_times_current():
    s = _run("normal")
    dc = s.energy_data["dc"]
    expected = round(dc["voltage"] * dc["current"], 0)
    assert dc["power"] == expected, f"dc power {dc['power']} != V×I {expected}"


def test_normal_ac_in_values():
    s = _run("normal")
    ac_in = s.energy_data["ac_in"]
    assert abs(ac_in["voltage"] - 120.0) < 0.2
    assert ac_in["connected"] == 1
    assert ac_in["power"] > 0


def test_normal_ac_in_power_equals_voltage_times_current():
    s = _run("normal")
    ac_in = s.energy_data["ac_in"]
    expected = round(ac_in["voltage"] * ac_in["current"], 0)
    assert ac_in["power"] == expected, f"ac_in power {ac_in['power']} != V×I {expected}"


def test_normal_status_absorption():
    """Normal: AC connected + charge_state=Absorption → vebus State 4 (Absorption)."""
    s = _run("normal")
    assert s.status == 4  # Absorption


# ── Fault scenario ────────────────────────────────────────────────────────────

def test_fault_all_fields_populated():
    s = _run("fault")
    _assert_ac_out_populated(s, "fault")
    _assert_dc_populated(s, "fault")
    _assert_ac_in_populated(s, "fault")
    _assert_status_set(s, "fault")


def test_fault_status_is_fault():
    s = _run("fault")
    assert s.status == 2  # Fault (vebus State 2)


def test_fault_ac_in_still_shows():
    """AC input should still display even when there's a fault."""
    s = _run("fault")
    assert s.energy_data["ac_in"]["power"] is not None
    assert s.energy_data["ac_in"]["connected"] == 1


# ── Low battery scenario ──────────────────────────────────────────────────────

def test_low_battery_all_fields_populated():
    s = _run("low_battery")
    _assert_ac_out_populated(s, "low_battery")
    _assert_dc_populated(s, "low_battery")
    _assert_ac_in_populated(s, "low_battery")
    _assert_status_set(s, "low_battery")


def test_low_battery_soc():
    s = _run("low_battery")
    assert s.energy_data["dc"]["soc"] == 15.0


def test_low_battery_dc_power_non_zero():
    s = _run("low_battery")
    assert s.energy_data["dc"]["power"] is not None
    assert s.energy_data["dc"]["power"] != 0


# ── AC disconnect scenario ────────────────────────────────────────────────────

def test_ac_disconnect_all_fields_populated():
    """Even with AC disconnected, all fields must have a value (not None)."""
    s = _run("ac_disconnect")
    _assert_ac_out_populated(s, "ac_disconnect")
    _assert_dc_populated(s, "ac_disconnect")
    _assert_ac_in_populated(s, "ac_disconnect")
    _assert_status_set(s, "ac_disconnect")


def test_ac_disconnect_connected_is_zero():
    s = _run("ac_disconnect")
    assert s.energy_data["ac_in"]["connected"] == 0


def test_ac_disconnect_ac_in_voltage_and_current_are_zero():
    s = _run("ac_disconnect")
    assert s.energy_data["ac_in"]["voltage"] == 0.0
    assert s.energy_data["ac_in"]["current"] == 0.0
    assert s.energy_data["ac_in"]["power"] == 0.0


def test_ac_disconnect_charge_state_is_inverting():
    s = _run("ac_disconnect")
    assert s.energy_data["dc"]["charge_state"] == 9  # Inverting (Samlex 9 → Victron 9)


# ── Heavy load scenario ───────────────────────────────────────────────────────

def test_heavy_load_all_fields_populated():
    s = _run("heavy_load")
    _assert_ac_out_populated(s, "heavy_load")
    _assert_dc_populated(s, "heavy_load")
    _assert_ac_in_populated(s, "heavy_load")
    _assert_status_set(s, "heavy_load")


def test_heavy_load_ac_out_power():
    s = _run("heavy_load")
    assert s.energy_data["L1"]["ac_power"] == 3800.0
    assert s.energy_data["overall"]["ac_power"] == 3800.0


# ── Heavy load with input scenario ───────────────────────────────────────────

def test_heavy_load_with_input_all_fields_populated():
    s = _run("heavy_load_with_input")
    _assert_ac_out_populated(s, "heavy_load_with_input")
    _assert_dc_populated(s, "heavy_load_with_input")
    _assert_ac_in_populated(s, "heavy_load_with_input")
    _assert_status_set(s, "heavy_load_with_input")


def test_heavy_load_with_input_ac_in_exceeds_ac_out():
    """Shore power must supply more current than the output load."""
    s = _run("heavy_load_with_input")
    assert s.energy_data["ac_in"]["current"] > s.energy_data["L1"]["ac_current"], (
        "Shore input current should exceed output current "
        "(it also feeds battery charging)"
    )


def test_heavy_load_with_input_battery_charging():
    s = _run("heavy_load_with_input")
    assert s.energy_data["dc"]["current"] > 0, "Battery should be charging (positive DC current)"
    assert s.energy_data["dc"]["power"]   > 0


# ── Heavy load on battery scenario ───────────────────────────────────────────

def test_heavy_load_battery_all_fields_populated():
    s = _run("heavy_load_battery")
    _assert_ac_out_populated(s, "heavy_load_battery")
    _assert_dc_populated(s, "heavy_load_battery")
    _assert_ac_in_populated(s, "heavy_load_battery")
    _assert_status_set(s, "heavy_load_battery")


def test_heavy_load_battery_dc_current_is_negative():
    """DC current must be negative when discharging (int16 two's complement)."""
    s = _run("heavy_load_battery")
    assert s.energy_data["dc"]["current"] < 0, (
        f"DC current should be negative (discharging), got {s.energy_data['dc']['current']}"
    )
    assert abs(s.energy_data["dc"]["current"] - (-145.0)) < 0.1


def test_heavy_load_battery_dc_power_is_negative():
    """DC power should be negative (V * negative I) when discharging."""
    s = _run("heavy_load_battery")
    dc = s.energy_data["dc"]
    assert dc["power"] < 0, f"DC power should be negative when discharging, got {dc['power']}"
    expected = round(dc["voltage"] * dc["current"], 0)
    assert dc["power"] == expected


def test_heavy_load_battery_ac_output():
    s = _run("heavy_load_battery")
    assert s.energy_data["L1"]["ac_power"] == 3500.0
    assert abs(s.energy_data["L1"]["ac_current"] - 29.2) < 0.1


def test_heavy_load_battery_ac_input_disconnected():
    s = _run("heavy_load_battery")
    assert s.energy_data["ac_in"]["connected"] == 0
    assert s.energy_data["ac_in"]["voltage"] == 0.0
    assert s.energy_data["ac_in"]["current"] == 0.0


def test_heavy_load_battery_state_is_inverting():
    s = _run("heavy_load_battery")
    assert s.status == 9  # Inverting


def test_heavy_load_battery_soc():
    s = _run("heavy_load_battery")
    assert s.energy_data["dc"]["soc"] == 62.0


if __name__ == "__main__":
    import traceback

    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = failed = 0
    for fn in tests:
        try:
            fn()
            print(f"  PASS  {fn.__name__}")
            passed += 1
        except Exception:
            print(f"  FAIL  {fn.__name__}")
            traceback.print_exc()
            failed += 1

    print(f"\n{passed} passed, {failed} failed.")
    if failed:
        sys.exit(1)
