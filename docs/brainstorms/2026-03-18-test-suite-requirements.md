---
date: 2026-03-18
topic: test-suite
---

# Test Suite for dbus-serialinverter

## Problem Frame

The driver has 4 passing tests covering P1 bug fixes. All other behaviors — error counting, D-Bus publishing, inverter driver logic, Solis Modbus handling, and startup/detection flow — are untested. Changes to any of these areas risk silent regression. A comprehensive test suite with a shared fixture layer is needed to make future changes safe to land.

## Requirements

- R1. Add a `tests/conftest.py` providing shared pytest fixtures: logger stub, utils stub, VeDbusService stub (dict-like, records written values), FakeInverter, and FakeLoop.
- R2. Test `Inverter` base class `energy_data` initialization: all expected keys (`ac_voltage`, `ac_current`, `ac_power`, `energy_forwarded`) are present for L1/L2/L3; `overall` contains `ac_power`, `energy_forwarded`, `power_limit`, `active_power_limit`.
- R3. Test `DbusHelper.publish_inverter()` error-counting behavior: error_count increments on failure, `inverter.online` becomes False at ≥10 consecutive failures, `loop.quit()` is called at ≥60 consecutive failures, error_count resets to 0 on success.
- R4. Test `DbusHelper.publish_dbus()` UpdateIndex: increments each call, wraps from 255 to 0.
- R5. Test `DbusHelper` text formatter methods: `gettextforkWh`, `gettextforW`, `gettextforV`, `gettextforA` return correctly formatted strings for representative values.
- R6. Test `Dummy.get_settings()`: returns `False` when `utils.INVERTER_TYPE != "Dummy"`; returns `True` and populates `max_ac_power`, `phase`, `position`, `serial_number`, `hardware_version`, and `power_limit` when type matches.
- R7. Test `Dummy.read_status_data()`: `ac_current == power / 230`, all L1/L2/L3 and overall fields are set, `status == 7`.
- R8. Test Solis status mapping using a mocked `read_input_registers`: raw register values 0→0, 1→1, 2→2, 3→7, any other→10; and failure→8 (Standby/Off).
- R9. Test Solis `read_input_registers()` data type handling with mocked `ModbusSerialClient`: `u16`, `u32`, `float` decode correctly; unsupported type returns `(False, 0)`; connection failure returns `(False, 0)`; error response returns `(False, 0)`.
- R10. Test Solis power limit write path: `write_registers()` is called when `power_limit` differs from the active limit read back; not called when they match.
- R11. Test `get_inverter()` retry logic: returns `None` after 3 rounds of failing `test_connection()`; returns the first inverter whose `test_connection()` succeeds.
- R12. Add clearly-marked regression stubs (`pytest.mark.xfail(strict=True, reason="todo NNN")`) for known bugs in todos 005–014, so they appear as expected failures in CI and turn into real failures once fixed.

## Success Criteria

- `python -m pytest tests/` passes with all non-stub tests green and all stub tests recorded as `xfail`.
- Each source module (`inverter.py`, `dbushelper.py`, `dummy.py`, `solis.py`, `dbus-serialinverter.py`) has at least one corresponding test file.
- A new contributor can run the full suite in under 10 seconds on a machine with no hardware and no VenusOS packages installed.
- When a future change breaks a tested behavior, at least one test fails clearly.

## Scope Boundaries

- No integration tests against real D-Bus or real serial hardware.
- No testing of `install.sh`, systemd unit, or VenusOS packaging.
- Solis tests mock `ModbusSerialClient` — they do not validate wire-level Modbus framing.
- `utils.py` config parsing is not re-tested beyond what test_002 already covers (the validation logic test is sufficient).
- The `conftest.py` fixtures are for reducing repetition; tests remain individually runnable without pytest if a `__main__` block is included.

## Key Decisions

- **Mock pymodbus for Solis**: Stub `ModbusSerialClient` at the test boundary so Solis logic (register parsing, status mapping, power limit diffing) can be tested without hardware.
- **Use conftest.py for shared fixtures**: Reduces the per-file boilerplate of stubbing out `dbus`, `gi`, `vedbus`, `settingsdevice`, and `utils`. Existing test_001–test_004 can be migrated or left as-is.
- **Include regression stubs for todos 005–014**: Mark with `xfail(strict=True)` so they surface as known failures in CI, not silent gaps. Each stub references its todo file.

## Dependencies / Assumptions

- pytest is available in the dev environment (already used by CLAUDE.md `python -m pytest tests/`).
- pymodbus is importable from `etc/dbus-serialinverter/pymodbus/` (embedded copy) for type-checking purposes, but the `ModbusSerialClient` is mocked in tests.
- Python 3.6+ (matches production target).

## Outstanding Questions

### Resolve Before Planning

_None — all product decisions are resolved._

### Deferred to Planning

- [Affects R12][Technical] Which specific todos 005–014 map cleanly to testable assertions vs. needing code changes first? The planner should read each todo file before writing stubs.
- [Affects R1][Technical] Does `conftest.py` need to handle the `sys.path` insertion for `etc/dbus-serialinverter/` once, or should each test file still manage its own path?

## Next Steps

→ `/ce:plan` for structured implementation planning
