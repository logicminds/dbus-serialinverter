"""Test 004: except clause in publish_inverter catches Exception, not BaseException."""
import sys
import os
import types
import logging

# Stub heavy dependencies
for mod in ["dbus", "gi", "gi.repository", "gi.repository.GLib",
            "vedbus", "settingsdevice"]:
    sys.modules.setdefault(mod, types.ModuleType(mod))

# Provide a minimal VeDbusService stub
vedbus_mod = sys.modules["vedbus"]
vedbus_mod.VeDbusService = type("VeDbusService", (), {"__init__": lambda self, *a, **kw: None})

settingsdevice_mod = sys.modules["settingsdevice"]
settingsdevice_mod.SettingsDevice = type("SettingsDevice", (), {"__init__": lambda self, *a, **kw: None})

utils_stub = types.ModuleType("utils")
utils_stub.logger = logging.getLogger("test")
utils_stub.INVERTER_POLL_INTERVAL = 1000
utils_stub.PUBLISH_CONFIG_VALUES = 0
utils_stub.DRIVER_VERSION = "0.1"
utils_stub.DRIVER_SUBVERSION = ".1"
utils_stub.publish_config_variables = lambda *a: None
sys.modules["utils"] = utils_stub

inverter_stub = types.ModuleType("inverter")
sys.modules["inverter"] = inverter_stub

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "etc", "dbus-serialinverter"))

import dbushelper


# ── helpers ───────────────────────────────────────────────────────────────────

class _FakeLoop:
    def __init__(self):
        self.quit_called = False
    def quit(self):
        self.quit_called = True


class _FakeInverter:
    port = "/dev/null"
    energy_data = {"overall": {"power_limit": None}}

    def refresh_data(self):
        raise RuntimeError("boom")


class _FakeDbusService:
    def __getitem__(self, path): return None
    def __setitem__(self, path, value): pass


# ── tests ─────────────────────────────────────────────────────────────────────

def test_runtime_error_calls_loop_quit():
    helper = dbushelper.DbusHelper.__new__(dbushelper.DbusHelper)
    helper.inverter = _FakeInverter()
    helper._dbusservice = _FakeDbusService()
    helper.error_count = 0

    loop = _FakeLoop()
    helper.publish_inverter(loop)
    assert loop.quit_called, "loop.quit() should be called on RuntimeError"


def test_keyboard_interrupt_propagates():
    """KeyboardInterrupt must NOT be swallowed by the except clause."""
    class _KIInverter(_FakeInverter):
        def refresh_data(self):
            raise KeyboardInterrupt

    helper = dbushelper.DbusHelper.__new__(dbushelper.DbusHelper)
    helper.inverter = _KIInverter()
    helper._dbusservice = _FakeDbusService()
    helper.error_count = 0

    loop = _FakeLoop()
    try:
        helper.publish_inverter(loop)
        assert False, "KeyboardInterrupt should propagate"
    except KeyboardInterrupt:
        pass  # correct — signal escaped the except clause
    assert not loop.quit_called, "loop.quit() must not be called for KeyboardInterrupt"


def test_system_exit_propagates():
    """SystemExit must NOT be swallowed by the except clause."""
    class _SEInverter(_FakeInverter):
        def refresh_data(self):
            raise SystemExit(0)

    helper = dbushelper.DbusHelper.__new__(dbushelper.DbusHelper)
    helper.inverter = _SEInverter()
    helper._dbusservice = _FakeDbusService()
    helper.error_count = 0

    loop = _FakeLoop()
    try:
        helper.publish_inverter(loop)
        assert False, "SystemExit should propagate"
    except SystemExit:
        pass  # correct
    assert not loop.quit_called


if __name__ == "__main__":
    test_runtime_error_calls_loop_quit()
    test_keyboard_interrupt_propagates()
    test_system_exit_propagates()
    print("All 004 tests passed.")
