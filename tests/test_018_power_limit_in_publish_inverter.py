"""Test 018: Power limit write lives in publish_inverter(), not read_status_data()."""
import sys
import os
import types
import logging
import unittest.mock as mock

for mod in ["dbus", "gi", "gi.repository", "gi.repository.GLib",
            "pymodbus", "pymodbus.client", "pymodbus.constants", "pymodbus.payload",
            "vedbus", "settingsdevice"]:
    sys.modules.setdefault(mod, types.ModuleType(mod))

_vedbus = sys.modules["vedbus"]
if not hasattr(_vedbus, "VeDbusService"):
    _vedbus.VeDbusService = type("VeDbusService", (), {"__init__": lambda self, *a, **kw: None})

_settings = sys.modules["settingsdevice"]
if not hasattr(_settings, "SettingsDevice"):
    _settings.SettingsDevice = type("SettingsDevice", (), {"__init__": lambda self, *a, **kw: None})

_utils = sys.modules.setdefault("utils", types.ModuleType("utils"))
if not hasattr(_utils, "logger"):
    _utils.logger = logging.getLogger("test")
for _attr, _val in [
    ("INVERTER_TYPE", "Solis"), ("INVERTER_MAX_AC_POWER", 800.0),
    ("INVERTER_PHASE", "L1"), ("INVERTER_POLL_INTERVAL", 1000),
    ("INVERTER_POSITION", 1), ("PUBLISH_CONFIG_VALUES", 0),
    ("DRIVER_VERSION", "0.1"), ("DRIVER_SUBVERSION", ".1"),
    ("publish_config_variables", lambda *a: None),
]:
    if not hasattr(_utils, _attr):
        setattr(_utils, _attr, _val)

sys.modules.setdefault("inverter", types.ModuleType("inverter"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "etc", "dbus-serialinverter"))
import dbushelper


class _FakeDbusService:
    def __init__(self, power_limit=800.0):
        self._store = {"/UpdateIndex": 0, "/Ac/PowerLimit": power_limit}

    def __getitem__(self, p):
        return self._store.get(p)

    def __setitem__(self, p, v):
        self._store[p] = v


class _FakeLoop:
    quit_called = False

    def quit(self):
        self.quit_called = True


def _make_helper(desired_watts, active_watts, refresh_ok=True):
    apply_calls = []

    class _FakeInverter:
        port = "/dev/null"
        status = 7
        online = True
        poll_interval = 1000
        max_ac_power = 800.0
        energy_data = {
            "L1": {"ac_voltage": None, "ac_current": None, "ac_power": None, "energy_forwarded": None},
            "L2": {"ac_voltage": None, "ac_current": None, "ac_power": None, "energy_forwarded": None},
            "L3": {"ac_voltage": None, "ac_current": None, "ac_power": None, "energy_forwarded": None},
            "overall": {
                "ac_power": None,
                "energy_forwarded": None,
                "power_limit": desired_watts,
                "active_power_limit": active_watts,
            },
        }

        def refresh_data(self):
            return refresh_ok

        def apply_power_limit(self, watts):
            apply_calls.append(watts)
            return True

    helper = dbushelper.DbusHelper.__new__(dbushelper.DbusHelper)
    helper.inverter = _FakeInverter()
    helper._dbusservice = _FakeDbusService(desired_watts)
    helper.error_count = 0
    return helper, _FakeLoop(), apply_calls


# ── Write fires when active != desired ───────────────────────────────────────

def test_apply_power_limit_called_when_limits_differ():
    helper, loop, calls = _make_helper(desired_watts=800.0, active_watts=400.0)
    helper.publish_inverter(loop)
    assert len(calls) == 1, "apply_power_limit() must be called when active != desired"
    assert calls[0] == 800.0


def test_apply_power_limit_not_called_when_limits_match():
    helper, loop, calls = _make_helper(desired_watts=800.0, active_watts=800.0)
    helper.publish_inverter(loop)
    assert len(calls) == 0, "apply_power_limit() must NOT be called when limits are equal"


def test_apply_power_limit_not_called_on_refresh_failure():
    helper, loop, calls = _make_helper(desired_watts=800.0, active_watts=400.0, refresh_ok=False)
    helper.publish_inverter(loop)
    assert len(calls) == 0, "apply_power_limit() must not be called when refresh failed"


def test_apply_power_limit_not_called_when_active_is_none():
    """If active_power_limit was never populated (e.g., first poll failed), skip write."""
    helper, loop, calls = _make_helper(desired_watts=800.0, active_watts=None)
    helper.publish_inverter(loop)
    assert len(calls) == 0


if __name__ == "__main__":
    test_apply_power_limit_called_when_limits_differ()
    test_apply_power_limit_not_called_when_limits_match()
    test_apply_power_limit_not_called_on_refresh_failure()
    test_apply_power_limit_not_called_when_active_is_none()
    print("All 018 tests passed.")
