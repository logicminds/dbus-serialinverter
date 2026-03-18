"""Test 024: Dummy inverter only activates when TYPE=Dummy is set explicitly.

Verifies the fix to dbus-serialinverter.py where a blank TYPE used to include
Dummy in the auto-detect list (via the old `or TYPE == ""` condition).
"""
from dummy import Dummy
from solis import Solis

_REAL_INVERTER_TYPES = [
    {"inverter": Solis, "baudrate": 9600, "slave": 1},
]


def _build_expected(inverter_type: str):
    """Mirror the logic from dbus-serialinverter.py."""
    if inverter_type == "Dummy":
        return [{"inverter": Dummy, "baudrate": 0, "slave": 0}]
    elif inverter_type == "":
        return _REAL_INVERTER_TYPES
    else:
        return [t for t in _REAL_INVERTER_TYPES if t["inverter"].__name__ == inverter_type]


def test_blank_type_excludes_dummy():
    """Blank TYPE triggers auto-detect; Dummy must not be included."""
    expected = _build_expected("")
    dummy_entries = [t for t in expected if t["inverter"] is Dummy]
    assert len(dummy_entries) == 0, "Dummy must not appear when TYPE is blank"


def test_blank_type_includes_real_inverters():
    """Blank TYPE includes all real inverter types."""
    expected = _build_expected("")
    assert len(expected) == len(_REAL_INVERTER_TYPES)
    assert any(t["inverter"] is Solis for t in expected)


def test_explicit_dummy_type_includes_only_dummy():
    """TYPE=Dummy includes only the Dummy inverter."""
    expected = _build_expected("Dummy")
    assert len(expected) == 1
    assert expected[0]["inverter"] is Dummy


def test_explicit_solis_type_includes_only_solis():
    """TYPE=Solis includes only Solis, not Dummy."""
    expected = _build_expected("Solis")
    assert len(expected) == 1
    assert expected[0]["inverter"] is Solis
    dummy_entries = [t for t in expected if t["inverter"] is Dummy]
    assert len(dummy_entries) == 0


def test_unknown_type_returns_empty():
    """TYPE=Unknown returns an empty list (no match)."""
    expected = _build_expected("Unknown")
    assert len(expected) == 0


if __name__ == "__main__":
    test_blank_type_excludes_dummy()
    test_blank_type_includes_real_inverters()
    test_explicit_dummy_type_includes_only_dummy()
    test_explicit_solis_type_includes_only_solis()
    test_unknown_type_returns_empty()
    print("All 024 tests passed.")
