"""Test 035: DbusHelper vebus path registration (setup_vedbus) and publish (publish_dbus)."""
import sys
import os
import types
import logging
import unittest.mock as mock

for mod in ["dbus", "gi", "gi.repository", "gi.repository.GLib", "vedbus", "settingsdevice"]:
    sys.modules.setdefault(mod, types.ModuleType(mod))

_dbus_mod = sys.modules["dbus"]
if not hasattr(_dbus_mod, "SessionBus"):
    _dbus_mod.SessionBus = mock.MagicMock(return_value=object())
if not hasattr(_dbus_mod, "SystemBus"):
    _dbus_mod.SystemBus = mock.MagicMock(return_value=object())

_vedbus = sys.modules["vedbus"]


class _VeDbusService:
    def __init__(self, *a, **kw):
        self._store = {}

    def add_path(self, path, value=None, writeable=False, gettextcallback=None):
        self._store[path] = value

    def __getitem__(self, p):
        return self._store.get(p)

    def __setitem__(self, p, v):
        self._store[p] = v


_vedbus.VeDbusService = _VeDbusService

_settings_mod = sys.modules["settingsdevice"]
_settings_mod.SettingsDevice = type(
    "SettingsDevice", (), {"__init__": lambda self, *a, **kw: None}
)

_utils = sys.modules.setdefault("utils", types.ModuleType("utils"))
if not hasattr(_utils, "logger"):
    _utils.logger = logging.getLogger("test")
for _attr, _val in [
    ("INVERTER_POLL_INTERVAL", 1000), ("PUBLISH_CONFIG_VALUES", 0),
    ("DRIVER_VERSION", "0.1"), ("DRIVER_SUBVERSION", ".1"),
    ("publish_config_variables", lambda *a: None),
]:
    if not hasattr(_utils, _attr):
        setattr(_utils, _attr, _val)

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "etc", "dbus-serialinverter"))

import dbushelper


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_vebus_inverter():
    """Minimal fake inverter with vebus SERVICE_PREFIX and all required energy_data."""
    inv = mock.MagicMock()
    inv.port = "/dev/ttyUSB0"
    inv.SERVICE_PREFIX = "com.victronenergy.vebus"
    inv.type = "Samlex"
    inv.serial_number = "ttyUSB0"
    inv.hardware_version = 0
    inv.max_ac_power = 4000.0
    inv.position = 1
    inv.phase = "L1"
    inv.status = 7
    inv.online = True
    inv.poll_interval = 1000
    inv.get_settings.return_value = True
    inv.energy_data = {
        "L1":  {"ac_voltage": 120.0, "ac_current": 5.0, "ac_power": 600.0, "energy_forwarded": None},
        "L2":  {"ac_voltage": None, "ac_current": None, "ac_power": None, "energy_forwarded": None},
        "L3":  {"ac_voltage": None, "ac_current": None, "ac_power": None, "energy_forwarded": None},
        "overall": {"ac_power": 600.0, "energy_forwarded": None, "power_limit": None, "active_power_limit": None},
        "dc": {"voltage": 24.5, "current": 25.0, "power": 612.5, "soc": 80.0, "charge_state": 3},
        "ac_in": {"voltage": 120.0, "current": 3.0, "power": 360.0, "connected": 1},
    }
    return inv


def _make_helper_bypass(inv):
    """Build DbusHelper via __new__ to skip __init__, injecting the fake inverter."""
    helper = dbushelper.DbusHelper.__new__(dbushelper.DbusHelper)
    helper.inverter = inv
    helper.instance = 257
    helper.settings = None
    helper.error_count = 0
    helper._dbusservice = _VeDbusService()
    helper._dbusservice._store["/UpdateIndex"] = 0
    return helper


# ── setup_vedbus path registration ────────────────────────────────────────────

def test_vebus_setup_registers_state_path():
    helper = _make_helper_bypass(_make_vebus_inverter())
    helper.inverter.get_settings.return_value = True
    # Call setup_vedbus directly (it also calls setup_instance; we need to stub that)
    with mock.patch.object(helper, "setup_instance"):
        helper.instance = 257
        result = helper.setup_vedbus()
    assert result is True
    assert "/State" in helper._dbusservice._store


def test_vebus_setup_registers_dc_voltage_path():
    helper = _make_helper_bypass(_make_vebus_inverter())
    with mock.patch.object(helper, "setup_instance"):
        helper.instance = 257
        helper.setup_vedbus()
    assert "/Dc/0/Voltage" in helper._dbusservice._store


def test_vebus_setup_registers_ac_out_paths():
    helper = _make_helper_bypass(_make_vebus_inverter())
    with mock.patch.object(helper, "setup_instance"):
        helper.instance = 257
        helper.setup_vedbus()
    assert "/Ac/Out/L1/V" in helper._dbusservice._store
    assert "/Ac/Out/L1/I" in helper._dbusservice._store
    assert "/Ac/Out/L1/P" in helper._dbusservice._store


def test_vebus_setup_registers_ac_in_paths():
    helper = _make_helper_bypass(_make_vebus_inverter())
    with mock.patch.object(helper, "setup_instance"):
        helper.instance = 257
        helper.setup_vedbus()
    assert "/Ac/ActiveIn/L1/V" in helper._dbusservice._store
    assert "/Ac/ActiveIn/Connected" in helper._dbusservice._store


def test_vebus_setup_registers_soc_path():
    helper = _make_helper_bypass(_make_vebus_inverter())
    with mock.patch.object(helper, "setup_instance"):
        helper.instance = 257
        helper.setup_vedbus()
    assert "/Soc" in helper._dbusservice._store


def test_vebus_setup_does_not_register_pvinverter_paths():
    """vebus setup must NOT register pvinverter-specific paths."""
    helper = _make_helper_bypass(_make_vebus_inverter())
    with mock.patch.object(helper, "setup_instance"):
        helper.instance = 257
        helper.setup_vedbus()
    assert "/Ac/L1/Voltage" not in helper._dbusservice._store
    assert "/StatusCode" not in helper._dbusservice._store
    assert "/Ac/PowerLimit" not in helper._dbusservice._store


# ── publish_dbus vebus path ────────────────────────────────────────────────────

def test_vebus_publish_writes_state():
    inv = _make_vebus_inverter()
    inv.status = 7
    helper = _make_helper_bypass(inv)
    helper.publish_dbus()
    assert helper._dbusservice["/State"] == 7


def test_vebus_publish_writes_dc_voltage():
    inv = _make_vebus_inverter()
    helper = _make_helper_bypass(inv)
    helper.publish_dbus()
    assert helper._dbusservice["/Dc/0/Voltage"] == 24.5


def test_vebus_publish_writes_soc():
    inv = _make_vebus_inverter()
    helper = _make_helper_bypass(inv)
    helper.publish_dbus()
    assert helper._dbusservice["/Soc"] == 80.0


def test_vebus_publish_writes_ac_out():
    inv = _make_vebus_inverter()
    helper = _make_helper_bypass(inv)
    helper.publish_dbus()
    assert helper._dbusservice["/Ac/Out/L1/V"] == 120.0
    assert helper._dbusservice["/Ac/Out/L1/P"] == 600.0


def test_vebus_publish_writes_ac_in_connected():
    inv = _make_vebus_inverter()
    helper = _make_helper_bypass(inv)
    helper.publish_dbus()
    assert helper._dbusservice["/Ac/ActiveIn/Connected"] == 1


def test_vebus_publish_writes_charge_state():
    inv = _make_vebus_inverter()
    helper = _make_helper_bypass(inv)
    helper.publish_dbus()
    assert helper._dbusservice["/VebusChargeState"] == 3


def test_vebus_publish_increments_update_index():
    inv = _make_vebus_inverter()
    helper = _make_helper_bypass(inv)
    helper.publish_dbus()
    assert helper._dbusservice["/UpdateIndex"] == 1


def test_vebus_publish_does_not_write_status_code():
    """vebus publish must NOT write to /StatusCode (pvinverter-only path)."""
    inv = _make_vebus_inverter()
    helper = _make_helper_bypass(inv)
    helper.publish_dbus()
    assert helper._dbusservice["/StatusCode"] is None


if __name__ == "__main__":
    test_vebus_setup_registers_state_path()
    test_vebus_setup_registers_dc_voltage_path()
    test_vebus_setup_registers_ac_out_paths()
    test_vebus_setup_registers_ac_in_paths()
    test_vebus_setup_registers_soc_path()
    test_vebus_setup_does_not_register_pvinverter_paths()
    test_vebus_publish_writes_state()
    test_vebus_publish_writes_dc_voltage()
    test_vebus_publish_writes_soc()
    test_vebus_publish_writes_ac_out()
    test_vebus_publish_writes_ac_in_connected()
    test_vebus_publish_writes_charge_state()
    test_vebus_publish_increments_update_index()
    test_vebus_publish_does_not_write_status_code()
    print("All 035 tests passed.")
