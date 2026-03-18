"""Test 006: DbusHelper.publish_inverter() error counting, offline flag, and loop.quit()."""
import sys
import os
import types
import logging

for mod in ["dbus", "gi", "gi.repository", "gi.repository.GLib", "vedbus", "settingsdevice"]:
    sys.modules.setdefault(mod, types.ModuleType(mod))

# Ensure VeDbusService stub is in place (conftest provides it; this is a fallback)
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


# ── Helpers ───────────────────────────────────────────────────────────────────

class _FakeLoop:
    def __init__(self):
        self.quit_called = False
    def quit(self):
        self.quit_called = True


class _FakeDbusService:
    def __init__(self):
        self._store = {"/UpdateIndex": 0, "/Ac/PowerLimit": 800.0}
    def __getitem__(self, path): return self._store.get(path)
    def __setitem__(self, path, value): self._store[path] = value


def _make_helper(refresh_returns):
    """Build a DbusHelper with a refresh_data that always returns refresh_returns."""
    class _FakeInverter:
        port = "/dev/null"
        status = 7
        online = True
        poll_interval = 1000
        energy_data = {
            "L1": {"ac_voltage": None, "ac_current": None, "ac_power": None, "energy_forwarded": None},
            "L2": {"ac_voltage": None, "ac_current": None, "ac_power": None, "energy_forwarded": None},
            "L3": {"ac_voltage": None, "ac_current": None, "ac_power": None, "energy_forwarded": None},
            "overall": {"ac_power": None, "energy_forwarded": None, "power_limit": 800.0, "active_power_limit": None},
        }
        def refresh_data(self):
            return refresh_returns

    helper = dbushelper.DbusHelper.__new__(dbushelper.DbusHelper)
    helper.inverter = _FakeInverter()
    helper._dbusservice = _FakeDbusService()
    helper.error_count = 0
    return helper


def _run_n_failures(helper, loop, n):
    for _ in range(n):
        helper.publish_inverter(loop)


# ── Success path ──────────────────────────────────────────────────────────────

def test_success_resets_error_count_to_zero():
    helper = _make_helper(refresh_returns=True)
    helper.error_count = 42
    helper.inverter.online = False
    helper.publish_inverter(_FakeLoop())
    assert helper.error_count == 0


def test_success_sets_online_true():
    helper = _make_helper(refresh_returns=True)
    helper.inverter.online = False
    helper.publish_inverter(_FakeLoop())
    assert helper.inverter.online is True


# ── Failure path: error count increments ─────────────────────────────────────

def test_single_failure_increments_error_count():
    helper = _make_helper(refresh_returns=False)
    helper.publish_inverter(_FakeLoop())
    assert helper.error_count == 1


# ── Boundary: online flag at count = 9 vs 10 ──────────────────────────────────

def test_error_count_9_inverter_still_online():
    helper = _make_helper(refresh_returns=False)
    loop = _FakeLoop()
    _run_n_failures(helper, loop, 9)
    assert helper.inverter.online is True, "inverter should still be online at count=9"
    assert loop.quit_called is False


def test_error_count_10_sets_inverter_offline():
    helper = _make_helper(refresh_returns=False)
    loop = _FakeLoop()
    _run_n_failures(helper, loop, 10)
    assert helper.inverter.online is False, "inverter must go offline at count=10"
    assert loop.quit_called is False, "loop.quit() must not be called at count=10"


# ── Boundary: loop.quit at count = 59 vs 60 ───────────────────────────────────

def test_error_count_59_does_not_call_loop_quit():
    helper = _make_helper(refresh_returns=False)
    loop = _FakeLoop()
    _run_n_failures(helper, loop, 59)
    assert loop.quit_called is False, "loop.quit() must not be called at count=59"


def test_error_count_60_calls_loop_quit():
    helper = _make_helper(refresh_returns=False)
    loop = _FakeLoop()
    _run_n_failures(helper, loop, 60)
    assert loop.quit_called is True, "loop.quit() must be called at count=60"


# ── Success after failures resets the counter ─────────────────────────────────

def test_success_after_failures_resets_count():
    helper = _make_helper(refresh_returns=False)
    loop = _FakeLoop()
    _run_n_failures(helper, loop, 5)
    assert helper.error_count == 5
    # Now succeeds
    helper.inverter.refresh_data = lambda: True
    helper.publish_inverter(loop)
    assert helper.error_count == 0


if __name__ == "__main__":
    test_success_resets_error_count_to_zero()
    test_success_sets_online_true()
    test_single_failure_increments_error_count()
    test_error_count_9_inverter_still_online()
    test_error_count_10_sets_inverter_offline()
    test_error_count_59_does_not_call_loop_quit()
    test_error_count_60_calls_loop_quit()
    test_success_after_failures_resets_count()
    print("All 006 tests passed.")
