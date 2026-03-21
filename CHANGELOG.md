# Changelog

All notable changes to this project will be documented in this file.

Starting with tagged releases (`v*`), release notes are generated automatically from commits since the previous tag and published in GitHub Releases.

## Unreleased

### Feature: VE.Bus (vebus) inverter/charger support

- Added `com.victronenergy.vebus` service type for multi-mode inverter/chargers (Samlex EVO),
  separate from the existing `com.victronenergy.pvinverter` path used by grid-tie solar inverters.
- Publishes full VRM dashboard data: AC output, AC input (shore power), DC/battery, SOC,
  inverter state, and charge state.
- Registered `/Settings/SystemSetup/AcInput1` via SettingsDevice so systemcalc recognizes
  the AC input source type (default: Grid).
- Added `/Ac/State/AcIn1Available` and `/Ac/ActiveIn/ActiveInput` paths required for VRM
  to render the AC Input panel correctly.

### Feature: SamlexTCP driver and Modbus TCP testing infrastructure

- Added `samlex_tcp.py` driver supporting `tcp://host:port` connections for network-attached
  Samlex inverters.
- Added `samlex_tcp_server.py` — a Modbus TCP server simulating Samlex EVO registers for
  hardware-free testing with multiple scenarios (normal, fault, low_battery, ac_disconnect,
  heavy_load, heavy_load_with_input, heavy_load_battery).
- TCP server register map driven from `config.ini` (single source of truth for addresses
  and scale factors).
- D-Bus object paths and service names sanitized for `tcp://` port strings.

### Fix: VRM dashboard widget rendering

- Fixed VRM DC/AC widgets blanking by coalescing `None` values to `0` on all D-Bus paths.
  The vebus spec requires numeric values — `None` causes VRM widgets to go blank.
- Fixed `/State` derivation and `/VebusChargeState` translation for correct inverter state
  display (Inverting, Bulk, Absorption, Float, etc.).
- Fixed signed int16 handling for DC current so negative (discharging) values display correctly.
- Fixed missing AC input power and DC power calculations in `publish_dbus()`.

### Feature: Private configuration support for Samlex EVO

- Added two-file configuration system for NDA-protected register values:
  - `config.ini` — Template with placeholder values (`???`), safe to commit
  - `config.ini.private` — Actual register values, git-ignored and never committed
- Updated `utils.py` to load `config.ini.private` if present, overlaying template values
- Updated `samlex.py` to interpret working status register correctly (value == 1 means AC input normal)
- Updated `docs/samlex.md` with new configuration workflow and illustrative register examples
- Added `config.ini.private` to `.gitignore` to prevent accidental commits of NDA-protected data

### Fix

- Eliminated `WARNING: USING OUTDATED REGISTRATION METHOD!` on startup by passing `register=False`
  to `VeDbusService` and calling `register()` explicitly after all mandatory D-Bus paths are added.
- Fixed `shift: 2: shift count out of range` boot error in `start-serialinverter.sh`: supply a
  default baud rate of 9600 when serial-starter passes only one argument, satisfying the two-arg
  contract expected by Victron's `run-service.sh`.
- Fixed `install.sh` not ensuring the serial-starter service mapping existed; installer now creates
  or amends `/data/conf/serial-starter.d` with the required `sinv→sinverter→dbus-serialinverter`
  entries idempotently and aborts with a clear error if the mapping cannot be verified.

### Feature set: Reliability and runtime hardening

- Strengthened startup/config validation and runtime safeguards, including MAX_AC_POWER validation,
  safer poll execution, refresh/publish gating, and explicit fatal-signal propagation.
- Improved Modbus handling with connection reuse, response-size checks, register address bounds,
  safer power-limit behavior, and clearer decoding/formatting paths.

### Feature set: Test coverage and verification expansion

- Added and expanded comprehensive tests across inverter base behavior, dbushelper lifecycle,
  Solis/Samlex paths, GLib integration, and regression coverage.
- Coverage tooling and policy were reinforced to keep quality gates strict and stable.

### Feature set: Samlex support and Modbus architecture

- Introduced Samlex EVO 4024 support and follow-up improvements for batching and robustness.
- Refactored shared inverter communication logic by extracting a reusable Modbus base.


### Feature set: CI, developer workflow, and docs

- Added CI + lint automation and improved local development ergonomics with conda/GLib guidance.
- Added/updated contributor-facing docs and repository process files.


### Feature set: Release automation (local changes pending release)

- Added a tag-triggered GitHub Actions release workflow for `v*` tags.
- Added release artifacts containing only `conf/` and `etc/` with SHA256 checksums.
- Added automatic release-note generation from git history since the previous tag.
- Added a generated `CHANGELOG-<tag>.md` file to each GitHub Release.

## v0.1.0 (Mar 24, 2023)

### Included commits

- initial commit
- add dummy inverter for testing
- some code cleanup
