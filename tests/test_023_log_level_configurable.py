"""Test 023: utils.py log level is read from config, not hardcoded to DEBUG."""
import os
import sys
import shutil
import subprocess
import tempfile

_DRIVER_DIR = os.path.join(os.path.dirname(__file__), "..", "etc", "dbus-serialinverter")
_UTILS_SRC = os.path.join(_DRIVER_DIR, "utils.py")

_BASE_CONFIG = """\
[DEFAULT]
PUBLISH_CONFIG_VALUES=1
LOG_LEVEL={level}

[INVERTER]
TYPE=
ADDRESS=1
POLL_INTERVAL=1000
MAX_AC_POWER=800
PHASE=L1
POSITION=1
"""


def _run_log_level_check(log_level):
    """Import utils with the given LOG_LEVEL and return the logger's effective level."""
    with tempfile.TemporaryDirectory() as tmpdir:
        shutil.copy(_utils_src(), os.path.join(tmpdir, "utils.py"))
        with open(os.path.join(tmpdir, "config.ini"), "w") as f:
            f.write(_BASE_CONFIG.format(level=log_level))
        script = (
            "import sys; sys.path.insert(0, r'%s'); import utils, logging; "
            "print(utils.logger.getEffectiveLevel())"
        ) % tmpdir
        result = subprocess.run([sys.executable, "-c", script],
                                capture_output=True, text=True)
        assert result.returncode == 0, f"Import failed: {result.stderr}"
        return int(result.stdout.strip())


def _utils_src():
    return _UTILS_SRC


def test_default_log_level_is_not_debug():
    """With LOG_LEVEL=INFO in config, the effective level must not be DEBUG (10)."""
    import logging
    level = _run_log_level_check("INFO")
    assert level != logging.DEBUG, (
        f"Expected level != DEBUG ({logging.DEBUG}), got {level}"
    )
    assert level == logging.INFO


def test_log_level_info():
    import logging
    level = _run_log_level_check("INFO")
    assert level == logging.INFO


def test_log_level_debug_when_configured():
    """Operators can re-enable DEBUG by setting LOG_LEVEL=DEBUG."""
    import logging
    level = _run_log_level_check("DEBUG")
    assert level == logging.DEBUG


def test_log_level_warning():
    import logging
    level = _run_log_level_check("WARNING")
    assert level == logging.WARNING


def test_no_hardcoded_set_level_debug_in_source():
    """The unconditional setLevel(logging.DEBUG) line must not appear in utils.py."""
    with open(_UTILS_SRC) as f:
        source = f.read()
    assert "setLevel(logging.DEBUG)" not in source, (
        "utils.py must not hardcode setLevel(logging.DEBUG)"
    )


if __name__ == "__main__":
    test_default_log_level_is_not_debug()
    test_log_level_info()
    test_log_level_debug_when_configured()
    test_log_level_warning()
    test_no_hardcoded_set_level_debug_in_source()
    print("All 023 tests passed.")
