---
title: "GLib conditional real/mock dispatch for test suite"
category: test-failures
date: 2026-03-18
tags:
  - glib
  - gi-repository
  - pytest
  - mock
  - conftest
  - ci
  - docker
  - venus-os
  - mainloop
  - timeout_add
components:
  - tests/conftest.py
  - tests/test_036_glib_integration.py
  - .docker/Dockerfile.test
  - .github/workflows/ci.yml
  - .github/workflows/docker-build.yml
  - etc/dbus-serialinverter/dbus-serialinverter.py
problem_type: missing-test-coverage
summary: >
  The test suite stubbed gi.repository.GLib with a hollow module, leaving
  the GLib.MainLoop, GLib.timeout_add, and DBusGMainLoop code paths in
  dbus-serialinverter.py completely uncovered. The fix adds a conditional
  real/mock dispatch fixture in conftest.py and four integration tests that
  run against real GLib on VenusOS/CI and emit a UserWarning when falling
  back to mocks on developer machines without python3-gi.
---

## Problem

**Symptoms:**
- `gi.repository.GLib` was stubbed with a hollow `types.ModuleType` across the entire test suite — unconditionally, before any test could attempt a real import.
- Production code in `dbus-serialinverter.py` uses `GLib.MainLoop()`, `GLib.timeout_add()`, and `DBusGMainLoop` — none of which were exercised by any test.
- A regression in the timer-based poll loop, mainloop lifecycle, or error-counting quit threshold would not be caught by any existing test.
- No mechanism existed to run tests against real GLib on VenusOS hardware or in a Venus-matched CI environment.
- `TODO.md` listed: `Better testing with glib support on linux, should only run if glib is detected` — reflecting the awareness of the gap but no solution.

## Root Cause

The test bootstrap pattern used `sys.modules.setdefault("gi.repository.GLib", types.ModuleType(...))` unconditionally. This installed an empty stub before any test could attempt a real import. The stub is a valid `ModuleType` but has no attributes — it cannot simulate `MainLoop`, `timeout_add`, or any GLib scheduling primitives.

The entry-point module (`dbus-serialinverter.py`) also cannot be imported in tests because its top-level code triggers `from gi.repository import GLib as gobject`, which either fails or gets the hollow stub before the real module can be loaded.

The root issue: **import stubs were treated as behavioral equivalents when they are not**. Silencing an import error with `types.ModuleType` creates the appearance of test coverage while the real execution surface remains untested.

## Solution

The fix has three parts: conftest detection, a fixture, and a Venus-based CI job.

### Step 1 — Detect real GLib before installing stubs (`tests/conftest.py`)

The detection block must run **before** the `setdefault` stub block. Because `setdefault` is a no-op if the key already exists, if the real import succeeds first, subsequent stub installs are harmless.

```python
# tests/conftest.py — insert before the setdefault block

import warnings

# ── GLib availability detection ───────────────────────────────────────────────
try:
    from gi.repository import GLib as _real_glib  # noqa: F401
    _GLIB_AVAILABLE = True
except ImportError:
    _GLIB_AVAILABLE = False

# ── VenusOS / D-Bus stubs (unchanged) ─────────────────────────────────────────
for _mod in ["dbus", "gi", "gi.repository", "gi.repository.GLib"]:
    sys.modules.setdefault(_mod, types.ModuleType(_mod))  # no-op if real already loaded
```

### Step 2 — Add session-scoped warning fixture and `glib` request fixture

```python
@pytest.fixture(scope="session")
def _glib_session_warning():
    """Emitted once per session when GLib tests fall back to mocks."""
    if not _GLIB_AVAILABLE:
        warnings.warn(
            "gi.repository.GLib is not installed — GLib integration tests are running "
            "against mock stubs. Install python3-gi for full fidelity.",
            UserWarning,
            stacklevel=2,
        )


@pytest.fixture
def glib(_glib_session_warning):
    """Returns real gi.repository.GLib when available, else the hollow mock stub."""
    if _GLIB_AVAILABLE:
        from gi.repository import GLib
        return GLib
    return sys.modules["gi.repository.GLib"]
```

The warning fires once per session (not per test). Tests that do not request the `glib` fixture are completely unaffected.

### Step 3 — Create `tests/test_036_glib_integration.py` (R4a–R4d)

Four tests use `hasattr(glib, "MainLoop")` to branch between real and mock paths:

- **R4a** (`test_timeout_add_fires`): In real mode, register a callback with `timeout_add(50, cb)`, run the loop on a daemon thread, join with a 2-second timeout, assert the callback fired. In mock mode, verify the stub attribute and mark fired directly.
- **R4b** (`test_mainloop_lifecycle`): In real mode, use `timeout_add` to call `loop.quit()` and assert the thread exits cleanly. In mock mode, use `FakeLoop` and verify `quit_called`.
- **R4c** (`test_poll_integration`): Recreate the `poll_inverter` closure inline (the entry-point is not importable). Wire it to a minimal `_FakeInverter` and a bypassed `DbusHelper`. In real mode, schedule via `timeout_add` and assert `publish_inverter` was reached. In mock mode, call directly.
- **R4d** (`test_dbusgmainloop_init`): Attempt `DBusGMainLoop(set_as_default=True)`. Accept `ImportError` (no dbus package) and known daemon-not-running exception types. Fail on anything unexpected.

Key pattern for `poll_inverter` closure recreation (R4c):

```python
_poll_lock = threading.Lock()

def poll_inverter():
    if not _poll_lock.acquire(blocking=False):
        return True
    def _run():
        try:
            helper.publish_inverter(fake_loop)
            results.append("ok")
        finally:
            _poll_lock.release()
    t = threading.Thread(target=_run)
    t.daemon = True
    t.start()
    return True
```

Permissive D-Bus exception handling (R4d):

```python
try:
    from dbus.mainloop.glib import DBusGMainLoop
    DBusGMainLoop(set_as_default=True)
except ImportError:
    pass
except Exception as exc:
    exc_name = type(exc).__name__
    known = ("DBusException", "RuntimeError", "GError", "OSError")
    assert any(exc_name == k or exc_name.endswith(k) for k in known), (
        f"Unexpected exception from DBusGMainLoop init: {type(exc).__name__}: {exc}"
    )
```

### Step 4 — Add conda environment for local GLib testing (`environment.yml`)

```yaml
name: dbus-serialinverter
channels:
  - conda-forge
  - defaults
dependencies:
  - python=3.11
  - pygobject>=3.42
  - pytest>=7.0
  - pytest-cov>=4.0
```

`conda-forge` provides `pygobject` (the `python3-gi` equivalent) on macOS and Linux without system packages.

### Step 5 — Add Venus-based Docker test image (`.docker/Dockerfile.test`)

```dockerfile
FROM victronenergy/venus-docker:latest

RUN pip3 install --no-cache-dir pytest pytest-cov

WORKDIR /workspace
```

The base image ships Python 3.8 with `python3-gi`, `python3-dbus`, and the full GLib/GObject stack.

### Step 6 — Add `test-glib` job to CI (`.github/workflows/ci.yml`)

```yaml
test-glib:
  name: Test with real GLib (Venus-based image)
  runs-on: ubuntu-latest
  container:
    image: ghcr.io/${{ github.repository_owner }}/dbus-serialinverter-test:latest
    credentials:
      username: ${{ github.actor }}
      password: ${{ secrets.GITHUB_TOKEN }}
  steps:
    - uses: actions/checkout@v6
    - name: Run tests (real GLib)
      run: python3 -m pytest tests/ -v --tb=short --cov --cov-report=term-missing --cov-fail-under=80
```

### Step 7 — Bootstrap the Docker image (one-time manual step)

The `test-glib` CI job requires the image pre-pushed to ghcr.io. After the PR is merged:
1. Go to `Actions → Build Test Docker Image → Run workflow`
2. Wait for the push to complete
3. Subsequent CI runs pull the image automatically

## Environment Behavior Matrix

| Environment | `_GLIB_AVAILABLE` | Test mode | UserWarning emitted |
|---|---|---|---|
| `dbus-serialinverter` conda env (local) | `True` | Real GLib | No |
| Base Anaconda / no `python3-gi` (local) | `False` | Mock stubs | Yes, once per session |
| CI `test` matrix (Python 3.11–3.14) | `False` | Mock stubs | Yes, once per session |
| CI `test-glib` Docker job (Venus image) | `True` | Real GLib | No |

## Files Changed

| File | Change | Summary |
|---|---|---|
| `tests/conftest.py` | Modified | GLib detection block before setdefault; `_glib_session_warning` and `glib` fixtures |
| `tests/test_036_glib_integration.py` | New | Four tests covering R4a–R4d; dual real/mock dispatch via `hasattr` branches |
| `environment.yml` | New | Conda env with `pygobject>=3.42` for local macOS/Linux GLib testing |
| `.docker/Dockerfile.test` | New | Venus-based image with `pytest` + `pytest-cov` for CI real-GLib job |
| `.github/workflows/docker-build.yml` | New | Builds and pushes test image to ghcr.io on Dockerfile changes or manual trigger |
| `.github/workflows/ci.yml` | Modified | Added `test-glib` job alongside existing test matrix |

No production code in `etc/dbus-serialinverter/` was modified. All 35 existing tests continue to pass without changes.

## Prevention

### Distinguish import stubs from behavioral stubs

`types.ModuleType("foo")` silences `ImportError` but provides no behavior. Any time a dependency is stubbed at the module level, explicitly track what behavioral surface area is left uncovered. Use comments like `# NOT-COVERED — requires real GLib` inline, or track in `TODO.md`.

### The real/mock dispatch pattern is the default template for platform-dependent dependencies

Any future dependency available on-target (VenusOS) but not on developer machines — serial port libraries, CAN bus libraries, D-Bus bindings — should use the same three-part structure:
1. Detect availability at session start in `conftest.py`
2. Return real or mock via a named pytest fixture
3. Emit a `UserWarning` when falling back to mock, never silently skip

Template:

```python
@pytest.fixture
def platform_dep(some_session_warning):
    if _DEP_AVAILABLE:
        import real_module
        return real_module
    return sys.modules["stubbed_module"]
```

### Never stub an event loop without testing that it fires callbacks

`GLib.timeout_add` and `GLib.MainLoop` are the production execution engine. Stub them to no-ops and the driver's poll cadence, lock behavior, and error-counting thresholds are tested with a fundamentally different scheduler.

### Thread safety in timer-based tests

When using real GLib's `timeout_add`, run `MainLoop.run()` on a daemon thread with a hard `join(timeout=2.0)` ceiling and assert `not t.is_alive()`. Always set daemon threads so a hung loop does not block the test process.

### Entry-point modules that execute on import must be handled consistently

`dbus-serialinverter.py` runs `main()` at module body level — it is not importable in tests. Tests recreate closures inline. This constraint must be maintained until the entry point is refactored to be import-safe (all logic in functions, `if __name__ == "__main__"` guard).

### Watch for Python version skew

The `test` matrix covers Python 3.11–3.14. The Venus image runs Python 3.8. Syntax or stdlib features added after 3.8 (`match/case`, `tomllib`, etc.) will fail the `test-glib` job while the matrix passes. Verify new language features are compatible with 3.8.

## Edge Cases

- **Detection order**: `conftest.py` detection runs before stubs only when pytest collects conftest first. Running `python tests/test_036_glib_integration.py` directly skips detection and always uses mock GLib regardless of environment.
- **Shared mutable utils stub**: Tests that mutate `utils.INVERTER_TYPE` without restoring cause silent ordering-dependent failures. Pattern: `saved = utils.X; try: ...; finally: utils.X = saved`.
- **Docker image bootstrap dependency**: On a fresh fork or org move, `test-glib` fails to pull the image until the build workflow is triggered manually once.
- **VeDbusService stub attribute drift**: The stub implements only `add_path`, `__getitem__`, `__setitem__`. If `publish_dbus()` calls new VeDbusService methods, tests fail with unrelated-looking `AttributeError`. Extend the stub immediately when adding new VeDbusService calls.

## See Also

- **Origin requirements**: `docs/brainstorms/2026-03-18-glib-test-support-requirements.md`
- **Conftest fixture architecture**: `docs/plans/2026-03-18-001-feat-comprehensive-test-suite-plan.md`
- **Closure recreation pattern**: `tests/test_003_poll_lock.py`, `tests/test_014_get_inverter_retry.py`
- **Production GLib usage**: `etc/dbus-serialinverter/dbus-serialinverter.py` (mainloop init and timer setup)
- **Developer setup**: `DEVELOPMENT.md`
- **Potentially conflicting plan (same conftest.py)**: `docs/plans/2026-03-18-004-feat-pymodbus-version-management-plan.md`
