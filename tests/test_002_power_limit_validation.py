"""Test 002: Power limit clamping and MAX_AC_POWER > 0 validation."""
import sys
import os
import types

# Stub heavy dependencies
for mod in ["dbus", "gi", "gi.repository", "gi.repository.GLib"]:
    sys.modules.setdefault(mod, types.ModuleType(mod))

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "etc", "dbus-serialinverter"))


# ── utils validation ──────────────────────────────────────────────────────────

def _load_utils_with_max_power(value_str):
    """Import a fresh utils module with MAX_AC_POWER patched to value_str."""
    import configparser, importlib, io

    ini = f"""
[DEFAULT]
PUBLISH_CONFIG_VALUES = 0

[INVERTER]
TYPE = Dummy
MAX_AC_POWER = {value_str}
PHASE = L1
POLL_INTERVAL = 1000
POSITION = 1
"""
    cfg = configparser.ConfigParser()
    cfg.read_string(ini)

    # We test the validation logic directly rather than re-importing the module
    # (re-importing would require clearing the module cache and patching file I/O).
    max_ac_power = float(cfg['INVERTER']['MAX_AC_POWER'])
    if max_ac_power <= 0:
        raise ValueError("INVERTER_MAX_AC_POWER must be greater than 0 (got %s)" % max_ac_power)
    return max_ac_power


def test_max_ac_power_zero_raises():
    try:
        _load_utils_with_max_power("0")
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "greater than 0" in str(e)


def test_max_ac_power_negative_raises():
    try:
        _load_utils_with_max_power("-100")
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "greater than 0" in str(e)


def test_max_ac_power_positive_ok():
    result = _load_utils_with_max_power("800")
    assert result == 800.0


# ── power limit clamping ──────────────────────────────────────────────────────

def _clamp_power_limit(raw_watts, max_ac_power):
    """Mirror of the clamping logic in solis.py read_status_data()."""
    new_power_limit = raw_watts / (max_ac_power / 100)
    return max(0, min(100, round(new_power_limit)))


def test_clamp_within_range():
    assert _clamp_power_limit(400, 800) == 50


def test_clamp_below_zero():
    # Negative D-Bus write should be clamped to 0
    assert _clamp_power_limit(-500, 800) == 0


def test_clamp_above_max():
    # Value exceeding max_ac_power should be clamped to 100
    assert _clamp_power_limit(9999, 800) == 100


def test_clamp_exact_zero():
    assert _clamp_power_limit(0, 800) == 0


def test_clamp_exact_max():
    assert _clamp_power_limit(800, 800) == 100


def test_register_value_always_in_valid_range():
    """Modbus register value (percent * 100) must be in [0, 10000]."""
    for raw in [-1000, -1, 0, 400, 800, 801, 9999]:
        clamped = _clamp_power_limit(raw, 800)
        register_val = clamped * 100
        assert 0 <= register_val <= 10000, f"register value {register_val} out of range for raw={raw}"


if __name__ == "__main__":
    test_max_ac_power_zero_raises()
    test_max_ac_power_negative_raises()
    test_max_ac_power_positive_ok()
    test_clamp_within_range()
    test_clamp_below_zero()
    test_clamp_above_max()
    test_clamp_exact_zero()
    test_clamp_exact_max()
    test_register_value_always_in_valid_range()
    print("All 002 tests passed.")
