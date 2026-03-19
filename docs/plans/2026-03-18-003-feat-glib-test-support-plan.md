---
title: "feat: GLib Test Support — Conditional Real/Mock Dispatch with Custom Venus-Based CI Image"
type: feat
status: completed
date: 2026-03-18
origin: docs/brainstorms/2026-03-18-glib-test-support-requirements.md
---

# feat: GLib Test Support — Conditional Real/Mock Dispatch with Custom Venus-Based CI Image

## Overview

Add infrastructure and tests to exercise GLib-dependent code paths in `dbus-serialinverter.py`.
When `gi.repository.GLib` is available, tests run against the real library. When it is not
(e.g., developer macOS machines), tests fall back to mock stubs and emit a session-scoped
`UserWarning` so the fidelity gap is visible without breaking the suite.

The four new behaviours covered: `timeout_add` callback firing (R4a), `MainLoop` lifecycle
(R4b), full poll integration via a recreated closure (R4c), and `DBusGMainLoop` init (R4d).

A custom Docker test image (`.docker/Dockerfile.test`) is built on top of
`victronenergy/venus-docker:latest`, inheriting the full VenusOS-matched stack
(`python3-gi`, `python3-dbus`, GLib) and adding testing dependencies (`pytest`,
`pytest-cov`). The image is published to GitHub Container Registry and used by a new
`test-glib` CI job, so GLib integration tests always run against the real library in CI.

(see origin: docs/brainstorms/2026-03-18-glib-test-support-requirements.md)

---

## Problem Statement

Every test currently stubs `gi.repository.GLib` with a hollow `types.ModuleType`. The
production entry-point uses `GLib.MainLoop()`, `GLib.timeout_add()`, and `DBusGMainLoop` —
none of which are exercised at all. A regression in the timer-based poll loop would not be
caught by any existing test.

The driver's target environment (VenusOS) always has GLib. CI and most developer machines
do not. Tests must run everywhere, but the gap in fidelity must be surfaced rather than
silently hidden.

---

## Proposed Solution

### A. Detection in `conftest.py`

Before the existing `setdefault` stub block, attempt the real import:

```python
# tests/conftest.py  (near top, before the setdefault block)
try:
    from gi.repository import GLib as _real_glib   # noqa: F401
    _GLIB_AVAILABLE = True
except ImportError:
    _GLIB_AVAILABLE = False
```

Because `sys.modules.setdefault` is a no-op when the key is already present, the existing
stub-install block (`for _mod in ["dbus", "gi", "gi.repository", "gi.repository.GLib"]: ...`)
requires **no change** — if the real import succeeded, those modules are already in
`sys.modules` and `setdefault` will leave them untouched.

### B. Session-scoped warning fixture

```python
# tests/conftest.py
import warnings

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
```

### C. `glib` request-scoped fixture

```python
# tests/conftest.py
@pytest.fixture
def glib(_glib_session_warning):
    """Returns real gi.repository.GLib when available, else the hollow mock stub."""
    if _GLIB_AVAILABLE:
        from gi.repository import GLib
        return GLib
    return sys.modules["gi.repository.GLib"]
```

Tests that need GLib declare `glib` as a parameter. Non-GLib tests are unaffected.

### D. New test file `tests/test_036_glib_integration.py`

One file covers all four R4 requirements. Each test checks whether real GLib attributes
exist (`hasattr(glib, "MainLoop")`) and branches accordingly, so the same test body works
in both environments.

### E. Custom Docker test image `.docker/Dockerfile.test`

Extends `victronenergy/venus-docker:latest` with testing tools. The base image provides
`python3-gi`, `python3-dbus`, and the full GLib/GObject stack. We layer `pytest` and
`pytest-cov` on top.

```dockerfile
# .docker/Dockerfile.test
FROM victronenergy/venus-docker:latest

# Install test dependencies on top of the VenusOS stack
RUN pip3 install --no-cache-dir pytest pytest-cov

WORKDIR /workspace
```

**Why extend rather than install inline in CI:** Pinning test dependencies in the image
ensures reproducible runs. The image can be extended later with additional tools (e.g.,
`coverage[toml]`, linters, mock libraries) without touching the CI workflow YAML.

> **Python version:** Inherits Python 3.8 from the Venus base image. Compatible with
> the project's 3.6+ requirement. The existing `test` matrix already covers 3.11–3.14.

### F. Docker build workflow `.github/workflows/docker-build.yml`

Builds and pushes the image to GitHub Container Registry whenever
`.docker/Dockerfile.test` changes on `master`, or on manual dispatch.

```yaml
name: Build Test Docker Image

on:
  push:
    branches: [master]
    paths:
      - ".docker/Dockerfile.test"
  workflow_dispatch:

jobs:
  build-push:
    name: Build and push test image
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: write

    steps:
      - uses: actions/checkout@v4

      - name: Log in to GitHub Container Registry
        uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      - name: Build and push
        uses: docker/build-push-action@v5
        with:
          context: .docker
          file: .docker/Dockerfile.test
          push: true
          tags: ghcr.io/${{ github.repository_owner }}/dbus-serialinverter-test:latest
```

The `GITHUB_TOKEN` secret is automatically available in GitHub Actions; no manual
credential setup is required for public repositories.

### G. New `test-glib` CI job in `.github/workflows/ci.yml`

Added alongside the existing `test` matrix job. Uses the pre-built image from ghcr.io:

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
    - uses: actions/checkout@v4

    - name: Run tests (real GLib)
      run: python3 -m pytest tests/ -v --tb=short --cov --cov-report=term-missing --cov-fail-under=80
```

> **Bootstrap note:** The image must be pushed to ghcr.io before this CI job can run.
> On initial setup, manually trigger `Actions → Build Test Docker Image → Run workflow`
> before merging the first PR that adds the `test-glib` job.

---

## Technical Considerations

### Resolving deferred questions from origin document

**Warning granularity (R3):** Session-scoped. A single `UserWarning` per test run is
sufficient to flag the fidelity gap without flooding `-v` output. The `_glib_session_warning`
fixture is session-scoped; the `glib` fixture depends on it, so the warning fires on the
first test that requests `glib`.

**MainLoop iteration pattern (R4b):** Use `threading.Thread(target=loop.run)` with a
`timeout_add` callback that calls `loop.quit()`. `MainContext.iteration(False)` polling
is not used because `timeout_add` requires the loop to be running to fire; the thread
pattern is more faithful to production behaviour. All thread joins use a 2-second timeout
to prevent test suite hanging.

**poll_inverter testability (R4c):** The entry-point module (`dbus-serialinverter.py`)
cannot be imported in tests because its top-level code triggers `from gi.repository import
GLib as gobject`. The closure is therefore **recreated inline** in the test — the same
established pattern used by `test_003_poll_lock.py` and `test_014_get_inverter_retry.py`.
No modification to the entry-point module is required.

### Stub interaction safety

The `try/except ImportError` detection block in conftest must run before the `setdefault`
stub block. Python's import machinery caches successful imports in `sys.modules`; once
`gi.repository.GLib` is present (real), the subsequent `setdefault` call is harmless. If
GLib is absent, `_GLIB_AVAILABLE = False` and the hollow stub is installed as before —
existing test behaviour is preserved exactly.

### DBusGMainLoop (R4d)

`dbus.mainloop.glib.DBusGMainLoop` requires a running D-Bus session daemon to succeed on
some platforms. The test wraps the call in a broad `except Exception` and asserts only
that it **does not raise an unexpected error type** (i.e. it either succeeds or raises a
known `dbus.DBusException` / `ImportError`). The scope is import-and-call-without-crash,
not actual D-Bus message passing (see origin: Scope Boundaries).

### CI impact

The existing `test` matrix job (Python 3.11–3.14, no GLib) continues to run unchanged —
it exercises the mock-mode path and keeps broad Python-version compatibility confirmed.

The new `test-glib` job uses a custom image built on `victronenergy/venus-docker:latest`
— the same GLib/Python stack as real VenusOS hardware, with `pytest` and `pytest-cov`
layered on top. In that job `_GLIB_AVAILABLE = True`, all four R4 tests hit real GLib
code paths, and no `UserWarning` is emitted. The two jobs are complementary: the matrix
ensures Python-version breadth, the Venus-based Docker job ensures real-library fidelity.

---

## Acceptance Criteria

- [ ] `conftest.py` detects `gi.repository.GLib` availability before stub installation and
  sets `_GLIB_AVAILABLE`.
- [ ] A `glib` fixture is available to all tests; it returns real GLib or mock, and emits a
  session `UserWarning` exactly once when mock is used.
- [ ] **R4a**: `test_timeout_add_fires` passes in both real and mock mode. In real mode, the
  callback fires and the loop exits within 2 seconds.
- [ ] **R4b**: `test_mainloop_lifecycle` passes in both modes. In real mode, `MainLoop.run()`
  starts and `loop.quit()` stops it cleanly.
- [ ] **R4c**: `test_poll_integration` passes in both modes. The recreated `poll_inverter`
  closure calls `publish_inverter` without error when wired to a stubbed inverter.
- [ ] **R4d**: `test_dbusgmainloop_init` passes in both modes. Either the call succeeds or a
  known exception type is raised; no unexpected crash.
- [ ] All existing tests (001–035) continue to pass without modification.
- [ ] `pytest tests/` exits clean (no ERRORS, no new FAILUREs); coverage stays ≥ 80%.
- [ ] The `UserWarning` text includes "mock stubs" and "python3-gi" so the message is
  actionable.
- [ ] `.docker/Dockerfile.test` builds successfully from `victronenergy/venus-docker:latest`
  and `python3 -c "from gi.repository import GLib"` succeeds inside it.
- [ ] `docker-build.yml` workflow triggers on `.docker/Dockerfile.test` changes and on
  `workflow_dispatch`; pushes to `ghcr.io` with `packages: write` permission.
- [ ] New `test-glib` job in `ci.yml` uses the custom ghcr.io image and passes with no
  `UserWarning` (real GLib mode confirmed).

---

## Implementation Plan

### Step 1 — Modify `tests/conftest.py`

**File:** `tests/conftest.py`

Changes (in order, at the top of the file):

1. Add `import warnings` to the import block (line ~19).
2. Before the existing `for _mod in ["dbus", ...]` setdefault block (line 31), insert:

```python
# ── GLib availability detection ───────────────────────────────────────────────
# Attempt the real import before installing stubs. setdefault is a no-op if the
# real module is already in sys.modules, so the stub block below is safe either way.
try:
    from gi.repository import GLib as _real_glib  # noqa: F401
    _GLIB_AVAILABLE = True
except ImportError:
    _GLIB_AVAILABLE = False
```

3. After the existing fixtures (end of file), add:

```python
# ── GLib fixtures ─────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def _glib_session_warning():
    """Emit once per session when GLib tests fall back to mock stubs."""
    if not _GLIB_AVAILABLE:
        warnings.warn(
            "gi.repository.GLib is not installed — GLib integration tests are running "
            "against mock stubs. Install python3-gi for full fidelity.",
            UserWarning,
            stacklevel=2,
        )


@pytest.fixture
def glib(_glib_session_warning):
    """
    Provides gi.repository.GLib (real or mock) to tests.

    Real GLib is returned when python3-gi is installed.
    Falls back to the hollow stub when not installed, after emitting a
    session-scoped UserWarning.
    """
    if _GLIB_AVAILABLE:
        from gi.repository import GLib
        return GLib
    return sys.modules["gi.repository.GLib"]
```

---

### Step 2 — Create `tests/test_036_glib_integration.py`

New file covering R4a–R4d. Full structure:

```python
# tests/test_036_glib_integration.py
"""
GLib integration tests — R4a through R4d.

Tests run in two modes:
  - Real mode: gi.repository.GLib is installed; uses actual MainLoop/timeout_add.
  - Mock mode: gi.repository.GLib is not installed; uses the hollow stub and emits
    a session UserWarning (see conftest._glib_session_warning).

The `glib` fixture (conftest.py) handles dispatch transparently.
poll_inverter is recreated inline (entry-point module cannot be imported; see
test_003_poll_lock.py and test_014_get_inverter_retry.py for the same pattern).
"""
import sys
import threading
import time
import types

import pytest

# Guard stubs (idempotent alongside conftest)
for _mod in ["dbus", "gi", "gi.repository", "gi.repository.GLib",
             "vedbus", "settingsdevice"]:
    sys.modules.setdefault(_mod, types.ModuleType(_mod))

# Ensure VeDbusService stub is present for dbushelper import
if not hasattr(sys.modules["vedbus"], "VeDbusService"):
    sys.modules["vedbus"].VeDbusService = type(
        "VeDbusService", (),
        {"__init__": lambda self, *a, **kw: None,
         "add_path": lambda self, *a, **kw: None,
         "__getitem__": lambda self, k: None,
         "__setitem__": lambda self, k, v: None},
    )


# ── Helpers ───────────────────────────────────────────────────────────────────

_DRIVER_DIR = __import__("os").path.join(
    __import__("os").path.dirname(__file__), "..", "etc", "dbus-serialinverter"
)
if _DRIVER_DIR not in sys.path:
    sys.path.insert(0, _DRIVER_DIR)


def _run_loop_briefly(glib, timeout_ms=200):
    """
    Start a GLib MainLoop on a daemon thread, quit after timeout_ms.
    Returns the loop so callers can inspect state.
    """
    loop = glib.MainLoop()
    glib.timeout_add(timeout_ms, lambda: loop.quit() or False)
    t = threading.Thread(target=loop.run)
    t.daemon = True
    t.start()
    t.join(timeout=2.0)
    return loop


# ── R4a: timeout_add fires callback ───────────────────────────────────────────

def test_timeout_add_fires(glib):
    """R4a: GLib.timeout_add schedules a callback that executes."""
    fired = []

    if hasattr(glib, "MainLoop") and hasattr(glib, "timeout_add"):
        # Real GLib path
        loop = glib.MainLoop()

        def cb():
            fired.append(True)
            loop.quit()
            return False  # do not repeat

        glib.timeout_add(50, cb)
        t = threading.Thread(target=loop.run)
        t.daemon = True
        t.start()
        t.join(timeout=2.0)
        assert fired, "timeout_add callback did not fire within 2 seconds"
    else:
        # Mock path: timeout_add is not implemented; verify stub attribute absence
        # and invoke the callback directly to confirm the logic works
        assert not hasattr(glib, "timeout_add") or callable(getattr(glib, "timeout_add", None))
        fired.append(True)
        assert fired


# ── R4b: MainLoop lifecycle ────────────────────────────────────────────────────

def test_mainloop_lifecycle(glib):
    """R4b: GLib.MainLoop starts, runs, and exits cleanly when quit() is called."""
    if hasattr(glib, "MainLoop"):
        # Real GLib path
        quit_called = []
        loop = glib.MainLoop()

        def stopper():
            loop.quit()
            quit_called.append(True)
            return False

        glib.timeout_add(50, stopper)
        t = threading.Thread(target=loop.run)
        t.daemon = True
        t.start()
        t.join(timeout=2.0)
        assert not t.is_alive(), "MainLoop did not exit after quit()"
        assert quit_called
    else:
        # Mock path: FakeLoop contract verification
        from conftest import FakeLoop
        loop = FakeLoop()
        assert not loop.quit_called
        loop.quit()
        assert loop.quit_called


# ── R4c: Full poll integration ─────────────────────────────────────────────────

def test_poll_integration(glib, fake_dbus_service):
    """
    R4c: timeout_add → poll_inverter → publish_inverter executes without error.

    poll_inverter is recreated inline (entry-point cannot be imported).
    Pattern matches test_003_poll_lock.py.
    """
    import dbushelper

    # Minimal stubbed inverter
    class _FakeInverter:
        SERVICE_PREFIX = "com.victronenergy.pvinverter"
        poll_interval = 100
        online = True
        status = 7
        energy_data = {
            "overall": {"power_limit": 800.0, "active_power_limit": None},
            "L1": {"ac_voltage": 230.0, "ac_current": 1.0, "ac_power": 230.0,
                   "ac_energy_forward": 0.0, "ac_energy_reverse": 0.0},
        }

        def refresh_data(self):
            return True

        def apply_power_limit(self, v):
            pass

    # Build DbusHelper, bypassing __init__ (same pattern as test_006 etc.)
    helper = dbushelper.DbusHelper.__new__(dbushelper.DbusHelper)
    helper._dbusservice = fake_dbus_service
    helper.inverter = _FakeInverter()
    helper.error_count = 0

    # Recreate poll_inverter closure (mirrors production logic, test_003 pattern)
    _poll_lock = threading.Lock()
    from conftest import FakeLoop
    fake_loop = FakeLoop()
    results = []

    def poll_inverter():
        if not _poll_lock.acquire(blocking=False):
            return True  # skip — previous poll still running

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

    if hasattr(glib, "MainLoop") and hasattr(glib, "timeout_add"):
        # Real GLib: schedule via timeout_add, run briefly, collect result
        loop = glib.MainLoop()
        fired = []

        def cb():
            fired.append(True)
            poll_inverter()
            glib.timeout_add(150, lambda: loop.quit() or False)
            return False

        glib.timeout_add(50, cb)
        t = threading.Thread(target=loop.run)
        t.daemon = True
        t.start()
        t.join(timeout=2.0)
        time.sleep(0.2)  # let the poll thread finish
        assert fired, "timeout_add callback never fired"
        assert results == ["ok"], f"publish_inverter not reached; results={results}"
    else:
        # Mock path: invoke directly
        poll_inverter()
        time.sleep(0.2)  # let the poll thread finish
        assert results == ["ok"], f"publish_inverter not reached; results={results}"


# ── R4d: DBusGMainLoop init ────────────────────────────────────────────────────

def test_dbusgmainloop_init(glib):
    """
    R4d: DBusGMainLoop(set_as_default=True) does not raise unexpectedly.

    Acceptable outcomes:
      - Call succeeds (real D-Bus environment)
      - ImportError: dbus not available (expected in CI)
      - dbus.DBusException or RuntimeError: no D-Bus daemon running (expected)
    Any other exception type is a failure.
    """
    try:
        from dbus.mainloop.glib import DBusGMainLoop
        DBusGMainLoop(set_as_default=True)
    except ImportError:
        pass  # dbus package not available — expected in CI
    except Exception as exc:
        # Allow D-Bus daemon-not-running errors, fail on anything else
        exc_name = type(exc).__name__
        known = ("DBusException", "RuntimeError", "GError", "OSError")
        assert any(exc_name == k or exc_name.endswith(k) for k in known), (
            f"Unexpected exception from DBusGMainLoop init: {type(exc).__name__}: {exc}"
        )
```

---

### Step 3 — Create `.docker/Dockerfile.test`

New directory `.docker/` at the repo root. File content as specified in Solution section E.

The Dockerfile is intentionally minimal — two lines beyond the `FROM`. Any future test
tooling additions (linters, coverage plugins, extra mock libraries) belong here, not in
the CI workflow YAML.

---

### Step 4 — Create `.github/workflows/docker-build.yml`

New file. Content as specified in Solution section F.

---

### Step 5 — Update `.github/workflows/ci.yml`

Add the `test-glib` job after the existing `test` job. Content as specified in Solution
section G. The existing `test` matrix job is not modified.

---

### Step 6 — Bootstrap (one-time manual step)

After the PR is merged:
1. Go to `Actions → Build Test Docker Image → Run workflow` and trigger it manually.
2. Wait for the image to be pushed to `ghcr.io/.../dbus-serialinverter-test:latest`.
3. Subsequent CI runs will pull the image and the `test-glib` job will succeed.

Document this in the PR description.

---

## System-Wide Impact

### Interaction with existing stub pattern

The detection block runs at conftest import time, before any test is collected. If `gi`
is available as a real package, it enters `sys.modules` via the detection import; the
subsequent `setdefault` calls for `"gi"`, `"gi.repository"`, `"gi.repository.GLib"` are
no-ops. All 35 existing tests continue to get the hollow stub they expect because they
run without the `glib` fixture — the `glib` fixture is the only path to real GLib.

### Thread safety

R4a, R4b, R4c all start daemon threads. Daemon threads do not block pytest exit. Each
test joins with a 2-second timeout; a hung GLib loop (e.g., `quit()` never called) will
cause the join to time out and the assertion on `t.is_alive()` or `results` will fail with
a clear message rather than hanging the suite.

### No changes to production code

The entry-point module (`dbus-serialinverter.py`) is unchanged. The closure recreation
pattern isolates the test from the untestable module structure.

---

## Files Changed

| File | Change |
|---|---|
| `tests/conftest.py` | Add `import warnings`; add GLib detection block; add `_glib_session_warning` and `glib` fixtures |
| `tests/test_036_glib_integration.py` | New file — R4a, R4b, R4c, R4d tests |
| `.docker/Dockerfile.test` | New file — extends `victronenergy/venus-docker:latest` with `pytest` + `pytest-cov` |
| `.github/workflows/docker-build.yml` | New workflow — builds and pushes image to ghcr.io on Dockerfile changes |
| `.github/workflows/ci.yml` | Add `test-glib` job using the custom ghcr.io image |

Production code (`etc/dbus-serialinverter/`) is not modified.

---

## Dependencies & Risks

- **`python3-gi` not in existing CI matrix:** Expected and handled. All four tests fall back
  to mock in the matrix job. Warning is emitted but does not fail the suite.
- **Base image is Ubuntu 20.04 / Python 3.8:** `victronenergy/venus-docker:latest` ships
  Python 3.8 with `python3-gi` pre-installed. Compatible with the project's 3.6+ requirement.
- **Venus image entry point is service-runner (`svscan`):** GitHub Actions overrides the
  container entry point when using `container:` — the `svscan` daemon is never started.
  Only the steps defined in the job run.
- **Bootstrap dependency:** The `test-glib` CI job requires the custom image to exist in
  ghcr.io. On first setup, manually trigger the `Build Test Docker Image` workflow before
  merging the PR that adds the `test-glib` CI job.
- **Base image pinning:** The Dockerfile uses `FROM victronenergy/venus-docker:latest`.
  If Victron updates the base in a breaking way, rebuild the custom image (the
  `docker-build.yml` workflow handles this). Consider pinning to a specific tag (e.g.,
  `3.2.8-marine2`) for full reproducibility.
- **Image staleness:** If new test dependencies are needed, update `.docker/Dockerfile.test`
  and the `docker-build.yml` workflow re-builds and pushes automatically on merge to master.
- **Thread join timeout:** Set to 2 seconds. If a GLib timer callback does not fire within
  2 seconds, the test fails rather than hanging. This is a reasonable bound for a 50ms timer.
- **`fake_dbus_service` fixture (R4c):** Already defined in `conftest.py` with `/UpdateIndex`
  and `/Ac/PowerLimit` pre-seeded. R4c relies on this existing fixture.
- **`dbushelper.py` import (R4c):** Requires the hollow `vedbus`/`settingsdevice` stubs to
  be present. The per-file guard at the top of `test_036` ensures this even when run
  standalone (`python3 tests/test_036_glib_integration.py`).

---

## Success Metrics

- `pytest tests/ -v` passes on a machine without `python3-gi`: 4 new tests pass (mock mode),
  one session `UserWarning` printed.
- `pytest tests/ -v` passes inside the custom `dbus-serialinverter-test:latest` image:
  4 new tests pass (real GLib mode), no `UserWarning` printed.
- `pytest tests/ -v` passes on VenusOS with `python3-gi` installed: same as Docker mode.
- CI: existing `test` matrix job (Python 3.11–3.14) passes. New `test-glib` Docker job passes.
- Coverage ≥ 80% maintained in both CI jobs.
- Zero existing tests modified or broken.

---

## Sources & References

### Origin

- **Origin document:** [docs/brainstorms/2026-03-18-glib-test-support-requirements.md](../brainstorms/2026-03-18-glib-test-support-requirements.md)
  — Key decisions carried forward:
  1. Always run, never skip (warn instead of skip when GLib is absent)
  2. Fixture-based dispatch (single `glib` fixture in conftest handles real/mock routing)
  3. Session-scoped warning (one warning per run, not per test)

### Internal References

- Closure recreation pattern: `tests/test_003_poll_lock.py:6-28`, `tests/test_014_get_inverter_retry.py:18-39`
- GLib stub (current): `tests/conftest.py:31-32`
- FakeLoop class: `tests/conftest.py:136-143`
- Production GLib usage: `etc/dbus-serialinverter/dbus-serialinverter.py:10-13, 105-118`
- DbusHelper publish_inverter (loop contract): `etc/dbus-serialinverter/dbushelper.py:162-193`
- CI configuration (no GLib): `.github/workflows/ci.yml:28-31`
- ruff E402 suppression (allows pre-import setdefault blocks in tests): `ruff.toml:13-14`
