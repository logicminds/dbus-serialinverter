"""Test 008: DbusHelper._fmt() factory returns correct unit-formatted strings."""
import sys
import os
import types
import logging

for mod in ["dbus", "gi", "gi.repository", "gi.repository.GLib", "vedbus", "settingsdevice"]:
    sys.modules.setdefault(mod, types.ModuleType(mod))

if not hasattr(sys.modules["vedbus"], "VeDbusService"):
    sys.modules["vedbus"].VeDbusService = type(
        "VeDbusService", (), {"__init__": lambda self, *a, **kw: None}
    )
if not hasattr(sys.modules["settingsdevice"], "SettingsDevice"):
    sys.modules["settingsdevice"].SettingsDevice = type(
        "SettingsDevice", (), {"__init__": lambda self, *a, **kw: None}
    )

utils_stub = sys.modules.setdefault("utils", types.ModuleType("utils"))
if not hasattr(utils_stub, "logger"):
    utils_stub.logger = logging.getLogger("test")
for _attr, _val in [
    ("INVERTER_POLL_INTERVAL", 1000), ("PUBLISH_CONFIG_VALUES", 0),
    ("DRIVER_VERSION", "0.1"), ("DRIVER_SUBVERSION", ".1"),
    ("publish_config_variables", lambda *a: None),
]:
    if not hasattr(utils_stub, _attr):
        setattr(utils_stub, _attr, _val)

sys.modules.setdefault("inverter", types.ModuleType("inverter"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "etc", "dbus-serialinverter"))
import dbushelper

# Build a helper instance without touching D-Bus constructor
_helper = dbushelper.DbusHelper.__new__(dbushelper.DbusHelper)


# ── kWh formatter ─────────────────────────────────────────────────────────────

def test_kwh_formats_decimal():
    fmt = _helper._fmt("%.2FkWh")
    assert fmt(None, 1.5) == "1.50kWh"


def test_kwh_formats_zero():
    fmt = _helper._fmt("%.2FkWh")
    assert fmt(None, 0.0) == "0.00kWh"


def test_kwh_formats_large_value():
    fmt = _helper._fmt("%.2FkWh")
    assert fmt(None, 1234.5) == "1234.50kWh"


# ── W formatter ───────────────────────────────────────────────────────────────

def test_w_formats_integer_result():
    fmt = _helper._fmt("%.0FW")
    assert fmt(None, 230.0) == "230W"


def test_w_formats_zero():
    fmt = _helper._fmt("%.0FW")
    assert fmt(None, 0.0) == "0W"


def test_w_rounds_fractional():
    # %.0F rounds to nearest integer
    fmt = _helper._fmt("%.0FW")
    assert fmt(None, 230.6) == "231W"


# ── V formatter ───────────────────────────────────────────────────────────────

def test_v_formats_voltage():
    fmt = _helper._fmt("%.0FV")
    assert fmt(None, 230.0) == "230V"


def test_v_formats_zero():
    fmt = _helper._fmt("%.0FV")
    assert fmt(None, 0.0) == "0V"


# ── A formatter ───────────────────────────────────────────────────────────────

def test_a_formats_current():
    # 800W / 230V ≈ 3.478A → rounds to 3A
    fmt = _helper._fmt("%.0FA")
    assert fmt(None, 3.478) == "3A"


def test_a_rounds_up():
    fmt = _helper._fmt("%.0FA")
    assert fmt(None, 3.6) == "4A"


def test_a_formats_zero():
    fmt = _helper._fmt("%.0FA")
    assert fmt(None, 0.0) == "0A"


# ── None input documents expected TypeError ───────────────────────────────────

def test_kwh_raises_on_none():
    """_fmt("%.2FkWh") calls float(value) — None is not valid. Documents this."""
    fmt = _helper._fmt("%.2FkWh")
    try:
        fmt(None, None)
        assert False, "Should raise TypeError when value is None"
    except TypeError:
        pass  # expected — D-Bus paths are initialised to 0, not None


if __name__ == "__main__":
    test_kwh_formats_decimal()
    test_kwh_formats_zero()
    test_kwh_formats_large_value()
    test_w_formats_integer_result()
    test_w_formats_zero()
    test_w_rounds_fractional()
    test_v_formats_voltage()
    test_v_formats_zero()
    test_a_formats_current()
    test_a_rounds_up()
    test_a_formats_zero()
    test_kwh_raises_on_none()
    print("All 008 tests passed.")
