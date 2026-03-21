# -*- coding: utf-8 -*-

from modbus_inverter import ModbusInverter
from utils import logger
import utils

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


class Samlex(ModbusInverter):
    INVERTERTYPE = "Samlex"
    SERVICE_PREFIX = "com.victronenergy.vebus"

    def __init__(self, port, baudrate, slave):
        super().__init__(port, baudrate, slave)
        self.type = self.INVERTERTYPE
        # Samlex-specific: raw charge state register value (published as /VebusChargeState)
        self.energy_data["dc"]["charge_state"] = None
        logger.info("Creating ModbusSerialClient (Samlex) on port %s with baudrate %s", port, baudrate)

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
        value = int(utils.config.get("SAMLEX_REGISTERS", key))
        if not (0 <= value <= 65535):
            raise ValueError(f"Register address {key}={value} is out of valid Modbus range (0-65535)")
        return value

    def _scale(self, key):
        """Return a float scaling factor from [SAMLEX_REGISTERS]."""
        return float(utils.config.get("SAMLEX_REGISTERS", key))

    # ── Modbus helpers ────────────────────────────────────────────────────────

    def _read_group(self, keys):
        """Read a group of registers in one batch. Returns dict key->value or None on failure."""
        try:
            addrs = {key: self._reg(key) for key in keys}
            min_addr = min(addrs.values())
            max_addr = max(addrs.values())
            count = max_addr - min_addr + 1
            ok, regs = self._read_batch(min_addr, count)
            if not ok:
                return None
            return {key: regs[addr - min_addr] for key, addr in addrs.items()}
        except (ValueError, IndexError) as exc:
            logger.error("_read_group failed for keys %s: %s", keys, exc)
            return None

    def _apply_scaled_fields(self, group_result, fields):
        """Apply scaled assignments from a group read result.

        fields: list of (reg_key, scale_key, section, field_name, digits)
        """
        for reg_key, scale_key, section, field_name, digits in fields:
            self.energy_data[section][field_name] = round(
                group_result[reg_key] * self._scale(scale_key), digits
            )

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
                logger.debug("Samlex: identity confirmed (register value %s)", regs[0])
                return True
            logger.debug("Samlex: identity mismatch or read failed")
            return False
        except (IOError, ValueError) as exc:
            logger.debug("test_connection() failed: %s", exc)
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

        # AC output (batch)
        ac_out = self._read_group(["REG_AC_OUT_VOLTAGE", "REG_AC_OUT_CURRENT", "REG_AC_OUT_POWER"])
        if ac_out:
            self._apply_scaled_fields(ac_out, [
                ("REG_AC_OUT_VOLTAGE", "SCALE_AC_OUT_VOLTAGE", "L1", "ac_voltage", 1),
                ("REG_AC_OUT_CURRENT", "SCALE_AC_OUT_CURRENT", "L1", "ac_current", 2),
                ("REG_AC_OUT_POWER",   "SCALE_AC_OUT_POWER",   "L1", "ac_power",   0),
            ])
            self.energy_data["overall"]["ac_power"] = self.energy_data["L1"]["ac_power"]
        else:
            error = True

        # DC / battery (batch)
        dc = self._read_group(["REG_DC_VOLTAGE", "REG_DC_CURRENT", "REG_SOC"])
        if dc:
            self._apply_scaled_fields(dc, [
                ("REG_DC_VOLTAGE", "SCALE_DC_VOLTAGE", "dc", "voltage", 2),
                ("REG_DC_CURRENT", "SCALE_DC_CURRENT", "dc", "current", 2),
            ])
            self.energy_data["dc"]["soc"] = round(dc["REG_SOC"], 1)
        else:
            error = True

        # AC input / shore power (batch)
        ac_in = self._read_group(["REG_AC_IN_VOLTAGE", "REG_AC_IN_CURRENT", "REG_AC_IN_CONNECTED"])
        if ac_in:
            self._apply_scaled_fields(ac_in, [
                ("REG_AC_IN_VOLTAGE",  "SCALE_AC_IN_VOLTAGE",  "ac_in", "voltage", 1),
                ("REG_AC_IN_CURRENT",  "SCALE_AC_IN_CURRENT",  "ac_in", "current", 2),
            ])
            # Working status: 0=Power saving, 1=AC input normal, 2=AC input abnormal, 3=Inverting, 4=Fault
            # "Connected" means AC input is present and normal (value == 1)
            self.energy_data["ac_in"]["connected"] = 1 if ac_in["REG_AC_IN_CONNECTED"] == 1 else 0
        else:
            error = True

        # Fault / status (batch)
        # Conservative mapping: non-zero fault → 10 (Error), no fault + AC output > 0 → 7 (Running), else → 8 (Standby)
        status_regs = self._read_group(["REG_FAULT", "REG_CHARGE_STATE"])
        if status_regs:
            fault = status_regs["REG_FAULT"]
            if fault != 0:
                self.status = 10  # Error
            elif (self.energy_data["L1"]["ac_power"] or 0) > 0:
                self.status = 7  # Running
            else:
                self.status = 8  # Standby
            self.energy_data["dc"]["charge_state"] = status_regs["REG_CHARGE_STATE"]
        else:
            self.status = 10  # Error on read failure
            error = True

        logger.debug("Samlex status: %s", self.status)
        return not error
