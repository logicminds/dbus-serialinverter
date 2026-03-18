"""Test 019: publish_dbus() is called only when refresh_data() succeeds."""
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
        self._store = {"/UpdateIndex": 0, "/Ac/PowerLimit": 800.0}

    def __getitem__(self, p):
        return self._store.get(p)

    def __setitem__(self, p, v):
        self._store[p] = v


class _FakeLoop:
    quit_called = False

    def quit(self):
        self.quit_called = True


def _make_helper(refresh_returns):
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
                "power_limit": 800.0,
                "active_power_limit": 800.0,
            },
        }

        def refresh_data(self):
            return refresh_returns

        def apply_power_limit(self, watts):
            return True

    helper = dbushelper.DbusHelper.__new__(dbushelper.DbusHelper)
    helper.inverter = _FakeInverter()
    helper._dbusservice = _FakeDbusService()
    helper.error_count = 0
    return helper, _FakeLoop()


# ── Success path: publish_dbus() called ───────────────────────────────────────

def test_publish_dbus_called_on_success():
    helper, loop = _make_helper(refresh_returns=True)
    calls = []
    helper.publish_dbus = lambda: calls.append(1)
    helper.publish_inverter(loop)
    assert len(calls) == 1, "publish_dbus() must be called when refresh succeeds"


# ── Failure path: publish_dbus() NOT called ───────────────────────────────────

def test_publish_dbus_not_called_on_failure():
    helper, loop = _make_helper(refresh_returns=False)
    calls = []
    helper.publish_dbus = lambda: calls.append(1)
    helper.publish_inverter(loop)
    assert len(calls) == 0, "publish_dbus() must NOT be called when refresh fails"


def test_publish_dbus_not_called_after_repeated_failures():
    helper, loop = _make_helper(refresh_returns=False)
    calls = []
    helper.publish_dbus = lambda: calls.append(1)
    for _ in range(10):
        helper.publish_inverter(loop)
    assert len(calls) == 0


def test_publish_dbus_called_again_after_recovery():
    helper, loop = _make_helper(refresh_returns=False)
    calls = []
    helper.publish_dbus = lambda: calls.append(1)
    # 3 failures
    for _ in range(3):
        helper.publish_inverter(loop)
    assert len(calls) == 0
    # Now succeeds
    helper.inverter.refresh_data = lambda: True
    helper.publish_inverter(loop)
    assert len(calls) == 1


if __name__ == "__main__":
    test_publish_dbus_called_on_success()
    test_publish_dbus_not_called_on_failure()
    test_publish_dbus_not_called_after_repeated_failures()
    test_publish_dbus_called_again_after_recovery()
    print("All 019 tests passed.")
