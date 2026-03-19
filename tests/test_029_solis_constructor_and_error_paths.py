"""Test 029: Solis uncovered lines — __init__, error branches in all read methods.

Missing lines:
  25-29     Solis.__init__ body
  45-47     test_connection() IOError path
  73-74     get_settings() serial read error → return False
  90-91     refresh_data() body
  160-161   _read_batch() when connection fails
  188       read_status_data batch 2 error
  205       read_status_data batch 3 error (single-phase)
  222       read_status_data batch 3 error (3-phase)
  259       read_status_data batch 5 error
"""
import sys
import os
import types
import logging
import unittest.mock as mock

for _mod in ["dbus", "gi", "gi.repository", "gi.repository.GLib",
             "pymodbus", "pymodbus.client", "pymodbus.constants", "pymodbus.payload"]:
    sys.modules.setdefault(_mod, types.ModuleType(_mod))

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
    _constants.Endian = type("Endian", (), {"Big": 0, "Little": 1})()

sys.modules["pymodbus.client"].ModbusSerialClient = mock.MagicMock

_utils = sys.modules.setdefault("utils", types.ModuleType("utils"))
if not hasattr(_utils, "logger"):
    _utils.logger = logging.getLogger("test")
for _attr, _val in [
    ("INVERTER_TYPE", "Solis"), ("INVERTER_MAX_AC_POWER", 800.0),
    ("INVERTER_PHASE", "L1"), ("INVERTER_POLL_INTERVAL", 1000), ("INVERTER_POSITION", 1),
]:
    if not hasattr(_utils, _attr):
        setattr(_utils, _attr, _val)

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "etc", "dbus-serialinverter"))

if "inverter" in sys.modules and not hasattr(sys.modules["inverter"], "Inverter"):
    del sys.modules["inverter"]

from inverter import Inverter
from solis import Solis


# ── Helpers ───────────────────────────────────────────────────────────────────

def _ok_result(registers):
    r = mock.MagicMock()
    r.isError.return_value = False
    r.registers = registers
    return r


def _err_result():
    r = mock.MagicMock()
    r.isError.return_value = True
    r.registers = []
    return r


def _make_solis(client):
    s = Solis.__new__(Solis)
    Inverter.__init__(s, port="/dev/null", baudrate=9600, slave=1)
    s.type = "Solis"
    s.max_ac_power = 800.0
    s.phase = "L1"
    s.client = client
    return s


def _connected_client():
    c = mock.MagicMock()
    c.is_socket_open.return_value = True
    c.read_input_registers.return_value = _ok_result([0])
    c.write_registers.return_value = _ok_result([0])
    return c


# ── Solis.__init__ (lines 25-29) ─────────────────────────────────────────────

def test_solis_constructor_sets_type():
    """Solis() via normal constructor covers __init__ body."""
    s = Solis(port="/dev/null", baudrate=9600, slave=1)
    assert s.type == "Solis"


def test_solis_constructor_sets_port():
    s = Solis(port="/dev/null", baudrate=9600, slave=1)
    assert s.port == "/dev/null"


def test_solis_constructor_calls_super_init():
    """Super().__init__ must populate energy_data."""
    s = Solis(port="/dev/null", baudrate=9600, slave=1)
    assert "L1" in s.energy_data
    assert "overall" in s.energy_data


def test_solis_constructor_creates_modbus_client():
    """ModbusSerialClient must be instantiated in __init__."""
    s = Solis(port="/dev/null", baudrate=9600, slave=1)
    assert s.client is not None


# ── test_connection() IOError path (lines 45-47) ────────────────────────────

def test_test_connection_returns_false_on_ioerror():
    """IOError during register read → return False (line 45-47)."""
    c = mock.MagicMock()
    c.is_socket_open.return_value = True
    c.read_input_registers.side_effect = IOError("serial port error")
    s = _make_solis(c)
    result = s.test_connection()
    assert result is False


# ── get_settings() serial read error → return False (lines 73-74) ───────────

def test_get_settings_returns_false_when_serial_read_fails():
    """Error reading serial registers → get_settings returns False."""
    c = _connected_client()
    # First call succeeds (hardware version), second (serial read) errors
    c.read_input_registers.side_effect = [
        _ok_result([3000]),   # read_input_registers for hardware_version (register 3000)
        _err_result(),        # serial number read (register 3060)
    ]
    s = _make_solis(c)
    result = s.get_settings()
    assert result is False


# ── refresh_data() (lines 90-91) ─────────────────────────────────────────────

def test_refresh_data_calls_read_status_data():
    """refresh_data delegates to read_status_data and returns its result."""
    s = _make_solis(_connected_client())
    calls = []
    s.read_status_data = lambda: calls.append(1) or True
    result = s.refresh_data()
    assert len(calls) == 1
    assert result is True


def test_refresh_data_propagates_false():
    s = _make_solis(_connected_client())
    s.read_status_data = lambda: False
    assert s.refresh_data() is False


# ── _read_batch() no connection (lines 160-161) ──────────────────────────────

def test_read_batch_returns_false_when_not_connected():
    """_read_batch returns (False, []) when _ensure_connected fails."""
    c = mock.MagicMock()
    c.is_socket_open.return_value = False
    c.connect.return_value = False
    s = _make_solis(c)
    ok, regs = s._read_batch(3002, 4)
    assert ok is False
    assert regs == []


# ── read_status_data error paths ─────────────────────────────────────────────

def _make_batch_solis(batch_results):
    """
    Create a Solis where each _read_batch call returns successive items
    from batch_results. Each element is either (True, [regs]) or (False, []).
    """
    c = _connected_client()
    s = _make_solis(c)
    results = iter(batch_results)
    s._read_batch = lambda addr, count: next(results)
    return s


def test_read_status_data_batch2_error_sets_error(monkeypatch):
    """Batch 2 (energy forward) error → read_status_data returns False (line 188)."""
    s = _make_batch_solis([
        (True, [0, 0, 100, 0]),    # batch 1: output_type=0, ac_power via regs[2:4]
        (False, []),                # batch 2: energy_forwarded error → line 188
        (True, [2300, 0, 0, 10]),   # batch 3: voltage/current
        (True, [3]),                # batch 4: status
        (True, [100]),              # batch 5: power limit
    ])
    result = s.read_status_data()
    assert result is False


def test_read_status_data_batch3_single_phase_error(monkeypatch):
    """Batch 3 single-phase error → read_status_data returns False (line 205)."""
    s = _make_batch_solis([
        (True, [0, 0, 100, 0]),    # batch 1: single-phase (output_type=0)
        (True, [10]),               # batch 2: energy_forwarded OK
        (False, []),                # batch 3: single-phase voltage/current error → line 205
        (True, [3]),                # batch 4: status
        (True, [100]),              # batch 5: power limit
    ])
    result = s.read_status_data()
    assert result is False


def test_read_status_data_batch3_3phase_error(monkeypatch):
    """Batch 3 3-phase error → read_status_data returns False (line 222)."""
    s = _make_batch_solis([
        (True, [1, 0, 100, 0]),    # batch 1: 3-phase (output_type=1)
        (True, [10]),               # batch 2: energy_forwarded OK
        (False, []),                # batch 3: 3-phase voltage/current error → line 222
        (True, [3]),                # batch 4: status
        (True, [100]),              # batch 5: power limit
    ])
    result = s.read_status_data()
    assert result is False


def test_read_status_data_batch5_error(monkeypatch):
    """Batch 5 (power limit read) error → read_status_data returns False (line 259)."""
    s = _make_batch_solis([
        (True, [0, 0, 100, 0]),    # batch 1: single-phase
        (True, [10]),               # batch 2: energy OK
        (True, [2300, 0, 0, 10]),  # batch 3: voltage/current OK
        (True, [3]),                # batch 4: status OK
        (False, []),                # batch 5: power limit error → line 259
    ])
    result = s.read_status_data()
    assert result is False


if __name__ == "__main__":
    test_solis_constructor_sets_type()
    test_solis_constructor_sets_port()
    test_solis_constructor_calls_super_init()
    test_solis_constructor_creates_modbus_client()
    test_test_connection_returns_false_on_ioerror()
    test_get_settings_returns_false_when_serial_read_fails()
    test_refresh_data_calls_read_status_data()
    test_refresh_data_propagates_false()
    test_read_batch_returns_false_when_not_connected()
    print("All 029 tests passed (monkeypatch tests skipped in __main__).")
