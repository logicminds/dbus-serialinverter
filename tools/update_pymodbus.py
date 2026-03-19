#!/usr/bin/env python3
"""
update_pymodbus.py — Manage the vendored pymodbus library version.

Usage:
  python tools/update_pymodbus.py [--version X.Y.Z]  # download + symlink for testing
  python tools/update_pymodbus.py --promote           # make tested version permanent
  python tools/update_pymodbus.py --rollback          # restore previous version
  python tools/update_pymodbus.py --status            # show current state

Workflow:
  1. Run with --version (or no version for latest stable).
     - Current pymodbus/ is backed up to pymodbus-<current>/.
     - New version is downloaded and extracted to pymodbus-<new>/.
     - A temporary symlink pymodbus -> pymodbus-<new>/ is created.
     - A smoke test and pytest run to check compatibility.
  2. If tests pass: run --promote.
     - Symlink is removed; pymodbus-<new>/ is renamed to pymodbus/.
  3. If tests fail: run --rollback.
     - Symlink is removed; pymodbus-<old>/ is restored as pymodbus/.

The repo is only committed in the post-promote or post-rollback state (plain dir).
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

# ── Paths ─────────────────────────────────────────────────────────────────────

REPO_ROOT = Path(__file__).resolve().parent.parent
DRIVER_DIR = REPO_ROOT / "etc" / "dbus-serialinverter"
PYMODBUS_LINK = DRIVER_DIR / "pymodbus"
STATE_FILE = DRIVER_DIR / ".pymodbus-state.json"
RUFF_TOML = REPO_ROOT / "ruff.toml"
PYPI_API = "https://pypi.org/pypi/pymodbus/json"

# ── State helpers ─────────────────────────────────────────────────────────────


def _read_state():
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {"mode": "stable", "active_version": _detect_stable_version(), "previous_version": None}


def _write_state(state):
    STATE_FILE.write_text(json.dumps(state, indent=2) + "\n")


def _detect_stable_version():
    """Read version from current pymodbus/version.py if it exists."""
    ver_file = PYMODBUS_LINK / "version.py"
    if ver_file.exists():
        text = ver_file.read_text()
        m = re.search(r'Version\("[^"]+",\s*(\d+),\s*(\d+),\s*(\d+)', text)
        if m:
            return f"{m.group(1)}.{m.group(2)}.{m.group(3)}"
    return "unknown"


def _versioned_dir(version):
    return DRIVER_DIR / f"pymodbus-{version}"


# ── PyPI helpers ──────────────────────────────────────────────────────────────


def _fetch_latest_stable():
    print("Querying PyPI for latest stable pymodbus...")
    try:
        with urllib.request.urlopen(PYPI_API, timeout=10) as resp:
            data = json.loads(resp.read())
    except Exception as e:
        print(f"ERROR: Could not reach PyPI: {e}", file=sys.stderr)
        sys.exit(1)
    version = data["info"]["version"]
    # Reject pre-release versions
    if re.search(r"(rc|a|b|dev)", version, re.IGNORECASE):
        print(f"ERROR: Latest PyPI version '{version}' appears to be a pre-release.", file=sys.stderr)
        sys.exit(1)
    print(f"Latest stable: {version}")
    return version


def _download_and_extract(version, target_dir):
    """Download pymodbus wheel from PyPI and extract to target_dir."""
    if target_dir.exists():
        # Validate existing dir has an __init__.py (not a partial extraction)
        if (target_dir / "__init__.py").exists():
            print(f"  {target_dir.name}/ already exists and looks valid — skipping download.")
            return
        else:
            print(f"  WARNING: {target_dir.name}/ exists but looks incomplete — re-extracting.")
            shutil.rmtree(target_dir)

    with tempfile.TemporaryDirectory(prefix="pymodbus_dl_") as tmp:
        tmp_path = Path(tmp)
        print(f"  Downloading pymodbus=={version} from PyPI...")
        try:
            subprocess.run(
                [sys.executable, "-m", "pip", "download", "--no-deps",
                 f"pymodbus=={version}", "-d", str(tmp_path)],
                check=True,
                capture_output=True,
            )
        except subprocess.CalledProcessError as e:
            print(f"ERROR: pip download failed:\n{e.stderr.decode()}", file=sys.stderr)
            sys.exit(1)

        whl_files = list(tmp_path.glob("pymodbus-*.whl"))
        if not whl_files:
            print("ERROR: No wheel file found after download.", file=sys.stderr)
            sys.exit(1)
        whl = whl_files[0]
        print(f"  Extracting {whl.name}...")

        target_dir.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(whl) as z:
            members = [m for m in z.namelist() if m.startswith("pymodbus/")]
            if not members:
                print("ERROR: Wheel does not contain a pymodbus/ directory.", file=sys.stderr)
                sys.exit(1)
            z.extractall(DRIVER_DIR, members)

        # The wheel extracts to DRIVER_DIR/pymodbus/; rename to versioned dir
        extracted = DRIVER_DIR / "pymodbus"
        if not extracted.exists():
            print("ERROR: Extraction produced no pymodbus/ directory.", file=sys.stderr)
            sys.exit(1)
        extracted.rename(target_dir)
        print(f"  Extracted to {target_dir.name}/")


def _ensure_ruff_excludes_versioned():
    """Add pymodbus-*/ glob to ruff.toml exclusions if not already present."""
    if not RUFF_TOML.exists():
        return
    content = RUFF_TOML.read_text()
    if "pymodbus-*/" in content:
        return
    # Insert the new exclusion alongside the existing one
    content = content.replace(
        '"etc/dbus-serialinverter/pymodbus"',
        '"etc/dbus-serialinverter/pymodbus",\n    "etc/dbus-serialinverter/pymodbus-*/",',
    )
    RUFF_TOML.write_text(content)
    print("  Updated ruff.toml to exclude pymodbus-*/ directories.")


# ── Symlink helpers ───────────────────────────────────────────────────────────


def _set_symlink(target_version):
    """Atomically point PYMODBUS_LINK at pymodbus-<target_version>/ (relative symlink)."""
    rel_target = f"pymodbus-{target_version}"
    tmp_link = DRIVER_DIR / "pymodbus.new"
    if tmp_link.exists() or tmp_link.is_symlink():
        tmp_link.unlink()
    os.symlink(rel_target, tmp_link)
    os.replace(tmp_link, PYMODBUS_LINK)
    print(f"  Symlink: pymodbus -> {rel_target}/")


def _remove_symlink():
    if PYMODBUS_LINK.is_symlink():
        PYMODBUS_LINK.unlink()


# ── Test helpers ──────────────────────────────────────────────────────────────


def _run_smoke_test():
    """Import check in a fresh subprocess (bypasses conftest.py stubs)."""
    print("\nRunning smoke test (real pymodbus import)...")
    result = subprocess.run(
        [sys.executable, "-c",
         f"import sys; sys.path.insert(0, {str(DRIVER_DIR)!r});"
         "from pymodbus.client import ModbusSerialClient;"
         "print('  smoke ok: ModbusSerialClient imported successfully')"],
        cwd=REPO_ROOT,
    )
    if result.returncode != 0:
        print("  FAIL: Smoke test failed — pymodbus import broken.", file=sys.stderr)
        return False
    return True


def _run_pytest():
    """Run the full test suite and return True on pass."""
    print("\nRunning pytest...")
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/", "-v", "--tb=short"],
        cwd=REPO_ROOT,
    )
    return result.returncode == 0


# ── Status helper ─────────────────────────────────────────────────────────────


def _show_status():
    state = _read_state()
    print("\npymodbus version manager status")
    print(f"  Mode:             {state['mode']}")
    print(f"  Active version:   {state['active_version']}")
    if state.get("previous_version"):
        print(f"  Previous version: {state['previous_version']}")

    # Current filesystem state
    if PYMODBUS_LINK.is_symlink():
        link_target = os.readlink(PYMODBUS_LINK)
        print(f"  pymodbus symlink: -> {link_target}  (testing — not yet promoted)")
    elif PYMODBUS_LINK.is_dir():
        print("  pymodbus/: plain directory  (stable)")

    # Retained versioned dirs
    versioned = sorted(DRIVER_DIR.glob("pymodbus-*/"))
    if versioned:
        print("\n  Retained versioned directories:")
        for d in versioned:
            size_mb = sum(f.stat().st_size for f in d.rglob("*") if f.is_file()) / 1_048_576
            print(f"    {d.name}/  ({size_mb:.1f} MB)")
    else:
        print("\n  No retained versioned directories.")


# ── Commands ──────────────────────────────────────────────────────────────────


def cmd_update(version):
    state = _read_state()

    if state["mode"] == "testing":
        print(f"ERROR: Already in testing mode for {state['active_version']}.")
        print("Run --promote or --rollback first.", file=sys.stderr)
        sys.exit(1)

    if PYMODBUS_LINK.is_symlink():
        print("ERROR: pymodbus/ is already a symlink — run --promote or --rollback first.",
              file=sys.stderr)
        sys.exit(1)

    if version is None:
        version = _fetch_latest_stable()

    current_version = state["active_version"]
    versioned_target = _versioned_dir(version)
    versioned_backup = _versioned_dir(current_version)

    print(f"\nUpdating pymodbus: {current_version} -> {version}")
    print(f"  Driver dir: {DRIVER_DIR}")

    # Step 1: back up current pymodbus/ to pymodbus-<current>/
    if not versioned_backup.exists():
        print(f"\n  Backing up pymodbus/ -> pymodbus-{current_version}/")
        PYMODBUS_LINK.rename(versioned_backup)
    else:
        print(f"\n  Removing current pymodbus/ (backup pymodbus-{current_version}/ already exists)")
        shutil.rmtree(PYMODBUS_LINK)

    # Step 2: download + extract new version
    print(f"\n  Fetching pymodbus {version}...")
    _download_and_extract(version, versioned_target)

    # Step 3: ensure ruff excludes versioned dirs
    _ensure_ruff_excludes_versioned()

    # Step 4: create temp symlink
    print("\n  Creating temporary symlink for testing...")
    _set_symlink(version)

    # Step 5: update state
    _write_state({
        "mode": "testing",
        "active_version": version,
        "previous_version": current_version,
    })

    # Step 6: smoke test + pytest
    smoke_ok = _run_smoke_test()
    pytest_ok = _run_pytest()

    print(f"\n{'='*60}")
    print(f"Smoke test:  {'PASS' if smoke_ok else 'FAIL'}")
    print(f"Pytest:      {'PASS' if pytest_ok else 'FAIL'}")
    print(f"{'='*60}")

    if smoke_ok and pytest_ok:
        print("\nAll tests passed!")
        print("  Run --promote to make this version permanent.")
        print("  Run --rollback to revert to the previous version.")
    else:
        print("\nTests FAILED.")
        print("  Fix the driver code, then re-run this command.")
        print("  Run --rollback to revert immediately.")


def cmd_promote():
    state = _read_state()

    if state["mode"] != "testing":
        print("ERROR: Not in testing mode. Nothing to promote.", file=sys.stderr)
        sys.exit(1)

    if not PYMODBUS_LINK.is_symlink():
        print("ERROR: pymodbus/ is not a symlink — state file may be out of sync.",
              file=sys.stderr)
        sys.exit(1)

    version = state["active_version"]
    versioned_dir = _versioned_dir(version)

    print(f"\nPromoting pymodbus {version} to permanent...")
    _remove_symlink()
    versioned_dir.rename(PYMODBUS_LINK)
    _write_state({
        "mode": "stable",
        "active_version": version,
        "previous_version": state.get("previous_version"),
    })
    print(f"  Done. pymodbus/ is now {version} (plain directory).")
    print(f"  pymodbus-{state.get('previous_version')}/ retained for reference.")
    print("  Delete it manually when no longer needed.")


def cmd_rollback():
    state = _read_state()

    if state["mode"] != "testing":
        print("ERROR: Not in testing mode. Nothing to roll back.", file=sys.stderr)
        sys.exit(1)

    previous = state.get("previous_version")
    if not previous:
        print("ERROR: No previous version recorded in state file.", file=sys.stderr)
        sys.exit(1)

    backup_dir = _versioned_dir(previous)
    if not backup_dir.exists():
        print(f"ERROR: Backup directory pymodbus-{previous}/ not found.", file=sys.stderr)
        sys.exit(1)

    active = state["active_version"]
    print(f"\nRolling back: {active} -> {previous}")
    _remove_symlink()
    backup_dir.rename(PYMODBUS_LINK)
    _write_state({
        "mode": "stable",
        "active_version": previous,
        "previous_version": None,
    })
    print(f"  Done. pymodbus/ restored to {previous} (plain directory).")
    print(f"  pymodbus-{active}/ retained for debugging.")
    print("  Delete it manually when no longer needed.")


# ── Entry point ───────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(
        description="Manage the vendored pymodbus version.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--version", metavar="X.Y.Z",
                       help="pymodbus version to install (default: latest stable)")
    group.add_argument("--promote", action="store_true",
                       help="make the tested version permanent")
    group.add_argument("--rollback", action="store_true",
                       help="revert to previous version")
    group.add_argument("--status", action="store_true",
                       help="show current state and disk usage")
    args = parser.parse_args()

    if args.promote:
        cmd_promote()
    elif args.rollback:
        cmd_rollback()
    elif args.status:
        _show_status()
    else:
        # --version X.Y.Z or no args (use latest)
        cmd_update(args.version)


if __name__ == "__main__":
    main()
