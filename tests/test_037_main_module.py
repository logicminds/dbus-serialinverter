"""Test 037: dbus-serialinverter.py — module-level expected_inverter_types logic and main().

dbus-serialinverter.py cannot be imported with a plain `import` statement (hyphen
in filename) and previously had 0% coverage.  Here we load it via importlib after
stubbing all external dependencies (dbus.mainloop.glib, gi.repository.GLib,
DbusHelper, inverter classes) so the real source lines execute and register in
coverage.

Module-level tests: verify that expected_inverter_types is built correctly for
each INVERTER_TYPE value.

main() tests: mock get_port / DbusHelper / gobject so main() runs to completion
or exits cleanly.
"""
import sys
import os
import types
import importlib.util
import unittest.mock as mock

import pytest

# ── Extra stubs not already provided by conftest ──────────────────────────────

# dbus.mainloop and dbus.mainloop.glib (conftest only stubs the top-level 'dbus')
for _mod_name in ["dbus.mainloop", "dbus.mainloop.glib"]:
    if _mod_name not in sys.modules:
        sys.modules[_mod_name] = types.ModuleType(_mod_name)

_dbml_glib = sys.modules["dbus.mainloop.glib"]
if not hasattr(_dbml_glib, "DBusGMainLoop"):
    _dbml_glib.DBusGMainLoop = mock.MagicMock(return_value=None)

# gi.repository.GLib stub needs MainLoop and timeout_add for main()
_glib_stub = sys.modules.setdefault("gi.repository.GLib", types.ModuleType("gi.repository.GLib"))

_DRIVER_DIR = os.path.join(os.path.dirname(__file__), "..", "etc", "dbus-serialinverter")
_ENTRYPOINT = os.path.join(_DRIVER_DIR, "dbus-serialinverter.py")


def _load_module(inverter_type="Dummy"):
    """Load dbus-serialinverter.py as a fresh module via importlib."""
    import utils as _utils
    old = _utils.INVERTER_TYPE
    _utils.INVERTER_TYPE = inverter_type
    try:
        spec = importlib.util.spec_from_file_location("_dbus_si_test", _ENTRYPOINT)
        mod = importlib.util.module_from_spec(spec)
        # Insert driver directory into path for the module's own relative imports
        if _DRIVER_DIR not in sys.path:
            sys.path.insert(0, _DRIVER_DIR)
        spec.loader.exec_module(mod)
        return mod
    finally:
        _utils.INVERTER_TYPE = old


# ── Module-level: expected_inverter_types selection ───────────────────────────

def test_expected_types_dummy_explicit():
    """INVERTER_TYPE='Dummy' → expected_inverter_types contains only Dummy."""
    mod = _load_module("Dummy")
    from dummy import Dummy
    assert len(mod.expected_inverter_types) == 1
    assert mod.expected_inverter_types[0]["inverter"] is Dummy


def test_expected_types_auto_detect():
    """INVERTER_TYPE='' → expected_inverter_types equals _REAL_INVERTER_TYPES (Solis + Samlex)."""
    mod = _load_module("")
    from solis import Solis
    from samlex import Samlex
    classes = [t["inverter"] for t in mod.expected_inverter_types]
    assert Solis in classes
    assert Samlex in classes
    # Order: Solis first
    assert classes.index(Solis) < classes.index(Samlex)


def test_expected_types_explicit_solis():
    """INVERTER_TYPE='Solis' → expected_inverter_types contains only Solis."""
    mod = _load_module("Solis")
    from solis import Solis
    assert len(mod.expected_inverter_types) == 1
    assert mod.expected_inverter_types[0]["inverter"] is Solis


def test_expected_types_explicit_samlex():
    """INVERTER_TYPE='Samlex' → expected_inverter_types contains only Samlex."""
    mod = _load_module("Samlex")
    from samlex import Samlex
    assert len(mod.expected_inverter_types) == 1
    assert mod.expected_inverter_types[0]["inverter"] is Samlex


def test_real_inverter_types_have_baudrate():
    """_REAL_INVERTER_TYPES entries must carry a non-negative baudrate."""
    mod = _load_module("")
    for entry in mod._REAL_INVERTER_TYPES:
        assert "baudrate" in entry
        assert entry["baudrate"] >= 0


# ── main(): sys.exit(1) when no inverter found ────────────────────────────────

def test_main_exits_on_no_inverter(monkeypatch):
    """main() must call sys.exit(1) when get_inverter returns None."""
    mod = _load_module("Dummy")
    monkeypatch.setattr(mod, "sleep", mock.MagicMock())

    # Override expected_inverter_types so all fail
    fail_class = type("_Fail", (), {
        "__init__": lambda self, **kw: None,
        "test_connection": lambda self: False,
    })
    mod.expected_inverter_types = [{"inverter": fail_class, "baudrate": 0, "slave": 0}]
    monkeypatch.setattr(sys, "argv", ["dbus-serialinverter.py", "/dev/null"])

    with pytest.raises(SystemExit) as exc:
        mod.main()
    assert exc.value.code == 1


# ── main(): successful startup (setup_vedbus returns True) ────────────────────

def test_main_runs_mainloop_on_success(monkeypatch):
    """main() must reach mainloop.run() when inverter connects and setup_vedbus returns True."""
    mod = _load_module("Dummy")

    # Fake inverter that always connects — must be a real class so __name__ works
    class _FakeInverterClass:
        SERVICE_PREFIX = "com.victronenergy.pvinverter"
        def __init__(self, port, baudrate, slave):
            self.port = port
            self.poll_interval = 1000
        def test_connection(self):
            return True
        def log_settings(self):
            pass

    mod.expected_inverter_types = [{"inverter": _FakeInverterClass, "baudrate": 0, "slave": 0}]

    # Fake DbusHelper
    fake_helper = mock.MagicMock()
    fake_helper.setup_vedbus.return_value = True

    reached_run = []

    fake_loop = mock.MagicMock()
    fake_loop.run.side_effect = lambda: reached_run.append(True)

    monkeypatch.setattr(sys, "argv", ["dbus-serialinverter.py", "/dev/null"])

    # Patch DbusHelper in the loaded module's namespace (from dbushelper import DbusHelper
    # creates a local binding — patching the source module does not affect it)
    mod.DbusHelper = mock.MagicMock(return_value=fake_helper)
    mod.gobject = mock.MagicMock()
    mod.gobject.MainLoop.return_value = fake_loop
    mod.DBusGMainLoop = mock.MagicMock(return_value=None)

    mod.main()

    assert reached_run, "mainloop.run() was never called"


# ── main(): sys.exit(1) when setup_vedbus fails ───────────────────────────────

def test_main_exits_when_setup_vedbus_fails(monkeypatch):
    """main() must call sys.exit(1) when setup_vedbus returns False."""
    mod = _load_module("Dummy")

    class _FakeInverterClass:
        SERVICE_PREFIX = "com.victronenergy.pvinverter"
        def __init__(self, port, baudrate, slave):
            self.port = port
            self.poll_interval = 1000
        def test_connection(self):
            return True
        def log_settings(self):
            pass

    mod.expected_inverter_types = [{"inverter": _FakeInverterClass, "baudrate": 0, "slave": 0}]

    fake_helper = mock.MagicMock()
    fake_helper.setup_vedbus.return_value = False

    monkeypatch.setattr(sys, "argv", ["dbus-serialinverter.py", "/dev/null"])

    mod.DbusHelper = mock.MagicMock(return_value=fake_helper)
    mod.gobject = mock.MagicMock()
    mod.DBusGMainLoop = mock.MagicMock(return_value=None)

    with pytest.raises(SystemExit) as exc:
        mod.main()
    assert exc.value.code == 1


# ── main(): get_port() falls back when no argv ────────────────────────────────

def test_main_get_port_fallback(monkeypatch):
    """get_port() returns '/dev/tty/USB9' when no argument is passed."""
    mod = _load_module("Dummy")
    monkeypatch.setattr(mod, "sleep", mock.MagicMock())

    # Capture which port is passed to the inverter constructor
    ports_seen = []
    fail_class = type("_Fail", (), {
        "__init__": lambda self, port, **kw: ports_seen.append(port) or None,
        "test_connection": lambda self: False,
    })
    mod.expected_inverter_types = [{"inverter": fail_class, "baudrate": 0, "slave": 0}]

    # No port argument — get_port() should fall back to "/dev/tty/USB9"
    monkeypatch.setattr(sys, "argv", ["dbus-serialinverter.py"])

    with pytest.raises(SystemExit):
        mod.main()

    assert ports_seen[0] == "/dev/tty/USB9"


# ── main(): KeyboardInterrupt exits cleanly ───────────────────────────────────

def test_main_keyboard_interrupt_exits_cleanly(monkeypatch):
    """KeyboardInterrupt during mainloop.run() must not propagate."""
    mod = _load_module("Dummy")

    class _FakeInverterClass:
        SERVICE_PREFIX = "com.victronenergy.pvinverter"
        def __init__(self, port, baudrate, slave):
            self.port = port
            self.poll_interval = 1000
        def test_connection(self):
            return True
        def log_settings(self):
            pass

    mod.expected_inverter_types = [{"inverter": _FakeInverterClass, "baudrate": 0, "slave": 0}]

    fake_helper = mock.MagicMock()
    fake_helper.setup_vedbus.return_value = True

    fake_loop = mock.MagicMock()
    fake_loop.run.side_effect = KeyboardInterrupt

    monkeypatch.setattr(sys, "argv", ["dbus-serialinverter.py", "/dev/null"])

    mod.DbusHelper = mock.MagicMock(return_value=fake_helper)
    mod.gobject = mock.MagicMock()
    mod.gobject.MainLoop.return_value = fake_loop
    mod.DBusGMainLoop = mock.MagicMock(return_value=None)

    # Must not raise
    mod.main()


if __name__ == "__main__":
    with mock.patch("time.sleep"):
        test_expected_types_dummy_explicit()
        test_expected_types_auto_detect()
        test_expected_types_explicit_solis()
        test_expected_types_explicit_samlex()
        test_real_inverter_types_have_baudrate()
    print("All 037 tests passed.")
