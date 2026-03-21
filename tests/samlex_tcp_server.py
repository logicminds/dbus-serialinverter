# -*- coding: utf-8 -*-
"""Samlex EVO Modbus TCP Server - Simulates a real inverter for testing.

This creates a true Modbus TCP server that responds to Modbus requests
with synthetic Samlex EVO data. The driver connects via TCP instead of
serial, using real Modbus protocol.

Usage:
    # Start the server
    python samlex_tcp_server.py

    # Or with custom options
    python samlex_tcp_server.py --port 5020 --identity 16420 --scenario fault

    # In another terminal, run the driver against it
    python dbus-serialinverter.py tcp://localhost:5020

The server supports multiple scenarios:
    - normal: Standard operation
    - fault: Simulates fault condition
    - low_battery: Low SOC
    - ac_disconnect: AC input disconnected
"""

import sys
import os
import argparse
import logging
import time
import threading
from typing import Dict, Optional

# Add path for pymodbus
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "etc", "dbus-serialinverter"))

from pymodbus.server import StartTcpServer
from pymodbus.datastore import ModbusSequentialDataBlock, ModbusSlaveContext, ModbusServerContext
from pymodbus.device import ModbusDeviceIdentification

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("samlex_tcp_server")


class SamlexModbusServer:
    """Modbus TCP server that simulates Samlex EVO inverter registers."""

    # Default register map for EVO-4024
    # NOTE: These are PLACEHOLDER addresses for testing only.
    # They do NOT match real Samlex register addresses (which are NDA-protected).
    # Using addresses in 4000-4150 range to look realistic but clearly not real.
    # Address -> Value (raw uint16)
    DEFAULT_REGISTERS = {
        # Identity register (EVO-4024 = 0x4024 = 16420)
        # PLACEHOLDER address - NOT the real register address
        4021: 16420,
        # Working status: 1 = AC input normal
        4084: 1,
        # Fault: 0 = no fault
        4092: 0,
        # DC voltage: 264 raw × 0.1 = 26.4V
        4115: 264,
        # DC current: 520 raw × 0.01 = 5.2A (charging)
        4129: 520,
        # AC output voltage: 1200 raw × 0.1 = 120.0V
        4023: 1200,
        # AC output current: 833 raw × 0.01 = 8.33A
        4037: 833,
        # AC output power: 1000 raw × 1.0 = 1000W
        4056: 1000,
        # SOC: 85% (no scaling)
        4048: 85,
        # Charge state: 2 = Absorption
        4061: 2,
        # AC input voltage: 1200 raw × 0.1 = 120.0V
        4107: 1200,
        # AC input current: 417 raw × 0.01 = 4.17A
        4138: 417,
        # AC input connected: 1 = yes
        4119: 1,
    }

    def __init__(self, host: str = "localhost", port: int = 5020,
                 slave_address: int = 1, scenario: str = "normal",
                 identity_value: int = 16420):
        """Initialize the Modbus TCP server.

        Args:
            host: Host address to bind to
            port: TCP port to listen on
            slave_address: Modbus slave address (unit ID)
            scenario: Test scenario (normal, fault, low_battery, ac_disconnect, heavy_load)
            identity_value: The identity register value (model-specific)
        """
        self.host = host
        self.port = port
        self.slave_address = slave_address
        self.scenario = scenario
        self.identity_value = identity_value
        self.registers = self._create_registers()
        self.server_thread: Optional[threading.Thread] = None
        self.server_running = False

    def _create_registers(self) -> Dict[int, int]:
        """Create register values based on scenario."""
        regs = dict(self.DEFAULT_REGISTERS)

        # Set identity
        regs[4021] = self.identity_value

        if self.scenario == "fault":
            regs[4092] = 1  # Fault code
            logger.info("Scenario: FAULT CONDITION")

        elif self.scenario == "low_battery":
            regs[4048] = 15  # Low SOC
            regs[4129] = 2000  # High discharge current (positive in raw)
            logger.info("Scenario: LOW BATTERY (15% SOC)")

        elif self.scenario == "ac_disconnect":
            regs[4084] = 3  # Inverting
            regs[4119] = 0  # AC input disconnected
            regs[4107] = 0  # AC input voltage 0
            regs[4138] = 0  # AC input current 0
            regs[4061] = 9  # Charge state = Inverting
            logger.info("Scenario: AC INPUT DISCONNECTED")

        elif self.scenario == "heavy_load":
            regs[4056] = 3800  # High power output
            regs[4037] = 317  # ~31.7A current (3800W / 120V)
            logger.info("Scenario: HEAVY LOAD (3800W)")

        else:
            logger.info("Scenario: NORMAL OPERATION")

        return regs

    def _make_context(self) -> ModbusServerContext:
        """Create Modbus server context with register data."""
        # Create data block with our registers
        # ModbusSequentialDataBlock stores values starting at address 0
        # We need to create a large enough block to cover all our registers
        max_addr = max(self.registers.keys()) if self.registers else 100

        # ModbusSequentialDataBlock needs a list of values starting at address 0
        values = []
        for addr in range(max_addr + 1):
            values.append(self.registers.get(addr, 0))

        # Debug: log the values we're setting
        logger.debug(f"Register block size: {len(values)}")
        for addr in sorted(self.registers.keys())[:10]:
            logger.debug(f"  Address {addr}: {self.registers[addr]}")

        # Create input registers block (function code 04)
        ir_block = ModbusSequentialDataBlock(0, values)

        # Create slave context - only input registers
        # zero_mode=True means addresses are 0-based (direct mapping)
        slave_context = ModbusSlaveContext(
            di=None,  # Discrete inputs
            co=None,  # Coils
            hr=None,  # Holding registers
            ir=ir_block,  # Input registers
            zero_mode=True  # Use 0-based addressing
        )

        # Create server context
        context = ModbusServerContext(
            slaves={self.slave_address: slave_context},
            single=False
        )

        return context

    def _make_identity(self) -> ModbusDeviceIdentification:
        """Create device identification."""
        identity = ModbusDeviceIdentification()
        identity.VendorName = "Samlex"
        identity.ProductCode = "EVO-4024"
        identity.ProductName = "Samlex EVO Series Inverter/Charger"
        identity.ModelName = "EVO-4024"
        identity.MajorMinorRevision = "1.0"
        return identity

    def start(self, blocking: bool = False):
        """Start the Modbus TCP server.

        Args:
            blocking: If True, blocks until server stops. If False, runs in thread.
        """
        context = self._make_context()
        identity = self._make_identity()

        logger.info(f"Starting Samlex Modbus TCP server on {self.host}:{self.port}")
        logger.info(f"Slave address: {self.slave_address}")
        logger.info(f"Identity value: {self.identity_value}")

        if blocking:
            # Run in foreground
            StartTcpServer(context=context, identity=identity, address=(self.host, self.port))
        else:
            # Run in background thread
            def _run_server():
                self.server_running = True
                try:
                    StartTcpServer(context=context, identity=identity, address=(self.host, self.port))
                finally:
                    self.server_running = False

            self.server_thread = threading.Thread(target=_run_server, daemon=True)
            self.server_thread.start()

            # Wait a bit for server to start
            time.sleep(0.5)
            logger.info("Server running in background thread")

    def stop(self):
        """Stop the server."""
        # Note: pymodbus TCP server doesn't have a clean stop method
        # It stops when the process exits or we can use a signal
        logger.info("Server stop requested (will stop on process exit)")
        self.server_running = False

    def get_connection_info(self) -> str:
        """Get connection string for driver."""
        return f"tcp://{self.host}:{self.port}"

    def __enter__(self):
        """Context manager entry."""
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.stop()
        return False


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Samlex EVO Modbus TCP Server",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Normal operation (default)
  python samlex_tcp_server.py

  # Different scenario
  python samlex_tcp_server.py --scenario fault

  # Custom port and identity
  python samlex_tcp_server.py --port 15020 --identity 8722
        """
    )

    parser.add_argument(
        "--host",
        default="localhost",
        help="Host to bind to (default: localhost)"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=5020,
        help="TCP port to listen on (default: 5020)"
    )
    parser.add_argument(
        "--slave",
        type=int,
        default=1,
        help="Modbus slave address (default: 1)"
    )
    parser.add_argument(
        "--identity",
        type=int,
        default=16420,
        help="Identity register value (default: 16420 for EVO-4024)"
    )
    parser.add_argument(
        "--scenario",
        choices=["normal", "fault", "low_battery", "ac_disconnect", "heavy_load"],
        default="normal",
        help="Test scenario (default: normal)"
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose logging"
    )

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    print("=" * 70)
    print("Samlex EVO Modbus TCP Server")
    print("=" * 70)
    print(f"Host: {args.host}")
    print(f"Port: {args.port}")
    print(f"Slave Address: {args.slave}")
    print(f"Identity: {args.identity}")
    print(f"Scenario: {args.scenario}")
    print("=" * 70)
    print()
    print(f"To connect the driver, use:")
    print(f"  python dbus-serialinverter.py tcp://{args.host}:{args.port}")
    print()
    print("Press Ctrl+C to stop...")
    print()

    server = SamlexModbusServer(
        host=args.host,
        port=args.port,
        slave_address=args.slave,
        scenario=args.scenario,
        identity_value=args.identity
    )

    try:
        # Run blocking (foreground)
        server.start(blocking=True)
    except KeyboardInterrupt:
        print("\n\nStopping server...")
        server.stop()
        print("Done.")


if __name__ == "__main__":
    sys.exit(main() or 0)
