---
date: 2026-03-18
topic: pymodbus-upgrade-script
---

# Pymodbus Version Management and Upgrade Script

## Problem Frame

The driver vendors pymodbus 3.1.3 as a plain directory at
`etc/dbus-serialinverter/pymodbus/`. When a newer pymodbus version is needed,
there is no mechanism to download, install, or swap versions without manually
replacing files. Additionally, pymodbus has had breaking API changes between
3.1.3 and later 3.x releases (e.g. `ModbusSerialClient` constructor signature,
`BinaryPayloadDecoder` removal), so any upgrade must be paired with a
compatibility check.

The target environment is VenusOS 3.7.1 with Python 3.12.1, which lifts any
Python version ceiling — the latest pymodbus is viable.

## Requirements

- R1. A script in `tools/` downloads a specified pymodbus version from PyPI,
  extracts the full package into a versioned subdirectory
  (`etc/dbus-serialinverter/pymodbus-<version>/`), and creates a temporary
  symlink `pymodbus → pymodbus-<version>/` for testing purposes. The existing
  `pymodbus/` directory is first backed up to `pymodbus-<current-version>/`.
- R2. The symlink is temporary — it exists only during the test window. Once
  the developer is satisfied, they run a `--promote` command that removes the
  symlink and renames the versioned directory to become the new plain
  `pymodbus/` directory. If testing fails, a `--rollback` command removes the
  symlink and restores the previous plain `pymodbus/` directory.
- R3. After switching via symlink, the script runs the project's existing test
  suite (`python -m pytest tests/`) and reports pass/fail clearly. No
  auto-fixing of driver code — breakage is surfaced for the developer to
  address.
- R4. The script accepts a `--version` flag; if omitted, it fetches the latest
  stable release from PyPI automatically.
- R5. The full package is vendored (not a trimmed subset), consistent with the
  current approach.

## Success Criteria

- `python tools/update_pymodbus.py --version X.Y.Z` backs up the current
  `pymodbus/`, downloads X.Y.Z to `pymodbus-X.Y.Z/`, creates the temp symlink,
  and runs tests.
- `python tools/update_pymodbus.py --promote` removes the symlink and makes
  `pymodbus-X.Y.Z/` the new canonical `pymodbus/` directory.
- `python tools/update_pymodbus.py --rollback` removes the symlink and
  restores the backed-up previous version as `pymodbus/`.
- The final production state is always a plain `pymodbus/` directory (no
  symlink); `install.sh` requires no changes.
- `python3 -c "from pymodbus.client import ModbusSerialClient"` works from
  `etc/dbus-serialinverter/` at all stages.

## Scope Boundaries

- The script does not auto-fix driver code when API breakage is detected.
- The script does not modify `install.sh` — production always uses a plain
  directory, so install.sh's `cp -rf pymodbus` remains valid.
- The script does not interact with opkg, pip, or system-wide Python packages.
- The symlink is a temporary testing scaffold only, not a permanent production
  structure. Commits should always contain a plain `pymodbus/` directory.

## Key Decisions

- **Symlink as temporary test scaffold, plain directory in production:** The
  symlink allows instant switching during testing without touching `install.sh`
  or git history. Once tests pass, `--promote` collapses it back to a plain
  directory, keeping the repo and deployment simple.
- **Full package vendored:** Avoids fragile manual curation of transitive
  imports each upgrade cycle.
- **Test suite as compatibility gate:** Rather than static analysis of API
  differences, running the existing tests after each switch provides concrete,
  actionable signal (supplemented by a subprocess import smoke test, since the
  test suite stubs all pymodbus imports via conftest.py).
- **No auto-fix:** API migrations require developer judgment; the script's job
  is upgrade plumbing, not code transformation.

## Dependencies / Assumptions

- Python 3.12.1 on VenusOS 3.7.1 — no Python version ceiling on pymodbus
  compatibility.
- PyPI is reachable from the developer workstation running the script (not
  from the VenusOS device itself).
- The script runs on the developer machine; deployment to VenusOS continues
  via `install.sh` unchanged.

## Outstanding Questions

### Resolve Before Planning

_(none — requirements are clear enough to plan)_

### Deferred to Planning

- [Affects R1][Technical] Does `install.sh` need to follow the symlink (copy
  the actual directory contents) rather than copying the symlink itself when
  deploying to `/opt/`?
- [Affects R2][Needs research] Does pymodbus distribute a pure-Python sdist on
  PyPI that can be extracted without `pip install`? If not, the script may need
  to use `pip download --no-deps` + wheel extraction.
- [Affects R4][Needs research] Which specific pymodbus API surface used by
  `solis.py`/`samlex.py` (`method='rtu'`, `BinaryPayloadDecoder`, `slave=`
  kwarg) has breaking changes in the target version? Document required driver
  fixes before or alongside the upgrade.

## Next Steps

→ `/ce:plan` for structured implementation planning
