"""Test 015: Regression stubs for todos 006–011, 013–014.

All xfail stubs have been resolved — bugs 006–011, 013, 014 are fixed.

Todos 005 and 012 were excluded from the start:
  - 005 (config no error handling): tested in test_016_config_error_handling.py
  - 012 (code simplification): not a behavioural regression — no assertion captures it.

This file is retained for its shared helpers used by other tests.
"""
import sys
import os
import types
import logging
import unittest.mock as mock

# ── Stub setup (idempotent alongside conftest.py) ─────────────────────────────

for _mod in ["dbus", "gi", "gi.repository", "gi.repository.GLib",
             "pymodbus", "pymodbus.client", "pymodbus.constants", "pymodbus.payload",
             "vedbus", "settingsdevice"]:
    sys.modules.setdefault(_mod, types.ModuleType(_mod))

_vedbus = sys.modules["vedbus"]
if not hasattr(_vedbus, "VeDbusService"):
    _vedbus.VeDbusService = type("VeDbusService", (), {"__init__": lambda self, *a, **kw: None})

_settings = sys.modules["settingsdevice"]
if not hasattr(_settings, "SettingsDevice"):
    _settings.SettingsDevice = type("SettingsDevice", (), {"__init__": lambda self, *a, **kw: None})

_payload = sys.modules["pymodbus.payload"]
if not hasattr(_payload, "BinaryPayloadDecoder"):
    class _FakeDecoder:
        def __init__(self, v=0): self._v = v
        def decode_16bit_uint(self): return int(self._v)
        def decode_32bit_uint(self): return int(self._v)
        def decode_32bit_float(self): return float(self._v)
        def decode_string(self, n): return b"teststr "
    class _FakeBPD:
        @classmethod
        def fromRegisters(cls, regs, endian): return _FakeDecoder(regs[0] if regs else 0)
    _payload.BinaryPayloadDecoder = _FakeBPD

_constants = sys.modules["pymodbus.constants"]
if not hasattr(_constants, "Endian"):
    _constants.Endian = type("Endian", (), {"Big": 0})()

sys.modules["pymodbus.client"].ModbusSerialClient = mock.MagicMock

_utils = sys.modules.setdefault("utils", types.ModuleType("utils"))
if not hasattr(_utils, "logger"):
    _utils.logger = logging.getLogger("test")
for _attr, _val in [
    ("INVERTER_TYPE", "Dummy"), ("INVERTER_MAX_AC_POWER", 800.0),
    ("INVERTER_PHASE", "L1"), ("INVERTER_POLL_INTERVAL", 1000),
    ("INVERTER_POSITION", 1), ("PUBLISH_CONFIG_VALUES", 0),
    ("DRIVER_VERSION", "0.1"), ("DRIVER_SUBVERSION", ".1"),
    ("publish_config_variables", lambda *a: None),
]:
    if not hasattr(_utils, _attr):
        setattr(_utils, _attr, _val)

# Note: "inverter" is NOT stubbed here — we need the real Inverter base class.
# If a prior test file's module body installed a stub, clear it first so the
# real inverter.py is imported from etc/dbus-serialinverter/.
if "inverter" in sys.modules and not hasattr(sys.modules["inverter"], "Inverter"):
    del sys.modules["inverter"]

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "etc", "dbus-serialinverter"))

from inverter import Inverter
from solis import Solis
from dummy import Dummy
import dbushelper


# ── Shared helpers ────────────────────────────────────────────────────────────

def _make_solis_with_client(client):
    s = Solis.__new__(Solis)
    Inverter.__init__(s, port="/dev/null", baudrate=9600, slave=1)
    s.type = "Solis"
    s.max_ac_power = 800.0
    s.phase = "L1"
    s.energy_data["overall"]["power_limit"] = 800.0
    s.energy_data["overall"]["active_power_limit"] = 800.0
    s.client = client
    return s


def _make_solis_all_reads_ok(register_value=0):
    """Solis with all register reads returning (True, register_value) scaled."""
    client = mock.MagicMock()
    client.connect.return_value = True
    client.read_input_registers.return_value = mock.MagicMock(
        **{"isError.return_value": False, "registers": [register_value]}
    )
    client.write_registers.return_value = mock.MagicMock(
        **{"isError.return_value": False}
    )
    s = _make_solis_with_client(client)
    return s


def _make_dbus_helper(refresh_returns):
    class _FakeInverter:
        port = "/dev/null"
        status = 7
        online = True
        poll_interval = 1000
        energy_data = {
            "L1": {"ac_voltage": None, "ac_current": None, "ac_power": None, "energy_forwarded": None},
            "L2": {"ac_voltage": None, "ac_current": None, "ac_power": None, "energy_forwarded": None},
            "L3": {"ac_voltage": None, "ac_current": None, "ac_power": None, "energy_forwarded": None},
            "overall": {"ac_power": None, "energy_forwarded": None, "power_limit": 800.0, "active_power_limit": None},
        }
        def refresh_data(self):
            return refresh_returns

    class _FakeDbusService:
        def __init__(self):
            self._store = {"/UpdateIndex": 0, "/Ac/PowerLimit": 800.0}
        def __getitem__(self, p): return self._store.get(p)
        def __setitem__(self, p, v): self._store[p] = v

    class _FakeLoop:
        quit_called = False
        def quit(self): self.quit_called = True

    helper = dbushelper.DbusHelper.__new__(dbushelper.DbusHelper)
    helper.inverter = _FakeInverter()
    helper._dbusservice = _FakeDbusService()
    helper.error_count = 0
    return helper, _FakeLoop()


if __name__ == "__main__":
    print("015: all stubs resolved — no xfail tests remain.")
