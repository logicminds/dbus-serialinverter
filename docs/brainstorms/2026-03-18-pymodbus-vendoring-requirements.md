---
date: 2026-03-18
topic: pymodbus-vendoring
---

# Pymodbus Vendoring and sys.path Fix

## Problem Frame

VenusOS ships pymodbus 2.5.3 as a system-wide package. This driver requires the
pymodbus 3.x API, which introduced breaking changes in both import paths and the
client interface (e.g. `from pymodbus.client import ModbusSerialClient` is 3.x only;
2.x used `from pymodbus.client.sync import ModbusSerialClient`).

Because VenusOS has no pip and a read-only root filesystem, there is no standard way
to upgrade the system package. The solution is to vendor pymodbus 3.1.3 directly in
the repo and force it onto sys.path ahead of the system copy.

The original implementation had a bug: each inverter file (`solis.py`, `samlex.py`)
contained a `sys.path.insert` using `os.path.join(__file__, "/opt/...")`. Because the
second argument is an absolute path, `os.path.join` ignores the first argument
entirely — `os.path.dirname(__file__)` was dead weight. The path always resolved to
`/opt/victronenergy/dbus-serialinverter/pymodbus`, which does not exist until
`install.sh` has been run. Running the driver locally without deploying to the device
silently fell back to system pymodbus 2.5.3, causing `ImportError` on the first
pymodbus import.

## Requirements

- R1. The vendored pymodbus directory is resolved relative to the script's own location
  so the driver works both in the development tree and after install on the device.
- R2. The sys.path manipulation happens in exactly one place (`utils.py`), which is
  already the first import in every inverter file.
- R3. Individual inverter files (`solis.py`, `samlex.py`, and any future drivers) must
  not contain their own sys.path manipulation for pymodbus.

## Success Criteria

- `python3 -c "from pymodbus.client import ModbusSerialClient"` succeeds when run from
  `etc/dbus-serialinverter/` without running install.sh first.
- All existing tests continue to pass.
- Any new inverter driver automatically gets the correct pymodbus version by virtue of
  importing utils.

## Scope Boundaries

- This does not upgrade pymodbus from 3.1.3 to a newer version.
- This does not replace opkg or attempt system-wide installation.
- This does not change how install.sh copies pymodbus to /opt/.

## Key Decisions

- **Vendor pymodbus 3.x rather than use the system 2.5.3:** The 2.x→3.x API is not
  backwards-compatible. Upgrading the system package via opkg is fragile across
  firmware updates (opkg installs outside /data/ are wiped). Vendoring is the standard
  pattern for VenusOS community drivers.
- **Centralize in utils.py:** Every inverter file already imports utils before any
  pymodbus import, making utils.py the correct and only place for this side effect.
- **Use os.path.abspath(__file__):** Resolves symlinks and relative invocations
  correctly, unlike the bare `__file__` that was used previously.

## Implementation

Fixed in `utils.py`:

```python
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "pymodbus"))
```

Removed the broken `sys.path.insert` blocks from `solis.py` and `samlex.py`.
