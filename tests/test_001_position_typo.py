"""Test 001: self.position is defined in Inverter base class (was self.positon typo)."""
import sys
import os
import types

# Stub out heavy dependencies before importing inverter
for mod in ["utils", "dbus", "gi", "gi.repository", "gi.repository.GLib"]:
    sys.modules.setdefault(mod, types.ModuleType(mod))

utils_mod = sys.modules["utils"]
utils_mod.logger = type("Logger", (), {
    "info": staticmethod(lambda *a, **kw: None),
    "debug": staticmethod(lambda *a, **kw: None),
    "warn": staticmethod(lambda *a, **kw: None),
    "error": staticmethod(lambda *a, **kw: None),
})()

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "etc", "dbus-serialinverter"))

from inverter import Inverter


class _ConcreteInverter(Inverter):
    """Minimal concrete subclass that does NOT set self.position in get_settings."""
    def test_connection(self): return True
    def get_settings(self): return True
    def refresh_data(self): return True


def test_position_attribute_exists_on_base_class():
    inv = _ConcreteInverter(port="/dev/null", baudrate=9600, slave=1)
    assert hasattr(inv, "position"), "Inverter base class must define self.position"


def test_positon_typo_is_gone():
    inv = _ConcreteInverter(port="/dev/null", baudrate=9600, slave=1)
    assert not hasattr(inv, "positon"), "Dead attribute self.positon must not exist"


def test_log_settings_does_not_raise_without_get_settings():
    """log_settings() must work even when a subclass never assigns self.position."""
    inv = _ConcreteInverter(port="/dev/null", baudrate=9600, slave=1)
    # Should not raise AttributeError
    inv.log_settings()


if __name__ == "__main__":
    test_position_attribute_exists_on_base_class()
    test_positon_typo_is_gone()
    test_log_settings_does_not_raise_without_get_settings()
    print("All 001 tests passed.")
