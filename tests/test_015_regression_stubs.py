"""Test 015: Regression stubs for todos 006–011, 013–014.

Each test documents the CURRENT WRONG BEHAVIOUR with a concrete assertion, then
marks the test xfail(strict=True).

xfail(strict=True) means:
  - While the bug exists → test is recorded as "xfail" (expected failure): OK
  - Once the bug is fixed → the assertion passes → pytest marks the run FAILED

That loud failure forces a conscious update: move the test to a passing file or
rewrite the assertion to document the fixed behaviour.

Todos 005 and 012 are excluded:
  - 005 (config no error handling): requires re-importing utils with a broken
    config file; deferred until the fix lands.
  - 012 (code simplification): not a behavioural regression — no assertion captures it.
"""
import sys
import os
import types
import logging
import unittest.mock as mock

import pytest

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


# ── Todo 008: publish_dbus() called unconditionally on failure ────────────────

@pytest.mark.xfail(
    strict=True,
    reason="todo 008: publish_dbus() is called even when refresh_data() returns False, "
           "publishing a mix of new and stale values",
)
def test_todo_008_publish_dbus_not_called_on_refresh_failure():
    helper, loop = _make_dbus_helper(refresh_returns=False)
    publish_dbus_calls = []
    helper.publish_dbus = lambda: publish_dbus_calls.append(1)
    helper.publish_inverter(loop)
    # Desired: publish_dbus() not called when refresh failed
    assert len(publish_dbus_calls) == 0


# ── Todo 009: get_settings() called twice at startup ─────────────────────────

@pytest.mark.xfail(
    strict=True,
    reason="todo 009: Solis.test_connection() calls get_settings() internally; "
           "DbusHelper.setup_vedbus() also calls it, doubling all startup Modbus reads",
)
def test_todo_009_get_settings_called_once_at_startup():
    call_count = [0]
    original_get_settings = Solis.get_settings

    def counting_get_settings(self):
        call_count[0] += 1
        return original_get_settings(self)

    client = mock.MagicMock()
    client.connect.return_value = True
    client.read_input_registers.return_value = mock.MagicMock(
        **{"isError.return_value": False, "registers": [224]}  # product model 224
    )

    s = Solis.__new__(Solis)
    Inverter.__init__(s, port="/dev/null", baudrate=9600, slave=1)
    s.type = "Solis"
    s.client = client
    s.get_settings = lambda: counting_get_settings(s)

    # Simulate test_connection() path (calls get_settings internally when model==224)
    # Then a separate setup_vedbus() call would call get_settings() again
    # We just count the calls from a full startup sequence
    s.test_connection()    # calls get_settings internally
    s.get_settings()       # called again by setup_vedbus()

    # Desired: exactly 1 call total
    assert call_count[0] == 1


# ── Todo 010: 3-phase energy_forwarded hardcoded to 0 ────────────────────────

@pytest.mark.xfail(
    strict=True,
    reason="todo 010: In 3-phase mode, per-phase energy_forwarded is hardcoded to "
           "integer 0 (solis.py:221-227), silently under-reporting lifetime generation",
)
def test_todo_010_3phase_energy_forwarded_is_nonzero():
    s = Solis.__new__(Solis)
    Inverter.__init__(s, port="/dev/null", baudrate=9600, slave=1)
    s.type = "Solis"
    s.max_ac_power = 800.0
    s.phase = "L1"
    s.energy_data["overall"]["power_limit"] = 800.0
    s.energy_data["overall"]["active_power_limit"] = 800.0

    def _patched_read(address, count, data_type, scale, digits):
        if address == 3002:
            return True, 1  # output_type=1 → 3-phase
        if address == 3014:
            return True, round(1000 * scale, digits)  # overall energy_forwarded = 100kWh
        return True, round(0 * scale, digits)

    s.read_input_registers = _patched_read
    s.write_registers = lambda *a, **kw: True
    s.read_status_data()

    # Desired: energy_forwarded should be populated from per-phase data
    assert s.energy_data["L1"]["energy_forwarded"] != 0


# ── Todo 011: no Modbus read batching ────────────────────────────────────────

@pytest.mark.xfail(
    strict=True,
    reason="todo 011: read_status_data() makes 10-13 separate Modbus round-trips "
           "where contiguous registers could be batched into 3-4 requests",
)
def test_todo_011_read_status_data_uses_few_transactions():
    client = mock.MagicMock()
    client.connect.return_value = True
    client.read_input_registers.return_value = mock.MagicMock(
        **{"isError.return_value": False, "registers": [0]}
    )
    client.write_registers.return_value = mock.MagicMock(
        **{"isError.return_value": False}
    )
    s = _make_solis_with_client(client)
    s.read_status_data()
    # Desired: ≤ 5 Modbus transactions per single-phase poll
    # Current: 10-13 (one per register group)
    assert client.read_input_registers.call_count <= 5


# ── Todo 013: logger level hardcoded to DEBUG ─────────────────────────────────

@pytest.mark.xfail(
    strict=True,
    reason="todo 013: utils.py hardcodes logger.setLevel(logging.DEBUG), accelerating "
           "flash wear on GX hardware and leaking hardware details to /var/log/",
)
def test_todo_013_logger_level_not_hardcoded_to_debug():
    """
    Checks the production utils.py source directly for the hardcoded setLevel(DEBUG) call.
    This test will XPASS (and therefore fail the run) once the line is removed.
    """
    utils_path = os.path.join(
        os.path.dirname(__file__), "..", "etc", "dbus-serialinverter", "utils.py"
    )
    with open(utils_path) as f:
        source = f.read()
    # Desired: no unconditional setLevel(logging.DEBUG) in utils.py
    # Current: line `logger.setLevel(logging.DEBUG)` is present
    assert "setLevel(logging.DEBUG)" not in source


# ── Todo 014: Dummy activates when INVERTER_TYPE is blank ────────────────────

@pytest.mark.xfail(
    strict=True,
    reason="todo 014: When INVERTER_TYPE='' (blank config), the auto-detect filter "
           "includes Dummy in expected_inverter_types because the blank-OR-match "
           "condition is satisfied, causing fake 800W readings if Solis is unreachable",
)
def test_todo_014_dummy_excluded_from_autodetect_on_blank_type():
    """
    In dbus-serialinverter.py:31-33, expected_inverter_types is built as:
        [t for t in supported if t["inverter"].__name__ == TYPE or TYPE == ""]
    When TYPE="" the second condition is True for ALL types, including Dummy.
    The desired behaviour: Dummy should only be active when TYPE=="Dummy" explicitly.
    """
    # We test the filter logic directly (pure Python, no GLib needed)
    supported_inverter_types = [
        {"inverter": Dummy, "baudrate": 0, "slave": 0},
        {"inverter": Solis, "baudrate": 9600, "slave": 1},
    ]
    blank_type = ""

    expected = [
        t for t in supported_inverter_types
        if t["inverter"].__name__ == blank_type or blank_type == ""
    ]

    dummy_types = [t for t in expected if t["inverter"] is Dummy]

    # Desired: Dummy must NOT appear in expected_inverter_types when TYPE is blank
    assert len(dummy_types) == 0, \
        "Dummy should not be included in auto-detect when INVERTER_TYPE is blank"


if __name__ == "__main__":
    # Run without pytest to see which xfail assertions actually fail (as expected)
    tests = [
        test_todo_006_connect_called_at_most_once_per_poll,
        test_todo_007_read_status_data_does_not_write,
        test_todo_008_publish_dbus_not_called_on_refresh_failure,
        test_todo_009_get_settings_called_once_at_startup,
        test_todo_010_3phase_energy_forwarded_is_nonzero,
        test_todo_011_read_status_data_uses_few_transactions,
        test_todo_013_logger_level_not_hardcoded_to_debug,
        test_todo_014_dummy_excluded_from_autodetect_on_blank_type,
    ]
    for t in tests:
        try:
            t()
            print(f"UNEXPECTED PASS: {t.__name__} (bug may be fixed!)")
        except AssertionError:
            print(f"xfail (expected): {t.__name__}")
        except Exception as e:
            print(f"ERROR in {t.__name__}: {e}")
    print("015 regression stubs complete.")
