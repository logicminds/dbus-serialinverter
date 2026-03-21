"""Test 042: dbushelper._port_id() — D-Bus-safe port identifier sanitization."""
import sys
import os

_DRIVER_DIR = os.path.join(os.path.dirname(__file__), "..", "etc", "dbus-serialinverter")
if _DRIVER_DIR not in sys.path:
    sys.path.insert(0, _DRIVER_DIR)

from dbushelper import _port_id


def test_serial_port_returns_device_name():
    assert _port_id("/dev/ttyUSB0") == "ttyUSB0"


def test_serial_ttyS_returns_device_name():
    assert _port_id("/dev/ttyS0") == "ttyS0"


def test_dev_null_returns_null():
    assert _port_id("/dev/null") == "null"


def test_tcp_localhost_replaces_colon():
    assert _port_id("tcp://localhost:5020") == "localhost_5020"


def test_tcp_ip_replaces_colon():
    assert _port_id("tcp://192.168.1.100:502") == "192.168.1.100_502"


def test_tcp_result_contains_no_colon():
    result = _port_id("tcp://localhost:5020")
    assert ":" not in result


def test_tcp_result_contains_no_slash():
    result = _port_id("tcp://localhost:5020")
    assert "/" not in result


if __name__ == "__main__":
    test_serial_port_returns_device_name()
    test_serial_ttyS_returns_device_name()
    test_dev_null_returns_null()
    test_tcp_localhost_replaces_colon()
    test_tcp_ip_replaces_colon()
    test_tcp_result_contains_no_colon()
    test_tcp_result_contains_no_slash()
    print("All 042 tests passed.")
