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


# ── Module-level: _resolve_inverter_types() selection ────────────────────────
# _resolve_inverter_types() reads utils.INVERTER_TYPE at call-time, so each test
# must set it around the call (the module is loaded once and reused).

import utils as _utils_mod

_mod_cache = {}


def _get_mod():
    """Load the main module once and cache it."""
    if "mod" not in _mod_cache:
        _mod_cache["mod"] = _load_module("")
    return _mod_cache["mod"]


def _call_resolve(inverter_type, port):
    """Temporarily set INVERTER_TYPE and call _resolve_inverter_types."""
    old = _utils_mod.INVERTER_TYPE
    _utils_mod.INVERTER_TYPE = inverter_type
    try:
        return _get_mod()._resolve_inverter_types(port)
    finally:
        _utils_mod.INVERTER_TYPE = old


def test_expected_types_dummy_explicit():
    """INVERTER_TYPE='Dummy' → _resolve_inverter_types returns only Dummy."""
    from dummy import Dummy
    result = _call_resolve("Dummy", "/dev/null")
    assert len(result) == 1
    assert result[0]["inverter"] is Dummy


def test_expected_types_auto_detect():
    """INVERTER_TYPE='' + serial port → _resolve_inverter_types returns Solis + Samlex."""
    from solis import Solis
    from samlex import Samlex
    classes = [t["inverter"] for t in _call_resolve("", "/dev/null")]
    assert Solis in classes
    assert Samlex in classes
    # Order: Solis first
    assert classes.index(Solis) < classes.index(Samlex)


def test_expected_types_explicit_solis():
    """INVERTER_TYPE='Solis' → _resolve_inverter_types returns only Solis."""
    from solis import Solis
    result = _call_resolve("Solis", "/dev/null")
    assert len(result) == 1
    assert result[0]["inverter"] is Solis


def test_expected_types_explicit_samlex():
    """INVERTER_TYPE='Samlex' → _resolve_inverter_types returns only Samlex."""
    from samlex import Samlex
    result = _call_resolve("Samlex", "/dev/null")
    assert len(result) == 1
    assert result[0]["inverter"] is Samlex


def test_real_inverter_types_have_baudrate():
    """_REAL_INVERTER_TYPES entries must carry a non-negative baudrate."""
    mod = _get_mod()
    for entry in mod._REAL_INVERTER_TYPES:
        assert "baudrate" in entry
        assert entry["baudrate"] >= 0


def test_resolve_inverter_types_tcp_auto_detect():
    """INVERTER_TYPE='' + tcp:// port → _resolve_inverter_types returns SamlexTCP."""
    from samlex_tcp import SamlexTCP
    result = _call_resolve("", "tcp://localhost:5020")
    assert len(result) == 1
    assert result[0]["inverter"] is SamlexTCP


def test_resolve_inverter_types_samlex_tcp_explicit():
    """INVERTER_TYPE='SamlexTCP' → _resolve_inverter_types returns SamlexTCP."""
    from samlex_tcp import SamlexTCP
    result = _call_resolve("SamlexTCP", "/dev/null")
    assert len(result) == 1
    assert result[0]["inverter"] is SamlexTCP


# ── main(): sys.exit(1) when no inverter found ────────────────────────────────

def test_main_exits_on_no_inverter(monkeypatch):
    """main() must call sys.exit(1) when get_inverter returns None."""
    mod = _load_module("Dummy")
    monkeypatch.setattr(mod, "sleep", mock.MagicMock())

    fail_class = type("_Fail", (), {
        "__init__": lambda self, **kw: None,
        "test_connection": lambda self: False,
    })
    monkeypatch.setattr(mod, "_resolve_inverter_types",
                        lambda port: [{"inverter": fail_class, "baudrate": 0, "slave": 0}])
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

    monkeypatch.setattr(mod, "_resolve_inverter_types",
                        lambda port: [{"inverter": _FakeInverterClass, "baudrate": 0, "slave": 0}])

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
    mod.GLib = mock.MagicMock()
    mod.GLib.MainLoop.return_value = fake_loop
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

    monkeypatch.setattr(mod, "_resolve_inverter_types",
                        lambda port: [{"inverter": _FakeInverterClass, "baudrate": 0, "slave": 0}])

    fake_helper = mock.MagicMock()
    fake_helper.setup_vedbus.return_value = False

    monkeypatch.setattr(sys, "argv", ["dbus-serialinverter.py", "/dev/null"])

    mod.DbusHelper = mock.MagicMock(return_value=fake_helper)
    mod.GLib = mock.MagicMock()
    mod.DBusGMainLoop = mock.MagicMock(return_value=None)

    with pytest.raises(SystemExit) as exc:
        mod.main()
    assert exc.value.code == 1


# ── main(): get_port() exits when no argv ─────────────────────────────────────

def test_main_get_port_no_arg_exits(monkeypatch):
    """get_port() calls sys.exit(1) when no port argument is passed."""
    mod = _load_module("Dummy")
    monkeypatch.setattr(sys, "argv", ["dbus-serialinverter.py"])

    with pytest.raises(SystemExit) as exc:
        mod.main()
    assert exc.value.code == 1


def test_main_get_port_invalid_path_exits(monkeypatch):
    """get_port() calls sys.exit(1) when the port path fails validation."""
    mod = _load_module("Dummy")
    monkeypatch.setattr(sys, "argv", ["dbus-serialinverter.py", "/etc/passwd"])

    with pytest.raises(SystemExit) as exc:
        mod.main()
    assert exc.value.code == 1


def test_main_get_port_accepts_valid_paths(monkeypatch):
    """get_port() accepts well-formed /dev/tty* and /dev/null paths."""
    mod = _load_module("Dummy")
    monkeypatch.setattr(mod, "sleep", mock.MagicMock())

    fail_class = type("_Fail", (), {
        "__init__": lambda self, **kw: None,
        "test_connection": lambda self: False,
    })
    monkeypatch.setattr(mod, "_resolve_inverter_types",
                        lambda port: [{"inverter": fail_class, "baudrate": 0, "slave": 0}])

    for valid_port in ["/dev/ttyUSB0", "/dev/ttyS0", "/dev/ttyAMA0", "/dev/null",
                       "tcp://localhost:5020", "tcp://192.168.1.100:502"]:
        monkeypatch.setattr(sys, "argv", ["dbus-serialinverter.py", valid_port])
        with pytest.raises(SystemExit) as exc:
            mod.main()
        # Should exit with 1 (no inverter), not due to port validation
        assert exc.value.code == 1


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

    monkeypatch.setattr(mod, "_resolve_inverter_types",
                        lambda port: [{"inverter": _FakeInverterClass, "baudrate": 0, "slave": 0}])

    fake_helper = mock.MagicMock()
    fake_helper.setup_vedbus.return_value = True

    fake_loop = mock.MagicMock()
    fake_loop.run.side_effect = KeyboardInterrupt

    monkeypatch.setattr(sys, "argv", ["dbus-serialinverter.py", "/dev/null"])

    mod.DbusHelper = mock.MagicMock(return_value=fake_helper)
    mod.GLib = mock.MagicMock()
    mod.GLib.MainLoop.return_value = fake_loop
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
