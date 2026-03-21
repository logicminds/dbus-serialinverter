"""Test 045: setup_instance registers /Settings/SystemSetup/AcInput1 for vebus.

Systemcalc reads /Settings/SystemSetup/AcInput1 to determine the AC source
type.  Without this setting, systemcalc reports AIS=240 (Inverting) and ini=0
even when the device publishes valid AC input data.

The driver must register this setting via SettingsDevice for vebus devices
(default=1, Grid) and must NOT register it for pvinverter devices.
"""
import unittest.mock as mock

import dbushelper


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_inverter(prefix, port="/dev/ttyUSB0"):
    inv = mock.MagicMock()
    inv.port = port
    inv.SERVICE_PREFIX = prefix
    return inv


def _capture_settings(prefix):
    """Run setup_instance and return the settings dict passed to SettingsDevice."""
    captured = {}

    def fake_settings_device(bus, settings, callback):
        captured["settings"] = settings
        # Provide a subscriptable object so get_role_instance() works
        inst = mock.MagicMock()
        inst.__getitem__ = lambda self, k: "vebus:257" if prefix.endswith("vebus") else "inverter:20"
        return inst

    inv = _make_inverter(prefix)
    helper = dbushelper.DbusHelper.__new__(dbushelper.DbusHelper)
    helper.inverter = inv
    helper.instance = 257
    helper.error_count = 0
    helper._prefix = prefix
    helper._dbusservice = mock.MagicMock()

    with mock.patch.object(dbushelper, "SettingsDevice", side_effect=fake_settings_device), \
         mock.patch.object(dbushelper, "get_bus", return_value=None):
        helper.setup_instance()

    return captured.get("settings", {})


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_vebus_registers_ac_input1_setting():
    settings = _capture_settings("com.victronenergy.vebus")
    assert "acInput1" in settings, "vebus setup_instance must register acInput1"


def test_vebus_ac_input1_path():
    settings = _capture_settings("com.victronenergy.vebus")
    assert settings["acInput1"][0] == "/Settings/SystemSetup/AcInput1"


def test_vebus_ac_input1_default_is_grid():
    """Default=1 (Grid) so systemcalc treats AC input as active."""
    settings = _capture_settings("com.victronenergy.vebus")
    assert settings["acInput1"][1] == 1


def test_vebus_ac_input1_range():
    """Min=0 (Not available), Max=3 (Shore power)."""
    settings = _capture_settings("com.victronenergy.vebus")
    assert settings["acInput1"][2] == 0  # min
    assert settings["acInput1"][3] == 3  # max


def test_pvinverter_does_not_register_ac_input1():
    settings = _capture_settings("com.victronenergy.pvinverter")
    assert "acInput1" not in settings, "pvinverter must NOT register acInput1"


def test_vebus_still_registers_instance_setting():
    """acInput1 must not break the existing instance setting."""
    settings = _capture_settings("com.victronenergy.vebus")
    assert "instance" in settings


if __name__ == "__main__":
    test_vebus_registers_ac_input1_setting()
    test_vebus_ac_input1_path()
    test_vebus_ac_input1_default_is_grid()
    test_vebus_ac_input1_range()
    test_pvinverter_does_not_register_ac_input1()
    test_vebus_still_registers_instance_setting()
    print("All 045 tests passed.")
