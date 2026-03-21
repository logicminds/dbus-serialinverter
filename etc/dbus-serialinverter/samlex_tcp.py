# -*- coding: utf-8 -*-
"""Samlex EVO driver with TCP Modbus support.

This extends the base Samlex driver to support Modbus TCP connections.
Use this when connecting to a Modbus TCP gateway or simulator.

Usage:
    TYPE=SamlexTCP
    ADDRESS=1
    # No port needed - uses tcp:// URL syntax

Or from command line:
    python dbus-serialinverter.py tcp://localhost:5020

The port argument accepted by this class can be:
    - /dev/ttyUSB0 (serial - passed to parent Samlex class)
    - tcp://localhost:5020 (TCP - handled by this class)
    - 192.168.1.100:502 (TCP shorthand - parsed by this class,
      but note that get_port() in dbus-serialinverter.py only
      validates tcp:// URLs and /dev/ paths)
"""

import re
from samlex import Samlex
from utils import logger


class SamlexTCP(Samlex):
    """Samlex EVO driver with Modbus TCP support.

    Extends the base Samlex driver to support TCP connections while
    maintaining full compatibility with the original behavior.
    """
    INVERTERTYPE = "SamlexTCP"

    def __init__(self, port, baudrate=None, slave=1):
        """Initialize the TCP-capable Samlex driver.

        Args:
            port: Either a serial device path or TCP URL (tcp://host:port or host:port)
            baudrate: Ignored for TCP connections
            slave: Modbus slave address (unit ID)
        """
        # Parse TCP URL if provided
        self.tcp_host = None
        self.tcp_port = None
        self.is_tcp = False

        parsed = self._parse_tcp_url(port)
        if parsed:
            self.is_tcp = True
            self.tcp_host, self.tcp_port = parsed
            # Don't call parent init yet - we'll create our own client
            self._init_tcp_client(port, slave)
        else:
            # Not TCP - use parent serial implementation
            super().__init__(port, baudrate, slave)

    def _parse_tcp_url(self, port: str):
        """Parse TCP URL format.

        Supports:
            - tcp://localhost:5020
            - tcp://192.168.1.100:502
            - 192.168.1.100:502 (shorthand)

        Returns:
            (host, port) tuple or None if not TCP
        """
        if not port:
            return None

        # Full URL format: tcp://host:port
        if port.startswith("tcp://"):
            match = re.match(r"tcp://([^:]+):(\d+)", port)
            if match:
                return match.group(1), int(match.group(2))
            return None

        # Shorthand format: host:port (must have both host and numeric port)
        if ":" in port and not port.startswith("/"):
            parts = port.rsplit(":", 1)
            if len(parts) == 2:
                host, port_str = parts
                if port_str.isdigit():
                    return host, int(port_str)

        return None

    def _init_tcp_client(self, original_port: str, slave: int):
        """Initialize TCP client without calling parent's __init__."""
        from pymodbus.client import ModbusTcpClient  # deferred: not available in test stubs

        # Initialize Inverter base class manually
        from inverter import Inverter
        Inverter.__init__(self, original_port, 0, slave)

        self.type = self.INVERTERTYPE
        self.energy_data["dc"]["charge_state"] = None

        # Create TCP client
        logger.info("Creating ModbusTcpClient (SamlexTCP) on %s:%s",
                    self.tcp_host, self.tcp_port)
        self.client = ModbusTcpClient(
            host=self.tcp_host,
            port=self.tcp_port,
            timeout=1
        )

    def _ensure_connected(self):
        """Override to handle TCP connection."""
        if not self.is_tcp:
            return super()._ensure_connected()

        if self.client.is_socket_open():
            return True
        logger.debug("Connecting to %s:%s", self.tcp_host, self.tcp_port)
        return self.client.connect()


# Factory function for backward compatibility
def create_samlex(port: str, baudrate=9600, slave=1):
    """Factory that creates appropriate Samlex variant based on port.

    Args:
        port: Serial device path or TCP URL
        baudrate: Serial baud rate (ignored for TCP)
        slave: Modbus slave address

    Returns:
        Samlex or SamlexTCP instance
    """
    if port and (port.startswith("tcp://") or
                 (":" in port and not port.startswith("/"))):
        return SamlexTCP(port, baudrate, slave)
    return Samlex(port, baudrate, slave)
