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
import configparser
import logging
import time
import threading
from typing import Any, Dict, Optional

# Add path for pymodbus and driver modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "etc", "dbus-serialinverter"))

from pymodbus.server import StartTcpServer
from pymodbus.datastore import ModbusSequentialDataBlock, ModbusSlaveContext, ModbusServerContext
from pymodbus.device import ModbusDeviceIdentification

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("samlex_tcp_server")

# ── Single source of truth: synthetic engineering values for the normal scenario ──
# Keys match [SAMLEX_REGISTERS] config keys exactly.
# Scaled registers (REG_*_VOLTAGE / CURRENT / POWER) hold target engineering-unit
# values; the raw uint16 sent over Modbus is computed as round(value / SCALE_*).
# Dimensionless/raw registers (FAULT, SOC, CHARGE_STATE, AC_IN_CONNECTED, IDENTITY)
# are stored as the exact raw uint16 written to the Modbus datastore.
_NORMAL_VALUES: Dict[str, Any] = {
    "REG_IDENTITY":        None,   # filled at runtime from identity_value arg
    "REG_AC_IN_CONNECTED": 1,      # raw: 1 = AC input normal
    "REG_FAULT":           0,      # raw: 0 = no fault
    "REG_DC_VOLTAGE":      26.4,   # V
    "REG_DC_CURRENT":      5.2,    # A (positive = charging)
    "REG_AC_OUT_VOLTAGE":  120.0,  # V
    "REG_AC_OUT_CURRENT":  8.33,   # A
    "REG_AC_OUT_POWER":    1000.0, # W
    "REG_SOC":             85,     # % (no scale)
    "REG_CHARGE_STATE":    2,      # raw: 2 = Absorption
    "REG_AC_IN_VOLTAGE":   120.0,  # V
    "REG_AC_IN_CURRENT":   4.17,   # A
}

# Maps each scaled REG_* key to its corresponding SCALE_* key in [SAMLEX_REGISTERS]
_SCALE_MAP: Dict[str, str] = {
    "REG_AC_OUT_VOLTAGE": "SCALE_AC_OUT_VOLTAGE",
    "REG_AC_OUT_CURRENT": "SCALE_AC_OUT_CURRENT",
    "REG_AC_OUT_POWER":   "SCALE_AC_OUT_POWER",
    "REG_DC_VOLTAGE":     "SCALE_DC_VOLTAGE",
    "REG_DC_CURRENT":     "SCALE_DC_CURRENT",
    "REG_AC_IN_VOLTAGE":  "SCALE_AC_IN_VOLTAGE",
    "REG_AC_IN_CURRENT":  "SCALE_AC_IN_CURRENT",
}


def _load_samlex_config() -> configparser.ConfigParser:
    """Load config.ini and config.ini.private (if present) from the driver directory.

    This is the same load order that utils.py uses, so the register map seen
    here is identical to the one the driver itself will use at runtime.
    """
    driver_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "etc", "dbus-serialinverter")
    cfg = configparser.ConfigParser()
    cfg.read(
        [
            os.path.join(driver_dir, "config.ini.samlexTCP"),
        ]
    )
    return cfg


class SamlexModbusServer:
    """Modbus TCP server that simulates Samlex EVO inverter registers.

    Register addresses and scale factors are read from config.ini (and
    config.ini.private when present) using the same load order as the
    driver itself, so there is a single source of truth for the register map.
    """

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
        self._cfg = _load_samlex_config()
        self.registers = self._create_registers()
        self.server_thread: Optional[threading.Thread] = None
        self.server_running = False

    def _build_registers(self, values: Dict[str, Any]) -> Dict[int, int]:
        """Convert a reg_key→engineering_value dict to addr→raw_uint16.

        Register addresses come from [SAMLEX_REGISTERS] REG_* keys in the
        loaded config.  Raw values for scaled registers are computed as
        round(engineering_value / SCALE_*) — the inverse of what the driver
        does when it reads them.  Registers whose config entry is still '???'
        are skipped with a warning so the server degrades gracefully when
        config.ini.private has not been installed.
        """
        cfg = self._cfg
        regs: Dict[int, int] = {}
        for reg_key, eng_val in values.items():
            addr_str = cfg.get("SAMLEX_REGISTERS", reg_key, fallback="???").strip()
            if addr_str == "???":
                logger.warning("Register %s not configured in config.ini; skipping", reg_key)
                continue
            addr = int(addr_str)

            if reg_key == "REG_IDENTITY":
                raw = self.identity_value
            elif reg_key in _SCALE_MAP:
                scale_key = _SCALE_MAP[reg_key]
                scale_str = cfg.get("SAMLEX_REGISTERS", scale_key, fallback="???").strip()
                if scale_str == "???":
                    logger.warning("Scale %s not configured; skipping %s", scale_key, reg_key)
                    continue
                raw = round(eng_val / float(scale_str))
            else:
                raw = int(eng_val)

            regs[addr] = raw
        return regs

    def _create_registers(self) -> Dict[int, int]:
        """Build the Modbus datastore values for the chosen scenario.

        Scenario overrides are expressed in engineering units (volts, amps,
        watts, raw codes) against the _NORMAL_VALUES keys — never against
        hard-coded addresses — so the address mapping stays solely in config.
        """
        values: Dict[str, Any] = dict(_NORMAL_VALUES)

        if self.scenario == "fault":
            values["REG_FAULT"] = 1
            logger.info("Scenario: FAULT CONDITION")

        elif self.scenario == "low_battery":
            values["REG_SOC"] = 15
            values["REG_DC_CURRENT"] = 20.0  # high discharge (positive raw; sign handled by driver)
            logger.info("Scenario: LOW BATTERY (15% SOC)")

        elif self.scenario == "ac_disconnect":
            values["REG_AC_IN_CONNECTED"] = 3  # raw: 3 = Inverting
            values["REG_AC_IN_VOLTAGE"] = 0.0
            values["REG_AC_IN_CURRENT"] = 0.0
            values["REG_CHARGE_STATE"] = 9    # raw: 9 = Inverting
            logger.info("Scenario: AC INPUT DISCONNECTED")

        elif self.scenario == "heavy_load":
            values["REG_AC_OUT_POWER"] = 3800.0
            values["REG_AC_OUT_CURRENT"] = 31.7  # 3800 W / 120 V
            logger.info("Scenario: HEAVY LOAD (3800W)")

        else:
            logger.info("Scenario: NORMAL OPERATION")

        return self._build_registers(values)

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
    print("To connect the driver, use:")
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
