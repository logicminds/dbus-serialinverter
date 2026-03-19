# -*- coding: utf-8 -*-

from utils import logger
from abc import ABC, abstractmethod

class Inverter(ABC):
    """
    This Class is the abstract baseclass for all inverters. For each inverter this class needs to be extended
    and the abstract methods need to be implemented. The main program in dbus-serialinverter.py will then
    use the individual implementations as type Inverter and work with it.
    """

    # VenusOS D-Bus service type prefix. Override in subclasses that are not PV inverters.
    # 'com.victronenergy.pvinverter' — grid-tied solar PV inverters (default)
    # 'com.victronenergy.vebus'      — multi-mode inverter/chargers
    SERVICE_PREFIX = "com.victronenergy.pvinverter"

    def __init__(self, port, baudrate, slave):
        self.port = port
        self.baudrate = baudrate
        self.slave = slave
        self.role = "inverter"
        self.type = "Generic"
        self.poll_interval = 1000
        self.online = True

        # Static data
        self.hardware_version = 0x0
        self.serial_number = None

        self.max_ac_power = None
        self.position = None # 0=Input1; 1=Output; 2=Input2
        self.phase = None

        self.status = None

        # Energy data
        self.energy_data = dict()

        for phase in ['L1', 'L2', 'L3']:
            self.energy_data[phase] = dict()
            self.energy_data[phase]['ac_voltage'] = None
            self.energy_data[phase]['ac_current'] = None
            self.energy_data[phase]['ac_power'] = None
            self.energy_data[phase]['energy_forwarded'] = None

        self.energy_data["overall"] = dict()
        self.energy_data['overall']['ac_power'] = None
        self.energy_data['overall']['energy_forwarded'] = None

        self.energy_data['overall']['power_limit'] = None
        self.energy_data['overall']['active_power_limit'] = None

        # DC / battery data (vebus inverter/chargers populate these)
        self.energy_data['dc'] = {
            'voltage': None,   # V (float)
            'current': None,   # A (float, positive = charging)
            'power':   None,   # W (float)
            'soc':     None,   # % (float, 0-100)
        }

        # AC input / shore power data (vebus inverter/chargers populate these)
        self.energy_data['ac_in'] = {
            'voltage':   None,  # V (float)
            'current':   None,  # A (float)
            'power':     None,  # W (float)
            'connected': None,  # 0 or 1
        }

    @abstractmethod
    def test_connection(self) -> bool:
        """
        This abstract method needs to be implemented for each inverter. It should return true if a connection
        to the inverter can be established, false otherwise.
        :return: the success state
        """
        # Each driver must override this function to test if a connection can be made
        # return false when failed, true if successful
        return False

    @abstractmethod
    def get_settings(self) -> bool:
        """
        Each driver must override this function to read/set the inverter settings
        It is called once after a successful connection by DbusHelper.setup_vedbus()
        Values: FIXME

        :return: false when fail, true if successful
        """
        return False

    @abstractmethod
    def refresh_data(self) -> bool:
        """
        Each driver must override this function to read inverter data and populate this class
        It is called each poll just before the data is published to vedbus

        :return:  false when fail, true if successful
        """
        return False

    def apply_power_limit(self, watts) -> bool:
        """
        Write the requested power limit to the inverter hardware.
        Override in inverters that support active power limiting.
        """
        return True

    def log_settings(self) -> None:
        logger.info(f"Inverter {self.type} connected to dbus from {self.port}")
        logger.info("=== Settings ===")
        logger.info("> Serial number: %s" % self.serial_number)
        logger.info("> Hardware version: %s" % self.hardware_version)
        logger.info("> Max. AC power: %s" % self.max_ac_power)
        logger.info("> Phase: %s" % self.phase)
        logger.info("> Position: %s" % self.position)
        return
