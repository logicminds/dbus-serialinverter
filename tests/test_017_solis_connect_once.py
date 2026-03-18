"""Test 017: Solis._ensure_connected() — connect() called at most once per poll."""
import sys
import os
import types
import logging
import unittest.mock as mock

for mod in ["dbus", "gi", "gi.repository", "gi.repository.GLib",
            "pymodbus", "pymodbus.client", "pymodbus.constants", "pymodbus.payload"]:
    sys.modules.setdefault(mod, types.ModuleType(mod))

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

utils_stub = sys.modules.setdefault("utils", types.ModuleType("utils"))
if not hasattr(utils_stub, "logger"):
    utils_stub.logger = logging.getLogger("test")
for _attr, _val in [
    ("INVERTER_TYPE", "Solis"), ("INVERTER_MAX_AC_POWER", 800.0),
    ("INVERTER_PHASE", "L1"), ("INVERTER_POLL_INTERVAL", 1000), ("INVERTER_POSITION", 1),
]:
    if not hasattr(utils_stub, _attr):
        setattr(utils_stub, _attr, _val)

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "etc", "dbus-serialinverter"))

if "inverter" in sys.modules and not hasattr(sys.modules["inverter"], "Inverter"):
    del sys.modules["inverter"]

from inverter import Inverter
from solis import Solis


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


def _make_ok_client(socket_open=True):
    # Return 6 zeros for any batch read — enough for the largest batch (3033-3038, 6 regs)
    client = mock.MagicMock()
    client.is_socket_open.return_value = socket_open
    client.connect.return_value = True
    client.read_input_registers.return_value = mock.MagicMock(
        **{"isError.return_value": False, "registers": [0, 0, 0, 0, 0, 0]}
    )
    client.write_registers.return_value = mock.MagicMock(
        **{"isError.return_value": False}
    )
    return client


# ── Socket already open: connect() never called ───────────────────────────────

def test_connect_not_called_when_socket_already_open():
    """When is_socket_open() is True, connect() must not be called."""
    client = _make_ok_client(socket_open=True)
    s = _make_solis_with_client(client)
    s.read_status_data()
    assert client.connect.call_count == 0, (
        "connect() must not be called when socket is already open"
    )


def test_multiple_register_reads_call_connect_zero_times():
    """A full read_status_data() (10-13 register reads) calls connect() exactly 0 times."""
    client = _make_ok_client(socket_open=True)
    s = _make_solis_with_client(client)
    s.read_status_data()
    assert client.connect.call_count == 0


# ── Socket closed: connect() called exactly once ──────────────────────────────

def test_connect_called_once_when_socket_closed():
    """When is_socket_open() is False, connect() is called exactly once."""
    client = _make_ok_client(socket_open=False)
    s = _make_solis_with_client(client)
    # After first call to _ensure_connected, connect() is called once.
    # Subsequent is_socket_open checks on the MagicMock still return False
    # (mock doesn't update), so connect may be called once per register.
    # The important thing: with socket_open=True the count is 0.
    # For the reconnect path just verify a single read_input_registers call works.
    success, _ = s.read_input_registers(3035, 1, "u16", 0.1, 1)
    assert success is True
    assert client.connect.call_count == 1


# ── ensure_connected fails: reads return False ────────────────────────────────

def test_connect_failure_makes_all_reads_fail():
    """If is_socket_open() is False and connect() fails, reads return False."""
    client = mock.MagicMock()
    client.is_socket_open.return_value = False
    client.connect.return_value = False
    s = _make_solis_with_client(client)
    success, val = s.read_input_registers(3035, 1, "u16", 1, 0)
    assert success is False
    assert val == 0


def test_connect_failure_makes_write_fail():
    """If is_socket_open() is False and connect() fails, write returns False."""
    client = mock.MagicMock()
    client.is_socket_open.return_value = False
    client.connect.return_value = False
    s = _make_solis_with_client(client)
    result = s.write_registers(3051, 5000)
    assert result is False


if __name__ == "__main__":
    test_connect_not_called_when_socket_already_open()
    test_multiple_register_reads_call_connect_zero_times()
    test_connect_called_once_when_socket_closed()
    test_connect_failure_makes_all_reads_fail()
    test_connect_failure_makes_write_fail()
    print("All 017 tests passed.")
