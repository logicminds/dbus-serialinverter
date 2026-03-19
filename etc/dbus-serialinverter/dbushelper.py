# -*- coding: utf-8 -*-
import sys
import os
import platform
import dbus

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

# (path_suffix, energy_data_key, format_string) for each per-phase measurement
_PHASE_PATHS = [
    ('Voltage',        'ac_voltage',       '%.0FV'),
    ('Current',        'ac_current',       '%.0FA'),
    ('Power',          'ac_power',         '%.0FW'),
    ('Energy/Forward', 'energy_forwarded', '%.2FkWh'),
]

class DbusHelper:
    def __init__(self, inverter):
        self.inverter = inverter
        self.instance = 1
        self.settings = None
        self.error_count = 0
        _prefix = getattr(self.inverter, "SERVICE_PREFIX", "com.victronenergy.pvinverter")
        self._dbusservice = VeDbusService(
            _prefix + "." + self.inverter.port[self.inverter.port.rfind("/") + 1 :],
            get_bus(),
        )

    def setup_instance(self):
        inverter_id = self.inverter.port[self.inverter.port.rfind("/") + 1 :]
        path = "/Settings/Devices/serialinverter"
        _prefix = getattr(self.inverter, "SERVICE_PREFIX", "com.victronenergy.pvinverter")
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

    def _fmt(self, fmt):
        """Return a D-Bus gettextcallback that formats a numeric value with `fmt`."""
        return lambda path, value: fmt % float(value)

    def setup_vedbus(self):
        # Set up dbus service and device instance
        # and notify of all the attributes we intend to update
        # This is only called once when a inverter is initiated
        self.setup_instance()
        short_port = self.inverter.port[self.inverter.port.rfind("/") + 1 :]
        _prefix = getattr(self.inverter, "SERVICE_PREFIX", "com.victronenergy.pvinverter")
        logger.info("%s" % (_prefix + "." + short_port))

        # Get the settings for the inverter
        if not self.inverter.get_settings():
            return False

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
            self._dbusservice.add_path("/Ac/In/1/Type", 3)  # 3=Shore power
            # AC output
            self._dbusservice.add_path("/Ac/Out/L1/V", 0, gettextcallback=self._fmt("%.0FV"))
            self._dbusservice.add_path("/Ac/Out/L1/I", 0, gettextcallback=self._fmt("%.0FA"))
            self._dbusservice.add_path("/Ac/Out/L1/P", 0, gettextcallback=self._fmt("%.0FW"))
            # AC input
            self._dbusservice.add_path("/Ac/ActiveIn/L1/V", 0, gettextcallback=self._fmt("%.0FV"))
            self._dbusservice.add_path("/Ac/ActiveIn/L1/I", 0, gettextcallback=self._fmt("%.0FA"))
            self._dbusservice.add_path("/Ac/ActiveIn/L1/P", 0, gettextcallback=self._fmt("%.0FW"))
            self._dbusservice.add_path("/Ac/ActiveIn/Connected", 0)
            # DC / battery
            self._dbusservice.add_path("/Dc/0/Voltage", 0, gettextcallback=self._fmt("%.2FV"))
            self._dbusservice.add_path("/Dc/0/Current", 0, gettextcallback=self._fmt("%.2FA"))
            self._dbusservice.add_path("/Dc/0/Power", 0, gettextcallback=self._fmt("%.0FW"))
            self._dbusservice.add_path("/Soc", 0, gettextcallback=self._fmt("%.0F%%"))
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

        return True

    def publish_inverter(self, loop):
        # This is called every inverter.poll_interval milli second as set up per inverter type to read and update the data
        # Only pvinverter service type exposes /Ac/PowerLimit; vebus devices leave power_limit as None
        _prefix = getattr(self.inverter, "SERVICE_PREFIX", "com.victronenergy.pvinverter")
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

        except Exception:
            logger.exception("Unhandled exception in publish_inverter, quitting")
            loop.quit()

    def publish_dbus(self):
        _prefix = getattr(self.inverter, "SERVICE_PREFIX", "com.victronenergy.pvinverter")

        if _prefix == "com.victronenergy.vebus":
            # vebus inverter/charger publish
            self._dbusservice["/State"] = self.inverter.status
            self._dbusservice["/Ac/Out/L1/V"] = self.inverter.energy_data["L1"]["ac_voltage"]
            self._dbusservice["/Ac/Out/L1/I"] = self.inverter.energy_data["L1"]["ac_current"]
            self._dbusservice["/Ac/Out/L1/P"] = self.inverter.energy_data["L1"]["ac_power"]
            dc = self.inverter.energy_data.get("dc", {})
            self._dbusservice["/Dc/0/Voltage"] = dc.get("voltage")
            self._dbusservice["/Dc/0/Current"] = dc.get("current")
            self._dbusservice["/Dc/0/Power"] = dc.get("power")
            self._dbusservice["/Soc"] = dc.get("soc")
            charge_state = dc.get("charge_state")
            if charge_state is not None:
                self._dbusservice["/VebusChargeState"] = charge_state
            ac_in = self.inverter.energy_data.get("ac_in", {})
            self._dbusservice["/Ac/ActiveIn/L1/V"] = ac_in.get("voltage")
            self._dbusservice["/Ac/ActiveIn/L1/I"] = ac_in.get("current")
            self._dbusservice["/Ac/ActiveIn/L1/P"] = ac_in.get("power")
            self._dbusservice["/Ac/ActiveIn/Connected"] = ac_in.get("connected")
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

        logger.debug("published to dbus [%s]" % str(self.inverter.energy_data["overall"]["ac_power"]))
