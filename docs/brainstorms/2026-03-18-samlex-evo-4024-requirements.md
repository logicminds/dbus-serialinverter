---
date: 2026-03-18
topic: samlex-evo-4024-support
---

# Samlex EVO 4024 Inverter/Charger Support

## Problem Frame

The dbus-serialinverter project currently only supports the Solis Mini 700 4G PV inverter. The user has a Samlex EVO 4024 inverter/charger (24V, 4000W, single-phase) and wants to monitor it on VenusOS via the same D-Bus integration. The EVO 4024 uses Modbus RTU over RS485, so the underlying communication infrastructure carries over — but a new driver and potentially expanded D-Bus paths are required.

## Requirements

- R1. A new `samlex.py` driver class extends `Inverter` and implements `test_connection()`, `get_settings()`, and `refresh_data()` using the EVO 4024's Modbus register map.
- R2. The driver reads and publishes AC output data: voltage, current, and power on the active phase (L1 for single-phase).
- R3. The driver reads and publishes battery data: DC voltage, DC current, and state of charge.
- R4. The driver reads and publishes AC input status: whether shore/generator power is connected and current charging state.
- R5. The driver reads and publishes fault/alarm status mapped to a VenusOS `StatusCode`.
- R6. The driver is registered in `supported_inverter_types` so it participates in auto-detection at startup.
- R7. `config.ini` is updated with appropriate defaults for the EVO 4024 (baud rate, slave ID, max AC power = 4000W, phase = L1).
- R8. All Modbus register addresses and scaling factors are stored in a `[SAMLEX_REGISTERS]` section of `config.ini`, not hardcoded in `samlex.py`. The public repo ships with `???` placeholder values showing the structure; users fill in real values privately. The section must include commented instructions explaining how to obtain the register map from Samlex (phone, email, and NDA context — see Dependencies).
- R9. If any `[SAMLEX_REGISTERS]` entry is missing or still set to `???`, `test_connection()` returns `False` — Samlex is silently skipped in auto-detection. No error is raised; other inverter types continue to be tried.

## Success Criteria

- The EVO 4024 is auto-detected on startup via `test_connection()` reading a known identification register.
- AC output, battery, AC input, and fault data are visible in VenusOS after connection.
- The driver coexists with the Solis driver; neither interferes with the other's auto-detection.

## Scope Boundaries

- No write/control operations (e.g., remote on/off, charge current setpoint) in this phase — read-only monitoring only.
- No 3-phase support; EVO 4024 is single-phase.
- Power limit write-back (as implemented for Solis) is out of scope unless the register map reveals a direct equivalent.

## Key Decisions

- **Modbus RTU over RS485**: Confirmed by user. Existing pymodbus stack is reused without changes.
- **Single-phase (L1)**: EVO 4024 is a single-phase device; L2/L3 paths will be zero or omitted.
- **Read-only first**: Scope is limited to monitoring; control commands deferred.
- **VenusOS service type: `com.victronenergy.inverter`**: Correct device class for a battery inverter/charger. Supports DC/battery paths. `dbushelper.py` will need new paths for battery voltage, current, SOC, and AC input status; the service name prefix will change from `pvinverter` to `inverter`.
- **Register map externalized in config.ini**: `[SAMLEX_REGISTERS]` section holds all addresses and scaling values. Driver code is publishable; actual values remain private. Repo ships with `???` placeholders.
- **Unconfigured registers → silent skip**: `test_connection()` checks for unconfigured registers first and returns `False` if any are missing/placeholder — preserves auto-detection behavior for users without a Samlex inverter.

## Dependencies / Assumptions

- **Modbus register map**: Available from Samlex as the "Modbus Communication Protocol Guide." To obtain it:
  - Call **604-525-3836** and ask for the Modbus Communication Protocol Guide for the EVO 4024.
  - Or email **techsupport@samlexamerica.com** — explain you are integrating the unit into a custom monitoring system (e.g., VenusOS).
  - Samlex may require signing an NDA before releasing the guide. The actual register values must be kept private (not committed to the public repo) as a result.
- Serial parameters (baud rate, parity, stop bits, slave ID) must be confirmed from the EVO 4024 manual or Samlex support. Assumed 9600 8N1, slave ID 1, until confirmed.
- The EVO 4024 exposes battery SOC directly via a Modbus register (common for inverter/chargers, but not guaranteed — may require a separate battery monitor register or calculation).

## Outstanding Questions

### Deferred to Planning

- **[Affects R1][Needs research]** Exact Modbus register addresses, data types, and scaling for all required data points — depends on register map from Samlex.
- **[Affects R1][Needs research]** Serial parameters (baud rate, parity, stop bits, slave ID) — confirm from EVO 4024 manual.
- **[Affects R3][Needs research]** Whether EVO 4024 exposes battery SOC as a Modbus register or whether it must be derived from voltage.
- **[Affects dbushelper.py][Technical]** If service type changes from `pvinverter`, `dbushelper.py` will need new D-Bus paths for DC/battery and AC input data — assess the extent of changes required.

## Next Steps

→ Obtain Modbus register map from Samlex (to fill in `[SAMLEX_REGISTERS]` values)
→ `/ce:plan` — planning can now proceed without the register map values, since they are externalized
