"""Test 010: Dummy.read_status_data() correctly calculates all energy fields."""
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
    ("INVERTER_TYPE", "Dummy"), ("INVERTER_MAX_AC_POWER", 800.0),
    ("INVERTER_PHASE", "L1"), ("INVERTER_POLL_INTERVAL", 1000), ("INVERTER_POSITION", 1),
]:
    if not hasattr(utils_stub, _attr):
        setattr(utils_stub, _attr, _val)

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "etc", "dbus-serialinverter"))

if "inverter" in sys.modules and not hasattr(sys.modules["inverter"], "Inverter"):
    del sys.modules["inverter"]

from inverter import Inverter
from dummy import Dummy


def _make_dummy(power_limit=400.0):
    d = Dummy.__new__(Dummy)
    Inverter.__init__(d, port="/dev/null", baudrate=0, slave=0)
    d.type = "Dummy"
    d.energy_data["overall"]["power_limit"] = power_limit
    return d


# ── Success path ──────────────────────────────────────────────────────────────

def test_read_status_data_returns_true():
    d = _make_dummy(400.0)
    assert d.read_status_data() is True


def test_l1_ac_voltage_is_230():
    d = _make_dummy(400.0)
    d.read_status_data()
    assert d.energy_data["L1"]["ac_voltage"] == 230.0


def test_l1_ac_current_equals_power_over_230():
    power = 400.0
    d = _make_dummy(power)
    d.read_status_data()
    expected = power / 230
    assert abs(d.energy_data["L1"]["ac_current"] - expected) < 0.001


def test_l1_ac_power_equals_power_limit():
    power = 400.0
    d = _make_dummy(power)
    d.read_status_data()
    assert d.energy_data["L1"]["ac_power"] == power


def test_l1_energy_forwarded_is_nonzero():
    d = _make_dummy(400.0)
    d.read_status_data()
    assert d.energy_data["L1"]["energy_forwarded"] == 0.1


def test_overall_ac_power_equals_power_limit():
    power = 400.0
    d = _make_dummy(power)
    d.read_status_data()
    assert d.energy_data["overall"]["ac_power"] == power


def test_status_is_7():
    d = _make_dummy(400.0)
    d.read_status_data()
    assert d.status == 7


# ── L2 and L3 are zeroed in single-phase mode ─────────────────────────────────

def test_l2_and_l3_are_zeroed():
    d = _make_dummy(400.0)
    d.read_status_data()
    for phase in ["L2", "L3"]:
        assert d.energy_data[phase]["ac_voltage"] == 0.0, f"{phase} voltage should be 0"
        assert d.energy_data[phase]["ac_current"] == 0.0, f"{phase} current should be 0"
        assert d.energy_data[phase]["ac_power"] == 0.0, f"{phase} power should be 0"
        assert d.energy_data[phase]["energy_forwarded"] == 0.0, f"{phase} energy should be 0"


# ── Edge case: power_limit = 0 ────────────────────────────────────────────────

def test_zero_power_limit_produces_zero_current():
    d = _make_dummy(0.0)
    d.read_status_data()
    assert d.energy_data["L1"]["ac_current"] == 0.0


# ── Edge case: None power_limit raises TypeError ──────────────────────────────

def test_none_power_limit_raises_type_error():
    """
    Documents a known fragility: power_limit=None causes TypeError at `None / 230`.
    get_settings() must always run before read_status_data().
    """
    d = _make_dummy()
    d.energy_data["overall"]["power_limit"] = None  # override to None
    try:
        d.read_status_data()
        assert False, "Should raise TypeError when power_limit is None"
    except TypeError:
        pass  # expected — caller must ensure get_settings() ran first


if __name__ == "__main__":
    test_read_status_data_returns_true()
    test_l1_ac_voltage_is_230()
    test_l1_ac_current_equals_power_over_230()
    test_l1_ac_power_equals_power_limit()
    test_l1_energy_forwarded_is_nonzero()
    test_overall_ac_power_equals_power_limit()
    test_status_is_7()
    test_l2_and_l3_are_zeroed()
    test_zero_power_limit_produces_zero_current()
    test_none_power_limit_raises_type_error()
    print("All 010 tests passed.")
