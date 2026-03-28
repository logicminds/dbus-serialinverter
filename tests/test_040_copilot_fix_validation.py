"""Test 040: Validates the three fixes from the Copilot PR review.

Fix 1 (modbus_inverter.py): _read_batch() treats truncated Modbus responses as failures.
Fix 2 (samlex.py):          _read_group() catches ValueError/IndexError and returns None.
Fix 3 (samlex.py):          test_connection() catches ValueError from _reg(), returns False.
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


# ── Helpers ───────────────────────────────────────────────────────────────────

def _full_config(identity_reg=200, identity_val=42):
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
    cfg.set("SAMLEX_REGISTERS", "REG_IDENTITY", str(identity_reg))
    cfg.set("SAMLEX_REGISTERS", "IDENTITY_VALUE", str(identity_val))
    return cfg


def _make_samlex(client=None):
    s = Samlex.__new__(Samlex)
    Inverter.__init__(s, port="/dev/null", baudrate=9600, slave=1)
    s.type = "Samlex"
    s.energy_data["dc"]["charge_state"] = None
    if client is None:
        client = mock.MagicMock()
        client.is_socket_open.return_value = True
    s.client = client
    return s


def _connected_client(registers=None, is_error=False):
    """Return a client whose reads succeed with the given register list."""
    client = mock.MagicMock()
    client.is_socket_open.return_value = True
    res = mock.MagicMock()
    res.isError.return_value = is_error
    res.registers = registers if registers is not None else []
    client.read_holding_registers.return_value = res
    return client


# ── Fix 1: _read_batch() truncated response ───────────────────────────────────

def test_read_batch_returns_false_on_truncated_response():
    """_read_batch must return (False, []) when response has fewer registers than requested."""
    s = _make_samlex(_connected_client(registers=[10]))  # only 1 register, but we ask for 3
    ok, regs = s._read_batch(address=100, count=3)
    assert ok is False
    assert regs == []


def test_read_batch_returns_true_on_exact_count():
    """_read_batch must return (True, regs) when response length matches count."""
    s = _make_samlex(_connected_client(registers=[1, 2, 3]))
    ok, regs = s._read_batch(address=100, count=3)
    assert ok is True
    assert regs == [1, 2, 3]


def test_read_batch_returns_true_when_response_exceeds_count():
    """_read_batch must not reject a response longer than count (device may pad)."""
    s = _make_samlex(_connected_client(registers=[1, 2, 3, 4, 5]))
    ok, regs = s._read_batch(address=100, count=3)
    assert ok is True


# ── Fix 2: _read_group() catches ValueError / IndexError ─────────────────────

def test_read_group_returns_none_on_value_error_from_reg():
    """_read_group must return None when _reg() raises ValueError (out-of-range address)."""
    utils_stub.config = _full_config()
    s = _make_samlex(_connected_client(registers=[100, 200, 300]))

    # Override _reg to raise ValueError for one of the keys
    original_reg = s._reg
    def bad_reg(key):
        if key == "REG_AC_OUT_VOLTAGE":
            raise ValueError("Register out of range")
        return original_reg(key)

    with mock.patch.object(s, "_reg", side_effect=bad_reg):
        result = s._read_group(["REG_AC_OUT_VOLTAGE", "REG_AC_OUT_CURRENT", "REG_AC_OUT_POWER"])

    assert result is None


def test_read_group_returns_none_on_index_error():
    """_read_group must return None when indexing raises IndexError (truncated batch)."""
    utils_stub.config = _full_config()
    # Registers 100, 101, 102 — batch returns only 1 value so indexing [1], [2] fails.
    # But _read_batch now guards this; test that _read_group handles it even if it slips through.
    s = _make_samlex()

    def short_read_batch(address, count):
        return True, []  # simulate caller receiving empty list despite ok=True

    with mock.patch.object(s, "_read_batch", side_effect=short_read_batch):
        result = s._read_group(["REG_AC_OUT_VOLTAGE", "REG_AC_OUT_CURRENT"])

    assert result is None


def test_read_group_returns_none_on_failed_batch():
    """_read_group must propagate None when _read_batch returns (False, [])."""
    utils_stub.config = _full_config()
    s = _make_samlex()

    with mock.patch.object(s, "_read_batch", return_value=(False, [])):
        result = s._read_group(["REG_AC_OUT_VOLTAGE", "REG_AC_OUT_CURRENT"])

    assert result is None


# ── Fix 3: test_connection() catches ValueError from _reg() ───────────────────

def test_connection_returns_false_when_reg_raises_value_error():
    """test_connection() must return False (not crash) when _reg() raises ValueError."""
    utils_stub.config = _full_config()
    s = _make_samlex(_connected_client(registers=[42]))

    with mock.patch.object(s, "_reg", side_effect=ValueError("out of range")):
        result = s.test_connection()

    assert result is False


def test_connection_does_not_propagate_value_error():
    """ValueError from _reg() must be swallowed, not raised to the caller."""
    utils_stub.config = _full_config()
    s = _make_samlex(_connected_client(registers=[42]))

    with mock.patch.object(s, "_reg", side_effect=ValueError("bad config")):
        try:
            s.test_connection()
        except ValueError:
            raise AssertionError("test_connection() must not propagate ValueError")


if __name__ == "__main__":
    test_read_batch_returns_false_on_truncated_response()
    test_read_batch_returns_true_on_exact_count()
    test_read_batch_returns_true_when_response_exceeds_count()
    test_read_group_returns_none_on_value_error_from_reg()
    test_read_group_returns_none_on_index_error()
    test_read_group_returns_none_on_failed_batch()
    test_connection_returns_false_when_reg_raises_value_error()
    test_connection_does_not_propagate_value_error()
    print("All 040 tests passed.")
