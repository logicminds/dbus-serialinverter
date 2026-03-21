# -*- coding: utf-8 -*-
"""Integration tests for Samlex EVO driver.

Tests the full driver lifecycle against either:
  - A mock Modbus client (for automated testing)
  - Real Samlex EVO hardware (for validation)

Usage:
    # Run with mock client (default)
    python tests/test_samlex_integration.py

    # Run with real hardware (requires Samlex EVO connected)
    python tests/test_samlex_integration.py --real-device /dev/ttyUSB0

    # Run specific test scenarios with mock
    python tests/test_samlex_integration.py --scenario fault_condition

    # Run all tests and show detailed output
    python tests/test_samlex_integration.py -v
"""

import sys
import os
import argparse
from typing import Optional, Dict, Any

# Add paths for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "etc", "dbus-serialinverter"))

# Stub out external dependencies before importing driver modules
import types
import configparser
import logging

for mod in ["dbus", "gi", "gi.repository", "gi.repository.GLib"]:
    sys.modules.setdefault(mod, types.ModuleType(mod))

# Import the mock client
from samlex_mock_client import MockModbusClient, create_evo_4024_registers, SamlexScenario

# Import driver modules
from samlex import Samlex
import utils

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("samlex_integration_test")


class SamlexIntegrationTest:
    """Integration test framework for Samlex EVO driver.

    Can run against either a mock client or real hardware.
    """

    # Default register configuration for testing (matches mock client defaults)
    DEFAULT_REGISTER_CONFIG = {
        # Identity
        "REG_IDENTITY": 0,
        "IDENTITY_VALUE": 16420,  # 0x4024 for EVO-4024
        # AC Output
        "REG_AC_OUT_VOLTAGE": 20,
        "REG_AC_OUT_CURRENT": 21,
        "REG_AC_OUT_POWER": 22,
        "SCALE_AC_OUT_VOLTAGE": 0.1,
        "SCALE_AC_OUT_CURRENT": 0.01,
        "SCALE_AC_OUT_POWER": 1.0,
        # DC/Battery
        "REG_DC_VOLTAGE": 10,
        "REG_DC_CURRENT": 11,
        "REG_SOC": 30,
        "SCALE_DC_VOLTAGE": 0.1,
        "SCALE_DC_CURRENT": 0.01,
        # AC Input
        "REG_AC_IN_VOLTAGE": 40,
        "REG_AC_IN_CURRENT": 41,
        "REG_AC_IN_CONNECTED": 42,
        "SCALE_AC_IN_VOLTAGE": 0.1,
        "SCALE_AC_IN_CURRENT": 0.01,
        # Status
        "REG_FAULT": 2,
        "REG_CHARGE_STATE": 31,
    }

    def __init__(self, use_mock: bool = True, device_port: Optional[str] = None,
                 identity_value: int = 16420, scenario: str = "normal"):
        """Initialize the test framework.

        Args:
            use_mock: If True, use a mock Modbus client
            device_port: Serial port for real device (required if use_mock=False)
            identity_value: The expected identity value from the inverter
            scenario: Test scenario (normal, fault, low_battery, ac_disconnect, heavy_load)
        """
        self.use_mock = use_mock
        self.device_port = device_port
        self.identity_value = identity_value
        self.scenario = scenario
        self.mock_client: Optional[MockModbusClient] = None
        self.samlex: Optional[Samlex] = None
        self.config = self._create_test_config()

        if not use_mock and not device_port:
            raise ValueError("device_port required when use_mock=False")

    def _create_test_config(self) -> configparser.ConfigParser:
        """Create test configuration."""
        cfg = configparser.ConfigParser()

        # INVERTER section
        cfg.add_section("INVERTER")
        cfg.set("INVERTER", "TYPE", "Samlex")
        cfg.set("INVERTER", "ADDRESS", "1")
        cfg.set("INVERTER", "POLL_INTERVAL", "1000")
        cfg.set("INVERTER", "MAX_AC_POWER", "4000")
        cfg.set("INVERTER", "PHASE", "L1")
        cfg.set("INVERTER", "POSITION", "1")

        # SAMLEX_REGISTERS section
        cfg.add_section("SAMLEX_REGISTERS")
        for key, value in self.DEFAULT_REGISTER_CONFIG.items():
            cfg.set("SAMLEX_REGISTERS", key, str(value))

        return cfg

    def setup(self):
        """Set up the test environment."""
        logger.info("Setting up integration test environment...")

        # Set up utils config
        utils.config = self.config
        utils.INVERTER_TYPE = "Samlex"
        utils.INVERTER_MAX_AC_POWER = 4000.0
        utils.INVERTER_PHASE = "L1"
        utils.INVERTER_POLL_INTERVAL = 1000
        utils.INVERTER_POSITION = 1

        # Create the Samlex driver instance
        self.samlex = Samlex(
            port=self.device_port or "/dev/null",
            baudrate=9600,
            slave=1
        )

        if self.use_mock:
            # Create mock client with appropriate scenario
            registers = create_evo_4024_registers()

            if self.scenario == "fault":
                registers = SamlexScenario.fault_condition(registers)
            elif self.scenario == "low_battery":
                registers = SamlexScenario.low_battery(registers)
            elif self.scenario == "ac_disconnect":
                registers = SamlexScenario.ac_input_disconnected(registers)
            elif self.scenario == "heavy_load":
                registers = SamlexScenario.heavy_load(registers)

            self.mock_client = MockModbusClient(registers=registers)

            # Replace the driver's client with our mock
            self.samlex.client = self.mock_client

            logger.info(f"Mock client configured for scenario: {self.scenario}")
        else:
            logger.info(f"Using real device on port: {self.device_port}")

        logger.info("Samlex driver ready")

    def teardown(self):
        """Clean up test environment."""
        logger.info("Tearing down test environment...")

        if self.samlex and hasattr(self.samlex, 'client') and self.samlex.client:
            try:
                if hasattr(self.samlex.client, 'close'):
                    self.samlex.client.close()
            except Exception as e:
                logger.warning(f"Error closing client: {e}")

        self.mock_client = None
        self.samlex = None

    def run_all_tests(self) -> Dict[str, Any]:
        """Run all integration tests.

        Returns:
            Dict with test results
        """
        results = {
            "passed": [],
            "failed": [],
            "skipped": []
        }

        tests = [
            ("test_connection", self.test_connection),
            ("test_get_settings", self.test_get_settings),
            ("test_refresh_data_basic", self.test_refresh_data_basic),
            ("test_ac_output_values", self.test_ac_output_values),
            ("test_dc_battery_values", self.test_dc_battery_values),
            ("test_ac_input_values", self.test_ac_input_values),
            ("test_status_mapping", self.test_status_mapping),
            ("test_charge_state", self.test_charge_state),
            ("test_multiple_poll_cycles", self.test_multiple_poll_cycles),
            ("test_energy_data_structure", self.test_energy_data_structure),
        ]

        # Add mock-only tests
        if self.use_mock:
            tests.extend([
                ("test_fault_condition", self.test_fault_condition),
                ("test_ac_input_disconnect", self.test_ac_input_disconnect),
                ("test_register_read_failure", self.test_register_read_failure),
                ("test_mock_client_call_history", self.test_mock_client_call_history),
            ])

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

    # ---------------------------------------------------------------------
    # Test methods
    # ---------------------------------------------------------------------

    def test_connection(self):
        """Test that driver can connect and identify the inverter."""
        result = self.samlex.test_connection()
        assert result is True, f"test_connection() should return True, got {result}"
        logger.info("Connection test passed")

    def test_get_settings(self):
        """Test that get_settings() populates all required fields."""
        result = self.samlex.get_settings()
        assert result is True, f"get_settings() should return True, got {result}"

        # Verify settings were populated
        assert self.samlex.max_ac_power == 4000.0, f"max_ac_power should be 4000.0, got {self.samlex.max_ac_power}"
        assert self.samlex.phase == "L1", f"phase should be L1, got {self.samlex.phase}"
        assert self.samlex.position == 1, f"position should be 1, got {self.samlex.position}"
        assert self.samlex.poll_interval == 1000, f"poll_interval should be 1000, got {self.samlex.poll_interval}"

        # Verify power limits are set to None for Samlex
        assert self.samlex.energy_data["overall"]["power_limit"] is None, \
            "power_limit should be None (not supported)"
        assert self.samlex.energy_data["overall"]["active_power_limit"] is None, \
            "active_power_limit should be None (not supported)"

        logger.info("Settings test passed")

    def test_refresh_data_basic(self):
        """Test basic refresh_data() call."""
        # First get settings
        self.samlex.get_settings()

        # Then refresh data
        result = self.samlex.refresh_data()
        assert result is True, f"refresh_data() should return True, got {result}"

        logger.info("Basic refresh data test passed")

    def test_ac_output_values(self):
        """Test AC output values are read and scaled correctly."""
        self.samlex.get_settings()
        self.samlex.refresh_data()

        # With default mock values:
        # - Raw voltage: 1200, scale: 0.1 -> expected: 120.0V
        # - Raw current: 833, scale: 0.01 -> expected: 8.33A
        # - Raw power: 1000, scale: 1.0 -> expected: 1000W

        voltage = self.samlex.energy_data["L1"]["ac_voltage"]
        current = self.samlex.energy_data["L1"]["ac_current"]
        power = self.samlex.energy_data["L1"]["ac_power"]

        logger.info(f"AC Output - Voltage: {voltage}V, Current: {current}A, Power: {power}W")

        # Allow some tolerance for floating point
        assert abs(voltage - 120.0) < 0.1, f"Expected voltage ~120.0V, got {voltage}V"
        assert abs(current - 8.33) < 0.01, f"Expected current ~8.33A, got {current}A"
        assert power == 1000, f"Expected power 1000W, got {power}W"

        # Verify power propagated to overall
        overall_power = self.samlex.energy_data["overall"]["ac_power"]
        assert overall_power == power, f"Overall power {overall_power} should match L1 power {power}"

        logger.info("AC output values test passed")

    def test_dc_battery_values(self):
        """Test DC/battery values are read and scaled correctly."""
        self.samlex.get_settings()
        self.samlex.refresh_data()

        # With default mock values:
        # - Raw voltage: 264, scale: 0.1 -> expected: 26.4V
        # - Raw current: 520, scale: 0.01 -> expected: 5.2A
        # - SOC: 85 (no scaling)

        voltage = self.samlex.energy_data["dc"]["voltage"]
        current = self.samlex.energy_data["dc"]["current"]
        soc = self.samlex.energy_data["dc"]["soc"]

        logger.info(f"DC Battery - Voltage: {voltage}V, Current: {current}A, SOC: {soc}%")

        assert abs(voltage - 26.4) < 0.1, f"Expected voltage ~26.4V, got {voltage}V"
        assert abs(current - 5.2) < 0.1, f"Expected current ~5.2A, got {current}A"
        assert soc == 85.0, f"Expected SOC 85%, got {soc}%"

        logger.info("DC battery values test passed")

    def test_ac_input_values(self):
        """Test AC input values are read and scaled correctly."""
        self.samlex.get_settings()
        self.samlex.refresh_data()

        # With default mock values:
        # - Raw voltage: 1200, scale: 0.1 -> expected: 120.0V
        # - Raw current: 417, scale: 0.01 -> expected: 4.17A
        # - Connected: 1

        voltage = self.samlex.energy_data["ac_in"]["voltage"]
        current = self.samlex.energy_data["ac_in"]["current"]
        connected = self.samlex.energy_data["ac_in"]["connected"]

        logger.info(f"AC Input - Voltage: {voltage}V, Current: {current}A, Connected: {connected}")

        assert abs(voltage - 120.0) < 0.1, f"Expected voltage ~120.0V, got {voltage}V"
        assert abs(current - 4.17) < 0.01, f"Expected current ~4.17A, got {current}A"
        assert connected == 1, f"Expected connected=1, got {connected}"

        logger.info("AC input values test passed")

    def test_status_mapping(self):
        """Test that status is mapped correctly."""
        self.samlex.get_settings()
        self.samlex.refresh_data()

        status = self.samlex.status
        charge_state = self.samlex.energy_data["dc"].get("charge_state")

        logger.info(f"Status: {status}, Charge State: {charge_state}")

        # With no fault and power > 0, status should be 7 (Running)
        assert status == 7, f"Expected status 7 (Running), got {status}"
        assert charge_state == 2, f"Expected charge state 2, got {charge_state}"

        logger.info("Status mapping test passed")

    def test_charge_state(self):
        """Test that charge state is stored correctly."""
        self.samlex.get_settings()
        self.samlex.refresh_data()

        charge_state = self.samlex.energy_data["dc"]["charge_state"]

        # Mock returns 2 (Absorption) by default
        assert charge_state == 2, f"Expected charge state 2, got {charge_state}"

        logger.info("Charge state test passed")

    def test_multiple_poll_cycles(self):
        """Test that multiple poll cycles work correctly."""
        self.samlex.get_settings()

        for i in range(3):
            result = self.samlex.refresh_data()
            assert result is True, f"Poll cycle {i+1} failed"
            logger.info(f"Poll cycle {i+1} complete - Status: {self.samlex.status}")

        logger.info("Multiple poll cycles test passed")

    def test_energy_data_structure(self):
        """Test that energy_data has the expected structure."""
        self.samlex.get_settings()
        self.samlex.refresh_data()

        # Check required keys exist
        required_sections = ["L1", "L2", "L3", "dc", "ac_in", "overall"]
        for section in required_sections:
            assert section in self.samlex.energy_data, \
                f"energy_data should have '{section}' section"

        # Check L1 has required fields
        l1_fields = ["ac_voltage", "ac_current", "ac_power", "energy_forwarded"]
        for field in l1_fields:
            assert field in self.samlex.energy_data["L1"], \
                f"L1 should have '{field}' field"

        # Check dc has required fields
        dc_fields = ["voltage", "current", "soc", "charge_state"]
        for field in dc_fields:
            assert field in self.samlex.energy_data["dc"], \
                f"dc should have '{field}' field"

        # Check ac_in has required fields
        ac_in_fields = ["voltage", "current", "connected"]
        for field in ac_in_fields:
            assert field in self.samlex.energy_data["ac_in"], \
                f"ac_in should have '{field}' field"

        # Check overall has required fields
        overall_fields = ["ac_power", "power_limit", "active_power_limit", "energy_forwarded"]
        for field in overall_fields:
            assert field in self.samlex.energy_data["overall"], \
                f"overall should have '{field}' field"

        logger.info("Energy data structure test passed")

    # ---------------------------------------------------------------------
    # Mock-only test methods (simulate fault conditions)
    # ---------------------------------------------------------------------

    def test_fault_condition(self):
        """Test that fault condition is detected (mock only)."""
        if not self.use_mock:
            logger.info("Skipping - requires mock client")
            return

        self.samlex.get_settings()

        # Simulate a fault
        self.mock_client.set_register(2, 1)  # Set fault register to 1

        # Refresh data
        self.samlex.refresh_data()

        # With fault != 0, status should be 10 (Error)
        status = self.samlex.status
        logger.info(f"Fault status: {status}")
        assert status == 10, f"Expected status 10 (Error) with fault, got {status}"

        logger.info("Fault condition test passed")

    def test_ac_input_disconnect(self):
        """Test AC input disconnect detection (mock only)."""
        if not self.use_mock:
            logger.info("Skipping - requires mock client")
            return

        self.samlex.get_settings()

        # Simulate AC input disconnected
        self.mock_client.set_register(42, 0)  # AC in connected = 0

        self.samlex.refresh_data()

        connected = self.samlex.energy_data["ac_in"]["connected"]
        logger.info(f"AC input connected: {connected}")
        assert connected == 0, f"Expected connected=0, got {connected}"

        logger.info("AC input disconnect test passed")

    def test_register_read_failure(self):
        """Test behavior when a register read fails (mock only)."""
        if not self.use_mock:
            logger.info("Skipping - requires mock client")
            return

        self.samlex.get_settings()

        # Configure mock to fail on fault register read
        self.mock_client.add_fail_address(2)

        try:
            result = self.samlex.refresh_data()
            # Should return False because the read failed
            assert result is False, f"Expected False on register read failure, got {result}"
        finally:
            # Clean up failure config
            self.mock_client.clear_failures()

        logger.info("Register read failure test passed")

    def test_mock_client_call_history(self):
        """Test that mock client tracks all Modbus calls."""
        if not self.use_mock:
            logger.info("Skipping - requires mock client")
            return

        # Clear history
        self.mock_client.clear_call_history()

        self.samlex.get_settings()
        self.samlex.refresh_data()

        history = self.mock_client.get_call_history()

        # Should have multiple read calls
        read_calls = [c for c in history if c["method"] == "read_input_registers"]
        assert len(read_calls) > 0, "Expected read_input_registers calls"

        # Log the calls
        logger.info(f"Mock client received {len(read_calls)} read calls:")
        for call in read_calls:
            logger.info(f"  address={call['address']}, count={call['count']}")

        logger.info("Mock client call history test passed")


def print_results(results: Dict[str, Any]) -> int:
    """Print test results in a readable format.

    Returns:
        Exit code (0 for success, 1 for failures)
    """
    print("\n" + "=" * 70)
    print("INTEGRATION TEST RESULTS")
    print("=" * 70)

    passed = len(results["passed"])
    failed = len(results["failed"])
    skipped = len(results["skipped"])
    total = passed + failed + skipped

    print(f"\nTotal: {total}")
    print(f"  Passed: {passed}")
    print(f"  Failed: {failed}")
    print(f"  Skipped: {skipped}")

    if results["passed"]:
        print("\n✓ Passed tests:")
        for test in results["passed"]:
            print(f"    - {test}")

    if results["failed"]:
        print("\n✗ Failed tests:")
        for test, error in results["failed"]:
            print(f"    - {test}: {error}")

    if results["skipped"]:
        print("\n⊘ Skipped tests:")
        for test in results["skipped"]:
            print(f"    - {test}")

    print("\n" + "=" * 70)

    if failed == 0:
        print("All tests passed! ✓")
        return 0
    else:
        print(f"{failed} test(s) failed.")
        return 1


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Samlex EVO Driver Integration Tests",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run with mock client (default)
  python tests/test_samlex_integration.py

  # Run with mock, specific scenario
  python tests/test_samlex_integration.py --scenario fault_condition

  # Run with real hardware
  python tests/test_samlex_integration.py --real-device /dev/ttyUSB0

  # Verbose output
  python tests/test_samlex_integration.py -v
        """
    )

    parser.add_argument(
        "--real-device",
        metavar="PORT",
        help="Run tests against real hardware on PORT (e.g., /dev/ttyUSB0)"
    )
    parser.add_argument(
        "--identity",
        type=int,
        default=16420,
        help="Expected identity value (default: 16420 for EVO-4024)"
    )
    parser.add_argument(
        "--scenario",
        choices=["normal", "fault", "low_battery", "ac_disconnect", "heavy_load"],
        default="normal",
        help="Test scenario to run with mock client"
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose output"
    )

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    use_mock = args.real_device is None
    device_port = args.real_device if not use_mock else None

    print("\n" + "=" * 70)
    print("Samlex EVO Driver Integration Tests")
    print("=" * 70)
    print(f"Mode: {'MOCK CLIENT' if use_mock else 'REAL HARDWARE'}")
    print(f"Device Port: {device_port or 'mock'}")
    print(f"Identity Value: {args.identity}")
    if use_mock:
        print(f"Scenario: {args.scenario}")
    print("=" * 70 + "\n")

    # Create test framework
    test_framework = SamlexIntegrationTest(
        use_mock=use_mock,
        device_port=device_port,
        identity_value=args.identity,
        scenario=args.scenario
    )

    try:
        # Setup
        test_framework.setup()

        # Run tests
        results = test_framework.run_all_tests()

        # Print results
        exit_code = print_results(results)

    except KeyboardInterrupt:
        print("\n\nTest interrupted by user")
        exit_code = 130

    except Exception as e:
        logger.exception("Test framework failed")
        print(f"\nFATAL ERROR: {e}")
        exit_code = 2

    finally:
        # Cleanup
        test_framework.teardown()

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
