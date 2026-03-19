---
date: 2026-03-18
topic: glib-test-support
---

# GLib Test Support

## Problem Frame

All existing tests stub out `gi.repository.GLib` with an empty module. Production code
in `dbus-serialinverter.py` uses `GLib.MainLoop()`, `GLib.timeout_add()`, and
`DBusGMainLoop` — none of which are exercised in the test suite today. This means the
timer-based poll loop and mainloop lifecycle have no test coverage, and divergence between
the mock and real GLib behaviour goes undetected.

The driver runs on VenusOS, which ships GLib. Developer machines (macOS, plain Linux) may
not have `gi.repository` installed. Tests must run in both environments: with real GLib
when available, with mocks as a fallback — and the fallback must be visible.

## Requirements

- R1. Detect at session start whether `gi.repository.GLib` is importable as a real library
  (not the current empty-module stub).

- R2. When real GLib is available, GLib-dependent tests run against the real
  `gi.repository.GLib` objects (`MainLoop`, `timeout_add`, `MainContext`).

- R3. When real GLib is not available, GLib-dependent tests run against the existing mock
  stubs and emit a `pytest.warns`-compatible `UserWarning` for each test (or once per
  session) stating that GLib is not installed and mock fidelity is limited.

- R4. Cover the following GLib-dependent behaviours:
  - R4a. `GLib.timeout_add` fires the registered callback after the given interval.
  - R4b. `GLib.MainLoop` starts, iterates, and stops when `quit()` is called.
  - R4c. Full poll integration: `timeout_add` → `poll_inverter` callback → `publish_inverter`
    executes without error when wired to a stubbed inverter and DbusHelper.
  - R4d. `DBusGMainLoop(set_as_default=True)` does not raise when called.

- R5. Non-GLib tests are unaffected — they continue to use the existing empty-module stubs
  and run without warnings.

- R6. The detection and fixture machinery lives in `tests/conftest.py` so every test file
  gets access without per-file boilerplate.

## Success Criteria

- `pytest tests/` passes on a machine without GLib installed, with a visible warning
  identifying which tests ran against mocks.
- `pytest tests/` passes on VenusOS or any machine with `python3-gi` installed, with the
  GLib tests confirmed to have used the real library.
- Coverage does not drop below the 60% floor.
- No existing test requires modification to support the new infrastructure.

## Scope Boundaries

- Does not add GLib tests for `dbushelper.py` internals beyond what is needed for the poll
  integration (R4c). DbusHelper unit tests remain mock-based.
- Does not attempt to bring up a real D-Bus session daemon; `DBusGMainLoop` init (R4d)
  is tested only for the absence of import/call errors, not for actual D-Bus message
  passing.
- Does not change the `FakeLoop` stub — it remains useful for non-GLib unit tests.
- Does not change CI configuration; CI already runs `pytest tests/` and the new tests
  will run there unchanged (GLib presence depends on the CI image).

## Key Decisions

- **Always run, never skip**: GLib tests run in every environment. Mock-mode tests produce
  a warning rather than being silenced. Rationale: skipping hides the coverage gap; a
  warning keeps it visible while not breaking CI.
- **Fixture-based dispatch**: A `glib` fixture in conftest returns real or mock GLib and
  sets the warning. Tests that need GLib request this fixture. Rationale: centralises
  detection, keeps test bodies clean, requires no per-file changes.

## Dependencies / Assumptions

- `gi.repository.GLib` is available via `python3-gi` (or `pygobject`) on VenusOS and
  optionally on developer machines.
- `dbus.mainloop.glib.DBusGMainLoop` may or may not be importable without a running D-Bus
  session; R4d tests should guard against `DBusException` at call time.

## Outstanding Questions

### Resolve Before Planning
*(none)*

### Deferred to Planning

- [Affects R3][Technical] What is the right granularity for the UserWarning — once per
  session (via a session-scoped fixture) or once per test? A session warning is less
  noisy; a per-test warning is more traceable in `-v` output.
- [Affects R4b][Needs research] Real GLib MainLoop iteration in a test requires running
  the loop on a thread or using `MainContext.iteration(may_block=False)` polling. Which
  pattern is more reliable in a pytest context without a real D-Bus daemon?
- [Affects R4c][Technical] `dbus-serialinverter.py` is an entry-point module (not a
  library); `poll_inverter` is a closure inside `main()`. Plan should determine whether
  to test it by calling `main()` with mocked args, by extracting the closure, or by a
  functional test that invokes the file as a subprocess.

## Next Steps

→ `/ce:plan` for structured implementation planning
