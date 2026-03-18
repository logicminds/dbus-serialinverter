# -*- coding: utf-8 -*-
"""
Shared pytest fixtures and session-scope stubs for dbus-serialinverter tests.

Strategy:
  - All VenusOS / D-Bus / pymodbus packages are stubbed with sys.modules.setdefault
    so this file is idempotent alongside the per-file setdefault calls in test_001–004.
  - A single mutable utils_stub is installed in sys.modules["utils"]. Tests that need
    different constant values mutate attributes on this object and restore them in a
    finally block (or use the save/restore pattern shown below).
  - Production modules imported after conftest loads automatically get these stubs.
"""

import sys
import os
import types
import logging
import unittest.mock as mock

import pytest

# ── Path setup ────────────────────────────────────────────────────────────────

_DRIVER_DIR = os.path.join(os.path.dirname(__file__), "..", "etc", "dbus-serialinverter")
if _DRIVER_DIR not in sys.path:
    sys.path.insert(0, _DRIVER_DIR)

# ── VenusOS / D-Bus stubs ─────────────────────────────────────────────────────

for _mod in ["dbus", "gi", "gi.repository", "gi.repository.GLib"]:
    sys.modules.setdefault(_mod, types.ModuleType(_mod))


class _VeDbusService:
    """Dict-backed stub for VeDbusService. Supports add_path / get / set."""

    def __init__(self, *args, **kwargs):
        self._store = {}

    def add_path(self, path, value=None, writeable=False, gettextcallback=None):
        self._store[path] = value

    def __getitem__(self, path):
        return self._store.get(path)

    def __setitem__(self, path, value):
        self._store[path] = value


_vedbus_mod = sys.modules.setdefault("vedbus", types.ModuleType("vedbus"))
_vedbus_mod.VeDbusService = _VeDbusService

_settings_mod = sys.modules.setdefault("settingsdevice", types.ModuleType("settingsdevice"))
_settings_mod.SettingsDevice = type(
    "SettingsDevice", (), {"__init__": lambda self, *a, **kw: None}
)

# ── pymodbus stubs ────────────────────────────────────────────────────────────

for _mod in ["pymodbus", "pymodbus.client", "pymodbus.constants", "pymodbus.payload"]:
    sys.modules.setdefault(_mod, types.ModuleType(_mod))


class _FakeDecoder:
    """Minimal BinaryPayloadDecoder substitute. Uses registers[0] as the raw value."""

    def __init__(self, value=0):
        self._value = value

    def decode_16bit_uint(self):
        return int(self._value)

    def decode_32bit_uint(self):
        return int(self._value)

    def decode_32bit_float(self):
        return float(self._value)

    def decode_string(self, n):
        return b"teststr "


class _FakeBinaryPayloadDecoder:
    @classmethod
    def fromRegisters(cls, registers, endian):
        val = registers[0] if registers else 0
        return _FakeDecoder(val)


sys.modules["pymodbus.payload"].BinaryPayloadDecoder = _FakeBinaryPayloadDecoder
sys.modules["pymodbus.constants"].Endian = type("Endian", (), {"Big": 0, "Little": 1})()
sys.modules["pymodbus.client"].ModbusSerialClient = mock.MagicMock

# ── utils stub ────────────────────────────────────────────────────────────────
# Single mutable object — tests mutate attributes then restore them.
# Do NOT replace sys.modules["utils"] from test files; mutate this object instead.

_utils_stub = types.ModuleType("utils")
_utils_stub.logger = logging.getLogger("SerialInverterTest")
_utils_stub.INVERTER_TYPE = "Dummy"
_utils_stub.INVERTER_MAX_AC_POWER = 800.0
_utils_stub.INVERTER_PHASE = "L1"
_utils_stub.INVERTER_POLL_INTERVAL = 1000
_utils_stub.INVERTER_POSITION = 1
_utils_stub.PUBLISH_CONFIG_VALUES = 0
_utils_stub.DRIVER_VERSION = "0.1"
_utils_stub.DRIVER_SUBVERSION = ".1"
_utils_stub.publish_config_variables = lambda *a: None

sys.modules["utils"] = _utils_stub


# ── Shared helpers (module-level, importable by test files) ───────────────────

class FakeLoop:
    """Stub for the GLib mainloop. Tracks whether quit() was called."""

    def __init__(self):
        self.quit_called = False

    def quit(self):
        self.quit_called = True


def make_modbus_result(registers, is_error=False):
    """Return a mock Modbus read result suitable for passing to BinaryPayloadDecoder."""
    result = mock.MagicMock()
    result.isError.return_value = is_error
    result.registers = registers
    return result


def make_modbus_error():
    """Return a mock Modbus result whose isError() returns True."""
    result = mock.MagicMock()
    result.isError.return_value = True
    result.registers = []
    return result


# ── pytest fixtures ───────────────────────────────────────────────────────────

@pytest.fixture
def fake_loop():
    """Fresh FakeLoop for each test."""
    return FakeLoop()


@pytest.fixture
def fake_dbus_service():
    """VeDbusService stub with common paths pre-seeded."""
    svc = _VeDbusService()
    # publish_dbus() reads /UpdateIndex via __getitem__ to increment it
    svc._store["/UpdateIndex"] = 0
    # publish_inverter() reads /Ac/PowerLimit to populate power_limit
    svc._store["/Ac/PowerLimit"] = 800.0
    return svc


@pytest.fixture
def modbus_mock():
    """
    MagicMock substitute for ModbusSerialClient.

    Default behaviour:
      - connect() returns True
      - read_input_registers() returns a result with registers=[0] and isError()=False
      - write_registers() returns a result with isError()=False

    Tests can override return values:
      modbus_mock.connect.return_value = False
      modbus_mock.read_input_registers.return_value = make_modbus_result([500])
    """
    client = mock.MagicMock()
    client.connect.return_value = True
    client.read_input_registers.return_value = make_modbus_result([0])
    client.write_registers.return_value = make_modbus_result([0])
    return client
