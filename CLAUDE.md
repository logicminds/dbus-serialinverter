# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A VenusOS driver that bridges serial-connected solar inverters (RS232/RS485/TTL UART) to the Victron D-Bus system. Runs on Victron GX devices or Raspberry Pi running VenusOS Large (Python 3.8+ required).

## Running the Driver

No build step — pure Python. All driver code lives in `etc/dbus-serialinverter/`.

```bash
# Run with dummy inverter (no hardware required)
cd etc/dbus-serialinverter
python dbus-serialinverter.py /dev/null

# Run with real hardware
python dbus-serialinverter.py /dev/ttyUSB0
```

On VenusOS target after installing (`./install.sh`), logs are at:
```bash
tail -f /var/log/dbus-serialinverter.<TTY>
```

## Architecture

The driver follows a plugin pattern — inverter-specific logic is isolated behind an abstract base class:

**`inverter.py`** — Abstract base class (`Inverter`) defining the interface all drivers must implement:
- `test_connection()` — probe if this inverter responds on the port
- `get_settings()` — read static config (serial number, hardware version, max power)
- `refresh_data()` — read dynamic state into `self.energy_data`

**`dbus-serialinverter.py`** — Entry point. Auto-detects inverter type by trying each registered type in `supported_inverter_types`. Runs a GLib mainloop with a GLib timer that spawns a poll thread every `poll_interval` ms.

**`dbushelper.py`** — Owns the D-Bus service (`com.victronenergy.pvinverter.<port>`). Calls `inverter.get_settings()` once at startup, then `inverter.refresh_data()` + `publish_dbus()` each poll cycle. Exits after 60 consecutive read failures.

**`solis.py`** — Modbus RTU driver for Solis mini inverters. Each register read opens a fresh connection (known issue). Supports single-phase and 3-phase. Can write power limit back to inverter.

**`dummy.py`** — Synthetic test inverter generating constant L1 data. Only active when `TYPE=Dummy` in config.

**`utils.py`** — Logging setup, config parsing, exports constants from `config.ini`.

## Configuration

Edit `etc/dbus-serialinverter/config.ini`:

```ini
[INVERTER]
TYPE=           # "Solis", "Dummy", or blank for auto-detect
POLL_INTERVAL=1000   # ms
MAX_AC_POWER=800     # W
PHASE=L1             # L1, L2, or L3
POSITION=1           # 0=AC input 1, 1=AC output, 2=AC input 2
```

## Pre-Commit Checklist

**Always run lint and tests before committing.** Both must pass clean.

```bash
# 1. Lint
ruff check etc/dbus-serialinverter/*.py tests/

# 2. Tests with coverage (must stay ≥ 80%)
python -m pytest tests/ -v --tb=short --cov --cov-report=term-missing --cov-fail-under=80
```

CI enforces the same checks on every push and PR. A commit that breaks lint or drops below 80% coverage will fail the pipeline.

## Running Tests

Tests live in `tests/` and have no external dependencies beyond the standard library. Each test file stubs out VenusOS/D-Bus packages so they run on any Python 3.8+ machine without hardware.

```bash
# Run all tests
python -m pytest tests/

# Run a single test file
python tests/test_001_position_typo.py

# Run without pytest (each file has a __main__ block)
for f in tests/test_*.py; do python "$f"; done
```

Test files mirror todo numbers:

| File | Covers |
|---|---|
| `test_001_position_typo.py` | `Inverter.position` base-class attribute |
| `test_002_power_limit_validation.py` | `MAX_AC_POWER > 0` startup check; power limit clamping |
| `test_003_poll_lock.py` | Concurrent poll prevention (threading.Lock) |
| `test_004_bare_except.py` | `except Exception` propagates `KeyboardInterrupt`/`SystemExit` |
| `test_005_inverter_energy_data_init.py` | `Inverter.__init__` energy_data structure and defaults |
| `test_006_dbushelper_error_counting.py` | Error counter, online flag, loop-quit threshold (60 failures) |
| `test_007_dbushelper_update_index.py` | UpdateIndex increment and 255→0 wrap |
| `test_008_dbushelper_text_formatters.py` | kWh / W / V / A text formatter output strings |
| `test_009_dummy_get_settings.py` | `Dummy.get_settings()` type-match gate |
| `test_010_dummy_read_status_data.py` | `Dummy.read_status_data()` field calculations |
| `test_011_solis_status_mapping.py` | Solis status register → Victron status code mapping |
| `test_012_solis_read_input_registers.py` | `Solis.read_input_registers()` data types and error paths |
| `test_013_solis_power_limit_write.py` | Power limit write trigger, value encoding, clamping |
| `test_014_get_inverter_retry.py` | `get_inverter()` retry loop (3 rounds, sleep, type ordering) |
| `test_015_regression_stubs.py` | `xfail(strict=True)` stubs for open todos 006–011, 013–014 |
| `test_036_glib_integration.py` | GLib conditional real/mock dispatch; MainLoop lifecycle, poll integration, DBusGMainLoop init |

When adding a new inverter or fixing a bug, add a corresponding test in `tests/` and verify it passes before committing.

## Adding a New Inverter Type

1. Create `etc/dbus-serialinverter/<brand>.py` extending `Inverter`
2. Implement `test_connection()`, `get_settings()`, `refresh_data()`
3. Register it in `dbus-serialinverter.py` `supported_inverter_types` list

## Known Issues (todos/)

The `todos/` directory tracks 14 open issues. P1 bugs (001–004) are fixed. Remaining open items start at P2:

## Dependencies

- Python 3.8+ (VenusOS Large required)
- `pymodbus` — embedded in `etc/dbus-serialinverter/pymodbus/`
- Victron `velib_python` (VeDbusService, SettingsDevice) — provided by VenusOS
- GObject/GLib (`gi.repository.GLib`) — provided by VenusOS
