"""Test 009: Dummy.get_settings() returns True only when INVERTER_TYPE == 'Dummy'."""
import sys
import os
import types
import logging

for mod in ["dbus", "gi", "gi.repository", "gi.repository.GLib"]:
    sys.modules.setdefault(mod, types.ModuleType(mod))

utils_stub = sys.modules.setdefault("utils", types.ModuleType("utils"))
if not hasattr(utils_stub, "logger"):
    utils_stub.logger = logging.getLogger("test")
for _attr, _val in [
    ("INVERTER_TYPE", "Dummy"),
    ("INVERTER_MAX_AC_POWER", 800.0),
    ("INVERTER_PHASE", "L1"),
    ("INVERTER_POLL_INTERVAL", 1000),
    ("INVERTER_POSITION", 1),
]:
    if not hasattr(utils_stub, _attr):
        setattr(utils_stub, _attr, _val)

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "etc", "dbus-serialinverter"))

if "inverter" in sys.modules and not hasattr(sys.modules["inverter"], "Inverter"):
    del sys.modules["inverter"]

from inverter import Inverter
from dummy import Dummy


def _make_dummy():
    d = Dummy.__new__(Dummy)
    Inverter.__init__(d, port="/dev/null", baudrate=0, slave=0)
    d.type = "Dummy"
    return d


# ── Matching TYPE ─────────────────────────────────────────────────────────────

def test_get_settings_returns_true_when_type_matches():
    utils_stub.INVERTER_TYPE = "Dummy"
    d = _make_dummy()
    assert d.get_settings() is True


def test_get_settings_populates_max_ac_power():
    utils_stub.INVERTER_TYPE = "Dummy"
    d = _make_dummy()
    d.get_settings()
    assert d.max_ac_power == utils_stub.INVERTER_MAX_AC_POWER


def test_get_settings_populates_phase():
    utils_stub.INVERTER_TYPE = "Dummy"
    d = _make_dummy()
    d.get_settings()
    assert d.phase == utils_stub.INVERTER_PHASE


def test_get_settings_populates_position():
    utils_stub.INVERTER_TYPE = "Dummy"
    d = _make_dummy()
    d.get_settings()
    assert d.position == utils_stub.INVERTER_POSITION


def test_get_settings_populates_serial_number():
    utils_stub.INVERTER_TYPE = "Dummy"
    d = _make_dummy()
    d.get_settings()
    assert d.serial_number == 12345678


def test_get_settings_populates_hardware_version():
    utils_stub.INVERTER_TYPE = "Dummy"
    d = _make_dummy()
    d.get_settings()
    assert d.hardware_version == "1.0.0"


def test_get_settings_populates_power_limit():
    utils_stub.INVERTER_TYPE = "Dummy"
    d = _make_dummy()
    d.get_settings()
    assert d.energy_data["overall"]["power_limit"] == utils_stub.INVERTER_MAX_AC_POWER


# ── Non-matching TYPE ─────────────────────────────────────────────────────────

def test_get_settings_returns_false_when_type_is_solis():
    original = utils_stub.INVERTER_TYPE
    try:
        utils_stub.INVERTER_TYPE = "Solis"
        d = _make_dummy()
        assert d.get_settings() is False
    finally:
        utils_stub.INVERTER_TYPE = original


def test_get_settings_returns_false_when_type_is_blank():
    """Blank TYPE must return False — Dummy must not self-activate on empty config."""
    original = utils_stub.INVERTER_TYPE
    try:
        utils_stub.INVERTER_TYPE = ""
        d = _make_dummy()
        assert d.get_settings() is False
    finally:
        utils_stub.INVERTER_TYPE = original


def test_get_settings_returns_false_when_type_is_unknown():
    original = utils_stub.INVERTER_TYPE
    try:
        utils_stub.INVERTER_TYPE = "Unknown"
        d = _make_dummy()
        assert d.get_settings() is False
    finally:
        utils_stub.INVERTER_TYPE = original


if __name__ == "__main__":
    test_get_settings_returns_true_when_type_matches()
    test_get_settings_populates_max_ac_power()
    test_get_settings_populates_phase()
    test_get_settings_populates_position()
    test_get_settings_populates_serial_number()
    test_get_settings_populates_hardware_version()
    test_get_settings_populates_power_limit()
    test_get_settings_returns_false_when_type_is_solis()
    test_get_settings_returns_false_when_type_is_blank()
    test_get_settings_returns_false_when_type_is_unknown()
    print("All 009 tests passed.")
