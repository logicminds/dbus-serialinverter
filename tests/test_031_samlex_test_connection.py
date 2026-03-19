"""Test 031: Samlex test_connection() — identity register match, mismatch, IOError."""
import sys
import os
import types
import logging
import configparser
import unittest.mock as mock

for mod in ["dbus", "gi", "gi.repository", "gi.repository.GLib",
            "pymodbus", "pymodbus.client", "pymodbus.constants", "pymodbus.payload"]:
    sys.modules.setdefault(mod, types.ModuleType(mod))

sys.modules["pymodbus.client"].ModbusSerialClient = mock.MagicMock
sys.modules["pymodbus.constants"].Endian = type("Endian", (), {"Big": 0})()
if not hasattr(sys.modules["pymodbus.payload"], "BinaryPayloadDecoder"):
    sys.modules["pymodbus.payload"].BinaryPayloadDecoder = mock.MagicMock

utils_stub = sys.modules.setdefault("utils", types.ModuleType("utils"))
if not hasattr(utils_stub, "logger"):
    utils_stub.logger = logging.getLogger("test")
for _attr, _val in [
    ("INVERTER_TYPE", "Samlex"), ("INVERTER_MAX_AC_POWER", 4000.0),
    ("INVERTER_PHASE", "L1"), ("INVERTER_POLL_INTERVAL", 1000), ("INVERTER_POSITION", 1),
]:
    if not hasattr(utils_stub, _attr):
        setattr(utils_stub, _attr, _val)

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "etc", "dbus-serialinverter"))

if "inverter" in sys.modules and not hasattr(sys.modules["inverter"], "Inverter"):
    del sys.modules["inverter"]

from inverter import Inverter
from samlex import Samlex, REQUIRED_SAMLEX_REGISTERS

_IDENTITY_REG = 200
_IDENTITY_VAL = 42


def _configured_config():
    cfg = configparser.ConfigParser()
    cfg.add_section("SAMLEX_REGISTERS")
    for i, key in enumerate(REQUIRED_SAMLEX_REGISTERS):
        cfg.set("SAMLEX_REGISTERS", key, str(100 + i))
    # Override identity with known values
    cfg.set("SAMLEX_REGISTERS", "REG_IDENTITY", str(_IDENTITY_REG))
    cfg.set("SAMLEX_REGISTERS", "IDENTITY_VALUE", str(_IDENTITY_VAL))
    return cfg


def _make_client(return_registers=None, is_error=False, raise_ioerror=False):
    client = mock.MagicMock()
    client.is_socket_open.return_value = True
    client.connect.return_value = True

    def _effect(address=0, count=1, slave=1):
        if raise_ioerror:
            raise IOError("port error")
        res = mock.MagicMock()
        res.isError.return_value = is_error
        res.registers = return_registers if return_registers is not None else [0]
        return res

    client.read_input_registers.side_effect = _effect
    return client


def _make_samlex(client):
    s = Samlex.__new__(Samlex)
    Inverter.__init__(s, port="/dev/null", baudrate=9600, slave=1)
    s.type = "Samlex"
    s.energy_data["dc"]["charge_state"] = None
    s.client = client
    return s


# ── Identity register matching ────────────────────────────────────────────────

def test_returns_true_when_identity_matches():
    utils_stub.config = _configured_config()
    s = _make_samlex(_make_client(return_registers=[_IDENTITY_VAL]))
    assert s.test_connection() is True


def test_returns_false_when_identity_mismatches():
    utils_stub.config = _configured_config()
    s = _make_samlex(_make_client(return_registers=[_IDENTITY_VAL + 1]))
    assert s.test_connection() is False


def test_returns_false_when_identity_read_errors():
    utils_stub.config = _configured_config()
    s = _make_samlex(_make_client(return_registers=[], is_error=True))
    assert s.test_connection() is False


# ── IOError handling ──────────────────────────────────────────────────────────

def test_returns_false_on_ioerror():
    utils_stub.config = _configured_config()
    s = _make_samlex(_make_client(raise_ioerror=True))
    assert s.test_connection() is False


# ── No Modbus I/O when unconfigured ──────────────────────────────────────────

def test_no_modbus_call_when_unconfigured():
    """When registers are not configured, test_connection() must not touch Modbus."""
    cfg = configparser.ConfigParser()  # empty config
    utils_stub.config = cfg
    client = mock.MagicMock()
    s = _make_samlex(client)
    result = s.test_connection()
    assert result is False
    client.read_input_registers.assert_not_called()


if __name__ == "__main__":
    test_returns_true_when_identity_matches()
    test_returns_false_when_identity_mismatches()
    test_returns_false_when_identity_read_errors()
    test_returns_false_on_ioerror()
    test_no_modbus_call_when_unconfigured()
    print("All 031 tests passed.")
