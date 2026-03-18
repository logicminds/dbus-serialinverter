"""Test 016: utils.py raises SystemExit with a clear message on bad config."""
import os
import sys
import shutil
import subprocess
import tempfile

_DRIVER_DIR = os.path.join(os.path.dirname(__file__), "..", "etc", "dbus-serialinverter")
_UTILS_SRC = os.path.join(_DRIVER_DIR, "utils.py")

_GOOD_CONFIG = """\
[DEFAULT]
PUBLISH_CONFIG_VALUES=1

[INVERTER]
TYPE=
ADDRESS=1
POLL_INTERVAL=1000
MAX_AC_POWER=800
PHASE=L1
POSITION=1
"""


def _run_import(config_content=None, write_config=True):
    """
    Copy utils.py into a temp dir, optionally write config.ini, then import utils.
    Returns (returncode, stdout, stderr).
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        shutil.copy(_UTILS_SRC, os.path.join(tmpdir, "utils.py"))
        if write_config and config_content is not None:
            with open(os.path.join(tmpdir, "config.ini"), "w") as f:
                f.write(config_content)
        result = subprocess.run(
            [sys.executable, "-c",
             "import sys; sys.path.insert(0, r'%s'); import utils" % tmpdir],
            capture_output=True,
            text=True,
        )
        return result.returncode, result.stdout, result.stderr


def test_good_config_exits_zero():
    """Sanity check: valid config.ini imports cleanly."""
    rc, _, _ = _run_import(_GOOD_CONFIG)
    assert rc == 0, "Expected clean import with valid config"


def test_missing_config_file_raises_system_exit():
    """No config.ini at all → SystemExit with clear message."""
    rc, _, stderr = _run_import(config_content=None, write_config=False)
    assert rc != 0, "Expected non-zero exit when config.ini is absent"
    assert "Config file missing or invalid" in stderr or "SystemExit" in stderr


def test_missing_inverter_section_raises_system_exit():
    """config.ini exists but has no [INVERTER] section → SystemExit."""
    bad_config = "[DEFAULT]\nPUBLISH_CONFIG_VALUES=1\n"
    rc, _, stderr = _run_import(bad_config)
    assert rc != 0
    assert "Config file missing or invalid" in stderr or "SystemExit" in stderr


def test_invalid_max_ac_power_raises_system_exit():
    """Non-numeric MAX_AC_POWER → SystemExit with 'Config error' message."""
    bad_config = _GOOD_CONFIG.replace("MAX_AC_POWER=800", "MAX_AC_POWER=notanumber")
    rc, _, stderr = _run_import(bad_config)
    assert rc != 0
    assert "Config error" in stderr or "SystemExit" in stderr


def test_zero_max_ac_power_raises_system_exit():
    """MAX_AC_POWER=0 → SystemExit (must be > 0)."""
    bad_config = _GOOD_CONFIG.replace("MAX_AC_POWER=800", "MAX_AC_POWER=0")
    rc, _, stderr = _run_import(bad_config)
    assert rc != 0
    assert "INVERTER_MAX_AC_POWER must be greater than 0" in stderr or "SystemExit" in stderr


def test_invalid_poll_interval_raises_system_exit():
    """Non-integer POLL_INTERVAL → SystemExit with 'Config error' message."""
    bad_config = _GOOD_CONFIG.replace("POLL_INTERVAL=1000", "POLL_INTERVAL=fast")
    rc, _, stderr = _run_import(bad_config)
    assert rc != 0
    assert "Config error" in stderr or "SystemExit" in stderr


if __name__ == "__main__":
    test_good_config_exits_zero()
    test_missing_config_file_raises_system_exit()
    test_missing_inverter_section_raises_system_exit()
    test_invalid_max_ac_power_raises_system_exit()
    test_zero_max_ac_power_raises_system_exit()
    test_invalid_poll_interval_raises_system_exit()
    print("All 016 tests passed.")
