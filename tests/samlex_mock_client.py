# -*- coding: utf-8 -*-
"""Mock ModbusSerialClient for Samlex integration testing.

This provides a simpler approach than a full Modbus server - it mocks the
pymodbus client to return pre-configured values based on register address.

Usage:
    from samlex_mock_client import MockModbusClient, MockModbusResponse

    # Create mock with register values
    registers = {
        0: 16420,    # Identity (EVO-4024)
        10: 264,     # DC voltage raw
        20: 1200,    # AC out voltage raw
    }
    mock_client = MockModbusClient(registers=registers)

    # Use with Samlex driver
    samlex = Samlex.__new__(Samlex)
    samlex.client = mock_client
"""

from typing import Dict, Optional, Set, List, Any


class MockModbusResponse:
    """Mock response object that mimics pymodbus response."""

    def __init__(self, registers: Optional[List[int]] = None, is_error: bool = False):
        """Create a mock response.

        Args:
            registers: List of register values
            is_error: Whether this response represents an error
        """
        self.registers = registers or []
        self._is_error = is_error

    def isError(self) -> bool:
        """Return True if this is an error response."""
        return self._is_error


class MockModbusClient:
    """Mock ModbusSerialClient for testing without real hardware.

    Simulates a Modbus RTU device by returning pre-configured register values
    based on the requested address. Supports:
    - Configurable register values
    - Simulated read failures
    - Connection state tracking
    - Call history for verification
    """

    def __init__(self, registers: Optional[Dict[int, int]] = None,
                 fail_addresses: Optional[Set[int]] = None,
                 raise_on_connect: Optional[Exception] = None):
        """Initialize the mock client.

        Args:
            registers: Dict mapping register addresses to values
            fail_addresses: Set of addresses that should return errors
            raise_on_connect: Exception to raise when connect() is called
        """
        self._registers = dict(registers) if registers else {}
        self._fail_addresses = set(fail_addresses) if fail_addresses else set()
        self._raise_on_connect = raise_on_connect
        self._connected = False
        self._call_history: List[Dict[str, Any]] = []

    # -------------------------------------------------------------------------
    # ModbusSerialClient interface
    # -------------------------------------------------------------------------

    def connect(self) -> bool:
        """Simulate connection establishment."""
        if self._raise_on_connect:
            raise self._raise_on_connect
        self._connected = True
        return True

    def close(self) -> None:
        """Simulate connection close."""
        self._connected = False

    def is_socket_open(self) -> bool:
        """Return connection state."""
        return self._connected

    def read_input_registers(self, address: int = 0, count: int = 1,
                             slave: int = 1) -> MockModbusResponse:
        """Simulate reading input registers (function code 04).

        Args:
            address: Starting register address
            count: Number of registers to read
            slave: Modbus slave address (ignored in mock)

        Returns:
            MockModbusResponse with register values or error
        """
        # Record call
        call_record = {
            "method": "read_input_registers",
            "address": address,
            "count": count,
            "slave": slave
        }
        self._call_history.append(call_record)

        # Check if any address in range should fail
        read_addresses = set(range(address, address + count))
        if self._fail_addresses & read_addresses:
            return MockModbusResponse(registers=[], is_error=True)

        # Build response values
        values = []
        for addr in range(address, address + count):
            values.append(self._registers.get(addr, 0))

        return MockModbusResponse(registers=values, is_error=False)

    def write_registers(self, address: int, values: List[int],
                        slave: int = 1) -> MockModbusResponse:
        """Simulate writing holding registers.

        Args:
            address: Starting register address
            values: Values to write
            slave: Modbus slave address (ignored in mock)

        Returns:
            MockModbusResponse indicating success
        """
        self._call_history.append({
            "method": "write_registers",
            "address": address,
            "values": values,
            "slave": slave
        })

        # Update stored registers
        for i, val in enumerate(values):
            self._registers[address + i] = val

        return MockModbusResponse(registers=[], is_error=False)

    # -------------------------------------------------------------------------
    # Mock-specific methods
    # -------------------------------------------------------------------------

    def set_register(self, address: int, value: int) -> None:
        """Set a register value dynamically.

        Args:
            address: Register address
            value: Register value (0-65535)
        """
        self._registers[address] = value

    def get_register(self, address: int) -> int:
        """Get current register value."""
        return self._registers.get(address, 0)

    def add_fail_address(self, address: int) -> None:
        """Add an address that should return errors."""
        self._fail_addresses.add(address)

    def remove_fail_address(self, address: int) -> None:
        """Remove an address from the failure set."""
        self._fail_addresses.discard(address)

    def clear_failures(self) -> None:
        """Clear all configured failure addresses."""
        self._fail_addresses.clear()

    def get_call_history(self) -> List[Dict[str, Any]]:
        """Return the call history for verification."""
        return list(self._call_history)

    def clear_call_history(self) -> None:
        """Clear the call history."""
        self._call_history.clear()


# ------------------------------------------------------------------------------
# Pre-configured register maps for testing
# ------------------------------------------------------------------------------

def create_evo_4024_registers() -> Dict[int, int]:
    """Create a realistic register map for EVO-4024 @ 24V.

    These values simulate a healthy inverter with:
    - AC input connected (shore power)
    - Battery charging at 26.4V, 5.2A
    - AC output at 120V, 8.33A, 1000W
    - SOC at 85%
    - No faults

    Returns:
        Dict mapping register addresses to raw values
    """
    return {
        # Identity register (EVO-4024 = 0x4024 = 16420)
        0: 16420,
        # Working status: 1 = AC input normal
        1: 1,
        # Fault: 0 = no fault
        2: 0,
        # DC voltage: 264 raw × 0.1 = 26.4V
        10: 264,
        # DC current: 520 raw × 0.01 = 5.2A (charging)
        11: 520,
        # AC output voltage: 1200 raw × 0.1 = 120.0V
        20: 1200,
        # AC output current: 833 raw × 0.01 = 8.33A
        21: 833,
        # AC output power: 1000 raw × 1.0 = 1000W
        22: 1000,
        # SOC: 85% (no scaling)
        30: 85,
        # Charge state: 2 = Absorption
        31: 2,
        # AC input voltage: 1200 raw × 0.1 = 120.0V
        40: 1200,
        # AC input current: 417 raw × 0.01 = 4.17A
        41: 417,
        # AC input connected: 1 = yes
        42: 1,
    }


def create_evo_2212_registers() -> Dict[int, int]:
    """Create a register map for EVO-2212 @ 12V.

    Returns:
        Dict mapping register addresses to raw values
    """
    return {
        # Identity register (EVO-2212 = 0x2212 = 8722)
        0: 8722,
        # Working status: 3 = Inverting
        1: 3,
        # Fault: 0 = no fault
        2: 0,
        # DC voltage: 132 raw × 0.1 = 13.2V
        10: 132,
        # DC current: 2000 raw × 0.01 = 20.0A (discharging, but positive in raw)
        11: 2000,
        # AC output voltage: 1200 raw × 0.1 = 120.0V
        20: 1200,
        # AC output current: 1500 raw × 0.01 = 15.0A
        21: 1500,
        # AC output power: 1800 raw × 1.0 = 1800W
        22: 1800,
        # SOC: 45%
        30: 45,
        # Charge state: 9 = Inverting
        31: 9,
        # AC input voltage: 0 (not connected)
        40: 0,
        # AC input current: 0
        41: 0,
        # AC input connected: 0 = no
        42: 0,
    }


# ------------------------------------------------------------------------------
# Scenario helpers
# ------------------------------------------------------------------------------

class SamlexScenario:
    """Helper class for creating test scenarios."""

    @staticmethod
    def fault_condition(registers: Dict[int, int], fault_code: int = 1) -> Dict[int, int]:
        """Modify registers to simulate a fault condition."""
        result = dict(registers)
        result[2] = fault_code  # Set fault register
        return result

    @staticmethod
    def low_battery(registers: Dict[int, int], soc: int = 15) -> Dict[int, int]:
        """Modify registers to simulate low battery."""
        result = dict(registers)
        result[30] = soc
        return result

    @staticmethod
    def ac_input_disconnected(registers: Dict[int, int]) -> Dict[int, int]:
        """Modify registers to simulate AC input disconnected."""
        result = dict(registers)
        result[42] = 0  # AC in connected = 0
        result[40] = 0  # AC in voltage = 0
        result[41] = 0  # AC in current = 0
        result[1] = 3   # Working status = Inverting
        return result

    @staticmethod
    def heavy_load(registers: Dict[int, int], power: int = 3800) -> Dict[int, int]:
        """Modify registers to simulate heavy load."""
        result = dict(registers)
        result[22] = power
        # Recalculate current based on power/voltage
        if result[20] > 0:
            voltage = result[20] * 0.1  # scaled voltage
            current_amps = power / voltage
            result[21] = int(current_amps * 100)  # scale back to raw
        return result


# ------------------------------------------------------------------------------
# Convenience factory functions
# ------------------------------------------------------------------------------

def create_mock_client_evo_4024(scenario: str = "normal") -> MockModbusClient:
    """Create a mock client configured for EVO-4024.

    Args:
        scenario: One of "normal", "fault", "low_battery", "ac_disconnect", "heavy_load"

    Returns:
        Configured MockModbusClient
    """
    registers = create_evo_4024_registers()

    if scenario == "fault":
        registers = SamlexScenario.fault_condition(registers)
    elif scenario == "low_battery":
        registers = SamlexScenario.low_battery(registers)
    elif scenario == "ac_disconnect":
        registers = SamlexScenario.ac_input_disconnected(registers)
    elif scenario == "heavy_load":
        registers = SamlexScenario.heavy_load(registers)
    elif scenario != "normal":
        raise ValueError(f"Unknown scenario: {scenario}")

    return MockModbusClient(registers=registers)


if __name__ == "__main__":
    # Quick test
    print("Testing MockModbusClient...")

    client = create_mock_client_evo_4024()

    print(f"Connected: {client.is_socket_open()}")
    client.connect()
    print(f"Connected after connect(): {client.is_socket_open()}")

    # Read identity
    resp = client.read_input_registers(address=0, count=1)
    print(f"Read identity: {resp.registers}")
    print(f"Is error: {resp.isError()}")

    # Read batch
    resp = client.read_input_registers(address=10, count=3)
    print(f"Read addresses 10-12: {resp.registers}")

    # Test failure simulation
    client.add_fail_address(20)
    resp = client.read_input_registers(address=20, count=1)
    print(f"Read address 20 (should fail): isError={resp.isError()}")

    print("Call history:")
    for call in client.get_call_history():
        print(f"  {call}")

    print("\nMockModbusClient test complete!")
