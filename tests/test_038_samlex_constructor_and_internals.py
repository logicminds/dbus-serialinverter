"""Test 038: Samlex __init__, _ensure_connected, _read_batch failure, refresh_data.

Covers samlex.py lines that existing tests miss:
  40-53  __init__ body (ModbusSerialClient instantiation + logger.info)
  85     _ensure_connected: return self.client.connect() (socket was closed)
  90-91  _read_batch: logger.error + early return when _ensure_connected fails
  138    refresh_data: return self.read_status_data()
"""
import sys
import os
import types
import logging
import configparser
import unittest.mock as mock

for _mod in ["dbus", "gi", "gi.repository", "gi.repository.GLib",
             "pymodbus", "pymodbus.client", "pymodbus.constants", "pymodbus.payload"]:
    sys.modules.setdefault(_mod, types.ModuleType(_mod))

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

_DRIVER_DIR = os.path.join(os.path.dirname(__file__), "..", "etc", "dbus-serialinverter")
if _DRIVER_DIR not in sys.path:
    sys.path.insert(0, _DRIVER_DIR)

if "inverter" in sys.modules and not hasattr(sys.modules["inverter"], "Inverter"):
    del sys.modules["inverter"]

from inverter import Inverter
from samlex import Samlex, REQUIRED_SAMLEX_REGISTERS


def _full_config():
    """ConfigParser with all required registers set to unique integer addresses."""
    cfg = configparser.ConfigParser()
    cfg.add_section("SAMLEX_REGISTERS")
    scales = {
        "SCALE_AC_OUT_VOLTAGE": "0.1", "SCALE_AC_OUT_CURRENT": "0.01",
        "SCALE_AC_OUT_POWER": "1.0", "SCALE_DC_VOLTAGE": "0.1",
        "SCALE_DC_CURRENT": "0.01", "SCALE_AC_IN_VOLTAGE": "0.1",
        "SCALE_AC_IN_CURRENT": "0.01",
    }
    for i, key in enumerate(REQUIRED_SAMLEX_REGISTERS):
        cfg.set("SAMLEX_REGISTERS", key, scales.get(key, str(100 + i)))
    return cfg


def _make_passing_client():
    client = mock.MagicMock()
    client.is_socket_open.return_value = True
    ok = mock.MagicMock()
    ok.isError.return_value = False
    ok.registers = [0]
    client.read_input_registers.return_value = ok
    return client


# ── __init__ (lines 40-53) ────────────────────────────────────────────────────

def test_constructor_sets_type():
    """Samlex.__init__ must set self.type = 'Samlex'."""
    s = Samlex(port="/dev/null", baudrate=9600, slave=1)
    assert s.type == "Samlex"


def test_constructor_initialises_charge_state():
    """Samlex.__init__ must initialise energy_data['dc']['charge_state'] to None."""
    s = Samlex(port="/dev/null", baudrate=9600, slave=1)
    assert s.energy_data["dc"]["charge_state"] is None


def test_constructor_creates_modbus_client():
    """Samlex.__init__ must instantiate a ModbusSerialClient and assign to self.client."""
    import modbus_inverter as modbus_inverter_mod
    with mock.patch.object(modbus_inverter_mod, "ModbusSerialClient") as mock_msc:
        s = Samlex(port="/dev/ttyUSB0", baudrate=9600, slave=1)
    assert mock_msc.called, "ModbusSerialClient constructor was not called"
    assert s.client is not None


def test_constructor_passes_port_to_modbus():
    """ModbusSerialClient must receive the port= argument from __init__."""
    import modbus_inverter as modbus_inverter_mod
    with mock.patch.object(modbus_inverter_mod, "ModbusSerialClient") as mock_msc:
        Samlex(port="/dev/ttyUSB1", baudrate=19200, slave=2)
    _, kwargs = mock_msc.call_args
    assert kwargs.get("port") == "/dev/ttyUSB1"


def test_constructor_passes_baudrate_to_modbus():
    """ModbusSerialClient must receive the baudrate= argument from __init__."""
    import modbus_inverter as modbus_inverter_mod
    with mock.patch.object(modbus_inverter_mod, "ModbusSerialClient") as mock_msc:
        Samlex(port="/dev/null", baudrate=19200, slave=1)
    _, kwargs = mock_msc.call_args
    assert kwargs.get("baudrate") == 19200


# ── _ensure_connected: reconnect path (line 85) ───────────────────────────────

def test_ensure_connected_calls_connect_when_socket_closed():
    """_ensure_connected must call client.connect() when is_socket_open() is False."""
    s = Samlex.__new__(Samlex)
    Inverter.__init__(s, port="/dev/null", baudrate=9600, slave=1)
    s.type = "Samlex"
    s.energy_data["dc"]["charge_state"] = None
    s.client = mock.MagicMock()
    s.client.is_socket_open.return_value = False
    s.client.connect.return_value = True

    result = s._ensure_connected()

    assert s.client.connect.called, "connect() must be called when socket is closed"
    assert result is True


def test_ensure_connected_returns_connect_result_on_failure():
    """_ensure_connected must propagate False from connect() when socket was closed."""
    s = Samlex.__new__(Samlex)
    Inverter.__init__(s, port="/dev/null", baudrate=9600, slave=1)
    s.type = "Samlex"
    s.energy_data["dc"]["charge_state"] = None
    s.client = mock.MagicMock()
    s.client.is_socket_open.return_value = False
    s.client.connect.return_value = False

    result = s._ensure_connected()
    assert result is False


# ── _read_batch: no-connection path (lines 90-91) ────────────────────────────

def test_read_batch_returns_false_when_connection_fails():
    """_read_batch must return (False, []) when _ensure_connected returns False."""
    s = Samlex.__new__(Samlex)
    Inverter.__init__(s, port="/dev/null", baudrate=9600, slave=1)
    s.type = "Samlex"
    s.energy_data["dc"]["charge_state"] = None
    s.client = mock.MagicMock()
    s.client.is_socket_open.return_value = False
    s.client.connect.return_value = False  # connection fails

    ok, regs = s._read_batch(address=100, count=1)
    assert ok is False
    assert regs == []


def test_read_batch_does_not_call_read_when_connection_fails():
    """_read_batch must not call read_input_registers when _ensure_connected fails."""
    s = Samlex.__new__(Samlex)
    Inverter.__init__(s, port="/dev/null", baudrate=9600, slave=1)
    s.type = "Samlex"
    s.energy_data["dc"]["charge_state"] = None
    s.client = mock.MagicMock()
    s.client.is_socket_open.return_value = False
    s.client.connect.return_value = False

    s._read_batch(address=100, count=1)
    s.client.read_input_registers.assert_not_called()


# ── refresh_data (line 138) ───────────────────────────────────────────────────

def test_refresh_data_delegates_to_read_status_data():
    """refresh_data() must call read_status_data() and return its result."""
    s = Samlex.__new__(Samlex)
    Inverter.__init__(s, port="/dev/null", baudrate=9600, slave=1)
    s.type = "Samlex"
    s.energy_data["dc"]["charge_state"] = None
    s.client = _make_passing_client()
    utils_stub.config = _full_config()

    with mock.patch.object(s, "read_status_data", return_value=True) as mock_rsd:
        result = s.refresh_data()

    mock_rsd.assert_called_once()
    assert result is True


def test_refresh_data_returns_false_on_failure():
    """refresh_data() propagates False from read_status_data()."""
    s = Samlex.__new__(Samlex)
    Inverter.__init__(s, port="/dev/null", baudrate=9600, slave=1)
    s.type = "Samlex"
    s.energy_data["dc"]["charge_state"] = None
    s.client = _make_passing_client()
    utils_stub.config = _full_config()

    with mock.patch.object(s, "read_status_data", return_value=False):
        result = s.refresh_data()

    assert result is False


if __name__ == "__main__":
    test_constructor_sets_type()
    test_constructor_initialises_charge_state()
    test_constructor_creates_modbus_client()
    test_constructor_passes_port_to_modbus()
    test_constructor_passes_baudrate_to_modbus()
    test_ensure_connected_calls_connect_when_socket_closed()
    test_ensure_connected_returns_connect_result_on_failure()
    test_read_batch_returns_false_when_connection_fails()
    test_read_batch_does_not_call_read_when_connection_fails()
    test_refresh_data_delegates_to_read_status_data()
    test_refresh_data_returns_false_on_failure()
    print("All 038 tests passed.")
