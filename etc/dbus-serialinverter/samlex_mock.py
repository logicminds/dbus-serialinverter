# -*- coding: utf-8 -*-
"""Samlex EVO Mock Inverter - Generates synthetic data for testing.

This inverter type simulates a Samlex EVO series inverter without requiring
any Modbus communication. It generates realistic synthetic data that can be
used to test the D-Bus integration, GUI displays, and VRM portal connectivity
without hardware.

Usage in config.ini:
    [INVERTER]
    TYPE=SamlexMock
    MAX_AC_POWER=4000
    PHASE=L1
    POSITION=1
    POLL_INTERVAL=1000

The mock inverter simulates:
- AC Output: 120V, 8-15A, 1000-3000W (varies over time)
- DC Battery: 26.4V, charging/discharging current
- SOC: 85% with gradual changes
- AC Input: 120V when connected
- Status: Normal operation with occasional variations
- Charge State: Cycles through charging states

D-Bus service: com.victronenergy.vebus (same as real Samlex)
"""

import time
import math
from inverter import Inverter
from utils import logger
import utils


class SamlexMock(Inverter):
    """Mock Samlex EVO inverter for testing without hardware.

    Generates synthetic data that simulates a real EVO-4024 inverter.
    Use TYPE=SamlexMock in config.ini for testing D-Bus integration
    without requiring physical hardware.
    """

    INVERTERTYPE = "SamlexMock"
    SERVICE_PREFIX = "com.victronenergy.vebus"

    def __init__(self, port, baudrate, slave):
        """Initialize the mock inverter.

        Args:
            port: Serial port (ignored for mock, but stored for reference)
            baudrate: Baud rate (ignored for mock)
            slave: Modbus slave address (ignored for mock)
        """
        super().__init__(port, baudrate, slave)
        self.type = self.INVERTERTYPE

        # Store port for identification
        self.port = port if port else "/dev/mock"

        # Initialize with realistic starting values
        self._dc_voltage = 26.4  # 24V nominal
        self._dc_current = 5.2   # Positive = charging
        self._soc = 85.0         # 85% state of charge
        self._charge_state = 2   # Absorption

        self._ac_out_voltage = 120.0
        self._ac_out_current = 8.33
        self._ac_out_power = 1000

        self._ac_in_voltage = 120.0
        self._ac_in_current = 4.17
        self._ac_in_connected = 1

        self._fault = 0
        self._status = 7  # Running

        # For time-based variations
        self._start_time = time.time()

        logger.info("SamlexMock: Initialized mock inverter on %s", self.port)
        logger.info("SamlexMock: Simulating EVO-4024 with synthetic data")

    def _update_synthetic_values(self):
        """Update synthetic values to simulate realistic changes over time."""
        elapsed = time.time() - self._start_time

        # Simulate AC load variation (1000-3000W range with sine wave)
        load_variation = 1000 + 1000 * math.sin(elapsed / 60)  # 60 second cycle
        self._ac_out_power = int(load_variation)
        self._ac_out_current = round(self._ac_out_power / self._ac_out_voltage, 2)

        # Simulate AC voltage slight variation (118-122V)
        self._ac_out_voltage = 120.0 + 2.0 * math.sin(elapsed / 30)

        # Simulate AC input (follows shore power availability)
        # Every 5 minutes, toggle AC input for 30 seconds
        cycle_position = (elapsed % 300) / 300  # 0-1 over 5 minutes
        if cycle_position > 0.9:  # Last 10% of cycle = no AC
            self._ac_in_connected = 0
            self._ac_in_voltage = 0
            self._ac_in_current = 0
            self._charge_state = 9  # Inverting
        else:
            self._ac_in_connected = 1
            self._ac_in_voltage = 120.0 + 1.0 * math.sin(elapsed / 20)
            self._ac_in_current = round(
                (self._ac_out_power / self._ac_in_voltage) * 0.9, 2
            )

        # Simulate SOC slowly changing
        if self._ac_in_connected:
            # Charging: SOC increases slowly
            self._soc = min(100.0, self._soc + 0.01)
            self._dc_current = 5.0 + 2.0 * math.sin(elapsed / 120)
            self._charge_state = 2  # Absorption
        else:
            # Discharging: SOC decreases
            self._soc = max(0.0, self._soc - 0.02)
            self._dc_current = -15.0 - 5.0 * math.sin(elapsed / 60)

        # DC voltage varies slightly with load
        self._dc_voltage = 26.4 - (abs(self._dc_current) * 0.01)

        # Calculate status
        if self._fault != 0:
            self._status = 10  # Error
        elif self._ac_out_power > 0:
            self._status = 7   # Running
        else:
            self._status = 8   # Standby

    def test_connection(self):
        """Always returns True for mock - no hardware to probe."""
        logger.debug("SamlexMock: test_connection() - always True")
        return True

    def get_settings(self):
        """Load settings from config."""
        # Settings from config
        self.max_ac_power = utils.INVERTER_MAX_AC_POWER
        self.phase = utils.INVERTER_PHASE
        self.poll_interval = utils.INVERTER_POLL_INTERVAL
        self.position = utils.INVERTER_POSITION

        # Power limiting not supported (same as real Samlex)
        self.energy_data["overall"]["power_limit"] = None
        self.energy_data["overall"]["active_power_limit"] = None

        # Mock hardware info
        self.hardware_version = 1
        self.serial_number = f"MOCK-{self.port.split('/')[-1]}"

        logger.debug("SamlexMock: settings loaded")
        logger.info("SamlexMock: Max power=%sW, Phase=%s",
                    self.max_ac_power, self.phase)
        return True

    def refresh_data(self):
        """Generate fresh synthetic data."""
        self._update_synthetic_values()
        return self.read_status_data()

    def read_status_data(self):
        """Populate energy_data with synthetic values."""
        # Update synthetic values first
        self._update_synthetic_values()

        # AC output
        self.energy_data["L1"]["ac_voltage"] = round(self._ac_out_voltage, 1)
        self.energy_data["L1"]["ac_current"] = round(self._ac_out_current, 2)
        self.energy_data["L1"]["ac_power"] = self._ac_out_power
        self.energy_data["overall"]["ac_power"] = self._ac_out_power

        # DC battery
        dc_v = round(self._dc_voltage, 2)
        dc_i = round(self._dc_current, 2)
        self.energy_data["dc"]["voltage"] = dc_v
        self.energy_data["dc"]["current"] = dc_i
        self.energy_data["dc"]["power"] = round(dc_v * dc_i, 0)
        self.energy_data["dc"]["soc"] = round(self._soc, 1)
        self.energy_data["dc"]["charge_state"] = self._charge_state

        # AC input
        ac_in_v = round(self._ac_in_voltage, 1)
        ac_in_i = round(self._ac_in_current, 2)
        self.energy_data["ac_in"]["voltage"] = ac_in_v
        self.energy_data["ac_in"]["current"] = ac_in_i
        self.energy_data["ac_in"]["power"] = round(ac_in_v * ac_in_i, 0)
        self.energy_data["ac_in"]["connected"] = self._ac_in_connected

        # Status — derive vebus /State from fault, AC connection, and charge stage
        # (mirrors the logic in samlex.py read_status_data)
        from samlex import _VEBUS_STATE_FROM_CHARGE
        if self._fault != 0:
            self.status = 2   # Fault
        elif self._ac_in_connected != 1:
            self.status = 9   # Inverting
        else:
            self.status = _VEBUS_STATE_FROM_CHARGE.get(self._charge_state, 9)

        logger.debug("SamlexMock: status=%s, AC=%sW, DC=%sV/%sA, SOC=%s%%",
                     self.status, self._ac_out_power,
                     self._dc_voltage, self._dc_current, self._soc)

        return True

    def apply_power_limit(self, watts):
        """Mock power limit - returns False (not supported, same as real)."""
        logger.warning("SamlexMock: Power limiting not supported (same as real EVO)")
        return False
