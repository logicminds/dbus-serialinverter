"""Test 005: Inverter base class initialises energy_data with correct keys and None values."""
import sys
import os
import types

for mod in ["utils", "dbus", "gi", "gi.repository", "gi.repository.GLib"]:
    sys.modules.setdefault(mod, types.ModuleType(mod))

utils_mod = sys.modules["utils"]
if not hasattr(utils_mod, "logger"):
    import logging
    utils_mod.logger = logging.getLogger("test")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "etc", "dbus-serialinverter"))

if "inverter" in sys.modules and not hasattr(sys.modules["inverter"], "Inverter"):
    del sys.modules["inverter"]

from inverter import Inverter


class _ConcreteInverter(Inverter):
    def test_connection(self): return True
    def get_settings(self): return True
    def refresh_data(self): return True


def _make_inverter():
    return _ConcreteInverter(port="/dev/null", baudrate=9600, slave=1)


# ── Phase keys ────────────────────────────────────────────────────────────────

def test_all_phase_keys_present():
    inv = _make_inverter()
    for phase in ["L1", "L2", "L3"]:
        for key in ["ac_voltage", "ac_current", "ac_power", "energy_forwarded"]:
            assert key in inv.energy_data[phase], \
                f"energy_data['{phase}'] missing key '{key}'"


def test_all_overall_keys_present():
    inv = _make_inverter()
    for key in ["ac_power", "energy_forwarded", "power_limit", "active_power_limit"]:
        assert key in inv.energy_data["overall"], \
            f"energy_data['overall'] missing key '{key}'"


def test_all_phase_values_default_to_none():
    inv = _make_inverter()
    for phase in ["L1", "L2", "L3"]:
        for key, val in inv.energy_data[phase].items():
            assert val is None, \
                f"energy_data['{phase}']['{key}'] should default to None, got {val!r}"


def test_all_overall_values_default_to_none():
    inv = _make_inverter()
    for key, val in inv.energy_data["overall"].items():
        assert val is None, \
            f"energy_data['overall']['{key}'] should default to None, got {val!r}"


def test_phases_are_independent_dicts():
    """Mutating one phase must not affect another."""
    inv = _make_inverter()
    inv.energy_data["L1"]["ac_power"] = 100.0
    assert inv.energy_data["L2"]["ac_power"] is None
    assert inv.energy_data["L3"]["ac_power"] is None


if __name__ == "__main__":
    test_all_phase_keys_present()
    test_all_overall_keys_present()
    test_all_phase_values_default_to_none()
    test_all_overall_values_default_to_none()
    test_phases_are_independent_dicts()
    print("All 005 tests passed.")
