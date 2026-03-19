"""Test 034: DbusHelper service name regression.

Verifies that DbusHelper uses the inverter's SERVICE_PREFIX to construct
the VenusOS D-Bus service name — not a hardcoded pvinverter string.

  Solis  (SERVICE_PREFIX = pvinverter) → com.victronenergy.pvinverter.<port>
  Samlex (SERVICE_PREFIX = vebus)      → com.victronenergy.vebus.<port>
"""
import sys
import os
import types
import logging
import unittest.mock as mock

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

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "etc", "dbus-serialinverter"))

import dbushelper


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_inverter(service_prefix, port="/dev/ttyUSB0"):
    inv = mock.MagicMock()
    inv.port = port
    inv.SERVICE_PREFIX = service_prefix
    return inv


def _make_helper_capture(service_prefix):
    """Build DbusHelper, capturing the service name passed to VeDbusService."""
    captured = {}

    class _CapturingSvc:
        def __init__(self, service_name=None, *args, **kw):
            captured["name"] = service_name
            self._store = {}
        def add_path(self, *a, **kw): pass
        def __getitem__(self, p): return self._store.get(p)
        def __setitem__(self, p, v): self._store[p] = v

    with mock.patch.object(dbushelper, "VeDbusService", _CapturingSvc), \
         mock.patch.object(dbushelper, "get_bus", return_value=None):
        inv = _make_inverter(service_prefix)
        helper = dbushelper.DbusHelper(inv)

    return helper, captured.get("name")


# ── Service name tests ────────────────────────────────────────────────────────

def test_pvinverter_prefix_for_solis():
    helper, svc_name = _make_helper_capture("com.victronenergy.pvinverter")
    assert svc_name is not None, "VeDbusService was not instantiated"
    assert svc_name.startswith("com.victronenergy.pvinverter."), (
        "Expected pvinverter prefix, got: %s" % svc_name
    )


def test_vebus_prefix_for_samlex():
    helper, svc_name = _make_helper_capture("com.victronenergy.vebus")
    assert svc_name is not None, "VeDbusService was not instantiated"
    assert svc_name.startswith("com.victronenergy.vebus."), (
        "Expected vebus prefix, got: %s" % svc_name
    )


def test_port_suffix_appended_pvinverter():
    _, svc_name = _make_helper_capture("com.victronenergy.pvinverter")
    assert svc_name.endswith("ttyUSB0"), "Port basename must be the service name suffix"


def test_port_suffix_appended_vebus():
    _, svc_name = _make_helper_capture("com.victronenergy.vebus")
    assert svc_name.endswith("ttyUSB0"), "Port basename must be the service name suffix"


def test_different_ports_produce_different_names():
    """Service name embeds the port so two devices on different ports get distinct names."""
    class _Capture:
        names = []
        def __init__(self, svc_name=None, *a, **kw):
            _Capture.names.append(svc_name)
            self._store = {}
        def add_path(self, *a, **kw): pass
        def __getitem__(self, p): return self._store.get(p)
        def __setitem__(self, p, v): self._store[p] = v

    _Capture.names.clear()
    with mock.patch.object(dbushelper, "VeDbusService", _Capture), \
         mock.patch.object(dbushelper, "get_bus", return_value=None):
        dbushelper.DbusHelper(_make_inverter("com.victronenergy.pvinverter", "/dev/ttyUSB0"))
        dbushelper.DbusHelper(_make_inverter("com.victronenergy.pvinverter", "/dev/ttyUSB1"))

    assert _Capture.names[0] != _Capture.names[1]
    assert _Capture.names[0].endswith("ttyUSB0")
    assert _Capture.names[1].endswith("ttyUSB1")


if __name__ == "__main__":
    test_pvinverter_prefix_for_solis()
    test_vebus_prefix_for_samlex()
    test_port_suffix_appended_pvinverter()
    test_port_suffix_appended_vebus()
    test_different_ports_produce_different_names()
    print("All 034 tests passed.")
