# -*- coding: utf-8 -*-

from modbus_inverter import ModbusInverter
from utils import logger
import utils

# Samlex EVO charge stage → Victron /State (vebus operating state)
# Derived from REG_CHARGE_STATE when AC is connected. Fault and AC-disconnected are handled first.
# Mapping configured to match Victron /State: 3=Bulk, 4=Absorption, 5=Float, 7=Equalize, 8=Passthru, 9=Inverting
_VEBUS_STATE_FROM_CHARGE = {
    0: 8,  # Standby      → Passthru
    1: 3,  # Bulk         → Bulk
    2: 4,  # Absorption   → Absorption
    3: 7,  # Equalization → Equalize
    4: 5,  # Float        → Float
    5: 8,  # Charger stop → Passthru
}

# Samlex EVO charge stage → Victron /VebusChargeState
# Samlex: 0=Standby, 1=Bulk, 2=Absorption, 3=Equalization, 4=Float, 5=ChargerStop, 9=Inverting
# Victron: 0=Idle, 1=Bulk, 2=Absorption, 3=Float, 5=Equalise, 9=Inverting
_CHARGE_STATE_MAP = {
    0: 0,  # Standby      → Idle
    1: 1,  # Bulk         → Bulk
    2: 2,  # Absorption   → Absorption
    3: 5,  # Equalization → Equalise
    4: 3,  # Float        → Float
    5: 0,  # Charger stop → Idle
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
)

# Optional registers — read if configured, otherwise skipped.
# Samlex EVO does not report SOC; a separate Battery Monitor provides it.
OPTIONAL_SAMLEX_REGISTERS = (
    "REG_SOC",
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

    def _has_register(self, key):
        """Return True if the optional register key is configured as a valid Modbus register."""
        val = utils.config.get("SAMLEX_REGISTERS", key, fallback="???").strip()
        if val == "???":
            return False
        try:
            value = int(val)
        except ValueError:
            return False
        return 0 <= value <= 65535

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

    def _read_batch(self, address, count):
        """Read `count` holding registers (FC03) from `address`. Samlex EVO uses FC03."""
        if not self._ensure_connected():
            logger.error("No connection")
            return False, []
        res = self.client.read_holding_registers(address=address, count=count, slave=self.slave)
        logger.debug("Read batch - address=%s, count=%s, slave=%s", address, count, self.slave)
        if res.isError():
            logger.error("Error reading registers %s-%s", address, address + count - 1)
            return False, []
        if len(res.registers) < count:
            logger.error(
                "Truncated response: expected %s registers, got %s (address=%s)",
                count, len(res.registers), address,
            )
            return False, []
        return True, res.registers

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
        # Step 2: confirm presence by reading REG_IDENTITY (configured via config.ini).
        try:
            ok, regs = self._read_batch(self._reg("REG_IDENTITY"), 1)
            if ok and regs[0] in (0, 1, 2, 3):
                logger.debug("Samlex: identity confirmed (operating mode %s)", regs[0])
                return True
            logger.debug("Samlex: unexpected operating mode %s or read failed", regs[0] if ok else "N/A")
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
            # Load power is computed after ac_in is read (see below).
        else:
            error = True

        # DC / battery (batch)
        dc_keys = ["REG_DC_VOLTAGE", "REG_DC_CURRENT"]
        has_soc = self._has_register("REG_SOC")
        if has_soc:
            dc_keys.append("REG_SOC")
        dc = self._read_group(dc_keys)
        if dc:
            self._apply_scaled_fields(dc, [
                ("REG_DC_VOLTAGE", "SCALE_DC_VOLTAGE", "dc", "voltage", 2),
                ("REG_DC_CURRENT", "SCALE_DC_CURRENT", "dc", "current", 2, True),
            ])
            if has_soc:
                self.energy_data["dc"]["soc"] = round(dc["REG_SOC"], 1)
            # else: SOC stays None — Battery Monitor provides it
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
            # AC connection status from REG_AC_IN_CONNECTED; uses bit 9 of the status word
            # to detect absent/abnormal AC input (configured via config.ini SCALE_AC_IN_CONNECTED).
            self.energy_data["ac_in"]["connected"] = 0 if (ac_in["REG_AC_IN_CONNECTED"] & 0x200) else 1
        else:
            error = True

        # DC current sign correction for VE.Bus convention:
        # /Dc/0/Current must be negative when inverting (consuming from battery),
        # positive when charging (pushing power to battery).
        # The Samlex EVO DC current register always returns a positive magnitude —
        # apply sign based on AC connection status.
        if self.energy_data["ac_in"]["connected"] == 0:
            dc_i = self.energy_data["dc"].get("current")
            dc_v = self.energy_data["dc"].get("voltage")
            if dc_i is not None and dc_i > 0:
                self.energy_data["dc"]["current"] = -dc_i
                if dc_v is not None:
                    self.energy_data["dc"]["power"] = round(-dc_v * dc_i, 0)

        # Compute AC load power (requires both ac_out and ac_in reads above).
        # AC power sign: positive=inverting (battery→loads), negative=charging (grid→battery).
        # When inverting: AC power is the load power directly.
        # When charging: the EVO uses a transfer switch — loads draw from AC input directly,
        # bypassing the output current sensor. Load power = grid_VA - charger_power.
        #   load_power = (V_in × I_in) + ac_p   (ac_p is negative, so this subtracts)
        if ac_out:
            ac_p = self.energy_data["L1"]["ac_power"]
            if ac_p < 0:
                gv = self.energy_data["ac_in"]["voltage"]
                gi = self.energy_data["ac_in"]["current"]
                grid_va = round(gv * gi, 0) if gv is not None and gi is not None else 0
                self.energy_data["L1"]["ac_power"] = max(0, grid_va + ac_p)
            self.energy_data["overall"]["ac_power"] = self.energy_data["L1"]["ac_power"]

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
