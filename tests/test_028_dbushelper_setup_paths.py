"""Test 028: DbusHelper uncovered paths — get_bus, __init__, get_role_instance,
handle_changed_setting, and setup_vedbus.

Missing lines:
  23        get_bus() body
  39-43     __init__ body
  50-62     setup_instance body
  65-67     get_role_instance body
  70-72     handle_changed_setting body
  82-129    setup_vedbus body
"""
import sys
import os
import types
import logging
import unittest.mock as mock

for _mod in ["dbus", "gi", "gi.repository", "gi.repository.GLib"]:
    sys.modules.setdefault(_mod, types.ModuleType(_mod))

# Ensure dbus has SessionBus / SystemBus attributes for get_bus() tests
_dbus_mod = sys.modules["dbus"]
if not hasattr(_dbus_mod, "SessionBus"):
    _dbus_mod.SessionBus = mock.MagicMock(return_value=object())
if not hasattr(_dbus_mod, "SystemBus"):
    _dbus_mod.SystemBus = mock.MagicMock(return_value=object())

_vedbus = sys.modules.setdefault("vedbus", types.ModuleType("vedbus"))


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

_settings_mod = sys.modules.setdefault("settingsdevice", types.ModuleType("settingsdevice"))
_settings_mod.SettingsDevice = type(
    "SettingsDevice", (), {"__init__": lambda self, *a, **kw: None}
)

_utils = sys.modules.setdefault("utils", types.ModuleType("utils"))
if not hasattr(_utils, "logger"):
    _utils.logger = logging.getLogger("test")
for _attr, _val in [
    ("INVERTER_POLL_INTERVAL", 1000),
    ("PUBLISH_CONFIG_VALUES", 0),
    ("DRIVER_VERSION", "0.1"),
    ("DRIVER_SUBVERSION", ".1"),
    ("publish_config_variables", lambda *a: None),
]:
    if not hasattr(_utils, _attr):
        setattr(_utils, _attr, _val)

sys.modules.setdefault("inverter", types.ModuleType("inverter"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "etc", "dbus-serialinverter"))
import dbushelper


# ── Shared helpers ────────────────────────────────────────────────────────────

class _FakeInverter:
    port = "/dev/ttyUSB0"
    type = "Dummy"
    status = 7
    online = True
    poll_interval = 1000
    max_ac_power = 800.0
    hardware_version = "1.0.0"
    serial_number = "12345678"
    position = 1
    role = "inverter"
    energy_data = {
        "L1": {"ac_voltage": 230.0, "ac_current": 1.0, "ac_power": 230.0, "energy_forwarded": 0.1},
        "L2": {"ac_voltage": 0.0, "ac_current": 0.0, "ac_power": 0.0, "energy_forwarded": 0.0},
        "L3": {"ac_voltage": 0.0, "ac_current": 0.0, "ac_power": 0.0, "energy_forwarded": 0.0},
        "overall": {"ac_power": 230.0, "energy_forwarded": 0.1, "power_limit": 800.0,
                    "active_power_limit": 800.0},
    }

    def get_settings(self):
        return True

    def refresh_data(self):
        return True

    def apply_power_limit(self, watts):
        return True


def _make_bare_helper():
    """Helper with no __init__ called — for testing individual methods."""
    h = dbushelper.DbusHelper.__new__(dbushelper.DbusHelper)
    h.inverter = _FakeInverter()
    h._dbusservice = _VeDbusService()
    h.instance = 1
    h.settings = None
    h.error_count = 0
    return h


# ── get_bus() (line 23) ───────────────────────────────────────────────────────

def test_get_bus_returns_session_bus_when_env_set():
    original = os.environ.get("DBUS_SESSION_BUS_ADDRESS")
    try:
        os.environ["DBUS_SESSION_BUS_ADDRESS"] = "unix:abstract=/tmp/test"
        _dbus_mod.SessionBus = mock.MagicMock(return_value="session_bus")
        result = dbushelper.get_bus()
        assert result == "session_bus"
    finally:
        if original is None:
            os.environ.pop("DBUS_SESSION_BUS_ADDRESS", None)
        else:
            os.environ["DBUS_SESSION_BUS_ADDRESS"] = original


def test_get_bus_returns_system_bus_when_no_env():
    original = os.environ.pop("DBUS_SESSION_BUS_ADDRESS", None)
    try:
        _dbus_mod.SystemBus = mock.MagicMock(return_value="system_bus")
        result = dbushelper.get_bus()
        assert result == "system_bus"
    finally:
        if original is not None:
            os.environ["DBUS_SESSION_BUS_ADDRESS"] = original


# ── DbusHelper.__init__ (lines 39-43) ────────────────────────────────────────

def test_init_sets_inverter():
    inv = _FakeInverter()
    with mock.patch.object(dbushelper, "get_bus", return_value=None):
        h = dbushelper.DbusHelper(inv)
    assert h.inverter is inv


def test_init_sets_instance_to_1():
    inv = _FakeInverter()
    with mock.patch.object(dbushelper, "get_bus", return_value=None):
        h = dbushelper.DbusHelper(inv)
    assert h.instance == 1


def test_init_sets_settings_to_none():
    inv = _FakeInverter()
    with mock.patch.object(dbushelper, "get_bus", return_value=None):
        h = dbushelper.DbusHelper(inv)
    assert h.settings is None


def test_init_sets_error_count_to_zero():
    inv = _FakeInverter()
    with mock.patch.object(dbushelper, "get_bus", return_value=None):
        h = dbushelper.DbusHelper(inv)
    assert h.error_count == 0


def test_init_creates_dbusservice():
    inv = _FakeInverter()
    with mock.patch.object(dbushelper, "get_bus", return_value=None):
        h = dbushelper.DbusHelper(inv)
    # VeDbusService is whatever stub is installed by the test harness — just
    # verify the attribute was set (not None).
    assert h._dbusservice is not None


# ── get_role_instance() (lines 65-67) ────────────────────────────────────────

def test_get_role_instance_parses_role_and_instance():
    h = _make_bare_helper()
    h.settings = {"instance": "inverter:20"}
    role, inst = h.get_role_instance()
    assert role == "inverter"
    assert inst == 20


def test_get_role_instance_returns_instance_as_int():
    h = _make_bare_helper()
    h.settings = {"instance": "pvinverter:25"}
    _, inst = h.get_role_instance()
    assert isinstance(inst, int)
    assert inst == 25


# ── handle_changed_setting() (lines 70-72) ───────────────────────────────────

def test_handle_changed_setting_instance_updates_role_and_instance():
    h = _make_bare_helper()
    h.settings = {"instance": "inverter:21"}
    h.handle_changed_setting("instance", "inverter:20", "inverter:21")
    assert h.inverter.role == "inverter"
    assert h.instance == 21


def test_handle_changed_setting_other_key_is_ignored():
    h = _make_bare_helper()
    h.settings = {"instance": "inverter:20"}
    original_instance = h.instance
    h.handle_changed_setting("someOtherKey", "old", "new")
    assert h.instance == original_instance


# ── setup_vedbus() (lines 82-129) ────────────────────────────────────────────

def test_setup_vedbus_returns_true_on_success():
    h = _make_bare_helper()
    h.setup_instance = lambda: None
    assert h.setup_vedbus() is True


def test_setup_vedbus_returns_false_when_get_settings_fails():
    h = _make_bare_helper()
    h.setup_instance = lambda: None
    h.inverter.get_settings = lambda: False
    assert h.setup_vedbus() is False


def test_setup_vedbus_adds_mgmt_paths():
    h = _make_bare_helper()
    h.setup_instance = lambda: None
    h.setup_vedbus()
    assert "/Mgmt/ProcessName" in h._dbusservice._store
    assert "/Mgmt/Connection" in h._dbusservice._store


def test_setup_vedbus_adds_device_instance():
    h = _make_bare_helper()
    h.setup_instance = lambda: None
    h.setup_vedbus()
    assert h._dbusservice._store["/DeviceInstance"] == 1


def test_setup_vedbus_adds_all_phase_paths():
    h = _make_bare_helper()
    h.setup_instance = lambda: None
    h.setup_vedbus()
    for phase in ["L1", "L2", "L3"]:
        for suffix in ["Voltage", "Current", "Power", "Energy/Forward"]:
            assert f"/Ac/{phase}/{suffix}" in h._dbusservice._store


def test_setup_vedbus_adds_overall_power_path():
    h = _make_bare_helper()
    h.setup_instance = lambda: None
    h.setup_vedbus()
    assert "/Ac/Power" in h._dbusservice._store
    assert "/Ac/Energy/Forward" in h._dbusservice._store


def test_setup_vedbus_adds_power_limit_path():
    h = _make_bare_helper()
    h.setup_instance = lambda: None
    h.setup_vedbus()
    assert "/Ac/PowerLimit" in h._dbusservice._store


def test_setup_vedbus_calls_publish_config_when_flag_set():
    h = _make_bare_helper()
    h.setup_instance = lambda: None
    calls = []
    original = _utils.PUBLISH_CONFIG_VALUES
    original_fn = _utils.publish_config_variables
    try:
        _utils.PUBLISH_CONFIG_VALUES = 1
        _utils.publish_config_variables = lambda svc: calls.append(svc)
        h.setup_vedbus()
    finally:
        _utils.PUBLISH_CONFIG_VALUES = original
        _utils.publish_config_variables = original_fn
    assert len(calls) == 1


def test_setup_vedbus_does_not_call_publish_config_when_flag_off():
    h = _make_bare_helper()
    h.setup_instance = lambda: None
    calls = []
    original = _utils.PUBLISH_CONFIG_VALUES
    original_fn = _utils.publish_config_variables
    try:
        _utils.PUBLISH_CONFIG_VALUES = 0
        _utils.publish_config_variables = lambda svc: calls.append(svc)
        h.setup_vedbus()
    finally:
        _utils.PUBLISH_CONFIG_VALUES = original
        _utils.publish_config_variables = original_fn
    assert len(calls) == 0


if __name__ == "__main__":
    test_get_bus_returns_session_bus_when_env_set()
    test_get_bus_returns_system_bus_when_no_env()
    test_init_sets_inverter()
    test_init_sets_instance_to_1()
    test_init_sets_settings_to_none()
    test_init_sets_error_count_to_zero()
    test_init_creates_dbusservice()
    test_get_role_instance_parses_role_and_instance()
    test_get_role_instance_returns_instance_as_int()
    test_handle_changed_setting_instance_updates_role_and_instance()
    test_handle_changed_setting_other_key_is_ignored()
    test_setup_vedbus_returns_true_on_success()
    test_setup_vedbus_returns_false_when_get_settings_fails()
    test_setup_vedbus_adds_mgmt_paths()
    test_setup_vedbus_adds_device_instance()
    test_setup_vedbus_adds_all_phase_paths()
    test_setup_vedbus_adds_overall_power_path()
    test_setup_vedbus_adds_power_limit_path()
    test_setup_vedbus_calls_publish_config_when_flag_set()
    test_setup_vedbus_does_not_call_publish_config_when_flag_off()
    print("All 028 tests passed.")
