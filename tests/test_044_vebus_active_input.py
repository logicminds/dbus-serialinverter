# -*- coding: utf-8 -*-
"""Test 044: /Ac/ActiveIn/ActiveInput is published correctly.

VRM uses ActiveInput (0=ACin-1 active, 240=inverting) to decide whether to
render the AC Input panel on the dashboard. Without this path the panel is
absent even when voltage/current/power values are correct.
"""

import sys
import os
import types
import logging

for mod in ["dbus", "gi", "gi.repository", "gi.repository.GLib", "vedbus", "settingsdevice"]:
    sys.modules.setdefault(mod, types.ModuleType(mod))

if not hasattr(sys.modules["vedbus"], "VeDbusService"):
    sys.modules["vedbus"].VeDbusService = type(
        "VeDbusService", (), {"__init__": lambda self, *a, **kw: None}
    )
if not hasattr(sys.modules["settingsdevice"], "SettingsDevice"):
    sys.modules["settingsdevice"].SettingsDevice = type(
        "SettingsDevice", (), {"__init__": lambda self, *a, **kw: None}
    )

utils_stub = sys.modules.setdefault("utils", types.ModuleType("utils"))
if not hasattr(utils_stub, "logger"):
    utils_stub.logger = logging.getLogger("test")
for _attr, _val in [
    ("INVERTER_POLL_INTERVAL", 1000),
    ("PUBLISH_CONFIG_VALUES", 0),
    ("DRIVER_VERSION", "0.1"),
    ("DRIVER_SUBVERSION", ".1"),
    ("publish_config_variables", lambda *a: None),
]:
    if not hasattr(utils_stub, _attr):
        setattr(utils_stub, _attr, _val)

sys.modules.setdefault("inverter", types.ModuleType("inverter"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "etc", "dbus-serialinverter"))
import dbushelper


class _FakeDbusService:
    def __init__(self):
        self._store = {"/UpdateIndex": 0}
    def __getitem__(self, path): return self._store.get(path)
    def __setitem__(self, path, value): self._store[path] = value


def _make_vebus_helper(connected):
    """Build a vebus DbusHelper with ac_in connected=connected."""
    class _FakeInverter:
        port = "/dev/null"
        status = 4  # Absorption
        online = True
        poll_interval = 1000
        SERVICE_PREFIX = "com.victronenergy.vebus"
        energy_data = {
            "L1": {"ac_voltage": 120.0, "ac_current": 8.3, "ac_power": 1000.0, "energy_forwarded": 0.0},
            "L2": {"ac_voltage": None, "ac_current": None, "ac_power": None, "energy_forwarded": None},
            "L3": {"ac_voltage": None, "ac_current": None, "ac_power": None, "energy_forwarded": None},
            "overall": {"ac_power": 1000.0, "energy_forwarded": 0.0, "power_limit": None, "active_power_limit": None},
            "dc": {"voltage": 26.4, "current": 6.0, "power": 158.0, "soc": 85.0, "charge_state": 2},
            "ac_in": {"voltage": 120.0, "current": 33.0, "power": 3960.0, "connected": connected},
        }
        def refresh_data(self): return True

    helper = dbushelper.DbusHelper.__new__(dbushelper.DbusHelper)
    helper.inverter = _FakeInverter()
    helper._dbusservice = _FakeDbusService()
    helper._prefix = "com.victronenergy.vebus"
    helper.error_count = 0
    return helper


def test_active_input_is_zero_when_ac_connected():
    """When AC is connected (Connected=1), ActiveInput must be 0 (ACin-1 active)."""
    helper = _make_vebus_helper(connected=1)
    helper.publish_dbus()
    assert helper._dbusservice["/Ac/ActiveIn/ActiveInput"] == 0, (
        "ActiveInput must be 0 when AC is connected — VRM uses this to show the AC Input panel"
    )


def test_active_input_is_240_when_ac_disconnected():
    """When AC is disconnected (Connected=0), ActiveInput must be 240 (inverting)."""
    helper = _make_vebus_helper(connected=0)
    helper.publish_dbus()
    assert helper._dbusservice["/Ac/ActiveIn/ActiveInput"] == 240


def test_active_input_is_240_when_connected_is_none():
    """If connected is None (read failure), ActiveInput defaults to 240 (safe/inverting)."""
    helper = _make_vebus_helper(connected=None)
    helper.publish_dbus()
    assert helper._dbusservice["/Ac/ActiveIn/ActiveInput"] == 240


def test_active_input_path_is_published():
    """ActiveInput path must be present in the D-Bus store after publish_dbus()."""
    helper = _make_vebus_helper(connected=1)
    helper.publish_dbus()
    assert "/Ac/ActiveIn/ActiveInput" in helper._dbusservice._store, (
        "/Ac/ActiveIn/ActiveInput must be registered — without it VRM hides the AC Input panel"
    )


def test_acin1_available_is_one_when_connected():
    """/Ac/State/AcIn1Available must be 1 when AC is connected.

    systemcalc reads this flag to determine if AC input 1 is physically present.
    When it is missing or 0, systemcalc reports ini=0 (Number of AC Inputs=0) and
    VRM hides the AC Input panel even when voltage/current/power values are correct.
    """
    helper = _make_vebus_helper(connected=1)
    helper.publish_dbus()
    assert helper._dbusservice["/Ac/State/AcIn1Available"] == 1


def test_acin1_available_is_zero_when_disconnected():
    """/Ac/State/AcIn1Available must be 0 when AC input is absent."""
    helper = _make_vebus_helper(connected=0)
    helper.publish_dbus()
    assert helper._dbusservice["/Ac/State/AcIn1Available"] == 0


if __name__ == "__main__":
    test_active_input_is_zero_when_ac_connected()
    test_active_input_is_240_when_ac_disconnected()
    test_active_input_is_240_when_connected_is_none()
    test_active_input_path_is_published()
    print("All 044 tests passed.")
