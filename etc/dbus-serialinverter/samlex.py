# -*- coding: utf-8 -*-
import sys
import os

from inverter import Inverter
from utils import logger
import utils

sys.path.insert(
    1,
    os.path.join(
        os.path.dirname(__file__),
        "/opt/victronenergy/dbus-serialinverter/pymodbus",
    ),
)

from pymodbus.client import ModbusSerialClient

# All keys that must be present and numeric in [SAMLEX_REGISTERS] before the
# driver attempts any Modbus communication.  test_connection() validates these.
REQUIRED_SAMLEX_REGISTERS = (
    "REG_AC_OUT_VOLTAGE",
    "REG_AC_OUT_CURRENT",
    "REG_AC_OUT_POWER",
    "SCALE_AC_OUT_VOLTAGE",
    "SCALE_AC_OUT_CURRENT",
    "SCALE_AC_OUT_POWER",
    "REG_DC_VOLTAGE",
    "REG_DC_CURRENT",
    "REG_SOC",
    "SCALE_DC_VOLTAGE",
    "SCALE_DC_CURRENT",
    "REG_AC_IN_VOLTAGE",
    "REG_AC_IN_CURRENT",
    "REG_AC_IN_CONNECTED",
    "SCALE_AC_IN_VOLTAGE",
    "SCALE_AC_IN_CURRENT",
    "REG_FAULT",
    "REG_CHARGE_STATE",
    "REG_IDENTITY",
    "IDENTITY_VALUE",
)


class Samlex(Inverter):
    INVERTERTYPE = "Samlex"
    SERVICE_PREFIX = "com.victronenergy.vebus"

    def __init__(self, port, baudrate, slave):
        super().__init__(port, baudrate, slave)
        self.type = self.INVERTERTYPE
        # Samlex-specific: raw charge state register value (published as /VebusChargeState)
        self.energy_data["dc"]["charge_state"] = None
        self.client = ModbusSerialClient(
            method="rtu",
            port=port,
            baudrate=baudrate,
            stopbits=1,
            parity="N",
            bytesize=8,
            timeout=1,
        )
        logger.info("Creating ModbusSerialClient (Samlex) on port %s with baudrate %s" % (port, baudrate))

    # ── Config validation ─────────────────────────────────────────────────────

    def _registers_configured(self):
        """Return True only when every required register key exists and is a valid number."""
        if not utils.config.has_section("SAMLEX_REGISTERS"):
            return False
        for key in REQUIRED_SAMLEX_REGISTERS:
            val = utils.config.get("SAMLEX_REGISTERS", key, fallback="???").strip()
            if val == "???":
                return False
            try:
                float(val)
            except ValueError:
                return False
        return True

    def _reg(self, key):
        """Return an integer register address or integer value from [SAMLEX_REGISTERS]."""
        return int(utils.config.get("SAMLEX_REGISTERS", key))

    def _scale(self, key):
        """Return a float scaling factor from [SAMLEX_REGISTERS]."""
        return float(utils.config.get("SAMLEX_REGISTERS", key))

    # ── Modbus helpers ────────────────────────────────────────────────────────

    def _ensure_connected(self):
        """Return True if the Modbus connection is open, connecting once if needed."""
        if self.client.is_socket_open():
            return True
        return self.client.connect()

    def _read_batch(self, address, count):
        """Read `count` raw u16 registers from `address`. Returns (success, list[int])."""
        if not self._ensure_connected():
            logger.error("No connection")
            return False, []
        res = self.client.read_input_registers(address=address, count=count, slave=self.slave)
        logger.debug("Read batch - address=%s, count=%s, slave=%s" % (address, count, self.slave))
        if res.isError():
            logger.error("Error reading registers %s-%s" % (address, address + count - 1))
            return False, []
        return True, res.registers

    # ── Inverter interface ────────────────────────────────────────────────────

    def test_connection(self):
        # Step 1: validate config — return False silently if registers not configured
        if not self._registers_configured():
            logger.debug("Samlex: register map not configured, skipping")
            return False
        # Step 2: confirm hardware identity via a single register read
        try:
            ok, regs = self._read_batch(self._reg("REG_IDENTITY"), 1)
            if ok and regs[0] == self._reg("IDENTITY_VALUE"):
                logger.debug("Samlex: identity confirmed (register value %s)" % regs[0])
                return True
            logger.debug("Samlex: identity mismatch or read failed")
            return False
        except IOError:
            logger.debug("test_connection(): IOError")
            return False

    def get_settings(self):
        # Settings from config
        self.max_ac_power = utils.INVERTER_MAX_AC_POWER
        self.phase = utils.INVERTER_PHASE
        self.poll_interval = utils.INVERTER_POLL_INTERVAL
        self.position = utils.INVERTER_POSITION  # explicit: base class has 'positon' typo (todo #001)

        # Power limiting is not supported on the EVO series over Modbus; keep both None so
        # publish_inverter() never calls apply_power_limit().
        self.energy_data["overall"]["power_limit"] = None
        self.energy_data["overall"]["active_power_limit"] = None

        # Hardware info: placeholder values until register map includes version/serial registers
        self.hardware_version = 0
        self.serial_number = self.port.split("/")[-1]

        logger.debug("Samlex: settings loaded")
        return True

    def refresh_data(self):
        return self.read_status_data()

    def read_status_data(self):
        """Read all dynamic data from the EVO series inverter. Returns True on full success, False on any failure."""
        error = False

        # AC output
        ok, regs = self._read_batch(self._reg("REG_AC_OUT_VOLTAGE"), 1)
        if ok:
            self.energy_data["L1"]["ac_voltage"] = round(regs[0] * self._scale("SCALE_AC_OUT_VOLTAGE"), 1)
        else:
            error = True

        ok, regs = self._read_batch(self._reg("REG_AC_OUT_CURRENT"), 1)
        if ok:
            self.energy_data["L1"]["ac_current"] = round(regs[0] * self._scale("SCALE_AC_OUT_CURRENT"), 2)
        else:
            error = True

        ok, regs = self._read_batch(self._reg("REG_AC_OUT_POWER"), 1)
        if ok:
            ac_power = round(regs[0] * self._scale("SCALE_AC_OUT_POWER"), 0)
            self.energy_data["L1"]["ac_power"] = ac_power
            self.energy_data["overall"]["ac_power"] = ac_power
        else:
            error = True

        # DC / battery
        ok, regs = self._read_batch(self._reg("REG_DC_VOLTAGE"), 1)
        if ok:
            self.energy_data["dc"]["voltage"] = round(regs[0] * self._scale("SCALE_DC_VOLTAGE"), 2)
        else:
            error = True

        ok, regs = self._read_batch(self._reg("REG_DC_CURRENT"), 1)
        if ok:
            self.energy_data["dc"]["current"] = round(regs[0] * self._scale("SCALE_DC_CURRENT"), 2)
        else:
            error = True

        ok, regs = self._read_batch(self._reg("REG_SOC"), 1)
        if ok:
            self.energy_data["dc"]["soc"] = round(regs[0], 1)
        else:
            error = True

        # AC input / shore power
        ok, regs = self._read_batch(self._reg("REG_AC_IN_VOLTAGE"), 1)
        if ok:
            self.energy_data["ac_in"]["voltage"] = round(regs[0] * self._scale("SCALE_AC_IN_VOLTAGE"), 1)
        else:
            error = True

        ok, regs = self._read_batch(self._reg("REG_AC_IN_CURRENT"), 1)
        if ok:
            self.energy_data["ac_in"]["current"] = round(regs[0] * self._scale("SCALE_AC_IN_CURRENT"), 2)
        else:
            error = True

        ok, regs = self._read_batch(self._reg("REG_AC_IN_CONNECTED"), 1)
        if ok:
            self.energy_data["ac_in"]["connected"] = regs[0]
        else:
            error = True

        # Fault / status
        # Conservative mapping until the EVO series fault register bits are documented:
        #   non-zero fault → 10 (Error)
        #   no fault + AC output > 0 → 7 (Running)
        #   no fault + no AC output → 8 (Standby)
        ok, regs = self._read_batch(self._reg("REG_FAULT"), 1)
        if ok:
            fault = regs[0]
            if fault != 0:
                self.status = 10  # Error
            elif (self.energy_data["L1"]["ac_power"] or 0) > 0:
                self.status = 7  # Running
            else:
                self.status = 8  # Standby
        else:
            self.status = 10  # Error on read failure
            error = True

        # Charge state (raw register → /VebusChargeState)
        ok, regs = self._read_batch(self._reg("REG_CHARGE_STATE"), 1)
        if ok:
            self.energy_data["dc"]["charge_state"] = regs[0]
        else:
            error = True

        logger.debug("Samlex status: %s" % self.status)
        return not error
