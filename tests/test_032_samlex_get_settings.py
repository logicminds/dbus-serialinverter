"""Test 032: Samlex get_settings() — settings populated from config, power limit suppressed."""
import sys
import os
import types
import logging
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
from samlex import Samlex


def _make_samlex():
    s = Samlex.__new__(Samlex)
    Inverter.__init__(s, port="/dev/ttyUSB0", baudrate=9600, slave=1)
    s.type = "Samlex"
    s.energy_data["dc"]["charge_state"] = None
    s.client = mock.MagicMock()
    return s


def test_returns_true():
    s = _make_samlex()
    assert s.get_settings() is True


def test_max_ac_power_from_config():
    utils_stub.INVERTER_MAX_AC_POWER = 4000.0
    s = _make_samlex()
    s.get_settings()
    assert s.max_ac_power == 4000.0


def test_phase_from_config():
    utils_stub.INVERTER_PHASE = "L1"
    s = _make_samlex()
    s.get_settings()
    assert s.phase == "L1"


def test_poll_interval_from_config():
    utils_stub.INVERTER_POLL_INTERVAL = 2000
    s = _make_samlex()
    s.get_settings()
    assert s.poll_interval == 2000


def test_position_explicitly_set():
    """position must be explicitly set — base class has 'positon' typo (todo #001)."""
    utils_stub.INVERTER_POSITION = 1
    s = _make_samlex()
    s.get_settings()
    assert s.position == 1, "self.position must be set explicitly in get_settings()"


def test_power_limit_suppressed():
    """Both power_limit and active_power_limit must be None (no write support)."""
    s = _make_samlex()
    s.get_settings()
    assert s.energy_data["overall"]["power_limit"] is None
    assert s.energy_data["overall"]["active_power_limit"] is None


def test_serial_number_derived_from_port():
    s = _make_samlex()
    s.get_settings()
    assert s.serial_number == "ttyUSB0"


def test_service_prefix_is_vebus():
    """Samlex must declare vebus service type, not pvinverter."""
    assert Samlex.SERVICE_PREFIX == "com.victronenergy.vebus"


if __name__ == "__main__":
    test_returns_true()
    test_max_ac_power_from_config()
    test_phase_from_config()
    test_poll_interval_from_config()
    test_position_explicitly_set()
    test_power_limit_suppressed()
    test_serial_number_derived_from_port()
    test_service_prefix_is_vebus()
    print("All 032 tests passed.")
