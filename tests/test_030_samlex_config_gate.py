"""Test 030: Samlex config gate (R9) — test_connection() returns False when
[SAMLEX_REGISTERS] is missing, has ??? placeholders, or has non-numeric values."""
import sys
import os
import types
import logging
import configparser
import unittest.mock as mock
import pytest

for mod in ["dbus", "gi", "gi.repository", "gi.repository.GLib",
            "pymodbus", "pymodbus.client", "pymodbus.constants", "pymodbus.payload"]:
    sys.modules.setdefault(mod, types.ModuleType(mod))

sys.modules["pymodbus.client"].ModbusSerialClient = mock.MagicMock
sys.modules["pymodbus.constants"].Endian = type("Endian", (), {"Big": 0})()

_payload = sys.modules["pymodbus.payload"]
if not hasattr(_payload, "BinaryPayloadDecoder"):
    _payload.BinaryPayloadDecoder = mock.MagicMock

utils_stub = sys.modules.setdefault("utils", types.ModuleType("utils"))
if not hasattr(utils_stub, "logger"):
    utils_stub.logger = logging.getLogger("test")
for _attr, _val in [
    ("INVERTER_TYPE", "Samlex"),
    ("INVERTER_MAX_AC_POWER", 4000.0),
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
from samlex import Samlex, REQUIRED_SAMLEX_REGISTERS


def _make_samlex():
    """Build a Samlex instance without opening a real serial port."""
    s = Samlex.__new__(Samlex)
    Inverter.__init__(s, port="/dev/null", baudrate=9600, slave=1)
    s.type = "Samlex"
    s.energy_data["dc"]["charge_state"] = None
    s.client = mock.MagicMock()
    s.client.is_socket_open.return_value = True
    s.client.connect.return_value = True
    return s


def _all_configured_config():
    """Return a ConfigParser with all SAMLEX_REGISTERS set to valid placeholder integers."""
    cfg = configparser.ConfigParser()
    cfg.add_section("SAMLEX_REGISTERS")
    base = 100
    for i, key in enumerate(REQUIRED_SAMLEX_REGISTERS):
        cfg.set("SAMLEX_REGISTERS", key, str(base + i))
    return cfg


# ── Section missing ───────────────────────────────────────────────────────────

def test_returns_false_when_section_missing():
    s = _make_samlex()
    cfg = configparser.ConfigParser()  # no SAMLEX_REGISTERS section at all
    utils_stub.config = cfg
    assert s.test_connection() is False


# ── Placeholder values ────────────────────────────────────────────────────────

def test_returns_false_when_all_values_are_placeholder():
    s = _make_samlex()
    cfg = configparser.ConfigParser()
    cfg.add_section("SAMLEX_REGISTERS")
    for key in REQUIRED_SAMLEX_REGISTERS:
        cfg.set("SAMLEX_REGISTERS", key, "???")
    utils_stub.config = cfg
    assert s.test_connection() is False


def test_returns_false_when_one_value_is_placeholder():
    s = _make_samlex()
    cfg = _all_configured_config()
    # Corrupt exactly one key
    cfg.set("SAMLEX_REGISTERS", "REG_IDENTITY", "???")
    utils_stub.config = cfg
    assert s.test_connection() is False


# ── Non-numeric values ────────────────────────────────────────────────────────

def test_returns_false_when_value_is_non_numeric():
    s = _make_samlex()
    cfg = _all_configured_config()
    cfg.set("SAMLEX_REGISTERS", "SCALE_AC_OUT_VOLTAGE", "abc")
    utils_stub.config = cfg
    assert s.test_connection() is False


# ── All configured: proceeds to Modbus ───────────────────────────────────────

def test_attempts_modbus_when_all_configured():
    """When all registers are configured, test_connection() must attempt a Modbus read."""
    s = _make_samlex()
    cfg = _all_configured_config()
    utils_stub.config = cfg

    # Mock read_input_registers to return an error (wrong device)
    fail = mock.MagicMock()
    fail.isError.return_value = True
    fail.registers = []
    s.client.read_input_registers.return_value = fail

    result = s.test_connection()
    assert result is False
    # Confirm Modbus was actually called
    assert s.client.read_input_registers.called


def test_returns_true_when_identity_register_matches():
    s = _make_samlex()
    cfg = _all_configured_config()
    # IDENTITY_VALUE is at index 19 → base 100+19 = 119
    identity_val = int(cfg.get("SAMLEX_REGISTERS", "IDENTITY_VALUE"))
    utils_stub.config = cfg

    def _read_effect(address=0, count=1, slave=1):
        res = mock.MagicMock()
        res.isError.return_value = False
        res.registers = [identity_val]
        return res

    s.client.read_input_registers.side_effect = _read_effect
    assert s.test_connection() is True


def test_reg_raises_on_negative_address():
    """_reg() must raise ValueError when the configured address is negative."""
    s = _make_samlex()
    cfg = _all_configured_config()
    cfg.set("SAMLEX_REGISTERS", "REG_IDENTITY", "-1")
    utils_stub.config = cfg
    with pytest.raises(ValueError, match="out of valid Modbus range"):
        s._reg("REG_IDENTITY")


def test_reg_raises_on_address_above_65535():
    """_reg() must raise ValueError when the configured address exceeds 65535."""
    s = _make_samlex()
    cfg = _all_configured_config()
    cfg.set("SAMLEX_REGISTERS", "REG_IDENTITY", "65536")
    utils_stub.config = cfg
    with pytest.raises(ValueError, match="out of valid Modbus range"):
        s._reg("REG_IDENTITY")


def test_reg_accepts_boundary_addresses():
    """_reg() must accept 0 and 65535 as valid Modbus register addresses."""
    s = _make_samlex()
    cfg = _all_configured_config()
    utils_stub.config = cfg
    cfg.set("SAMLEX_REGISTERS", "REG_IDENTITY", "0")
    assert s._reg("REG_IDENTITY") == 0
    cfg.set("SAMLEX_REGISTERS", "REG_IDENTITY", "65535")
    assert s._reg("REG_IDENTITY") == 65535


if __name__ == "__main__":
    test_returns_false_when_section_missing()
    test_returns_false_when_all_values_are_placeholder()
    test_returns_false_when_one_value_is_placeholder()
    test_returns_false_when_value_is_non_numeric()
    test_attempts_modbus_when_all_configured()
    test_returns_true_when_identity_register_matches()
    test_reg_raises_on_negative_address()
    test_reg_raises_on_address_above_65535()
    test_reg_accepts_boundary_addresses()
    print("All 030 tests passed.")
