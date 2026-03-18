"""Test 007: publish_dbus() UpdateIndex increments correctly and wraps 255 → 0."""
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
    ("INVERTER_POLL_INTERVAL", 1000), ("PUBLISH_CONFIG_VALUES", 0),
    ("DRIVER_VERSION", "0.1"), ("DRIVER_SUBVERSION", ".1"),
    ("publish_config_variables", lambda *a: None),
]:
    if not hasattr(utils_stub, _attr):
        setattr(utils_stub, _attr, _val)

sys.modules.setdefault("inverter", types.ModuleType("inverter"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "etc", "dbus-serialinverter"))
import dbushelper


# ── Helpers ───────────────────────────────────────────────────────────────────

class _FakeDbusService:
    def __init__(self, start_index=0):
        self._store = {"/UpdateIndex": start_index}

    def __getitem__(self, path):
        return self._store.get(path)

    def __setitem__(self, path, value):
        self._store[path] = value


def _make_helper_with_index(start_index):
    class _FakeInverter:
        status = 7
        energy_data = {
            "L1": {"ac_voltage": 0, "ac_current": 0, "ac_power": 0, "energy_forwarded": 0},
            "L2": {"ac_voltage": 0, "ac_current": 0, "ac_power": 0, "energy_forwarded": 0},
            "L3": {"ac_voltage": 0, "ac_current": 0, "ac_power": 0, "energy_forwarded": 0},
            "overall": {"ac_power": 0, "energy_forwarded": 0},
        }

    helper = dbushelper.DbusHelper.__new__(dbushelper.DbusHelper)
    helper.inverter = _FakeInverter()
    helper._dbusservice = _FakeDbusService(start_index)
    return helper


def _get_index(helper):
    return helper._dbusservice["/UpdateIndex"]


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_index_increments_from_zero():
    helper = _make_helper_with_index(0)
    helper.publish_dbus()
    assert _get_index(helper) == 1


def test_index_increments_midrange():
    helper = _make_helper_with_index(100)
    helper.publish_dbus()
    assert _get_index(helper) == 101


def test_index_does_not_wrap_at_254():
    """254 + 1 = 255, which is NOT > 255, so no wrap should occur."""
    helper = _make_helper_with_index(254)
    helper.publish_dbus()
    assert _get_index(helper) == 255, "254 should increment to 255 without wrapping"


def test_index_wraps_at_255():
    """255 + 1 = 256 > 255, so it must wrap to 0."""
    helper = _make_helper_with_index(255)
    helper.publish_dbus()
    assert _get_index(helper) == 0, "255 must wrap to 0"


def test_index_stays_in_valid_range_after_many_calls():
    helper = _make_helper_with_index(0)
    for _ in range(300):
        helper.publish_dbus()
    assert 0 <= _get_index(helper) <= 255


if __name__ == "__main__":
    test_index_increments_from_zero()
    test_index_increments_midrange()
    test_index_does_not_wrap_at_254()
    test_index_wraps_at_255()
    test_index_stays_in_valid_range_after_many_calls()
    print("All 007 tests passed.")
