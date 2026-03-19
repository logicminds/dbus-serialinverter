# -*- coding: utf-8 -*-

from inverter import Inverter
from utils import logger

from pymodbus.client import ModbusSerialClient


class ModbusInverter(Inverter):
    """Base class for Modbus RTU inverter drivers.

    Provides shared client setup, connection management, and register reads.
    Subclasses implement test_connection(), get_settings(), and refresh_data().
    """

    def __init__(self, port, baudrate, slave):
        super().__init__(port, baudrate, slave)
        self.client = ModbusSerialClient(
            method="rtu",
            port=port,
            baudrate=baudrate,
            stopbits=1,
            parity="N",
            bytesize=8,
            timeout=1,
        )

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
        logger.debug("Read batch - address=%s, count=%s, slave=%s", address, count, self.slave)
        if res.isError():
            logger.error("Error reading registers %s-%s", address, address + count - 1)
            return False, []
        if len(res.registers) < count:
            logger.error("Truncated response: expected %s registers, got %s (address=%s)", count, len(res.registers), address)
            return False, []
        return True, res.registers
