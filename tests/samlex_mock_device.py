# -*- coding: utf-8 -*-
"""Mock Samlex EVO Modbus device for integration testing (DEPRECATED).

WARNING: This PTY-based approach requires the 'serial' module which may not be
available in all test environments. For new tests, use samlex_mock_client.py
instead which provides a simpler mock that works without serial dependencies.

This file is kept for reference but is not actively used in the test suite.

Creates a virtual serial port pair using PTY (pseudo-terminal) and runs a
Modbus server that responds like a real Samlex EVO inverter.

Usage:
    # Start the mock device
    from samlex_mock_device import SamlexMockDevice
    mock = SamlexMockDevice()
    mock.start()
    port = mock.get_client_port()  # e.g., '/dev/ttys001'

    # Connect your driver to the port
    driver = Samlex(port, 9600, slave=1)

    # Clean up
    mock.stop()
"""

import os
import pty
import threading
import time
import struct
from collections import defaultdict

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "etc", "dbus-serialinverter"))

# Use the embedded pymodbus
from pymodbus.server import StartSerialServer
from pymodbus.datastore import ModbusSequentialDataBlock, ModbusSlaveContext, ModbusServerContext
from pymodbus.transaction import ModbusRtuFramer


class SamlexMockDevice:
    """Mock Samlex EVO inverter for integration testing.

    Creates a virtual serial port and responds to Modbus RTU requests
    with configurable register values that simulate a real EVO unit.
    """

    # Default realistic values for EVO-4024 @ 24V
    DEFAULT_REGISTERS = {
        # Identity - EVO-4024 returns 0x4024 = 16420
        0: 16420,
        # Working status: 0=Power saving, 1=AC in normal, 2=AC in abnormal,
        #                 3=Inverting, 4=Fault
        1: 1,  # AC input normal
        # Fault register: 0=no fault
        2: 0,
        # DC voltage (scaled: 260 * 0.1 = 26.0V)
        10: 260,
        # DC current (scaled: 500 * 0.01 = 5.0A charging)
        11: 500,
        # AC output voltage (scaled: 1200 * 0.1 = 120.0V)
        20: 1200,
        # AC output current (scaled: 833 * 0.01 = 8.33A)
        21: 833,
        # AC output power (scaled: 1000 * 1.0 = 1000W)
        22: 1000,
        # SOC (0-100, no scaling)
        30: 85,
        # Charger state
        31: 2,  # Absorption
        # AC input voltage (scaled: 1200 * 0.1 = 120.0V)
        40: 1200,
        # AC input current (scaled: 417 * 0.01 = 4.17A)
        41: 417,
        # AC input connected (1=yes)
        42: 1,
    }

    def __init__(self, slave_address=1, baudrate=9600, registers=None):
        """Initialize the mock device.

        Args:
            slave_address: Modbus slave address (default 1)
            baudrate: Serial baud rate (must match client)
            registers: Dict of register_address -> value to override defaults
        """
        self.slave_address = slave_address
        self.baudrate = baudrate
        self._registers = dict(self.DEFAULT_REGISTERS)
        if registers:
            self._registers.update(registers)

        self._server_thread = None
        self._server_stop_event = threading.Event()
        self._master_fd = None
        self._slave_fd = None
        self._client_port = None
        self._server_running = False

    def _create_virtual_serial(self):
        """Create a PTY pair for virtual serial communication."""
        # Create pseudo-terminal pair
        self._master_fd, self._slave_fd = pty.openpty()

        # Get the slave port name (client connects to this)
        self._client_port = os.ttyname(self._slave_fd)

        # Server will read from master_fd
        return self._master_fd

    def _make_server_context(self):
        """Create Modbus server context with our register data."""
        # Create data blocks for input registers (function code 04)
        # ModbusSequentialDataBlock(start_address, [values])
        max_addr = max(self._registers.keys()) if self._registers else 100
        # Create a list of values for contiguous registers
        values = []
        for addr in range(max_addr + 1):
            values.append(self._registers.get(addr, 0))

        # Input registers (function code 04)
        ir_block = ModbusSequentialDataBlock(0, values)

        # Create slave context
        slave_context = ModbusSlaveContext(
            di=None,   # Discrete inputs (not used)
            co=None,   # Coils (not used)
            hr=None,   # Holding registers (not used)
            ir=ir_block  # Input registers
        )

        # Create server context
        context = ModbusServerContext(slaves={self.slave_address: slave_context}, single=False)
        return context

    def _run_server(self):
        """Run the Modbus server (called in separate thread)."""
        try:
            context = self._make_server_context()

            # Start serial server on the master FD
            # Note: This is a simplified approach - pymodbus serial server
            # expects a serial port. We'll use a custom approach.
            self._server_running = True

            # Read from master_fd and process Modbus requests
            while not self._server_stop_event.is_set():
                try:
                    # Read available data
                    import select
                    ready, _, _ = select.select([self._master_fd], [], [], 0.1)
                    if ready:
                        data = os.read(self._master_fd, 256)
                        if data:
                            response = self._process_modbus_frame(data)
                            if response:
                                os.write(self._master_fd, response)
                except Exception as e:
                    if not self._server_stop_event.is_set():
                        print(f"Mock device error: {e}")

        except Exception as e:
            print(f"Server thread error: {e}")
        finally:
            self._server_running = False

    def _process_modbus_frame(self, data):
        """Process a Modbus RTU request frame and return response.

        This is a minimal RTU server implementation for input registers (function code 04).
        """
        if len(data) < 8:  # Minimum RTU frame: slave(1) + fc(1) + addr(2) + count(2) + crc(2)
            return None

        slave_id = data[0]
        if slave_id != self.slave_address:
            return None

        function_code = data[1]

        if function_code == 0x04:  # Read Input Registers
            return self._handle_read_input_registers(data)
        else:
            # Unsupported function - return exception
            return bytes([slave_id, function_code | 0x80, 0x01])  # Illegal function

    def _crc16(self, data):
        """Calculate Modbus CRC16."""
        crc = 0xFFFF
        for byte in data:
            crc ^= byte
            for _ in range(8):
                if crc & 0x0001:
                    crc = (crc >> 1) ^ 0xA001
                else:
                    crc >>= 1
        return crc

    def _handle_read_input_registers(self, data):
        """Handle Modbus function code 04 - Read Input Registers."""
        slave_id = data[0]
        function_code = data[1]

        # Parse starting address and quantity
        start_addr = struct.unpack(">H", data[2:4])[0]
        quantity = struct.unpack(">H", data[4:6])[0]

        # Build response
        response_data = []
        for addr in range(start_addr, start_addr + quantity):
            value = self._registers.get(addr, 0)
            response_data.extend(struct.pack(">H", value))

        # Build RTU response: slave + fc + byte_count + data
        byte_count = len(response_data)
        response = bytes([slave_id, function_code, byte_count]) + bytes(response_data)

        # Add CRC
        crc = self._crc16(response)
        response += bytes([crc & 0xFF, (crc >> 8) & 0xFF])

        return response

    def start(self, timeout=5):
        """Start the mock device server.

        Args:
            timeout: Seconds to wait for server to be ready

        Returns:
            str: The serial port path to connect to (e.g., '/dev/ttys001')
        """
        self._create_virtual_serial()

        # Start server thread
        self._server_thread = threading.Thread(target=self._run_server, daemon=True)
        self._server_thread.start()

        # Wait for server to be ready
        start_time = time.time()
        while not self._server_running and time.time() - start_time < timeout:
            time.sleep(0.1)

        if not self._server_running:
            raise RuntimeError("Mock device server failed to start")

        # Small delay to ensure everything is ready
        time.sleep(0.2)

        return self._client_port

    def stop(self, timeout=2):
        """Stop the mock device server."""
        self._server_stop_event.set()

        if self._server_thread:
            self._server_thread.join(timeout=timeout)

        # Close file descriptors
        if self._master_fd:
            os.close(self._master_fd)
        if self._slave_fd:
            os.close(self._slave_fd)

        self._server_running = False

    def get_client_port(self):
        """Return the serial port path clients should connect to."""
        return self._client_port

    def set_register(self, address, value):
        """Set a register value dynamically.

        Args:
            address: Register address
            value: Register value (0-65535)
        """
        self._registers[address] = value

    def get_register(self, address):
        """Get current register value."""
        return self._registers.get(address, 0)

    def simulate_fault(self, fault_code=1):
        """Simulate a fault condition.

        Args:
            fault_code: Fault register value (0=no fault)
        """
        # Assuming fault register is at address 2
        self._registers[2] = fault_code

    def simulate_disconnected_ac_input(self):
        """Simulate AC input disconnected."""
        # Assuming AC connected register is at address 42
        self._registers[42] = 0

    def simulate_low_battery(self, soc=15):
        """Simulate low battery condition.

        Args:
            soc: State of charge (0-100)
        """
        self._registers[30] = soc

    def __enter__(self):
        """Context manager entry."""
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.stop()
        return False


def create_test_registers(identity_value=16420):
    """Create a complete register map for testing.

    Returns a dict with all standard Samlex EVO registers configured
    for a realistic test scenario.

    Args:
        identity_value: The identity register value (e.g., 16420 for EVO-4024)
    """
    registers = {
        # Identity register (address 0 in example, but configurable)
        0: identity_value,
        # Working status
        1: 1,  # AC input normal
        # Fault
        2: 0,  # No fault
        # DC voltage (26.4V)
        10: 264,
        # DC current (5.2A charging)
        11: 520,
        # AC out voltage (120.0V)
        20: 1200,
        # AC out current (8.33A)
        21: 833,
        # AC out power (1000W)
        22: 1000,
        # SOC
        30: 85,
        # Charge state (2 = Absorption)
        31: 2,
        # AC in voltage
        40: 1200,
        # AC in current
        41: 417,
        # AC in connected
        42: 1,
    }
    return registers


if __name__ == "__main__":
    # Quick test of the mock device
    print("Starting Samlex mock device...")

    mock = SamlexMockDevice()
    port = mock.start()

    print(f"Mock device running on: {port}")
    print(f"Connect with: port='{port}', baudrate=9600, slave=1")
    print("")
    print("Register values:")
    for addr, val in sorted(mock._registers.items()):
        print(f"  Address {addr}: {val}")

    print("")
    print("Press Ctrl+C to stop...")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping...")
        mock.stop()
        print("Done.")
