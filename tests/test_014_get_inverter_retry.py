"""Test 014: get_inverter() retries 3 times and returns None on total failure.

get_inverter() is a nested function inside main() in dbus-serialinverter.py and
closes over expected_inverter_types. Following the test_003 pattern, we recreate
the retry logic here as a standalone factory (_make_get_inverter) rather than
importing the entry-point module. This is intentional — importing dbus-serialinverter.py
would trigger the GLib/D-Bus imports it depends on.

If get_inverter() is ever moved to module scope in dbus-serialinverter.py, these
tests can be updated to exercise the real implementation directly.
"""
import time
import unittest.mock as mock


# ── Mirror of the production get_inverter() logic ─────────────────────────────

def _make_get_inverter(inverter_types):
    """
    Returns a get_inverter(port) function that mirrors dbus-serialinverter.py:56-77.
    Each inverter type dict must have 'inverter' (class) and 'baudrate' (int).
    Optional 'slave' (int, default 1).
    """
    def get_inverter(port):
        count = 3
        while count > 0:
            for test in inverter_types:
                inverter_class = test["inverter"]
                inv = inverter_class(
                    port=port,
                    baudrate=test["baudrate"],
                    slave=test.get("slave", 1),
                )
                if inv.test_connection():
                    return inv
            count -= 1
            time.sleep(0.5)
        return None
    return get_inverter


# ── Fake inverter classes ─────────────────────────────────────────────────────

def _always_fail_class():
    class _AlwaysFail:
        def __init__(self, **kw): pass
        def test_connection(self): return False
    return _AlwaysFail


def _always_succeed_class():
    class _AlwaysSucceed:
        def __init__(self, **kw):
            self.port = kw.get("port", "")
        def test_connection(self): return True
    return _AlwaysSucceed


# ── Tests ─────────────────────────────────────────────────────────────────────

@mock.patch("time.sleep")
def test_returns_none_after_three_failed_rounds(mock_sleep):
    get_inverter = _make_get_inverter([
        {"inverter": _always_fail_class(), "baudrate": 0, "slave": 0}
    ])
    result = get_inverter("/dev/null")
    assert result is None


@mock.patch("time.sleep")
def test_sleep_called_after_each_failed_round(mock_sleep):
    """Sleep must be called after each failed round (3 rounds → 3 sleeps)."""
    get_inverter = _make_get_inverter([
        {"inverter": _always_fail_class(), "baudrate": 0, "slave": 0}
    ])
    get_inverter("/dev/null")
    assert mock_sleep.call_count == 3


@mock.patch("time.sleep")
def test_returns_inverter_on_first_success(mock_sleep):
    SucceedClass = _always_succeed_class()
    get_inverter = _make_get_inverter([
        {"inverter": SucceedClass, "baudrate": 0, "slave": 0}
    ])
    result = get_inverter("/dev/null")
    assert isinstance(result, SucceedClass)


@mock.patch("time.sleep")
def test_no_sleep_when_first_attempt_succeeds(mock_sleep):
    get_inverter = _make_get_inverter([
        {"inverter": _always_succeed_class(), "baudrate": 0, "slave": 0}
    ])
    get_inverter("/dev/null")
    assert mock_sleep.call_count == 0


@mock.patch("time.sleep")
def test_first_type_in_list_wins(mock_sleep):
    """If both types would succeed, the first in the list must be returned."""
    call_order = []

    class _FirstType:
        def __init__(self, **kw): pass
        def test_connection(self):
            call_order.append("first")
            return True

    class _SecondType:
        def __init__(self, **kw): pass
        def test_connection(self):
            call_order.append("second")
            return True

    get_inverter = _make_get_inverter([
        {"inverter": _FirstType, "baudrate": 0},
        {"inverter": _SecondType, "baudrate": 0},
    ])
    result = get_inverter("/dev/null")
    assert isinstance(result, _FirstType)
    assert "second" not in call_order, "Second type must not be tried if first succeeds"


@mock.patch("time.sleep")
def test_tries_all_types_before_sleeping(mock_sleep):
    """Within a single round, all inverter types are tried before sleeping."""
    call_order = []

    class _FailA:
        def __init__(self, **kw): pass
        def test_connection(self):
            call_order.append("A")
            return False

    class _FailB:
        def __init__(self, **kw): pass
        def test_connection(self):
            call_order.append("B")
            return False

    get_inverter = _make_get_inverter([
        {"inverter": _FailA, "baudrate": 0},
        {"inverter": _FailB, "baudrate": 0},
    ])
    get_inverter("/dev/null")
    # Both types tried in each of 3 rounds → 6 total attempts
    assert call_order.count("A") == 3
    assert call_order.count("B") == 3


if __name__ == "__main__":
    with mock.patch("time.sleep"):
        test_returns_none_after_three_failed_rounds(mock.MagicMock())
        test_sleep_called_after_each_failed_round(mock.MagicMock())
        test_returns_inverter_on_first_success(mock.MagicMock())
        test_no_sleep_when_first_attempt_succeeds(mock.MagicMock())
        test_first_type_in_list_wins(mock.MagicMock())
        test_tries_all_types_before_sleeping(mock.MagicMock())
    print("All 014 tests passed.")
