# -*- coding: utf-8 -*-

from modbus_inverter import ModbusInverter
from utils import logger
import utils

# Samlex Charger State (raw) → Victron /State (vebus operating state)
# Derived when AC is connected.  Fault and AC-disconnected are handled first.
# Victron: 4=Absorption, 5=Float, 6=Storage, 7=Equalize, 8=Passthru, 9=Inverting
_VEBUS_STATE_FROM_CHARGE = {
    0: 8,  # Standby (no charging) → Passthru
    1: 7,  # Equalization          → Equalize
    2: 4,  # Absorption            → Absorption
    3: 5,  # Float                 → Float
    4: 6,  # Storage               → Storage
    9: 9,  # Inverting             → Inverting
}

# Samlex EVO Charger State register → Victron /VebusChargeState
# Samlex (reg 8): 0=Standby, 1=Equalization, 2=Absorption, 3=Float, 4=Storage, 9=Inverting
# Victron:        0=Idle,    1=Bulk,          2=Absorption, 3=Float, 4=Storage, 5=Equalise, 9=Inverting
# Note: Samlex has no distinct Bulk stage; passing raw values would mismap
# Equalization (Samlex 1) as Bulk (Victron 1).
_CHARGE_STATE_MAP = {
    0: 0,  # Standby      → Idle
    1: 5,  # Equalization → Equalise
    2: 2,  # Absorption   → Absorption
    3: 3,  # Float        → Float
    4: 4,  # Storage      → Storage
    9: 9,  # Inverting    → Inverting
}

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

    @staticmethod
    def _to_int16(value):
        """Convert a uint16 Modbus register value to signed int16."""
        return value - 65536 if value > 32767 else value

    def _apply_scaled_fields(self, group_result, fields):
        """Apply scaled assignments from a group read result.

        fields: list of (reg_key, scale_key, section, field_name, digits[, signed])
        When signed is True the raw uint16 is interpreted as int16 before scaling.
        """
        for field in fields:
            reg_key, scale_key, section, field_name, digits = field[:5]
            signed = field[5] if len(field) > 5 else False
            raw = group_result[reg_key]
            if signed:
                raw = self._to_int16(raw)
            self.energy_data[section][field_name] = round(
                raw * self._scale(scale_key), digits
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
                ("REG_AC_OUT_CURRENT", "SCALE_AC_OUT_CURRENT", "L1", "ac_current", 2, True),
                ("REG_AC_OUT_POWER",   "SCALE_AC_OUT_POWER",   "L1", "ac_power",   0, True),
            ])
            self.energy_data["overall"]["ac_power"] = self.energy_data["L1"]["ac_power"]
        else:
            error = True

        # DC / battery (batch)
        dc = self._read_group(["REG_DC_VOLTAGE", "REG_DC_CURRENT", "REG_SOC"])
        if dc:
            self._apply_scaled_fields(dc, [
                ("REG_DC_VOLTAGE", "SCALE_DC_VOLTAGE", "dc", "voltage", 2),
                ("REG_DC_CURRENT", "SCALE_DC_CURRENT", "dc", "current", 2, True),
            ])
            self.energy_data["dc"]["soc"] = round(dc["REG_SOC"], 1)
            v = self.energy_data["dc"]["voltage"]
            i = self.energy_data["dc"]["current"]
            self.energy_data["dc"]["power"] = round(v * i, 0) if v is not None and i is not None else None
        else:
            error = True

        # AC input / shore power (batch)
        ac_in = self._read_group(["REG_AC_IN_VOLTAGE", "REG_AC_IN_CURRENT", "REG_AC_IN_CONNECTED"])
        if ac_in:
            self._apply_scaled_fields(ac_in, [
                ("REG_AC_IN_VOLTAGE",  "SCALE_AC_IN_VOLTAGE",  "ac_in", "voltage", 1),
                ("REG_AC_IN_CURRENT",  "SCALE_AC_IN_CURRENT",  "ac_in", "current", 2, True),
            ])
            v = self.energy_data["ac_in"]["voltage"]
            i = self.energy_data["ac_in"]["current"]
            self.energy_data["ac_in"]["power"] = round(v * i, 0) if v is not None and i is not None else None
            # Working status: 0=Power saving, 1=AC input normal, 2=AC input abnormal, 3=Inverting, 4=Fault
            # "Connected" means AC input is present and normal (value == 1)
            self.energy_data["ac_in"]["connected"] = 1 if ac_in["REG_AC_IN_CONNECTED"] == 1 else 0
        else:
            error = True

        # Fault / status (batch)
        status_regs = self._read_group(["REG_FAULT", "REG_CHARGE_STATE"])
        if status_regs:
            fault = status_regs["REG_FAULT"]
            raw_cs = status_regs["REG_CHARGE_STATE"]
            self.energy_data["dc"]["charge_state"] = _CHARGE_STATE_MAP.get(raw_cs, 0)
            if raw_cs not in _CHARGE_STATE_MAP:
                logger.warning("Unknown Samlex charge state %s; defaulting to Idle", raw_cs)

            # Derive vebus /State from fault, AC connection, and charge stage.
            # Priority: fault > AC disconnected > charge-stage-based state.
            ac_connected = self.energy_data["ac_in"]["connected"]
            if fault != 0:
                self.status = 2   # Fault
            elif ac_connected != 1:
                self.status = 9   # Inverting (no AC input)
            else:
                self.status = _VEBUS_STATE_FROM_CHARGE.get(raw_cs, 9)
        else:
            self.status = 2   # Fault (comms failure — safest default)
            error = True

        logger.debug("Samlex status: %s", self.status)
        return not error
