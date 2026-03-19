# Development Guide

## Prerequisites

- [Anaconda](https://www.anaconda.com/download) or Miniconda
- [Homebrew](https://brew.sh) (macOS)

## Setup

Clone the repo and create the conda environment:

```bash
git clone <repo-url>
cd dbus-serialinverter
conda env create -f environment.yml
conda activate dbus-serialinverter
```

The environment installs Python 3.11, `pygobject` (real GLib bindings), `pytest`, and `pytest-cov`.

## Running Tests

```bash
conda activate dbus-serialinverter

# Full suite with coverage
python -m pytest tests/ -v --tb=short --cov --cov-report=term-missing --cov-fail-under=80

# Single file
python -m pytest tests/test_036_glib_integration.py -v

# Without pytest (each file has a __main__ block)
for f in tests/test_*.py; do python "$f"; done
```

### GLib test modes

Tests detect `gi.repository.GLib` at import time and branch accordingly:

| Environment | Mode | Result |
|---|---|---|
| `dbus-serialinverter` conda env | **Real GLib** | All 4 GLib tests hit actual `MainLoop`/`timeout_add` |
| Base Anaconda / no `python3-gi` | **Mock** | GLib tests use hollow stubs; one `UserWarning` emitted |
| CI `test` matrix (Python 3.11–3.14) | **Mock** | Same as above |
| CI `test-glib` Docker job | **Real GLib** | Venus-based image; no warning |

If you see the warning below, activate the conda environment:

```
UserWarning: gi.repository.GLib is not installed — GLib integration tests are running
against mock stubs. Install python3-gi for full fidelity.
```

## Linting

```bash
ruff check etc/dbus-serialinverter/*.py tests/
```

Both lint and tests must pass clean before committing — CI enforces the same checks.

## Running the Driver Locally

No build step required. All driver code lives in `etc/dbus-serialinverter/`.

```bash
# Dummy inverter — no hardware needed
cd etc/dbus-serialinverter
python dbus-serialinverter.py /dev/null

# Real hardware
python dbus-serialinverter.py /dev/ttyUSB0
```

## Configuration

Edit `etc/dbus-serialinverter/config.ini`:

```ini
[INVERTER]
TYPE=           # Solis, Dummy, or blank for auto-detect
POLL_INTERVAL=1000
MAX_AC_POWER=800
PHASE=L1
POSITION=1
```

## Adding a New Inverter

1. Create `etc/dbus-serialinverter/<brand>.py` extending `Inverter`
2. Implement `test_connection()`, `get_settings()`, `refresh_data()`
3. Register it in `dbus-serialinverter.py` `supported_inverter_types`
4. Add a test file in `tests/` and verify it passes

## Pre-Commit Checklist

```bash
ruff check etc/dbus-serialinverter/*.py tests/
python -m pytest tests/ -v --tb=short --cov --cov-report=term-missing --cov-fail-under=80
```

Both must pass clean. Coverage must stay at or above 80%.

## CI

| Job | Python | GLib | Trigger |
|---|---|---|---|
| `test` matrix | 3.11, 3.12, 3.13, 3.14 | Mock stubs | Every push / PR |
| `test-glib` | 3.8 (Venus image) | Real | Every push / PR |
| `lint` | 3.12 | — | Every push / PR |
| `Build Test Docker Image` | — | — | `.docker/Dockerfile.test` changes or manual dispatch |

### First-time Docker image bootstrap

The `test-glib` CI job requires the custom image to exist in `ghcr.io` before it can run.
After the first PR that introduces the `test-glib` job is merged:

1. Go to **Actions → Build Test Docker Image → Run workflow**
2. Wait for the push to complete
3. Subsequent CI runs will pull the image automatically
