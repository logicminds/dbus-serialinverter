"""Test 027: Inverter abstract method default bodies and apply_power_limit default.

Lines 58, 69, 79 are the `return False` bodies of abstract methods — reachable
via super() calls from a concrete subclass. Line 86 is the default `return True`
in apply_power_limit, covered when a concrete inverter doesn't override it.
Lines 88-96 cover log_settings().
"""
import sys
import os
import types
import logging

for _mod in ["dbus", "gi", "gi.repository", "gi.repository.GLib"]:
    sys.modules.setdefault(_mod, types.ModuleType(_mod))

_utils = sys.modules.setdefault("utils", types.ModuleType("utils"))
if not hasattr(_utils, "logger"):
    _utils.logger = logging.getLogger("test")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "etc", "dbus-serialinverter"))

if "inverter" in sys.modules and not hasattr(sys.modules["inverter"], "Inverter"):
    del sys.modules["inverter"]

from inverter import Inverter


class _CallSuperInverter(Inverter):
    """Concrete inverter that delegates to super() for all abstract methods."""

    def test_connection(self):
        return super().test_connection()

    def get_settings(self):
        return super().get_settings()

    def refresh_data(self):
        return super().refresh_data()


def _make():
    return _CallSuperInverter(port="/dev/null", baudrate=9600, slave=1)


# ── Abstract method bodies (lines 58, 69, 79) ─────────────────────────────────

def test_abstract_test_connection_returns_false():
    """super().test_connection() body (line 58) returns False."""
    assert _make().test_connection() is False


def test_abstract_get_settings_returns_false():
    """super().get_settings() body (line 69) returns False."""
    assert _make().get_settings() is False


def test_abstract_refresh_data_returns_false():
    """super().refresh_data() body (line 79) returns False."""
    assert _make().refresh_data() is False


# ── apply_power_limit default (line 86) ───────────────────────────────────────

def test_default_apply_power_limit_returns_true():
    """Base apply_power_limit (line 86) returns True when not overridden."""
    inv = _make()
    assert inv.apply_power_limit(500) is True


def test_default_apply_power_limit_any_value():
    """Base apply_power_limit ignores the value and returns True."""
    inv = _make()
    for watts in [0, 100, 800, 9999]:
        assert inv.apply_power_limit(watts) is True


# ── log_settings (lines 88-96) ───────────────────────────────────────────────

def test_log_settings_runs_without_error():
    """log_settings() should complete without raising."""
    inv = _make()
    inv.serial_number = "SN123"
    inv.hardware_version = "1.0"
    inv.max_ac_power = 800.0
    inv.phase = "L1"
    inv.position = 1
    inv.log_settings()  # should not raise


def test_log_settings_returns_none():
    inv = _make()
    inv.serial_number = "SN123"
    inv.hardware_version = "1.0"
    inv.max_ac_power = 800.0
    inv.phase = "L1"
    inv.position = 1
    result = inv.log_settings()
    assert result is None


if __name__ == "__main__":
    test_abstract_test_connection_returns_false()
    test_abstract_get_settings_returns_false()
    test_abstract_refresh_data_returns_false()
    test_default_apply_power_limit_returns_true()
    test_default_apply_power_limit_any_value()
    test_log_settings_runs_without_error()
    test_log_settings_returns_none()
    print("All 027 tests passed.")
