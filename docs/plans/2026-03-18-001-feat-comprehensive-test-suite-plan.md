---
title: "feat: Comprehensive Test Suite for dbus-serialinverter"
type: feat
status: active
date: 2026-03-18
origin: docs/brainstorms/2026-03-18-test-suite-requirements.md
---

# feat: Comprehensive Test Suite for dbus-serialinverter

## Overview

Expand the test suite from 4 P1-fix tests to full behavioral coverage of every major module. Add a shared `conftest.py` fixture layer, 10 new test files covering R2–R11, and a regression stub file (R12) that documents current known-broken behaviors as `xfail(strict=True)` — so they surface loudly in CI when code is fixed without a test update.

The suite must run in under 10 seconds on a machine with no VenusOS packages, no D-Bus, and no serial hardware.

## Problem Statement / Motivation

The driver's core behaviors — D-Bus publishing, error recovery, inverter driver logic, Modbus handling — are entirely untested beyond the 4 P1 fixes. Any future change to `dbushelper.py`, `dummy.py`, `solis.py`, or `inverter.py` has no safety net. The 10 open todos (005–014) represent known bugs that need regression guards before they can be safely fixed. (see origin: docs/brainstorms/2026-03-18-test-suite-requirements.md)

## Technical Approach

### Architecture

**Module isolation strategy (CRITICAL — resolves brainstorm deferred question)**

The established per-file stub pattern (`sys.modules.setdefault`) is idempotent but does not help when multiple tests need different values for the same module constant (e.g., `utils.INVERTER_TYPE = "Dummy"` vs `""`). The strategy:

1. `conftest.py` installs a **single mutable `utils_stub` object** into `sys.modules["utils"]` at session start. All project modules that import `utils` get a reference to this same object.
2. Tests that need different constant values mutate attributes on the existing stub object and restore them via a function-scoped `utils_config` fixture using `yield`. They do NOT replace `sys.modules["utils"]` with a new object — that would break already-imported modules that hold a reference to the old object.
3. For Solis tests, the `client` attribute is injected directly on the already-constructed `Solis` instance rather than replacing `ModbusSerialClient` in `sys.modules` per-test.

**`conftest.py` session-scope setup (installed once, at module load):**
- `sys.modules.setdefault` for `dbus`, `gi`, `gi.repository`, `gi.repository.GLib`, `vedbus`, `settingsdevice`, `pymodbus`, `pymodbus.client`, `pymodbus.constants`, `pymodbus.payload`
- Install VeDbusService stub class (dict-like, `add_path`/`__getitem__`/`__setitem__`)
- Install SettingsDevice stub
- Install the `utils_stub` mutable module object
- Install pymodbus stubs (`Endian`, `BinaryPayloadDecoder`)
- `sys.path.insert` for `etc/dbus-serialinverter/` (idempotent via `setdefault` above)

**conftest.py pytest fixtures:**
- `fake_loop()` — function-scoped, returns `FakeLoop` with `quit_called` flag
- `fake_dbus_service()` — function-scoped, returns `_VeDbusService` with `/UpdateIndex=0` and `/Ac/PowerLimit=800.0` pre-seeded
- `utils_config(request)` — function-scoped, accepts a param dict of attributes to set on `utils_stub`, yields, then restores originals. Used as indirect fixture where needed.
- `modbus_mock()` — function-scoped, returns a `unittest.mock.MagicMock` pre-configured as a `ModbusSerialClient` substitute with a helper method `configure_register(address, value, data_type)` for setting return values.

**R11 isolation strategy — `get_inverter()` is nested inside `main()`:**

`get_inverter()` closes over `expected_inverter_types` (a module-level computed list) and uses `time.sleep`. Rather than refactoring `dbus-serialinverter.py`, use the test_003 pattern: recreate the retry logic as a standalone helper in the test file, mirror the production logic exactly, and document this explicitly. This keeps production code untouched while providing coverage. Add a note in the test that a future refactor to move `get_inverter()` out of `main()` would allow testing the real implementation directly.

**Modbus mock design (reusable for Solis and future Samlex driver):**

```python
# tests/conftest.py (excerpt)
import unittest.mock as mock

@pytest.fixture
def modbus_mock():
    """MagicMock substitute for ModbusSerialClient. Supports call-count assertions."""
    client = mock.MagicMock()
    client.connect.return_value = True

    def make_register_result(value, is_error=False):
        result = mock.MagicMock()
        result.isError.return_value = is_error
        result.registers = [value]
        return result

    client._make_register_result = make_register_result
    return client
```

Tests inject this mock directly on the Solis instance after construction:
```python
# tests/test_NNN_solis_*.py
solis = Solis.__new__(Solis)
Inverter.__init__(solis, port="/dev/null", baudrate=9600, slave=1)
solis.client = modbus_mock
solis.type = "Solis"
```

**BinaryPayloadDecoder stub** — installed at session scope:
```python
# In conftest.py module body (not a fixture)
class _FakeDecoder:
    def __init__(self, value=0):
        self._value = value
    def decode_16bit_uint(self): return int(self._value)
    def decode_32bit_uint(self): return int(self._value)
    def decode_32bit_float(self): return float(self._value)
    def decode_string(self, n): return b"teststr "

class _FakeBinaryPayloadDecoder:
    _next_value = 0
    @classmethod
    def fromRegisters(cls, registers, endian):
        return _FakeDecoder(registers[0] if registers else 0)

sys.modules["pymodbus.payload"].BinaryPayloadDecoder = _FakeBinaryPayloadDecoder
sys.modules["pymodbus.constants"].Endian = type("Endian", (), {"Big": 0})()
```

### Implementation Phases

#### Phase 1: Shared Fixture Layer

**Files to create:** `tests/conftest.py`

**Deliverables:**
- Session-scope `sys.modules` stubs for all VenusOS/D-Bus/pymodbus packages
- Mutable `utils_stub` module installed in `sys.modules["utils"]`
- `_VeDbusService` stub class (with `add_path`, `__getitem__`, `__setitem__`, `_store` dict)
- `FakeLoop` class
- All pytest fixtures: `fake_loop`, `fake_dbus_service`, `modbus_mock`, `utils_config`
- `sys.path.insert` for `etc/dbus-serialinverter/`

**Verification:** `python -m pytest tests/conftest.py --collect-only` completes without error. Existing tests 001–004 still pass.

**Key implementation note:** `conftest.py` uses `sys.modules.setdefault` for all package stubs (not assignment) so that existing standalone test files remain runnable without pytest (they do their own setdefault calls which become no-ops once conftest has run first under pytest).

---

#### Phase 2: Core Behavioral Tests

**2a. `test_005_inverter_energy_data_init.py`** — covers R2

Tests that `Inverter.__init__` correctly initializes `energy_data`:
- All four keys (`ac_voltage`, `ac_current`, `ac_power`, `energy_forwarded`) exist for L1, L2, L3
- `energy_data['overall']` has `ac_power`, `energy_forwarded`, `power_limit`, `active_power_limit`
- All values default to `None`

```python
# tests/test_005_inverter_energy_data_init.py
def test_all_phase_keys_present():
def test_all_overall_keys_present():
def test_all_values_default_to_none():
```

---

**2b. `test_006_dbushelper_error_counting.py`** — covers R3

Tests `DbusHelper.publish_inverter()` error-counting state machine. Uses `DbusHelper.__new__` + attribute injection (proven pattern from test_004). Uses `fake_loop` and `fake_dbus_service` fixtures.

**Critical boundary assertions:**

| Test function | Input | Expected |
|---|---|---|
| `test_success_resets_error_count` | refresh returns True | `error_count == 0`, `online == True` |
| `test_failure_increments_error_count` | refresh returns False once | `error_count == 1`, `online == True` |
| `test_error_count_9_still_online` | 9 consecutive failures | `online == True`, `quit_called == False` |
| `test_error_count_10_sets_offline` | 10 consecutive failures | `online == False`, `quit_called == False` |
| `test_error_count_59_no_quit` | 59 consecutive failures | `quit_called == False` |
| `test_error_count_60_calls_loop_quit` | 60 consecutive failures | `quit_called == True` |

Helper to drive N failures:
```python
def _run_n_failures(helper, loop, n):
    for _ in range(n):
        helper.publish_inverter(loop)
```

Note: `publish_inverter` calls `publish_dbus()` unconditionally — the fake dbusservice must support all write paths (`__setitem__`). The `/UpdateIndex` path must be pre-seeded to 0 in `fake_dbus_service`.

---

**2c. `test_007_dbushelper_update_index.py`** — covers R4

Tests `DbusHelper.publish_dbus()` UpdateIndex wrap-around. Uses `DbusHelper.__new__` + injection.

```python
# tests/test_007_dbushelper_update_index.py
def test_index_increments_from_zero():    # 0 → 1
def test_index_increments_midrange():     # 100 → 101
def test_index_does_not_wrap_at_254():    # 254 → 255 (no wrap)
def test_index_wraps_at_255():            # 255 → 0 (the actual wrap boundary)
```

The wrap condition is `if index > 255: index = 0`, so index 255 + 1 = 256 > 255 → wraps to 0. Test `test_index_does_not_wrap_at_254` is critical to verify the boundary is at 255 and not earlier.

---

**2d. `test_008_dbushelper_text_formatters.py`** — covers R5

Tests all four formatter methods with exact expected output strings:

```python
# tests/test_008_dbushelper_text_formatters.py
# gettextforkWh: "%.2FkWh" — note: %F is alias for %f in CPython
def test_kwh_formatter_formats_correctly():
    helper = DbusHelper.__new__(DbusHelper)
    assert helper.gettextforkWh(None, 1.5) == "1.50kWh"
    assert helper.gettextforkWh(None, 0.0) == "0.00kWh"

def test_w_formatter_formats_correctly():
    assert helper.gettextforW(None, 230.0) == "230W"
    assert helper.gettextforW(None, 0.0) == "0W"

def test_v_formatter_formats_correctly():
    assert helper.gettextforV(None, 230.0) == "230V"

def test_a_formatter_formats_correctly():
    assert helper.gettextforA(None, 3.5) == "4A"  # rounded to nearest integer

def test_kwh_formatter_raises_on_none():
    """Documents that formatters do not handle None — only called with numeric values."""
    try:
        helper.gettextforkWh(None, None)
        assert False, "Should raise TypeError"
    except TypeError:
        pass
```

**Note on `%F`:** In CPython, `%.2F` is equivalent to `%.2f` (produces lowercase decimal output). The test asserts the actual output `"1.50kWh"` so any silent regression in format handling would fail.

---

**2e. `test_009_dummy_get_settings.py`** — covers R6

Tests `Dummy.get_settings()` with TYPE matching and non-matching. Mutates `utils_stub.INVERTER_TYPE` directly before each test.

```python
# tests/test_009_dummy_get_settings.py
def test_get_settings_succeeds_when_type_matches():
    utils_stub.INVERTER_TYPE = "Dummy"
    d = Dummy.__new__(Dummy)
    Inverter.__init__(d, port="/dev/null", baudrate=0, slave=0)
    d.type = "Dummy"
    assert d.get_settings() is True
    assert d.max_ac_power == utils_stub.INVERTER_MAX_AC_POWER
    assert d.phase == utils_stub.INVERTER_PHASE
    assert d.position == utils_stub.INVERTER_POSITION
    assert d.serial_number == 12345678
    assert d.hardware_version == "1.0.0"

def test_get_settings_fails_when_type_mismatches():
    utils_stub.INVERTER_TYPE = "Solis"
    ...
    assert d.get_settings() is False

def test_get_settings_fails_when_type_blank():
    """Blank TYPE must return False — Dummy should not self-activate on blank config."""
    utils_stub.INVERTER_TYPE = ""
    ...
    assert d.get_settings() is False
```

Restore `utils_stub.INVERTER_TYPE = "Dummy"` in cleanup (or use a fixture that yields and restores).

---

**2f. `test_010_dummy_read_status_data.py`** — covers R7

Tests `Dummy.read_status_data()` calculations. Specifies `power_limit=400.0` before calling.

```python
# tests/test_010_dummy_read_status_data.py
def test_read_status_data_populates_all_fields():
    d = _make_dummy()
    d.energy_data['overall']['power_limit'] = 400.0
    result = d.read_status_data()
    assert result is True
    assert d.energy_data['L1']['ac_voltage'] == 230.0
    assert abs(d.energy_data['L1']['ac_current'] - 400.0 / 230) < 0.001
    assert d.energy_data['L1']['ac_power'] == 400.0
    assert d.status == 7

def test_l2_l3_zeroed_in_single_phase():
    ...  # L2/L3 voltage, current, power all 0.0

def test_read_status_data_with_none_power_limit_raises():
    """Documents that power_limit=None causes TypeError — get_settings must run first."""
    d = _make_dummy()
    # power_limit defaults to None from Inverter.__init__
    try:
        d.read_status_data()
        assert False, "Should raise TypeError when power_limit is None"
    except TypeError:
        pass  # known fragility — documented
```

---

**2g. `test_011_solis_status_mapping.py`** — covers R8

Tests Solis status code mapping in `read_status_data()` by mocking all register reads to return success, then controlling only register 3043 (status register).

Uses `modbus_mock` fixture injected on the Solis instance. Because `read_status_data()` reads many registers, the mock defaults all reads to `(True, 0)` and register 3043 is set to the status under test.

```python
# tests/test_011_solis_status_mapping.py
@pytest.mark.parametrize("raw,expected", [
    (0, 0),   # Waiting
    (1, 1),   # OpenRun
    (2, 2),   # SoftRun
    (3, 7),   # Generating
    (4, 10),  # Fault (else branch)
    (255, 10),# Fault (else branch, high value)
])
def test_status_code_mapping(raw, expected, modbus_mock):
    solis = _make_solis(modbus_mock)
    _configure_status_register(modbus_mock, raw)
    solis.read_status_data()
    assert solis.status == expected

def test_status_read_failure_sets_standby(modbus_mock):
    """When register 3043 read fails, status is set to 8 (Standby/Off)."""
    solis = _make_solis(modbus_mock)
    _configure_status_register_error(modbus_mock)
    solis.read_status_data()
    assert solis.status == 8
```

**Mock strategy:** Override `solis.read_input_registers` as a method on the instance:
```python
def _make_solis_with_mock_reads(register_map):
    """register_map: {address: (success, value)}. Missing addresses return (True, 0)."""
    solis = Solis.__new__(Solis)
    Inverter.__init__(solis, port="/dev/null", baudrate=9600, slave=1)
    solis.type = "Solis"
    solis.max_ac_power = 800.0
    solis.phase = "L1"
    original = solis.read_input_registers

    def patched_read(address, count, data_type, scale, digits):
        if address in register_map:
            success, val = register_map[address]
            return success, round(val * scale, digits)
        return True, 0

    solis.read_input_registers = patched_read
    solis.write_registers = lambda *a, **kw: True
    return solis
```

This is cleaner than mocking the Modbus client for high-level behavior tests — it patches one level up.

---

**2h. `test_012_solis_read_input_registers.py`** — covers R9

Tests `Solis.read_input_registers()` with a real Solis instance whose `client` attribute is the `modbus_mock` fixture.

```python
# tests/test_012_solis_read_input_registers.py
def test_u16_decode(modbus_mock):
    modbus_mock.read_input_registers.return_value = _make_result([500])
    success, val = solis.read_input_registers(3035, 1, "u16", 0.1, 1)
    assert success is True
    assert abs(val - 50.0) < 0.01  # 500 * 0.1

def test_u32_decode(modbus_mock): ...
def test_float_decode(modbus_mock): ...

def test_unsupported_data_type_returns_false(modbus_mock):
    modbus_mock.read_input_registers.return_value = _make_result([0])
    success, val = solis.read_input_registers(3035, 1, "invalid_type", 1, 0)
    assert success is False
    assert val == 0

def test_connection_failure_returns_false(modbus_mock):
    modbus_mock.connect.return_value = False
    success, val = solis.read_input_registers(3035, 1, "u16", 1, 0)
    assert success is False
    assert val == 0

def test_register_error_response_returns_false(modbus_mock):
    modbus_mock.read_input_registers.return_value = _make_error_result()
    success, val = solis.read_input_registers(3035, 1, "u16", 1, 0)
    assert success is False
    assert val == 0

def test_write_registers_returns_false_on_connection_failure(modbus_mock):
    modbus_mock.connect.return_value = False
    result = solis.write_registers(3051, 5000)
    assert result is False

def test_write_registers_returns_false_on_error_response(modbus_mock):
    modbus_mock.write_registers.return_value = _make_error_result()
    result = solis.write_registers(3051, 5000)
    assert result is False
```

Helpers:
```python
def _make_result(registers):
    r = unittest.mock.MagicMock()
    r.isError.return_value = False
    r.registers = registers
    return r

def _make_error_result():
    r = unittest.mock.MagicMock()
    r.isError.return_value = True
    return r
```

---

**2i. `test_013_solis_power_limit_write.py`** — covers R10

Tests that `write_registers` is called only when the power limit has changed, and not when unchanged. Uses the `_make_solis_with_mock_reads` pattern plus a MagicMock for `write_registers`.

```python
# tests/test_013_solis_power_limit_write.py
def test_write_triggered_when_power_limit_changes():
    solis = _make_solis(register_map={3049: (True, 50)})  # 50% = 400W active
    solis.energy_data['overall']['power_limit'] = 800.0   # user wants 100%
    write_mock = unittest.mock.MagicMock(return_value=True)
    solis.write_registers = write_mock
    solis.read_status_data()
    assert write_mock.call_count == 1
    assert write_mock.call_args[0][1] == 10000  # 100% * 100

def test_write_not_triggered_when_power_limit_unchanged():
    solis = _make_solis(register_map={3049: (True, 100)})  # 100% active
    solis.energy_data['overall']['power_limit'] = 800.0    # also 100%
    write_mock = unittest.mock.MagicMock(return_value=True)
    solis.write_registers = write_mock
    solis.read_status_data()
    assert write_mock.call_count == 0

def test_power_limit_clamped_before_write():
    """Write value must always be in [0, 10000]."""
    solis = _make_solis(register_map={3049: (True, 50)})
    solis.energy_data['overall']['power_limit'] = 9999.0  # far above max
    write_mock = unittest.mock.MagicMock(return_value=True)
    solis.write_registers = write_mock
    solis.read_status_data()
    written_value = write_mock.call_args[0][1]
    assert 0 <= written_value <= 10000
```

---

**2j. `test_014_get_inverter_retry.py`** — covers R11

Because `get_inverter()` is nested inside `main()` and closes over `expected_inverter_types`, use the test_003 pattern: **recreate the retry logic** as a testable factory in the test file. Patch `time.sleep` to eliminate the 0.5s delay.

```python
# tests/test_014_get_inverter_retry.py
import time
import unittest.mock

def _make_get_inverter(inverter_types):
    """Mirrors dbus-serialinverter.py get_inverter() logic, extracted for testing."""
    def get_inverter(port):
        count = 3
        while count > 0:
            for test in inverter_types:
                inverter_class = test["inverter"]
                inv = inverter_class(port=port, baudrate=test["baudrate"],
                                     slave=test.get("slave", 1))
                if inv.test_connection():
                    return inv
            count -= 1
            time.sleep(0.5)
        return None
    return get_inverter

@unittest.mock.patch("time.sleep")
def test_returns_none_after_three_failed_rounds(mock_sleep):
    class _AlwaysFail:
        def __init__(self, **kw): pass
        def test_connection(self): return False

    get_inverter = _make_get_inverter([
        {"inverter": _AlwaysFail, "baudrate": 0, "slave": 0}
    ])
    result = get_inverter("/dev/null")
    assert result is None
    assert mock_sleep.call_count == 3  # sleep called after each failed round

@unittest.mock.patch("time.sleep")
def test_returns_inverter_on_first_success(mock_sleep):
    class _AlwaysSucceed:
        def __init__(self, **kw): self.port = "/dev/null"
        def test_connection(self): return True

    get_inverter = _make_get_inverter([
        {"inverter": _AlwaysSucceed, "baudrate": 0, "slave": 0}
    ])
    result = get_inverter("/dev/null")
    assert isinstance(result, _AlwaysSucceed)
    assert mock_sleep.call_count == 0  # no sleep needed

@unittest.mock.patch("time.sleep")
def test_returns_first_matching_type_in_list(mock_sleep):
    """First type in list wins even if second type also succeeds."""
    call_order = []

    class _FirstType:
        def __init__(self, **kw): pass
        def test_connection(self):
            call_order.append("first")
            return True

    class _SecondType:
        def __init__(self, **kw): pass
        def test_connection(self):
            call_order.append("second")
            return True

    get_inverter = _make_get_inverter([
        {"inverter": _FirstType, "baudrate": 0},
        {"inverter": _SecondType, "baudrate": 0},
    ])
    result = get_inverter("/dev/null")
    assert isinstance(result, _FirstType)
    assert "second" not in call_order
```

---

#### Phase 3: Regression Stubs (R12)

**`test_015_regression_stubs.py`** — one file, all 8 testable todos marked `xfail(strict=True)`.

Each stub:
1. Contains a concrete assertion that documents the *current wrong behavior*
2. Is marked `@pytest.mark.xfail(strict=True, reason="todo NNN: <title>")` — fails if the bug is silently fixed without updating the test

| Todo | Regression assertion |
|---|---|
| 006 | `client.connect.call_count > 1` after one `read_status_data()` call |
| 007 | `write_registers.call_count == 1` during `read_status_data()` (write is in the read path, should be 0) |
| 008 | `publish_dbus()` call count ≥ 1 even when `refresh_data()` returns False |
| 009 | `get_settings.call_count == 2` after `test_connection()` + `setup_vedbus()` |
| 010 | `energy_data['L1']['energy_forwarded'] == 0` after 3-phase `read_status_data()` |
| 011 | `client.read_input_registers.call_count > 7` per single `read_status_data()` call |
| 013 | `utils_logger.level == logging.DEBUG` after utils import |
| 014 | `Dummy(port, 0, 0).get_settings()` returns True when `INVERTER_TYPE == ""`  |

Todos 005 and 012 are excluded: 005 (config error handling) requires re-importing utils with a broken config — feasible but complex enough to defer to when the fix lands; 012 (code simplification) is not behaviorally testable.

```python
# tests/test_015_regression_stubs.py
"""Regression stubs for todos 005-014. All tests document current wrong behavior.
When a bug is fixed, the corresponding test must be updated or moved to a passing test file.

xfail(strict=True) means: if the assertion starts passing, pytest FAILS the run loudly.
This forces a conscious decision when fixing bugs.
"""
import pytest

@pytest.mark.xfail(strict=True, reason="todo 006: connect() called per register read instead of once per poll")
def test_todo_006_connect_called_once_per_poll(modbus_mock):
    solis = _make_solis_with_client(modbus_mock)
    modbus_mock.connect.return_value = True
    modbus_mock.read_input_registers.return_value = _make_result([0])
    solis.read_status_data()
    # Current behavior: connect() called many times (once per read_input_registers call)
    # Desired behavior: connect() called at most once per poll
    assert modbus_mock.connect.call_count <= 1  # xfail: currently > 1

@pytest.mark.xfail(strict=True, reason="todo 007: power limit write happens inside read path")
def test_todo_007_write_not_in_read_path():
    solis = _make_solis_with_mock_reads({3049: (True, 50)})
    solis.energy_data['overall']['power_limit'] = 800.0
    write_mock = unittest.mock.MagicMock(return_value=True)
    solis.write_registers = write_mock
    solis.read_status_data()
    # Desired: read_status_data() should NOT trigger any write
    assert write_mock.call_count == 0  # xfail: currently == 1

@pytest.mark.xfail(strict=True, reason="todo 008: publish_dbus called unconditionally even on refresh failure")
def test_todo_008_publish_dbus_not_called_on_failure(fake_loop, fake_dbus_service):
    publish_dbus_calls = []
    helper = _make_dbushelper(fake_dbus_service, refresh_returns=False)
    helper.publish_dbus = lambda: publish_dbus_calls.append(1)
    helper.publish_inverter(fake_loop)
    # Desired: publish_dbus not called when refresh_data returns False
    assert len(publish_dbus_calls) == 0  # xfail: currently called anyway

@pytest.mark.xfail(strict=True, reason="todo 009: get_settings called twice at startup")
def test_todo_009_get_settings_called_once_at_startup():
    call_count = [0]
    original = _stub_solis_get_settings(call_count)
    # Simulate: test_connection() (calls get_settings internally) + setup_vedbus() (calls it again)
    _run_startup_sequence()
    # Desired: get_settings called exactly once
    assert call_count[0] == 1  # xfail: currently 2

@pytest.mark.xfail(strict=True, reason="todo 010: 3-phase energy_forwarded hardcoded to integer 0")
def test_todo_010_3phase_energy_forwarded_nonzero():
    solis = _make_solis_with_mock_reads({3002: (True, 1)})  # output_type=1 → 3-phase
    solis.read_status_data()
    # Desired: per-phase energy_forwarded should reflect actual values, not 0
    assert solis.energy_data['L1']['energy_forwarded'] != 0  # xfail: hardcoded to 0

@pytest.mark.xfail(strict=True, reason="todo 011: no batching — 10-13 separate Modbus round-trips per poll")
def test_todo_011_read_status_data_uses_few_transactions(modbus_mock):
    solis = _make_solis_with_client(modbus_mock)
    solis.energy_data['overall']['power_limit'] = 0.0
    modbus_mock.read_input_registers.return_value = _make_result([0])
    solis.read_status_data()
    # Desired: ≤ 5 transactions for a single-phase poll
    assert modbus_mock.read_input_registers.call_count <= 5  # xfail: currently 10-13

@pytest.mark.xfail(strict=True, reason="todo 013: logger.setLevel(DEBUG) hardcoded in utils.py")
def test_todo_013_logger_not_debug_level():
    import logging
    # After utils import, logger should not be hardcoded to DEBUG
    assert _get_utils_logger_level() != logging.DEBUG  # xfail: currently DEBUG

@pytest.mark.xfail(strict=True, reason="todo 014: Dummy self-activates when INVERTER_TYPE is blank")
def test_todo_014_dummy_inactive_on_blank_type():
    utils_stub.INVERTER_TYPE = ""
    d = _make_dummy()
    # Desired: Dummy should not activate when TYPE is blank
    result = d.get_settings()
    utils_stub.INVERTER_TYPE = "Dummy"  # restore
    assert result is False  # xfail: currently returns True when TYPE="" because Dummy checks TYPE == "Dummy" and "" != "Dummy"... wait
```

**Note on 014:** Re-reading `dummy.py:20` — it checks `utils.INVERTER_TYPE == "Dummy"`, so blank type returns False already. The actual bug is in `dbus-serialinverter.py:31-33` where `expected_inverter_types` includes Dummy when `utils.INVERTER_TYPE == ""`. The xfail stub should test that behavior instead:
```python
# The bug is in the type-selection filter, not in Dummy.get_settings()
# expected_inverter_types includes Dummy when TYPE="" because:
#   inverter_type["inverter"].__name__ == "" → False, but utils.INVERTER_TYPE == "" → True
# So Dummy is included in auto-detect even though it's a synthetic test device.
# Stub: assert Dummy is not in expected_inverter_types when TYPE="" and Solis fails to connect.
```
This requires importing `dbus-serialinverter.py` which triggers D-Bus. Alternative: test the filter logic directly as a pure Python expression (same pattern as test_002 does for the validation logic).

---

### System-Wide Impact

**Interaction graph:** `conftest.py` → every test file → production modules. The conftest stub layer is invisible to production code (same `sys.modules` entries, just stubbed). No production code changes required.

**Error propagation:** If `conftest.py` fails to load (syntax error, import failure), all tests will fail with a conftest collection error. Keep conftest.py simple — no complex logic, only stubs and fixtures.

**State lifecycle risks:** The mutable `utils_stub` object persists across all tests. Tests that mutate attributes must restore them. Use a pattern like:
```python
def test_something_with_different_type():
    original = utils_stub.INVERTER_TYPE
    utils_stub.INVERTER_TYPE = "Solis"
    try:
        # test body
    finally:
        utils_stub.INVERTER_TYPE = original
```
Or extract this into the `utils_config` fixture.

**API surface parity:** The `_VeDbusService` stub in conftest must support all methods called in production: `add_path(path, value, writeable=False, gettextcallback=None)`, `__getitem__`, `__setitem__`. The `gettextcallback` parameter must be accepted but can be ignored in the stub.

**Integration test scenarios not covered:**
- Full D-Bus service lifecycle (requires VenusOS)
- Modbus wire protocol correctness (requires pymodbus + real hardware)
- GLib mainloop timer dispatch (not testable without GLib)
- RS232/RS485 serial framing (hardware-only)

## Acceptance Criteria

### Functional Requirements
- [ ] `python -m pytest tests/` passes: all non-xfail tests green, all xfail tests recorded as `xfail` (not `XPASS`)
- [ ] `python tests/test_NNN_*.py` (without pytest) still works for all new test files — each has a `__main__` block
- [ ] Each source module has at least one test file: `inverter.py` → 005, `dbushelper.py` → 006/007/008, `dummy.py` → 009/010, `solis.py` → 011/012/013, `dbus-serialinverter.py` → 014
- [ ] R3 boundary cases are explicitly tested at count=9 and count=59 (not just 10 and 60)
- [ ] R4 wrap-around is tested at 254→255 (no wrap) AND 255→0 (wraps)
- [ ] R5 formatter tests assert exact output strings, not just no-exception
- [ ] R12 stubs contain concrete assertions that will fail (as xfail) if the bug is silently fixed

### Non-Functional Requirements
- [ ] Full suite completes in under 10 seconds on a developer machine
- [ ] No real serial port, D-Bus connection, or pymodbus network call is made during tests
- [ ] All new code is Python 3.6+ compatible (no walrus operator, no `|` union types, no `match` statements)

### Quality Gates
- [ ] Existing tests 001–004 continue to pass unchanged
- [ ] `conftest.py` uses `sys.modules.setdefault` (not plain assignment) for package stubs — idempotent with existing per-file stubs
- [ ] The `utils_stub` is the same object across all tests (not replaced, only mutated-and-restored)

## Dependencies & Prerequisites

- pytest available in dev environment (already confirmed by CLAUDE.md)
- `unittest.mock` available (Python 3.3+, within the 3.6+ constraint)
- No new third-party packages required
- No changes to production source files required (except potentially extracting `get_inverter()` from `main()` if R11 with the pure recreation approach feels too fragile — deferred decision)

## Risk Analysis & Mitigation

**Risk: Module cache pollution between tests**
Mitigation: Use the mutable stub pattern (mutate-and-restore, not replace). Document the pattern in conftest.py with a comment. Function-scoped fixtures that mutate and restore are the safety net.

**Risk: `get_inverter()` recreation in test_014 drifts from production logic**
Mitigation: Add a comment in test_014 that documents the production location (`dbus-serialinverter.py:56-77`) and the intentional recreation. Future refactor of the production function to module-level unblocks using the real implementation.

**Risk: xfail stubs silently become vacuous if the assert is wrong direction**
Mitigation: Each xfail assert documents the *current broken behavior*. Run the full suite before and after adding each stub to confirm it records `xfail` (not `xpass` or `error`).

**Risk: BinaryPayloadDecoder stub registers[0] shortcut is wrong for multi-register reads**
Mitigation: The stub is sufficient for behavioral tests (verifying logic flow, not wire protocol). The decode path that uses `registers[0]` only matters when the mock's register list has the right value. Set `registers=[<expected_raw_value>]` explicitly in each test.

## Documentation Plan

Update `CLAUDE.md` test table with the new test files after implementation:

| File | Covers |
|---|---|
| `test_005_inverter_energy_data_init.py` | `Inverter` base class `energy_data` dict initialization |
| `test_006_dbushelper_error_counting.py` | Error count 0→10 (offline), 0→60 (quit), reset on success |
| `test_007_dbushelper_update_index.py` | `publish_dbus()` UpdateIndex 0–255 wrap-around |
| `test_008_dbushelper_text_formatters.py` | `gettextforW/V/A/kWh` exact output format |
| `test_009_dummy_get_settings.py` | `Dummy.get_settings()` TYPE matching and blank-TYPE |
| `test_010_dummy_read_status_data.py` | `Dummy.read_status_data()` calculations and None guard |
| `test_011_solis_status_mapping.py` | Solis status register → Victron code mapping |
| `test_012_solis_read_input_registers.py` | `read_input_registers()` all data types and error paths |
| `test_013_solis_power_limit_write.py` | Power limit write triggers only on change |
| `test_014_get_inverter_retry.py` | `get_inverter()` 3-round retry and first-match logic |
| `test_015_regression_stubs.py` | xfail stubs for todos 006–011, 013–014 |

## Sources & References

### Origin

- **Origin document:** [docs/brainstorms/2026-03-18-test-suite-requirements.md](docs/brainstorms/2026-03-18-test-suite-requirements.md)
  Key decisions carried forward: (1) mock pymodbus at the boundary, (2) add conftest.py for shared fixtures, (3) include xfail stubs for todos 005–014

### Internal References

- Existing stub pattern: `tests/test_001_position_typo.py:7-16`
- VeDbusService stub pattern: `tests/test_004_bare_except.py:12-17`
- `DbusHelper.__new__` injection pattern: `tests/test_004_bare_except.py:61-63`
- Poll-lock recreation pattern (motivation for R11 approach): `tests/test_003_poll_lock.py:6-28`
- Clamping logic extraction pattern (motivation for pure-function tests): `tests/test_002_power_limit_validation.py:64-67`
- UpdateIndex wrap source: `etc/dbus-serialinverter/dbushelper.py:192-196`
- Status mapping source: `etc/dbus-serialinverter/solis.py:229-244`
- Power limit write source: `etc/dbus-serialinverter/solis.py:256-260`
- FIXME comment (todo 007 evidence): `etc/dbus-serialinverter/dbushelper.py:135`

### Related Work

- Samlex EVO 4024 requirements doc (will also use ModbusSerialClient mock): `docs/brainstorms/2026-03-18-samlex-evo-4024-requirements.md`
- Open todos: `todos/005-pending-p2-*.md` through `todos/014-pending-p3-*.md`
