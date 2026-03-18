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
from pymodbus.constants import Endian
from pymodbus.payload import BinaryPayloadDecoder

class Solis(Inverter):
    INVERTERTYPE = "Solis"

    def __init__(self, port, baudrate, slave):
        super(Solis, self).__init__(port, baudrate, slave)
        self.type = self.INVERTERTYPE

        self.client = ModbusSerialClient(method = 'rtu', port = port, baudrate = baudrate, stopbits = 1, parity = 'N', bytesize = 8, timeout = 1)
        logger.info("Creating ModbusSerialClient on port %s with baudrate %s" % (port, baudrate))

    def test_connection(self):
        try:
            logger.debug("test_connection(): Connected!")
            # Product model
            success, self.product_model = self.read_input_registers(2999, 1, "u16", 1, 0)
            if (success):
                logger.debug("Product model: %s" % self.product_model)
                if (self.product_model == 224):
                    return True
                else:
                    logger.warn("Unsupported product model: %s" % self.product_model)
                    return False
            else:
                return False
        except IOError:
            logger.debug("test_connection(): IOError")
            return False

    def get_settings(self):
        # Static info from config
        self.max_ac_power = utils.INVERTER_MAX_AC_POWER
        self.phase = utils.INVERTER_PHASE
        self.poll_interval = utils.INVERTER_POLL_INTERVAL
        self.position = utils.INVERTER_POSITION

        # Software version
        success, self.hardware_version = self.read_input_registers(3000, 1, "u16", 1, 0)
        logger.debug("DSP version: %s" % self.hardware_version)

        # Serial
        res = self.client.read_input_registers(address = 3060,
                                count = 4,
                                slave = self.slave)

        if not res.isError():
            serialparts = []
            for x in res.registers:
                serialparts.append((hex(x)[2:])[::-1])

            self.serial_number = ''.join(serialparts)
            logger.debug("Serial: %s" % self.serial_number)
        else:
            logger.debug("Error reading serial number")
            return False

        # Power limit
        success, power_limit = self.read_input_registers(3049, 1, "u16", 0.01, 0)
        if (success):
            power_limit_watts = float(self.max_ac_power * (int(power_limit) / 100))
            self.energy_data['overall']['power_limit'] = power_limit_watts
            self.energy_data['overall']['active_power_limit'] = power_limit_watts
            logger.debug("Active power limit: %d W (%d %%)" % (power_limit_watts, power_limit))

        return True

    def refresh_data(self):
        # call all functions that will refresh the inverter data.
        # This will be called for every iteration (1 second)
        # Return True if success, False for failure
        result = self.read_status_data()
        return result

    def _ensure_connected(self):
        """Return True if the Modbus connection is open, connecting once if needed."""
        if self.client.is_socket_open():
            return True
        return self.client.connect()

    def read_input_registers(self, address, count, data_type, scale, digits):
        connection = self._ensure_connected()
        if (connection):
            res = self.client.read_input_registers(address = address,
                                    count = count,
                                    slave = self.slave)

            logger.debug("Read input register - address=%s, count=%s, slave=%s" % (address, count, self.slave))

            if not res.isError():
                decoder = BinaryPayloadDecoder.fromRegisters(res.registers, Endian.Big)

                if (data_type == 'string'):
                    data = decoder.decode_string(8)
                elif (data_type == 'float'):
                    data = decoder.decode_32bit_float()
                elif (data_type == 'u16'):
                    data = decoder.decode_16bit_uint()
                elif (data_type == 'u32'):
                    data = decoder.decode_32bit_uint()
                else:
                    logger.warn("Unsupported data type specified: %s" % data_type)
                    return False, 0

                logger.debug("Register: %s - Raw data: %s" % (address, data))

                # Scale
                data = round(data * scale, digits)
                logger.debug("Register: %s - Scaled data: %s" % (address, data))
                return True, data
            else:
                logger.error("Error reading register %s" % address)
                logger.debug(res)
        else:
            logger.error("No connection")

        return False, 0

    def write_registers(self, address, value):
        connection = self._ensure_connected()
        if (connection):
            res = self.client.write_registers(address, value, slave = self.slave)
            logger.debug("Write register - address=%s, value=%s, slave=%s" % (address, value, self.slave))
            if not res.isError():
                logger.debug(res)
                return True
            else:
                logger.error("Error writing register %s" % address)
        else:
            logger.error("No connection")

        return False

    def apply_power_limit(self, watts):
        new_pct = max(0, min(100, round(watts / (self.max_ac_power / 100))))
        logger.info("Applying power limit: %d W (%d %%)" % (watts, new_pct))
        return self.write_registers(3051, new_pct * 100)

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

    def read_status_data(self):
        error = False

        # Batch 1: output_type (3002) + ac_power (3004-3005) in one 4-register read.
        # Register layout: [output_type, unused, ac_power_hi, ac_power_lo]
        ok, regs = self._read_batch(3002, 4)
        if ok:
            output_type = regs[0]
            decoder = BinaryPayloadDecoder.fromRegisters(regs[2:4], Endian.Big)
            self.energy_data['overall']['ac_power'] = decoder.decode_32bit_uint()
        else:
            output_type = 0
            error = True

        # Batch 2: energy forwarded overall (3014, 1 reg)
        ok, regs = self._read_batch(3014, 1)
        if ok:
            self.energy_data['overall']['energy_forwarded'] = round(regs[0] * 0.1, 2)
        else:
            error = True

        if output_type == 0:
            # Single-phase inverter
            for phase in ['L1', 'L2', 'L3']:
                self.energy_data[phase]['ac_voltage'] = 0.0
                self.energy_data[phase]['ac_current'] = 0.0
                self.energy_data[phase]['ac_power'] = 0.0
                self.energy_data[phase]['energy_forwarded'] = 0.0

            # Batch 3: phase voltage (3035) and current (3038) in one 4-register read.
            # Register layout: [voltage, unused, unused, current]
            ok, regs = self._read_batch(3035, 4)
            if ok:
                self.energy_data[self.phase]['ac_voltage'] = round(regs[0] * 0.1, 0)
                self.energy_data[self.phase]['ac_current'] = round(regs[3] * 0.1, 2)
            else:
                error = True

            self.energy_data[self.phase]['ac_power'] = self.energy_data['overall']['ac_power']
            self.energy_data[self.phase]['energy_forwarded'] = self.energy_data['overall']['energy_forwarded']
        else:
            # 3-phase inverter
            # Batch 3: all phase voltages and currents (3033-3038, 6 regs).
            # Register layout: [L1V, L2V, L3V, L1A, L2A, L3A]
            ok, regs = self._read_batch(3033, 6)
            if ok:
                self.energy_data['L1']['ac_voltage'] = round(regs[0] * 0.1, 0)
                self.energy_data['L2']['ac_voltage'] = round(regs[1] * 0.1, 0)
                self.energy_data['L3']['ac_voltage'] = round(regs[2] * 0.1, 0)
                self.energy_data['L1']['ac_current'] = round(regs[3] * 0.1, 2)
                self.energy_data['L2']['ac_current'] = round(regs[4] * 0.1, 2)
                self.energy_data['L3']['ac_current'] = round(regs[5] * 0.1, 2)
            else:
                error = True

            # Energy forwarded L1/L2/L3: per-phase registers not yet implemented;
            # publish None so VenusOS knows the value is unavailable, not zero.
            self.energy_data['L1']['energy_forwarded'] = None
            self.energy_data['L2']['energy_forwarded'] = None
            self.energy_data['L3']['energy_forwarded'] = None

        # Batch 4: status (3043, 1 reg)
        # Victron: 0=Waiting; 1=OpenRun; 2=SoftRun; 7=Generating; 8=Off; 10=Fault
        ok, regs = self._read_batch(3043, 1)
        if ok:
            status = regs[0]
            if status == 0:
                self.status = 0
            elif status == 1:
                self.status = 1
            elif status == 2:
                self.status = 2
            elif status == 3:
                self.status = 7
            else:
                self.status = 10
        else:
            self.status = 8
            error = True

        logger.debug("Inverter status: %s" % self.status)

        # Batch 5: active power limit (3049, 1 reg) — read only
        ok, regs = self._read_batch(3049, 1)
        if ok:
            power_limit_pct = round(regs[0] * 0.01, 0)
            power_limit_watts = float(self.max_ac_power * (int(power_limit_pct) / 100))
            self.energy_data['overall']['active_power_limit'] = power_limit_watts
            logger.debug("Active power limit: %d W (%d %%)" % (power_limit_watts, power_limit_pct))
        else:
            error = True

        return not error
