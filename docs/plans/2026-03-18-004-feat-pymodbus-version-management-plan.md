---
title: "feat: Pymodbus Version Management and Upgrade Script"
type: feat
status: completed
date: 2026-03-18
origin: docs/brainstorms/2026-03-18-pymodbus-upgrade-script-requirements.md
---

# feat: Pymodbus Version Management and Upgrade Script

## Overview

Add `tools/update_pymodbus.py` — a developer-side script that manages the vendored pymodbus
library. The script downloads a new version from PyPI into a versioned subdirectory
(`pymodbus-<version>/`), creates a **temporary symlink** `pymodbus → pymodbus-<version>/`
for testing, then either promotes (collapses the symlink into a plain `pymodbus/` directory)
or rolls back (restores the previous plain directory). Production always ends up with a plain
`pymodbus/` — no permanent symlinks, no `install.sh` changes required.

Target upgrade: vendored pymodbus **3.1.3** → **3.12.1** (latest stable, released
2026-02-19). Three breaking API changes in `solis.py` must be addressed alongside the vendor
swap.

## CLI Design

```
python tools/update_pymodbus.py [--version X.Y.Z]   # fetch + test (creates temp symlink)
python tools/update_pymodbus.py --promote            # make new version permanent
python tools/update_pymodbus.py --rollback           # revert to previous version
python tools/update_pymodbus.py --status             # show active version and disk usage
```

## Workflow

```
Before:   pymodbus/               ← plain directory, 3.1.3

Step 1 (update --version 3.12.1):
          pymodbus → pymodbus-3.12.1/   ← temp symlink for testing
          pymodbus-3.1.3/               ← backup of previous pymodbus/
          pymodbus-3.12.1/              ← newly downloaded

Step 2a (--promote, tests passed):
          pymodbus/               ← plain directory, 3.12.1 (symlink removed, dir renamed)
          pymodbus-3.1.3/         ← retained for reference; operator may delete manually

Step 2b (--rollback, tests failed):
          pymodbus/               ← plain directory, 3.1.3 restored (symlink removed)
          pymodbus-3.12.1/        ← retained for debugging; operator may delete manually
```

The repo is only committed in the post-promote or post-rollback state — always a plain
`pymodbus/` directory.

## Problem Statement / Motivation

The driver vendors pymodbus 3.1.3 as a plain directory with no mechanism to upgrade or roll
back safely. Pymodbus 3.12.1 brings bug fixes and Python 3.12 alignment, but three hard
breaking changes affect `solis.py`:

| API | 3.1.3 | 3.12.1 | Removed in |
|---|---|---|---|
| `ModbusSerialClient(method='rtu', ...)` | Works (via `**kwargs`) | `TypeError` | 3.7.0 |
| `from pymodbus.constants import Endian` / `Endian.Big` | Works | `ImportError` | 3.10.0 |
| `from pymodbus.payload import BinaryPayloadDecoder` | Works | `ImportError` | 3.10.0 |
| `slave=` kwarg on read/write | Works | Must use `device_id=` | 3.10.0 |

(See origin: docs/brainstorms/2026-03-18-pymodbus-upgrade-script-requirements.md)

## Technical Approach

### Pymodbus Distribution Format

pymodbus 3.12.1 is distributed as a **pure Python wheel** (`py3-none-any.whl`). A wheel is
a zip archive. Extraction only needs stdlib:

```python
subprocess.run(["pip", "download", "--no-deps", f"pymodbus=={version}",
                "-d", str(tmp_dir)], check=True)
# find the .whl file in tmp_dir
with zipfile.ZipFile(whl_path) as z:
    members = [m for m in z.namelist() if m.startswith("pymodbus/")]
    z.extractall(versioned_dir.parent, members)
# Result: etc/dbus-serialinverter/pymodbus-3.12.1/
```

`pip download` runs on the developer machine. No pip activity on VenusOS.

### Version Resolution

When `--version` is omitted, query PyPI JSON API:

```python
url = "https://pypi.org/pypi/pymodbus/json"
data = json.loads(urllib.request.urlopen(url).read())
version = data["info"]["version"]  # latest stable, pre-releases excluded
```

Validate that the resolved version string contains no `rc`, `a`, `b`, or `dev` suffix.

### Symlink Mechanics

```python
# Atomic swap: never leave pymodbus/ absent
tmp_link = driver_dir / "pymodbus.new"
os.symlink(f"pymodbus-{version}", tmp_link)   # relative symlink
os.replace(tmp_link, driver_dir / "pymodbus") # atomic rename
```

Relative symlinks survive any directory copy (including `install.sh` scenarios if symlink
is ever left in place, though production promote always removes it).

### Promote

```python
symlink = driver_dir / "pymodbus"
target = driver_dir / f"pymodbus-{active_version}"
symlink.unlink()                           # remove temp symlink
target.rename(driver_dir / "pymodbus")    # rename versioned dir to canonical name
```

### Rollback

```python
symlink = driver_dir / "pymodbus"
backup = driver_dir / f"pymodbus-{previous_version}"
symlink.unlink()                           # remove temp symlink
backup.rename(driver_dir / "pymodbus")    # restore backup
```

### State Tracking

The script writes a small JSON state file (`etc/dbus-serialinverter/.pymodbus-state.json`)
to track the current testing state:

```json
{
  "mode": "testing",         // or "stable"
  "active_version": "3.12.1",
  "previous_version": "3.1.3"
}
```

This lets `--promote` and `--rollback` know which directories to operate on without
requiring the developer to re-specify the version. The state file is `.gitignore`-listed
since it reflects transient testing state.

### Test Gate

The test suite stubs all pymodbus imports via `conftest.py`, so pytest alone cannot
validate that the vendored library is importable. The script runs a **subprocess smoke
test first**, then pytest:

```python
# Smoke test (fresh process, no conftest.py interference)
subprocess.run([
    sys.executable, "-c",
    "import sys; sys.path.insert(0, 'etc/dbus-serialinverter/pymodbus');"
    "from pymodbus.client import ModbusSerialClient; print('smoke ok')"
], check=True, cwd=repo_root)

# Full test suite
subprocess.run([sys.executable, "-m", "pytest", "tests/", "-v", "--tb=short"],
               cwd=repo_root)
```

### ruff.toml Update

`ruff.toml` currently excludes `etc/dbus-serialinverter/pymodbus`. The versioned backup
directories (`pymodbus-3.1.3/` etc.) also contain third-party code. Update to:

```toml
exclude = [
    "etc/dbus-serialinverter/pymodbus",
    "etc/dbus-serialinverter/pymodbus-*/",
]
```

The script applies this update automatically when creating the first versioned directory.

### pymodbus 3.12.1 API Changes Required in `solis.py`

All changes are confined to `etc/dbus-serialinverter/solis.py`:

| Location | Current (3.1.3) | Required (3.12.1) |
|---|---|---|
| Line 8 | `from pymodbus.constants import Endian` | **Remove** |
| Line 9 | `from pymodbus.payload import BinaryPayloadDecoder` | **Remove** |
| Line 18 | `ModbusSerialClient(method='rtu', port=port, ...)` | `ModbusSerialClient(port, baudrate=..., ...)` — `port` is positional, `method=` gone |
| Lines 53, 94, 130, 152 | `slave=self.slave` | `device_id=self.slave` |
| Lines 99, 167 | `BinaryPayloadDecoder.fromRegisters(regs, Endian.Big).decode_*()` | `ModbusSerialClient.convert_from_registers(regs[0:N], ModbusSerialClient.DATATYPE.TYPE, word_order="big")` |

DATATYPE mapping:
- `decode_16bit_uint()` (1 reg) → `DATATYPE.UINT16`, slice `[0:1]`
- `decode_32bit_uint()` (2 regs) → `DATATYPE.UINT32`, slice `[0:2]`
- `decode_32bit_float()` (2 regs) → `DATATYPE.FLOAT32`, slice `[0:2]`
- `decode_string(8)` → `DATATYPE.STRING`, full registers slice

`samlex.py` only needs the constructor fix (`method='rtu'` removal, lines 44-52).

`conftest.py` stub for `BinaryPayloadDecoder.fromRegisters` (lines 85-92) must be updated
to match new solis.py call sites after the API migration.

### stdlib-Only Constraint

The script uses only Python standard library except for invoking `pip download` as a
subprocess on the developer machine:

- `urllib.request` — PyPI JSON API
- `json` — parse version response
- `zipfile` — extract wheel
- `os`, `pathlib` — filesystem and symlink ops
- `subprocess` — pip download, smoke test, pytest
- `argparse` — CLI
- `shutil` — temp dir cleanup
- `tempfile` — download staging area

## Acceptance Criteria

### Script

- [ ] `python tools/update_pymodbus.py --version 3.12.1` backs up current `pymodbus/` to
  `pymodbus-3.1.3/`, downloads + extracts 3.12.1 to `pymodbus-3.12.1/`, creates temp
  symlink, runs smoke test and pytest, reports both results
- [ ] `python tools/update_pymodbus.py` (no `--version`) resolves latest stable from PyPI
- [ ] Re-running with the same version when `pymodbus-X.Y.Z/` already exists skips download
- [ ] `python tools/update_pymodbus.py --promote` removes symlink, renames versioned dir to
  `pymodbus/`, updates state file to `stable`
- [ ] `python tools/update_pymodbus.py --rollback` removes symlink, restores previous
  `pymodbus/` from backup
- [ ] `python tools/update_pymodbus.py --status` prints active version, mode
  (stable/testing), and all retained versioned directories with disk usage
- [ ] `.pymodbus-state.json` is created/updated at each stage; added to `.gitignore`
- [ ] Temp download files are cleaned up on both success and failure
- [ ] Script fails clearly with a helpful message if: version not found on PyPI, network
  error, `--promote`/`--rollback` called when not in testing mode

### Migration (one-time, auto-detected)

- [ ] Script detects whether a `.pymodbus-state.json` exists; if not, treats current
  `pymodbus/` as 3.1.3 and initializes stable state

### ruff.toml

- [ ] Script updates `ruff.toml` exclusion to cover `etc/dbus-serialinverter/pymodbus-*/`
  on first versioned directory creation (idempotent)

### Driver API (`solis.py` migration to 3.12.1)

- [ ] `method='rtu'` removed; `port` passed as first positional arg
- [ ] `from pymodbus.constants import Endian` and
  `from pymodbus.payload import BinaryPayloadDecoder` removed
- [ ] All `slave=self.slave` renamed to `device_id=self.slave`
- [ ] `BinaryPayloadDecoder.fromRegisters(...).decode_*()` chains replaced with
  `ModbusSerialClient.convert_from_registers(regs[0:N], DATATYPE.*, word_order="big")`
- [ ] `samlex.py` constructor fixed (remove `method='rtu'`)
- [ ] `conftest.py` stub updated to match new solis.py call sites
- [ ] All existing tests pass; CI `--cov-fail-under=80` maintained

## Dependencies & Risks

| Risk | Mitigation |
|---|---|
| `pip` not available on developer machine | Unlikely; document as prerequisite |
| PyPI unreachable | Clear error message + exit non-zero |
| Partial versioned dir (aborted download) | Check for `__init__.py` before trusting cached dir |
| `convert_from_registers` register slice count wrong | Map each `decode_*` to correct count in code and verify with test stubs |
| State file out of sync | `--status` displays raw filesystem state alongside state file for cross-check |
| Versioned dirs accumulate on disk | `--status` shows disk usage; operator deletes manually |

## Files to Create / Modify

| File | Change |
|---|---|
| `tools/update_pymodbus.py` | **Create** — main script |
| `tools/__init__.py` | **Create** — empty, makes tools a package (optional) |
| `etc/dbus-serialinverter/solis.py` | **Modify** — pymodbus 3.12.1 API migration |
| `etc/dbus-serialinverter/samlex.py` | **Modify** — remove `method='rtu'` from constructor |
| `tests/conftest.py` | **Modify** — update BinaryPayloadDecoder stub after solis.py migration |
| `ruff.toml` | **Modify** — extend pymodbus exclusion to versioned dirs |
| `.gitignore` | **Modify** — add `.pymodbus-state.json` and `pymodbus-*/` patterns |

## Sources & References

### Origin

- **Origin document:** [docs/brainstorms/2026-03-18-pymodbus-upgrade-script-requirements.md](../brainstorms/2026-03-18-pymodbus-upgrade-script-requirements.md)
  Key decisions: symlink as temporary test scaffold (not permanent), plain `pymodbus/` in
  production (install.sh unchanged), full package vendored, test gate supplemented by
  subprocess smoke test.

### Internal References

- `etc/dbus-serialinverter/utils.py:13` — sys.path insert (unchanged)
- `etc/dbus-serialinverter/install.sh:21` — `cp -rf pymodbus` (no change needed)
- `etc/dbus-serialinverter/solis.py:7-9,18,53,94,99,130,152,167` — all pymodbus call sites
- `etc/dbus-serialinverter/samlex.py:44-52` — ModbusSerialClient constructor
- `tests/conftest.py:62-94` — pymodbus stub setup
- `ruff.toml:6` — current pymodbus exclusion
- `etc/dbus-serialinverter/pymodbus/version.py:40` — vendored version declaration

### External References

- pymodbus 3.12.1 on PyPI: https://pypi.org/project/pymodbus/
- Official API changes guide: https://pymodbus.readthedocs.io/en/stable/source/api_changes.html
- BinaryPayloadDecoder removal discussion: https://github.com/pymodbus-dev/pymodbus/discussions/2525
- `convert_from_registers` usage: https://github.com/pymodbus-dev/pymodbus/discussions/2554
