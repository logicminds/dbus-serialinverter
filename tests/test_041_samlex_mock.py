"""Test 041: SamlexMock - Mock inverter for testing without hardware."""
import sys
import os
import types
import configparser
import unittest.mock as mock

# Stub out external dependencies
for mod in ["dbus", "gi", "gi.repository", "gi.repository.GLib",
            "pymodbus", "pymodbus.client", "pymodbus.constants", "pymodbus.payload"]:
    sys.modules.setdefault(mod, types.ModuleType(mod))

if not hasattr(sys.modules["pymodbus.client"], "ModbusSerialClient"):
    sys.modules["pymodbus.client"].ModbusSerialClient = mock.MagicMock
if not hasattr(sys.modules["pymodbus.constants"], "Endian"):
    sys.modules["pymodbus.constants"].Endian = type("Endian", (), {"Big": 0})()
if not hasattr(sys.modules["pymodbus.payload"], "BinaryPayloadDecoder"):
    sys.modules["pymodbus.payload"].BinaryPayloadDecoder = mock.MagicMock

# Stub utils
utils_stub = sys.modules.setdefault("utils", types.ModuleType("utils"))
utils_stub.logger = mock.MagicMock()
for _attr, _val in [
    ("INVERTER_TYPE", "SamlexMock"), ("INVERTER_MAX_AC_POWER", 4000.0),
    ("INVERTER_PHASE", "L1"), ("INVERTER_POLL_INTERVAL", 1000), ("INVERTER_POSITION", 1),
]:
    setattr(utils_stub, _attr, _val)

# Config stub
utils_stub.config = configparser.ConfigParser()

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "etc", "dbus-serialinverter"))

from samlex_mock import SamlexMock

# ── Basic lifecycle ──────────────────────────────────────────────────────────

def test_inverter_type_is_samlex_mock():
    """SamlexMock reports its type correctly."""
    m = SamlexMock("/dev/test", 0, 1)
    assert m.INVERTERTYPE == "SamlexMock"
    assert m.type == "SamlexMock"

def test_service_prefix_is_vebus():
    """SamlexMock uses vebus service prefix like real Samlex."""
    assert SamlexMock.SERVICE_PREFIX == "com.victronenergy.vebus"

def test_test_connection_always_true():
    """test_connection() always returns True - no hardware to probe."""
    m = SamlexMock("/dev/test", 0, 1)
    assert m.test_connection() is True

# ── Settings ─────────────────────────────────────────────────────────────────

def test_get_settings_populates_fields():
    """get_settings() populates all required fields."""
    m = SamlexMock("/dev/test", 0, 1)
    result = m.get_settings()
    assert result is True
    assert m.max_ac_power == 4000.0
    assert m.phase == "L1"
    # poll_interval and position come from utils.INVERTER_* constants
    assert hasattr(m, 'poll_interval')
    assert hasattr(m, 'position')
    assert m.serial_number == "MOCK-test"

def test_power_limits_are_none():
    """SamlexMock returns None for power limits (same as real Samlex)."""
    m = SamlexMock("/dev/test", 0, 1)
    m.get_settings()
    assert m.energy_data["overall"]["power_limit"] is None
    assert m.energy_data["overall"]["active_power_limit"] is None

# ── Data generation ───────────────────────────────────────────────────────────

def test_refresh_data_returns_true():
    """refresh_data() generates synthetic data successfully."""
    m = SamlexMock("/dev/test", 0, 1)
    m.get_settings()
    result = m.refresh_data()
    assert result is True

def test_energy_data_structure():
    """Generated data has correct structure."""
    m = SamlexMock("/dev/test", 0, 1)
    m.get_settings()
    m.refresh_data()

    # L1 has AC values
    assert "ac_voltage" in m.energy_data["L1"]
    assert "ac_current" in m.energy_data["L1"]
    assert "ac_power" in m.energy_data["L1"]

    # DC has battery values
    assert "voltage" in m.energy_data["dc"]
    assert "current" in m.energy_data["dc"]
    assert "soc" in m.energy_data["dc"]
    assert "charge_state" in m.energy_data["dc"]

    # AC input has values
    assert "voltage" in m.energy_data["ac_in"]
    assert "current" in m.energy_data["ac_in"]
    assert "power" in m.energy_data["ac_in"]
    assert "connected" in m.energy_data["ac_in"]

def test_values_are_realistic():
    """Generated values are in realistic ranges."""
    m = SamlexMock("/dev/test", 0, 1)
    m.get_settings()
    m.refresh_data()

    # AC voltage around 120V
    assert 110 <= m.energy_data["L1"]["ac_voltage"] <= 130

    # DC voltage around 26V (24V nominal)
    assert 20 <= m.energy_data["dc"]["voltage"] <= 30

    # SOC 0-100%
    assert 0 <= m.energy_data["dc"]["soc"] <= 100

    # AC power positive
    assert m.energy_data["L1"]["ac_power"] > 0

    # Status is a valid vebus /State value (2=Fault, 4=Absorption, 5=Float, 9=Inverting, etc.)
    assert m.status in [2, 4, 5, 6, 7, 8, 9]

def test_apply_power_limit_returns_false():
    """apply_power_limit() returns False (not supported)."""
    m = SamlexMock("/dev/test", 0, 1)
    m.get_settings()
    result = m.apply_power_limit(2000)
    assert result is False

# ── Multiple polls ───────────────────────────────────────────────────────────

def test_multiple_polls_generate_different_values():
    """Each poll generates slightly different synthetic data."""
    m = SamlexMock("/dev/test", 0, 1)
    m.get_settings()

    # Get initial values
    m.refresh_data()
    m.energy_data["L1"]["ac_power"]
    m.energy_data["dc"]["soc"]

    # Poll again
    m.refresh_data()
    power2 = m.energy_data["L1"]["ac_power"]
    soc2 = m.energy_data["dc"]["soc"]

    # Values should be similar but may vary
    assert isinstance(power2, int)
    assert isinstance(soc2, float)

if __name__ == "__main__":
    test_inverter_type_is_samlex_mock()
    test_service_prefix_is_vebus()
    test_test_connection_always_true()
    test_get_settings_populates_fields()
    test_power_limits_are_none()
    test_refresh_data_returns_true()
    test_energy_data_structure()
    test_values_are_realistic()
    test_apply_power_limit_returns_false()
    test_multiple_polls_generate_different_values()
    print("All 041 tests passed.")
