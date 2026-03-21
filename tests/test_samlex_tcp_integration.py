# -*- coding: utf-8 -*-
"""TCP-based integration tests for Samlex EVO driver.

This uses a real Modbus TCP server that the driver connects to.
This tests the actual Modbus protocol stack without requiring serial hardware.

Usage:
    # Run TCP integration tests (automatically starts/stops server)
    python tests/test_samlex_tcp_integration.py

    # Run against existing server
    python tests/test_samlex_tcp_integration.py --server localhost:5020

    # Verbose output
    python tests/test_samlex_tcp_integration.py -v
"""

import sys
import os
import argparse
import time
import threading
from typing import Optional, Dict, Any

# Add paths for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "etc", "dbus-serialinverter"))
sys.path.insert(0, os.path.dirname(__file__))

# conftest.py stubs out pymodbus as a plain ModuleType (not a package) so that
# most tests don't need the real library. But samlex_tcp_server needs the real
# embedded pymodbus with its server subpackage, so clear any stubs first.
for _pm in list(sys.modules.keys()):
    if _pm == "pymodbus" or _pm.startswith("pymodbus."):
        del sys.modules[_pm]

# Import the TCP server
from samlex_tcp_server import SamlexModbusServer

# Stub out external dependencies before importing driver modules
import types
import configparser
import logging

for mod in ["dbus", "gi", "gi.repository", "gi.repository.GLib"]:
    sys.modules.setdefault(mod, types.ModuleType(mod))

# Import driver modules
from samlex_tcp import SamlexTCP
from samlex import REQUIRED_SAMLEX_REGISTERS
import utils

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("samlex_tcp_test")


class SamlexTCPIntegrationTest:
    """Integration test using TCP Modbus server."""

    # NOTE: These are PLACEHOLDER addresses for TCP testing only.
    # They match the samlex_tcp_server.py placeholder addresses.
    # Real Samlex register addresses are NDA-protected and not exposed here.
    DEFAULT_REGISTER_CONFIG = {
        # Identity - PLACEHOLDER address
        "REG_IDENTITY": 4021,
        "IDENTITY_VALUE": 16420,
        # AC Output - PLACEHOLDER addresses
        "REG_AC_OUT_VOLTAGE": 4023,
        "REG_AC_OUT_CURRENT": 4037,
        "REG_AC_OUT_POWER": 4056,
        "SCALE_AC_OUT_VOLTAGE": 0.1,
        "SCALE_AC_OUT_CURRENT": 0.01,
        "SCALE_AC_OUT_POWER": 1.0,
        # DC/Battery - PLACEHOLDER addresses
        "REG_DC_VOLTAGE": 4115,
        "REG_DC_CURRENT": 4129,
        "REG_SOC": 4048,
        "SCALE_DC_VOLTAGE": 0.1,
        "SCALE_DC_CURRENT": 0.01,
        # AC Input - PLACEHOLDER addresses
        "REG_AC_IN_VOLTAGE": 4107,
        "REG_AC_IN_CURRENT": 4138,
        "REG_AC_IN_CONNECTED": 4119,
        "SCALE_AC_IN_VOLTAGE": 0.1,
        "SCALE_AC_IN_CURRENT": 0.01,
        # Status - PLACEHOLDER addresses
        "REG_FAULT": 4092,
        "REG_CHARGE_STATE": 4061,
    }

    def __init__(self, server_host: str = "localhost", server_port: int = 5020,
                 external_server: Optional[str] = None, scenario: str = "normal"):
        """Initialize TCP integration test.

        Args:
            server_host: Host for the TCP server
            server_port: Port for the TCP server
            external_server: If set, connect to existing server instead of starting one
            scenario: Test scenario
        """
        self.server_host = server_host
        self.server_port = server_port
        self.external_server = external_server
        self.scenario = scenario
        self.server: Optional[SamlexModbusServer] = None
        self.samlex: Optional[SamlexTCP] = None
        self.config = self._create_config()

    def _create_config(self) -> configparser.ConfigParser:
        """Create test configuration."""
        cfg = configparser.ConfigParser()

        cfg.add_section("INVERTER")
        cfg.set("INVERTER", "TYPE", "SamlexTCP")
        cfg.set("INVERTER", "ADDRESS", "1")
        cfg.set("INVERTER", "POLL_INTERVAL", "1000")
        cfg.set("INVERTER", "MAX_AC_POWER", "4000")
        cfg.set("INVERTER", "PHASE", "L1")
        cfg.set("INVERTER", "POSITION", "1")

        cfg.add_section("SAMLEX_REGISTERS")
        for key, value in self.DEFAULT_REGISTER_CONFIG.items():
            cfg.set("SAMLEX_REGISTERS", key, str(value))

        return cfg

    def setup(self):
        """Set up the test environment."""
        logger.info("Setting up TCP integration test...")

        # Set up utils config
        utils.config = self.config
        utils.INVERTER_TYPE = "SamlexTCP"
        utils.INVERTER_MAX_AC_POWER = 4000.0
        utils.INVERTER_PHASE = "L1"
        utils.INVERTER_POLL_INTERVAL = 1000
        utils.INVERTER_POSITION = 1

        if not self.external_server:
            # Start our own server
            self.server = SamlexModbusServer(
                host=self.server_host,
                port=self.server_port,
                slave_address=1,
                scenario=self.scenario,
                identity_value=16420
            )
            self.server.start(blocking=False)
            logger.info(f"TCP server started on {self.server_host}:{self.server_port}")
            time.sleep(0.5)  # Wait for server to be ready
            connection_string = f"tcp://{self.server_host}:{self.server_port}"
        else:
            connection_string = (f"tcp://{self.external_server}"
                               if not self.external_server.startswith("tcp://")
                               else self.external_server)
            logger.info(f"Using external server: {connection_string}")

        # Create the Samlex TCP driver
        self.samlex = SamlexTCP(
            port=connection_string,
            baudrate=0,  # Ignored for TCP
            slave=1
        )

        logger.info("SamlexTCP driver created")

    def teardown(self):
        """Clean up test environment."""
        logger.info("Tearing down TCP integration test...")

        if self.samlex and self.samlex.client:
            try:
                self.samlex.client.close()
            except Exception as e:
                logger.warning(f"Error closing client: {e}")

        if self.server:
            self.server.stop()
            logger.info("TCP server stopped")

    def run_all_tests(self) -> Dict[str, Any]:
        """Run all TCP integration tests."""
        results = {
            "passed": [],
            "failed": [],
            "skipped": []
        }

        tests = [
            ("test_tcp_connection", self.test_tcp_connection),
            ("test_identity_verification", self.test_identity_verification),
            ("test_get_settings", self.test_get_settings),
            ("test_refresh_data", self.test_refresh_data),
            ("test_ac_output_values", self.test_ac_output_values),
            ("test_dc_battery_values", self.test_dc_battery_values),
            ("test_ac_input_values", self.test_ac_input_values),
            ("test_status_mapping", self.test_status_mapping),
            ("test_multiple_polls", self.test_multiple_polls),
        ]

        for test_name, test_func in tests:
            logger.info(f"\n{'='*60}")
            logger.info(f"Running: {test_name}")
            logger.info(f"{'='*60}")
            try:
                test_func()
                results["passed"].append(test_name)
                logger.info(f"✓ {test_name} PASSED")
            except AssertionError as e:
                results["failed"].append((test_name, str(e)))
                logger.error(f"✗ {test_name} FAILED: {e}")
            except Exception as e:
                results["failed"].append((test_name, f"Exception: {e}"))
                logger.error(f"✗ {test_name} ERROR: {e}")

        return results

    # -------------------------------------------------------------------------
    # Test methods
    # -------------------------------------------------------------------------

    def test_tcp_connection(self):
        """Test that TCP connection works."""
        assert self.samlex.is_tcp, "Driver should detect TCP mode"
        assert self.samlex.tcp_host == self.server_host, "TCP host should match"
        assert self.samlex.tcp_port == self.server_port, "TCP port should match"
        logger.info("TCP mode confirmed")

    def test_identity_verification(self):
        """Test identity register verification."""
        result = self.samlex.test_connection()
        assert result is True, "Identity verification should succeed"
        logger.info("Identity verification passed")

    def test_get_settings(self):
        """Test settings loading."""
        result = self.samlex.get_settings()
        assert result is True, "get_settings() should return True"
        assert self.samlex.max_ac_power == 4000.0
        logger.info("Settings loaded successfully")

    def test_refresh_data(self):
        """Test basic data refresh."""
        self.samlex.get_settings()
        result = self.samlex.refresh_data()
        assert result is True, "refresh_data() should return True"
        logger.info("Data refresh successful")

    def test_ac_output_values(self):
        """Test AC output values."""
        self.samlex.get_settings()
        self.samlex.refresh_data()

        voltage = self.samlex.energy_data["L1"]["ac_voltage"]
        current = self.samlex.energy_data["L1"]["ac_current"]
        power = self.samlex.energy_data["L1"]["ac_power"]

        logger.info(f"AC Output: {voltage}V, {current}A, {power}W")

        assert abs(voltage - 120.0) < 0.1, f"Expected ~120V, got {voltage}V"
        assert power == 1000, f"Expected 1000W, got {power}W"

    def test_dc_battery_values(self):
        """Test DC/battery values."""
        self.samlex.get_settings()
        self.samlex.refresh_data()

        voltage = self.samlex.energy_data["dc"]["voltage"]
        current = self.samlex.energy_data["dc"]["current"]
        soc = self.samlex.energy_data["dc"]["soc"]

        logger.info(f"DC Battery: {voltage}V, {current}A, {soc}%")

        assert abs(voltage - 26.4) < 0.1, f"Expected ~26.4V, got {voltage}V"
        assert soc == 85.0, f"Expected 85% SOC, got {soc}%"

    def test_ac_input_values(self):
        """Test AC input values."""
        self.samlex.get_settings()
        self.samlex.refresh_data()

        voltage = self.samlex.energy_data["ac_in"]["voltage"]
        current = self.samlex.energy_data["ac_in"]["current"]
        connected = self.samlex.energy_data["ac_in"]["connected"]

        logger.info(f"AC Input: {voltage}V, {current}A, connected={connected}")

        assert abs(voltage - 120.0) < 0.1
        assert connected == 1

    def test_status_mapping(self):
        """Test status mapping."""
        self.samlex.get_settings()
        self.samlex.refresh_data()

        status = self.samlex.status
        charge_state = self.samlex.energy_data["dc"]["charge_state"]

        logger.info(f"Status: {status}, Charge State: {charge_state}")

        # With no fault and power > 0, status should be 7 (Running)
        assert status == 7, f"Expected status 7, got {status}"

    def test_multiple_polls(self):
        """Test multiple poll cycles."""
        self.samlex.get_settings()

        for i in range(5):
            result = self.samlex.refresh_data()
            assert result is True, f"Poll {i+1} failed"
            time.sleep(0.05)

        logger.info("5 poll cycles completed successfully")


def print_results(results: Dict[str, Any]) -> int:
    """Print test results."""
    print("\n" + "=" * 70)
    print("TCP INTEGRATION TEST RESULTS")
    print("=" * 70)

    passed = len(results["passed"])
    failed = len(results["failed"])
    total = passed + failed

    print(f"\nTotal: {total}")
    print(f"  Passed: {passed}")
    print(f"  Failed: {failed}")

    if results["passed"]:
        print("\n✓ Passed tests:")
        for test in results["passed"]:
            print(f"    - {test}")

    if results["failed"]:
        print("\n✗ Failed tests:")
        for test, error in results["failed"]:
            print(f"    - {test}: {error}")

    print("\n" + "=" * 70)

    return 0 if failed == 0 else 1


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Samlex EVO TCP Integration Tests",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run with auto-started server
  python tests/test_samlex_tcp_integration.py

  # Connect to existing server
  python tests/test_samlex_tcp_integration.py --server localhost:5020

  # Custom port
  python tests/test_samlex_tcp_integration.py --port 15020

  # Different scenario
  python tests/test_samlex_tcp_integration.py --scenario fault
        """
    )

    parser.add_argument(
        "--server",
        metavar="HOST:PORT",
        help="Connect to existing server instead of starting one"
    )
    parser.add_argument(
        "--host",
        default="localhost",
        help="Server host (default: localhost)"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=5020,
        help="Server port (default: 5020)"
    )
    parser.add_argument(
        "--scenario",
        choices=["normal", "fault", "low_battery", "ac_disconnect", "heavy_load"],
        default="normal",
        help="Test scenario (default: normal)"
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose logging"
    )

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    print("\n" + "=" * 70)
    print("Samlex EVO TCP Integration Tests")
    print("=" * 70)
    print(f"Mode: {'EXTERNAL SERVER' if args.server else 'AUTO SERVER'}")
    if args.server:
        print(f"Server: {args.server}")
    else:
        print(f"Server: {args.host}:{args.port}")
    print(f"Scenario: {args.scenario}")
    print("=" * 70 + "\n")

    test = SamlexTCPIntegrationTest(
        server_host=args.host,
        server_port=args.port,
        external_server=args.server,
        scenario=args.scenario
    )

    try:
        test.setup()
        results = test.run_all_tests()
        exit_code = print_results(results)
    except KeyboardInterrupt:
        print("\n\nTest interrupted")
        exit_code = 130
    except Exception as e:
        logger.exception("Test failed")
        print(f"\nFATAL ERROR: {e}")
        exit_code = 2
    finally:
        test.teardown()

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
