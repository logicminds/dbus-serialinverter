# -*- coding: utf-8 -*-
import sys
import os
import platform
import dbus
from pathlib import Path

# Victron packages
sys.path.insert(
    1,
    os.path.join(
        os.path.dirname(__file__),
        "/opt/victronenergy/dbus-systemcalc-py/ext/velib_python",
    ),
)

from vedbus import VeDbusService
from settingsdevice import SettingsDevice

from utils import logger
import utils

def get_bus():
    return (
        dbus.SessionBus()
        if "DBUS_SESSION_BUS_ADDRESS" in os.environ
        else dbus.SystemBus()
    )


def _port_id(port: str) -> str:
    """Return a D-Bus-safe identifier for a port string.

    /dev/ttyUSB0        → ttyUSB0
    tcp://localhost:5020 → localhost_5020
    """
    if port.startswith("tcp://"):
        return port[len("tcp://"):].replace(":", "_")
    return Path(port).name

# (path_suffix, energy_data_key, format_string) for each per-phase measurement
_PHASE_PATHS = [
    ('Voltage',        'ac_voltage',       '%.0FV'),
    ('Current',        'ac_current',       '%.0FA'),
    ('Power',          'ac_power',         '%.0FW'),
    ('Energy/Forward', 'energy_forwarded', '%.2FkWh'),
]

class DbusHelper:
    _DEFAULT_PREFIX = "com.victronenergy.pvinverter"
    _EXTERNAL_SOC_CHECK_INTERVAL = 60  # re-scan D-Bus every N publish cycles

    def __init__(self, inverter):
        self.inverter = inverter
        self.instance = 1
        self.settings = None
        self.error_count = 0
        self._prefix = getattr(inverter, "SERVICE_PREFIX", self._DEFAULT_PREFIX)
        self._dbusservice = VeDbusService(
            self._prefix + "." + _port_id(self.inverter.port),
            get_bus(),
            register=False,
        )
        self._soc_source = getattr(utils, "INVERTER_SOC_SOURCE", "auto")
        self._has_external_soc = False
        self._soc_check_counter = 0

    def _get_prefix(self):
        """Return the cached service prefix, falling back to inverter attribute lookup.

        Provides a safe access path for code paths where __init__ was bypassed (e.g. tests).
        """
        try:
            return self._prefix
        except AttributeError:
            return getattr(self.inverter, "SERVICE_PREFIX", self._DEFAULT_PREFIX)

    def setup_instance(self):
        inverter_id = _port_id(self.inverter.port)
        path = "/Settings/Devices/serialinverter"
        _prefix = self._get_prefix()
        if _prefix == "com.victronenergy.vebus":
            default_instance = "vebus:257"  # vebus devices use 257-261 range
        else:
            default_instance = "inverter:20"  # pvinverters from 20-29
        settings = {
            "instance": [
                path + "_" + str(inverter_id).replace(" ", "_") + "/ClassAndVrmInstance",
                default_instance,
                0,
                0,
            ],
        }
        if _prefix == "com.victronenergy.vebus":
            # systemcalc reads /Settings/SystemSetup/AcInput1 to determine the
            # AC source type.  Without this setting (or when it is 0 = "Not
            # available"), systemcalc reports AIS=240 (Inverting) and ini=0 even
            # when the device itself publishes valid AC input data.
            # Values: 0=Not available, 1=Grid, 2=Generator, 3=Shore power
            settings["acInput1"] = [
                "/Settings/SystemSetup/AcInput1",
                1,   # default: Grid
                0,
                3,
            ]
        self.settings = SettingsDevice(get_bus(), settings, self.handle_changed_setting)
        self.inverter.role, self.instance = self.get_role_instance()

    def get_role_instance(self):
        val = self.settings["instance"].split(":")
        logger.info("DeviceInstance = %d", int(val[1]))
        return val[0], int(val[1])

    def handle_changed_setting(self, setting, oldvalue, newvalue):
        if setting == "instance":
            self.inverter.role, self.instance = self.get_role_instance()
            logger.info("Changed DeviceInstance = %d", self.instance)

    def _detect_external_soc(self):
        """Scan D-Bus for an external battery monitor (BMV / SmartShunt).

        Sets self._has_external_soc = True when a com.victronenergy.battery.*
        service is present on the bus, meaning VenusOS already has a dedicated
        SOC source and this driver should publish /Soc = None.
        """
        try:
            bus = get_bus()
            names = bus.list_names()
            self._has_external_soc = any(
                str(n).startswith("com.victronenergy.battery.") for n in names
            )
            logger.info(
                "SOC_SOURCE=%s: external battery monitor %s",
                self._soc_source,
                "detected" if self._has_external_soc else "not found",
            )
        except Exception:
            logger.exception("Failed to scan D-Bus for external battery monitor")

    def _fmt(self, fmt):
        """Return a D-Bus gettextcallback that formats a numeric value with `fmt`."""
        return lambda path, value: fmt % float(value)

    def setup_vedbus(self):
        # Set up dbus service and device instance
        # and notify of all the attributes we intend to update
        # This is only called once when a inverter is initiated
        self.setup_instance()
        short_port = _port_id(self.inverter.port)
        _prefix = self._get_prefix()
        logger.info("%s.%s", _prefix, short_port)

        # Get the settings for the inverter
        if not self.inverter.get_settings():
            return False

        if getattr(self, "_soc_source", "auto") == "auto":
            self._detect_external_soc()

        # Create the management objects, as specified in the ccgx dbus-api document
        self._dbusservice.add_path("/Mgmt/ProcessName", __file__)
        self._dbusservice.add_path(
            "/Mgmt/ProcessVersion", "Python " + platform.python_version()
        )
        self._dbusservice.add_path("/Mgmt/Connection", "Serial " + self.inverter.port)

        # Create the mandatory objects
        self._dbusservice.add_path("/DeviceInstance", self.instance)
        self._dbusservice.add_path("/ProductId", 0xA144)
        self._dbusservice.add_path("/ProductName", "SerialInverter (" + self.inverter.type + ")")
        self._dbusservice.add_path("/FirmwareVersion", str(utils.DRIVER_VERSION) + utils.DRIVER_SUBVERSION)
        self._dbusservice.add_path("/HardwareVersion", self.inverter.hardware_version)
        self._dbusservice.add_path("/Connected", 1)
        self._dbusservice.add_path("/CustomName", "SerialInverter (" + self.inverter.type + ")", writeable=True)
        self._dbusservice.add_path("/Serial", self.inverter.serial_number)
        self._dbusservice.add_path("/UpdateIndex", 0)

        if _prefix == "com.victronenergy.vebus":
            # vebus inverter/charger paths (Samlex EVO and similar multi-mode devices)
            self._dbusservice.add_path("/State", 0)
            self._dbusservice.add_path("/Mode", 3)  # 3=On (invert + charge)
            self._dbusservice.add_path("/VebusChargeState", 0)
            self._dbusservice.add_path("/Ac/NumberOfAcInputs", 1)
            self._dbusservice.add_path("/Ac/NumberOfPhases", 1)
            self._dbusservice.add_path("/Ac/In/1/Type", 3)   # 3=Shore power
            self._dbusservice.add_path("/Ac/State/AcIn1Available", 0)  # updated each poll
            # AC output
            self._dbusservice.add_path("/Ac/Out/L1/V", 0, gettextcallback=self._fmt("%.0FV"))
            self._dbusservice.add_path("/Ac/Out/L1/I", 0, gettextcallback=self._fmt("%.0FA"))
            self._dbusservice.add_path("/Ac/Out/L1/P", 0, gettextcallback=self._fmt("%.0FW"))
            # AC input
            self._dbusservice.add_path("/Ac/ActiveIn/ActiveInput", 240)  # 0=ACin-1, 240=inverting
            self._dbusservice.add_path("/Ac/ActiveIn/L1/V", 0, gettextcallback=self._fmt("%.0FV"))
            self._dbusservice.add_path("/Ac/ActiveIn/L1/I", 0, gettextcallback=self._fmt("%.0FA"))
            self._dbusservice.add_path("/Ac/ActiveIn/L1/P", 0, gettextcallback=self._fmt("%.0FW"))
            self._dbusservice.add_path("/Ac/ActiveIn/Connected", 0)
            # DC / battery
            self._dbusservice.add_path("/Dc/0/Voltage", 0, gettextcallback=self._fmt("%.2FV"))
            self._dbusservice.add_path("/Dc/0/Current", 0, gettextcallback=self._fmt("%.2FA"))
            self._dbusservice.add_path("/Dc/0/Power", 0, gettextcallback=self._fmt("%.0FW"))
            self._dbusservice.add_path("/Soc", 0, gettextcallback=self._fmt("%.0F%%"))
            # NOTE: When external battery monitor is detected and SOC_SOURCE=auto,
            # DC values are set to None in publish_dbus() so VenusOS uses BMV data
        else:
            # pvinverter paths (Solis, Dummy, and similar grid-tie PV inverters)
            self._dbusservice.add_path("/Ac/MaxPower", self.inverter.max_ac_power)
            self._dbusservice.add_path("/Position", self.inverter.position)  # 0=AC input 1; 1=AC output; 2=AC input 2
            self._dbusservice.add_path("/StatusCode", 0)  # 0-6=Startup; 7=Running; 8=Standby; 9=Boot; 10=Error

            for phase in ["L1", "L2", "L3"]:
                for suffix, _, fmt in _PHASE_PATHS:
                    self._dbusservice.add_path(
                        f"/Ac/{phase}/{suffix}", 0, gettextcallback=self._fmt(fmt)
                    )

            self._dbusservice.add_path("/Ac/Power", 0, gettextcallback=self._fmt("%.0FW"))
            self._dbusservice.add_path("/Ac/Energy/Forward", 0, gettextcallback=self._fmt("%.2FkWh"))
            self._dbusservice.add_path(
                "/Ac/PowerLimit",
                self.inverter.energy_data["overall"]["power_limit"],
                gettextcallback=self._fmt("%.0FW"),
                writeable=True,
            )

        logger.info(f"Publish config values = {utils.PUBLISH_CONFIG_VALUES}")
        if utils.PUBLISH_CONFIG_VALUES == 1:
            utils.publish_config_variables(self._dbusservice)

        self._dbusservice.register()

        return True

    def publish_inverter(self, loop):
        # This is called every inverter.poll_interval milli second as set up per inverter type to read and update the data
        # Only pvinverter service type exposes /Ac/PowerLimit; vebus devices leave power_limit as None
        _prefix = self._get_prefix()
        if _prefix != "com.victronenergy.vebus":
            self.inverter.energy_data["overall"]["power_limit"] = self._dbusservice["/Ac/PowerLimit"]
        try:
            # Call the inverter's refresh_data function
            success = self.inverter.refresh_data()
            if success:
                self.error_count = 0
                self.inverter.online = True
                self.inverter.poll_interval = utils.INVERTER_POLL_INTERVAL
                active = self.inverter.energy_data['overall'].get('active_power_limit')
                desired = self.inverter.energy_data['overall']['power_limit']
                if active is not None and active != desired:
                    self.inverter.apply_power_limit(desired)
                # Publish only when data is fresh and consistent
                self.publish_dbus()
            else:
                self.error_count += 1
                # If the inverter is offline for more than 10 polls (polled every second for most inverters)
                if self.error_count >= 10:
                    self.inverter.online = False
                # If the inverter is offline for more than 60 polls, quit. VenusOS will restart the driver anyway.
                if self.error_count >= 60:
                    logger.warning("Inverter seems to be offline, quitting!")
                    loop.quit()

        except (KeyboardInterrupt, SystemExit):
            raise
        except Exception:
            logger.exception("Unhandled exception in publish_inverter, quitting")
            loop.quit()

    def publish_dbus(self):
        _prefix = self._get_prefix()

        if _prefix == "com.victronenergy.vebus":
            # vebus inverter/charger publish
            self._dbusservice["/State"] = self.inverter.status
            self._dbusservice["/Ac/Out/L1/V"] = self.inverter.energy_data["L1"]["ac_voltage"]
            self._dbusservice["/Ac/Out/L1/I"] = self.inverter.energy_data["L1"]["ac_current"]
            self._dbusservice["/Ac/Out/L1/P"] = self.inverter.energy_data["L1"]["ac_power"]
            dc = self.inverter.energy_data.get("dc", {})

            # Periodic re-scan for external battery monitor (SOC_SOURCE=auto)
            soc_source = getattr(self, "_soc_source", "auto")
            if soc_source == "auto":
                counter = getattr(self, "_soc_check_counter", 0) + 1
                if counter >= self._EXTERNAL_SOC_CHECK_INTERVAL:
                    counter = 0
                    self._detect_external_soc()
                self._soc_check_counter = counter

            has_external = getattr(self, "_has_external_soc", False)
            use_external_dc = soc_source == "none" or (soc_source == "auto" and has_external)

            # DC values: use external battery monitor when configured/available
            if use_external_dc:
                self._dbusservice["/Dc/0/Voltage"] = None
                self._dbusservice["/Dc/0/Current"] = None
                self._dbusservice["/Dc/0/Power"] = None
                self._dbusservice["/Soc"] = None
            else:
                self._dbusservice["/Dc/0/Voltage"] = dc.get("voltage")
                self._dbusservice["/Dc/0/Current"] = dc.get("current")
                self._dbusservice["/Dc/0/Power"] = dc.get("power")
                self._dbusservice["/Soc"] = dc.get("soc")
            charge_state = dc.get("charge_state")
            if charge_state is not None:
                self._dbusservice["/VebusChargeState"] = charge_state
            ac_in = self.inverter.energy_data.get("ac_in", {})
            connected = ac_in.get("connected") or 0
            self._dbusservice["/Ac/State/AcIn1Available"] = 1 if connected == 1 else 0
            self._dbusservice["/Ac/ActiveIn/ActiveInput"] = 0 if connected == 1 else 240
            self._dbusservice["/Ac/ActiveIn/L1/V"] = ac_in.get("voltage") or 0
            self._dbusservice["/Ac/ActiveIn/L1/I"] = ac_in.get("current") or 0
            self._dbusservice["/Ac/ActiveIn/L1/P"] = ac_in.get("power") or 0
            self._dbusservice["/Ac/ActiveIn/Connected"] = connected
        else:
            # pvinverter publish
            self._dbusservice["/StatusCode"] = self.inverter.status

            for phase in ["L1", "L2", "L3"]:
                for suffix, field, _ in _PHASE_PATHS:
                    self._dbusservice[f"/Ac/{phase}/{suffix}"] = self.inverter.energy_data[phase][field]

            self._dbusservice["/Ac/Power"] = self.inverter.energy_data["overall"]["ac_power"]
            self._dbusservice["/Ac/Energy/Forward"] = self.inverter.energy_data["overall"]["energy_forwarded"]

        # Increment UpdateIndex - to show that new data is available
        index = self._dbusservice["/UpdateIndex"] + 1  # increment index
        if index > 255:  # Maximum value of the index
            index = 0  # Overflow from 255 to 0
        self._dbusservice["/UpdateIndex"] = index

        logger.debug("published to dbus [%s]", self.inverter.energy_data["overall"]["ac_power"])
