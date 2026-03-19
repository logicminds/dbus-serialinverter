---
title: "feat: Add Samlex EVO 4024 Inverter/Charger Driver"
type: feat
status: active
date: 2026-03-18
origin: docs/brainstorms/2026-03-18-samlex-evo-4024-requirements.md
---

# feat: Add Samlex EVO 4024 Inverter/Charger Driver

## Overview

Add a new `samlex.py` driver that integrates the Samlex EVO 4024 24V/4000W inverter/charger into VenusOS over Modbus RTU (RS485). The driver publishes AC output, battery DC, AC input (shore power), and fault status to the Victron D-Bus. Because the EVO 4024 is a multi-mode inverter/charger — not a PV inverter — it registers under `com.victronenergy.vebus`, requiring targeted changes to `dbushelper.py` and `inverter.py`.

The Modbus register map is protected by Samlex NDA. All register addresses and scaling factors are externalized into a `[SAMLEX_REGISTERS]` section of `config.ini`, which ships with `???` placeholder values. Users fill these in privately after obtaining the "Modbus Communication Protocol Guide" from Samlex support.

## Problem Statement

The project currently only supports the Solis Mini 700 4G (PV inverter). The user has a Samlex EVO 4024 on the same bus and wants full monitoring via VenusOS. The underlying Modbus RTU stack is already present; what is missing is:

1. A driver class implementing the EVO 4024 register map
2. Expanded D-Bus paths for DC/battery, AC input, and charger state — paths that `com.victronenergy.pvinverter` does not carry
3. A mechanism to select the correct VenusOS service type per driver

## Proposed Solution

### Service type selection (affects `dbushelper.py`)

Add a class-level `SERVICE_PREFIX` attribute to the `Inverter` base class, defaulting to `"com.victronenergy.pvinverter"`. `Samlex` overrides it to `"com.victronenergy.vebus"`. `DbusHelper.__init__()` reads `inverter.SERVICE_PREFIX` instead of the current hardcoded string.

> **Correction from brainstorm:** The origin document specified `com.victronenergy.inverter`. Research confirms this is incorrect for a multi-mode inverter/charger — `com.victronenergy.inverter` has no AC input paths and no charger state. The correct service type is `com.victronenergy.vebus`, consistent with the SMA SunnyIsland Venus driver and Victron's dbus-systemcalc-py source. *(see origin: docs/brainstorms/2026-03-18-samlex-evo-4024-requirements.md — Key Decisions)*

### Energy data extension (affects `inverter.py`)

Add two new sub-dicts to `Inverter.__init__()`:

```python
self.energy_data['dc'] = {
    'voltage': None,   # V (float)
    'current': None,   # A (float, positive = charging)
    'power':   None,   # W (float)
    'soc':     None,   # % (float, 0-100)
}
self.energy_data['ac_in'] = {
    'voltage':   None,  # V (float)
    'current':   None,  # A (float)
    'power':     None,  # W (float)
    'connected': None,  # 0 or 1
}
```

Existing Solis and Dummy drivers leave these as `None`; `publish_dbus()` skips `None` values. No behavior change for existing drivers.

### New D-Bus paths (affects `dbushelper.py`)

`setup_vedbus()` conditionally registers extended paths when `inverter.SERVICE_PREFIX` is not `pvinverter`:

```
/Dc/0/Voltage           %.2FV
/Dc/0/Current           %.2FA
/Dc/0/Power             %.0FW
/Soc                    %.0F%%
/Ac/Out/L1/V            %.0FV
/Ac/Out/L1/I            %.0FA
/Ac/Out/L1/P            %.0FW
/Ac/ActiveIn/L1/V       %.0FV
/Ac/ActiveIn/L1/I       %.0FA
/Ac/ActiveIn/L1/P       %.0FW
/Ac/ActiveIn/Connected  %d
/State                  %d
/Mode                   %d
/VebusChargeState       %d
/Ac/NumberOfAcInputs    %d
/Ac/NumberOfPhases      %d
/Ac/In/1/Type           %d
```

Note: `pvinverter` uses the flat `/Ac/L1/Voltage` style; `vebus` uses the nested `/Ac/Out/L1/V` style. These are separate path sets registered under different conditions.

### `samlex.py` driver

Implements `Inverter` with:

- `SERVICE_PREFIX = "com.victronenergy.vebus"`
- `test_connection()`: validates `[SAMLEX_REGISTERS]` config first (returns `False` on any `???` or missing key), then reads one identity register
- `get_settings()`: reads static registers (hardware version, serial number); sets `self.position`, `self.phase`, `self.max_ac_power` from config; sets `active_power_limit = None` (no write support)
- `refresh_data()`: three batched Modbus reads (AC output, DC/battery, AC input); populates `energy_data`; maps fault register to `self.status`
- `_ensure_connected()`: the `is_socket_open()` guard pattern from Solis — connect once, reconnect only on confirmed failure
- `_read_batch(address, count)`: contiguous register batch helper (same pattern as Solis)
- `apply_power_limit()`: not overridden (base class no-op)

### Register map externalization (affects `config.ini` and `utils.py`)

Add a `[SAMLEX_REGISTERS]` section to `config.ini` with `???` placeholder values and a prominent comment block directing users to Samlex support. Add a `REQUIRED_SAMLEX_REGISTERS` tuple to `samlex.py` listing all expected keys. `test_connection()` iterates this tuple.

`utils.py` reads the section using `config.get(..., fallback=None)` with explicit presence checks — never raw dict access (avoids `KeyError` on missing section or keys).

### Registration (affects `dbus-serialinverter.py`)

```python
from samlex import Samlex
_REAL_INVERTER_TYPES = [
    {"inverter": Solis,   "baudrate": 9600, "slave": 1},
    {"inverter": Samlex,  "baudrate": 9600, "slave": 1},  # after Solis
]
```

Samlex is registered after Solis to preserve existing Solis detection behavior.

## Technical Considerations

### Avoiding known bugs — do not repeat these patterns

| Bug (todo) | Pattern to avoid | Correct pattern |
|---|---|---|
| todo #001 | Relying on base class `self.position` (typo: `positon`) | Set `self.position = utils.INVERTER_POSITION` explicitly in `get_settings()` |
| todo #006 | Calling `connect()` on every register read | `_ensure_connected()` guard; connect once |
| todo #007 | Writing power limit inside `read_status_data()` | No writes in `read_status_data()`; use D-Bus callback (out of scope for this driver since no write support) |
| todo #008 | Calling `publish_dbus()` after partial failure | Return `False` from `refresh_data()` on any critical register failure |
| todo #009 | `test_connection()` calling `get_settings()` | `test_connection()` reads only an identity register; `get_settings()` is separate |
| todo #011 | Per-register reads (200–400ms per poll) | Batch all contiguous register blocks from day one |

### `active_power_limit` suppression

The EVO 4024 does not expose a power-limit write over Modbus (scope excluded by brainstorm). Set both `energy_data['overall']['active_power_limit']` and `energy_data['overall']['power_limit']` to `None` in `get_settings()`. This prevents `publish_inverter()` from calling `apply_power_limit()` every tick.

### D-Bus instance numbering

`vebus` devices use device instances in the 257–261 range by convention. Update `default_instance` in `DbusHelper.get_role_instance()` (or its equivalent) to `"vebus:257"` when `SERVICE_PREFIX == "com.victronenergy.vebus"`.

### Fault register to StatusCode mapping

Until the register map is obtained, the Samlex driver will use a conservative mapping:

| Condition | StatusCode |
|---|---|
| Any fault bit set | 10 (Error) |
| No fault, AC output present | 7 (Running) |
| No fault, no AC output | 8 (Standby) |
| Register read failure | 10 (Error) |

This table must be revised once the EVO 4024 fault register bit meanings are known from the Samlex register map.

### `[SAMLEX_REGISTERS]` section structure

Placeholder section to ship in `config.ini`:

```ini
# ============================================================
# SAMLEX EVO 4024 REGISTER MAP
# ============================================================
# Register addresses below are protected by Samlex NDA.
# To obtain the "Modbus Communication Protocol Guide":
#   Phone: 604-525-3836
#   Email: techsupport@samlexamerica.com
#   Explain you are integrating with a custom monitoring
#   system (e.g., VenusOS). An NDA may be required.
#
# Leave values as "???" to skip Samlex during auto-detection.
# ============================================================
[SAMLEX_REGISTERS]
# AC output
REG_AC_OUT_VOLTAGE    = ???
REG_AC_OUT_CURRENT    = ???
REG_AC_OUT_POWER      = ???
SCALE_AC_OUT_VOLTAGE  = ???
SCALE_AC_OUT_CURRENT  = ???
SCALE_AC_OUT_POWER    = ???
# DC / battery
REG_DC_VOLTAGE        = ???
REG_DC_CURRENT        = ???
REG_SOC               = ???
SCALE_DC_VOLTAGE      = ???
SCALE_DC_CURRENT      = ???
# AC input
REG_AC_IN_VOLTAGE     = ???
REG_AC_IN_CURRENT     = ???
REG_AC_IN_CONNECTED   = ???
SCALE_AC_IN_VOLTAGE   = ???
SCALE_AC_IN_CURRENT   = ???
# Status / fault
REG_FAULT             = ???
REG_CHARGE_STATE      = ???
REG_IDENTITY          = ???
IDENTITY_VALUE        = ???
```

The exact keys will be known once the register map is in hand. `REQUIRED_SAMLEX_REGISTERS` in `samlex.py` mirrors this list.

## System-Wide Impact

- **Interaction graph:** `test_connection()` runs inside `get_inverter()` for each type in `_REAL_INVERTER_TYPES`. Adding Samlex adds one more Modbus probe during auto-detection. If `[SAMLEX_REGISTERS]` is unconfigured (public repo default), this probe returns `False` immediately with no I/O — negligible overhead.

- **`dbushelper.py` is shared:** The service type and D-Bus path changes affect the helper used by Solis and Dummy. A regression test must be written for the existing service name (`pvinverter`) before touching `dbushelper.py`.

- **Error propagation:** `refresh_data()` returning `False` increments the error counter in `publish_inverter()`. The existing 10-failure offline flag and 60-failure quit threshold are inherited without change. Samlex has more register groups than Solis; batch-read design ensures a single failed batch returns `False` for the entire poll cycle rather than publishing mixed-freshness data (mitigating todo #008 for this driver).

- **State lifecycle:** No persistent state outside `energy_data`. Reconnection is handled by `_ensure_connected()` at the start of each poll batch. No orphan state on restart.

## Acceptance Criteria

- [ ] A1. `samlex.py` class named `Samlex` extends `Inverter`, implements `test_connection()`, `get_settings()`, and `refresh_data()` *(R1)*
- [ ] A2. `test_connection()` returns `False` immediately when any `[SAMLEX_REGISTERS]` key is missing or equals `???` — no Modbus I/O attempted *(R9)*
- [ ] A3. `test_connection()` reads the identity register and confirms the value matches `IDENTITY_VALUE`; returns `False` on mismatch or `IOError` *(R1)*
- [ ] A4. AC output voltage, current, and power are published to `/Ac/Out/L1/V`, `/Ac/Out/L1/I`, `/Ac/Out/L1/P` *(R2)*
- [ ] A5. DC voltage, current, and SOC are published to `/Dc/0/Voltage`, `/Dc/0/Current`, `/Soc` *(R3)*
- [ ] A6. AC input connected status and power are published to `/Ac/ActiveIn/Connected`, `/Ac/ActiveIn/L1/V`, `/Ac/ActiveIn/L1/P` *(R4)*
- [ ] A7. Fault register is read and mapped to `/State`; any fault bit → StatusCode 10 *(R5)*
- [ ] A8. `Samlex` is in `_REAL_INVERTER_TYPES` after `Solis`; `TYPE=Samlex` in config selects it explicitly *(R6)*
- [ ] A9. `config.ini` includes the `[SAMLEX_REGISTERS]` section with `???` placeholders and the Samlex support comment block (phone + email + NDA note) *(R7, R8)*
- [ ] A10. Existing Solis and Dummy auto-detection is not affected when `[SAMLEX_REGISTERS]` has placeholder values *(R9)*
- [ ] A11. `DbusHelper` uses `SERVICE_PREFIX = "com.victronenergy.pvinverter"` for Solis/Dummy and `"com.victronenergy.vebus"` for Samlex
- [ ] A12. Tests pass for: config validation gate (R9), identity register matching, AC/DC data fields, status mapping, dbushelper service name selection
- [ ] A13. `ruff check` passes; `pytest --cov-fail-under=80` passes (CI threshold)

## Dependencies & Risks

**Dependency:** Register map from Samlex — required to fill in actual register addresses before the driver can be tested on hardware. Code and tests can be written and verified structurally without it; real-hardware testing requires it.

**Risk — `dbushelper.py` service type change:** This is the highest-risk change as it touches the shared helper. Mitigation: write a service-name regression test first (before any `dbushelper.py` edits), then make the change and confirm the test still passes.

**Risk — vebus path naming:** Path names for `com.victronenergy.vebus` differ from `pvinverter` (e.g., `/Ac/Out/L1/V` vs `/Ac/L1/Voltage`). Publishing to wrong paths causes silent data loss in VenusOS. Mitigation: validate against the Victron dbus wiki and `dbus_modbustcp/attributes.csv` before writing path strings.

**Risk — VRM portal registration:** `com.victronenergy.vebus` devices need a device instance in the 257–261 range and may trigger VRM energy flow diagrams. If the instance range is wrong, multiple vebus devices on the same GX could conflict. Mitigation: document the instance range and test on a dev VenusOS instance before shipping.

**Risk — Samlex hardware unavailable for testing:** The driver can be unit-tested with mocks, but end-to-end verification requires the EVO 4024 on a serial port. Structural correctness (config validation, data math, status mapping) is fully testable without hardware.

## Files to Create or Modify

| File | Change |
|---|---|
| `etc/dbus-serialinverter/samlex.py` | **Create** — new driver class |
| `etc/dbus-serialinverter/inverter.py` | **Modify** — add `SERVICE_PREFIX`, extend `energy_data` with `dc` and `ac_in` sub-dicts |
| `etc/dbus-serialinverter/dbushelper.py` | **Modify** — service name from `SERVICE_PREFIX`, conditional D-Bus path registration for vebus paths, conditional `publish_dbus()` for DC/AC-in data |
| `etc/dbus-serialinverter/config.ini` | **Modify** — add `[SAMLEX_REGISTERS]` section with comment block and `???` placeholders |
| `etc/dbus-serialinverter/utils.py` | **Modify** — parse `[SAMLEX_REGISTERS]` with safe fallback access; export constants or expose `config` object |
| `etc/dbus-serialinverter/dbus-serialinverter.py` | **Modify** — import `Samlex`, add to `_REAL_INVERTER_TYPES` after `Solis` |
| `tests/conftest.py` | **Modify** — extend utils stub to expose a `configparser` object with `[SAMLEX_REGISTERS]` section for test injection |
| `tests/test_030_samlex_config_gate.py` | **Create** — tests for R9: missing section, `???` values, non-numeric values, all-valid path |
| `tests/test_031_samlex_test_connection.py` | **Create** — identity register match, mismatch, IOError |
| `tests/test_032_samlex_get_settings.py` | **Create** — settings populated correctly, register failure path |
| `tests/test_033_samlex_refresh_data.py` | **Create** — AC/DC/AC-in fields, scaling, batch failure → False, fault mapping |
| `tests/test_034_dbushelper_service_type.py` | **Create** — regression: pvinverter prefix for Solis; vebus prefix for Samlex |

## Outstanding Questions (Deferred to Implementation)

- **[Needs register map]** Exact register addresses, data types, count of contiguous blocks — determines `_read_batch()` call sites in `refresh_data()`
- **[Needs register map]** Fault register bit field meanings — determines StatusCode mapping table
- **[Needs register map]** Whether SOC is a direct register or must be derived from DC voltage
- **[Needs register map]** Whether the EVO 4024 reports frequency on AC output or AC input
- **[Technical]** Confirm correct VRM device instance range for `com.victronenergy.vebus` on VenusOS Large (expected: 257–261)
- **[Technical]** Whether `SettingsDevice` `default_instance` key format differs for `vebus` vs `pvinverter`

## Sources

### Origin

- **Origin document:** [docs/brainstorms/2026-03-18-samlex-evo-4024-requirements.md](../brainstorms/2026-03-18-samlex-evo-4024-requirements.md)
  - Key decisions carried forward: Modbus RTU over RS485 (reuse pymodbus), read-only monitoring first, register map externalized in config.ini, `???` → silent skip in auto-detection
  - **Correction:** origin specified `com.victronenergy.inverter`; research confirms `com.victronenergy.vebus` is the correct service type for a multi-mode inverter/charger

### Internal References

- Abstract base class: `etc/dbus-serialinverter/inverter.py:13` — constructor signature and `energy_data` structure
- Solis driver (reference implementation): `etc/dbus-serialinverter/solis.py`
  - `test_connection()` pattern: `solis.py:31–47`
  - `_ensure_connected()` pattern: `solis.py:93–97`
  - `_read_batch()` pattern: `solis.py:157–167`
  - `read_status_data()` batch pattern: `solis.py:169–261`
- D-Bus helper: `etc/dbus-serialinverter/dbushelper.py`
  - Service name construction: `dbushelper.py:43–47`
  - `setup_vedbus()` path registration: `dbushelper.py:78–129`
  - `publish_dbus()`: `dbushelper.py:161–177`
- Config parsing: `etc/dbus-serialinverter/utils.py:16–19`
- Driver registration: `etc/dbus-serialinverter/dbus-serialinverter.py:23–25`
- Test stub pattern: `tests/conftest.py`, `tests/test_011_solis_status_mapping.py`

### External References

- Victron D-Bus service types: https://github.com/victronenergy/venus/wiki/dbus
- Victron D-Bus API (mandatory paths): https://github.com/victronenergy/venus/wiki/dbus-api
- Modbus TCP register list (paths by service type): https://github.com/victronenergy/dbus_modbustcp/blob/master/attributes.csv
- Real-world vebus third-party driver: https://github.com/madsci1016/SMAVenusDriver
- Samlex support: techsupport@samlexamerica.com / 604-525-3836 (request "Modbus Communication Protocol Guide"; NDA likely required)
