"""Test 025: utils.py direct coverage via importlib.

Loads the real utils.py by file path so coverage tracks it, without
disturbing the sys.modules['utils'] stub used by all other tests.
"""
import importlib.util
import os

_DRIVER_DIR = os.path.join(os.path.dirname(__file__), "..", "etc", "dbus-serialinverter")
_UTILS_PATH = os.path.abspath(os.path.join(_DRIVER_DIR, "utils.py"))


def _load_utils_real():
    """Execute the real utils.py via importlib so coverage tracks it.

    Uses a unique module name to avoid touching sys.modules['utils'].
    """
    spec = importlib.util.spec_from_file_location("_utils_cov", _UTILS_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ── Module-level constants ────────────────────────────────────────────────────

def test_driver_version_is_float():
    mod = _load_utils_real()
    assert isinstance(mod.DRIVER_VERSION, float)


def test_driver_version_value():
    mod = _load_utils_real()
    assert mod.DRIVER_VERSION == 0.3


def test_driver_subversion_is_string():
    mod = _load_utils_real()
    assert isinstance(mod.DRIVER_SUBVERSION, str)


def test_inverter_type_is_string():
    mod = _load_utils_real()
    assert isinstance(mod.INVERTER_TYPE, str)


def test_inverter_max_ac_power_positive():
    mod = _load_utils_real()
    assert mod.INVERTER_MAX_AC_POWER > 0


def test_inverter_phase_is_valid():
    mod = _load_utils_real()
    assert mod.INVERTER_PHASE in ("L1", "L2", "L3")


def test_inverter_poll_interval_positive():
    mod = _load_utils_real()
    assert mod.INVERTER_POLL_INTERVAL > 0


def test_inverter_position_valid():
    mod = _load_utils_real()
    assert mod.INVERTER_POSITION in (0, 1, 2)


def test_publish_config_values_is_int():
    mod = _load_utils_real()
    assert isinstance(mod.PUBLISH_CONFIG_VALUES, int)


def test_logger_exists():
    mod = _load_utils_real()
    import logging
    assert isinstance(mod.logger, logging.Logger)


# ── publish_config_variables ──────────────────────────────────────────────────

def test_publish_config_variables_adds_paths():
    """publish_config_variables adds at least one /Info/Config/ path."""
    mod = _load_utils_real()
    added = {}

    class _FakeSvc:
        def add_path(self, path, value):
            added[path] = value

    mod.publish_config_variables(_FakeSvc())
    assert len(added) > 0
    for path in added:
        assert path.startswith("/Info/Config/")


def test_publish_config_variables_only_primitive_types():
    """Only float/int/str/list values are published to D-Bus."""
    mod = _load_utils_real()
    added = {}

    class _FakeSvc:
        def add_path(self, path, value):
            added[path] = value

    mod.publish_config_variables(_FakeSvc())
    for path, value in added.items():
        assert isinstance(value, (float, int, str, list)), (
            f"{path} has unexpected type {type(value)}"
        )


def test_publish_config_variables_includes_driver_version():
    """DRIVER_VERSION constant is published."""
    mod = _load_utils_real()
    added = {}

    class _FakeSvc:
        def add_path(self, path, value):
            added[path] = value

    mod.publish_config_variables(_FakeSvc())
    keys = [p.split("/")[-1] for p in added]
    assert "DRIVER_VERSION" in keys


if __name__ == "__main__":
    test_driver_version_is_float()
    test_driver_version_value()
    test_driver_subversion_is_string()
    test_inverter_type_is_string()
    test_inverter_max_ac_power_positive()
    test_inverter_phase_is_valid()
    test_inverter_poll_interval_positive()
    test_inverter_position_valid()
    test_publish_config_values_is_int()
    test_logger_exists()
    test_publish_config_variables_adds_paths()
    test_publish_config_variables_only_primitive_types()
    test_publish_config_variables_includes_driver_version()
    print("All 025 tests passed.")
