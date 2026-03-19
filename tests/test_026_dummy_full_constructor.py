"""Test 026: Dummy.__init__, test_connection(), and refresh_data() coverage.

Existing tests (009, 010) use Dummy.__new__ + Inverter.__init__ to bypass
Dummy.__init__, leaving lines 10-11, 14, 41-42 uncovered.
These tests instantiate Dummy normally via its constructor.
"""
import sys
import os
import types
import logging

# ── Stubs (conftest already installed these, but guard for direct execution) ──

for _mod in ["dbus", "gi", "gi.repository", "gi.repository.GLib"]:
    sys.modules.setdefault(_mod, types.ModuleType(_mod))

_utils = sys.modules.setdefault("utils", types.ModuleType("utils"))
if not hasattr(_utils, "logger"):
    _utils.logger = logging.getLogger("test")
for _attr, _val in [
    ("INVERTER_TYPE", "Dummy"),
    ("INVERTER_MAX_AC_POWER", 800.0),
    ("INVERTER_PHASE", "L1"),
    ("INVERTER_POLL_INTERVAL", 1000),
    ("INVERTER_POSITION", 1),
]:
    if not hasattr(_utils, _attr):
        setattr(_utils, _attr, _val)

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "etc", "dbus-serialinverter"))

if "inverter" in sys.modules and not hasattr(sys.modules["inverter"], "Inverter"):
    del sys.modules["inverter"]

from dummy import Dummy


def _make_dummy_via_constructor():
    """Instantiate Dummy via normal constructor (covers __init__ lines 10-11)."""
    _utils.INVERTER_TYPE = "Dummy"
    return Dummy(port="/dev/null", baudrate=0, slave=0)


# ── __init__ (lines 10-11) ────────────────────────────────────────────────────

def test_constructor_sets_type():
    d = _make_dummy_via_constructor()
    assert d.type == "Dummy"


def test_constructor_sets_port():
    d = _make_dummy_via_constructor()
    assert d.port == "/dev/null"


def test_constructor_calls_super_init():
    """Dummy.__init__ calls super().__init__, so energy_data must be populated."""
    d = _make_dummy_via_constructor()
    assert "L1" in d.energy_data
    assert "overall" in d.energy_data


# ── test_connection() (line 14) ───────────────────────────────────────────────

def test_test_connection_returns_true_when_type_is_dummy():
    _utils.INVERTER_TYPE = "Dummy"
    d = _make_dummy_via_constructor()
    assert d.test_connection() is True


def test_test_connection_returns_false_when_type_is_not_dummy():
    _utils.INVERTER_TYPE = "Dummy"
    d = _make_dummy_via_constructor()
    original = _utils.INVERTER_TYPE
    try:
        _utils.INVERTER_TYPE = "Solis"
        assert d.test_connection() is False
    finally:
        _utils.INVERTER_TYPE = original


# ── refresh_data() (lines 41-42) ─────────────────────────────────────────────

def test_refresh_data_returns_true():
    _utils.INVERTER_TYPE = "Dummy"
    d = _make_dummy_via_constructor()
    d.get_settings()
    assert d.refresh_data() is True


def test_refresh_data_populates_overall_ac_power():
    _utils.INVERTER_TYPE = "Dummy"
    d = _make_dummy_via_constructor()
    d.get_settings()
    d.refresh_data()
    assert d.energy_data["overall"]["ac_power"] == d.energy_data["overall"]["power_limit"]


def test_refresh_data_sets_status_7():
    _utils.INVERTER_TYPE = "Dummy"
    d = _make_dummy_via_constructor()
    d.get_settings()
    d.refresh_data()
    assert d.status == 7


if __name__ == "__main__":
    test_constructor_sets_type()
    test_constructor_sets_port()
    test_constructor_calls_super_init()
    test_test_connection_returns_true_when_type_is_dummy()
    test_test_connection_returns_false_when_type_is_not_dummy()
    test_refresh_data_returns_true()
    test_refresh_data_populates_overall_ac_power()
    test_refresh_data_sets_status_7()
    print("All 026 tests passed.")
