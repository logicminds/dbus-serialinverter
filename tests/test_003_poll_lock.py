"""Test 003: concurrent poll prevention via threading.Lock."""
import threading
import time


def _make_poll_inverter():
    """Recreate poll_inverter() closure from dbus-serialinverter.py without imports."""
    _poll_lock = threading.Lock()
    calls = []

    def poll_inverter(work_duration=0):
        if not _poll_lock.acquire(blocking=False):
            calls.append("skipped")
            return True

        def _run():
            try:
                time.sleep(work_duration)
                calls.append("ran")
            finally:
                _poll_lock.release()

        t = threading.Thread(target=_run)
        t.daemon = True
        t.start()
        return True

    return poll_inverter, calls


def test_single_poll_runs():
    poll, calls = _make_poll_inverter()
    poll(work_duration=0)
    time.sleep(0.05)
    assert calls == ["ran"]


def test_concurrent_poll_skipped():
    poll, calls = _make_poll_inverter()
    # First poll holds the lock for 100 ms
    poll(work_duration=0.1)
    time.sleep(0.01)  # let thread start and acquire lock
    # Second tick fires while first is still running
    poll(work_duration=0)
    time.sleep(0.15)  # wait for first to finish
    assert "skipped" in calls, "Second concurrent poll should have been skipped"
    assert calls.count("ran") == 1, "Exactly one poll should have executed"


def test_sequential_polls_both_run():
    poll, calls = _make_poll_inverter()
    poll(work_duration=0)
    time.sleep(0.05)
    poll(work_duration=0)
    time.sleep(0.05)
    assert calls.count("ran") == 2, "Sequential polls should both run"
    assert "skipped" not in calls


def test_lock_released_after_poll():
    """Lock must be released even when poll completes normally."""
    poll, calls = _make_poll_inverter()
    poll(work_duration=0)
    time.sleep(0.05)
    # A subsequent poll must be able to run (lock not permanently held)
    poll(work_duration=0)
    time.sleep(0.05)
    assert calls.count("ran") == 2


if __name__ == "__main__":
    test_single_poll_runs()
    test_concurrent_poll_skipped()
    test_sequential_polls_both_run()
    test_lock_released_after_poll()
    print("All 003 tests passed.")
