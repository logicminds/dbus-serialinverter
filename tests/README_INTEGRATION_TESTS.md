# Samlex EVO Integration Tests

This directory contains comprehensive integration tests for the Samlex EVO series driver using multiple approaches:

1. **Mock Modbus client** - Fast, automated testing without hardware
2. **TCP Modbus server** - True Modbus protocol testing over TCP
3. **Real Samlex EVO hardware** - Validation against actual inverter

## Quick Start

```bash
# Run mock client tests (fastest, no server needed)
python tests/test_samlex_integration.py

# Run TCP integration tests (true Modbus protocol)
# Uses config.ini.samlexTCP for placeholder register addresses
python tests/test_samlex_tcp_integration.py

# Run with real hardware (requires Samlex EVO connected)
python tests/test_samlex_integration.py --real-device /dev/ttyUSB0
```

## Test File Overview

| File | Purpose |
|------|---------|
| `test_samlex_integration.py` | Mock client integration tests (14 tests) |
| `test_samlex_tcp_integration.py` | TCP Modbus server tests (9 tests) |
| `samlex_mock_client.py` | Mock Modbus client for testing without hardware |
| `samlex_tcp_server.py` | Modbus TCP server that simulates a real inverter |
| `samlex_mock_device.py` | PTY-based mock (deprecated, kept for reference) |

## Config Files for Testing

| Config File | Use With | Description |
|-------------|----------|-------------|
| `config.ini` (template) | Any | Production template with `???` placeholders |
| `config.ini.samlexTCP` | SamlexTCP | Placeholder register addresses for TCP testing (4000-4150 range) |
| `config.ini.private` | Samlex (real) | Your real NDA-protected register values - never commit this |

### Using config.ini.samlexTCP

```bash
# For testing with TCP server:
cp etc/dbus-serialinverter/config.ini.samlexTCP etc/dbus-serialinverter/config.ini.private

# Start TCP server
python tests/samlex_tcp_server.py --port 5020

# Run driver
python dbus-serialinverter.py tcp://localhost:5020
```

The `config.ini.samlexTCP` file contains placeholder register addresses that match
the test server. These are NOT real Samlex addresses - they only work with the test server!

## Approach 1: Mock Client Tests (Recommended for CI)

The mock client intercepts Modbus calls and returns pre-configured values.

```bash
# Run all mock client tests
python tests/test_samlex_integration.py

# Run specific scenario
python tests/test_samlex_integration.py --scenario fault
python tests/test_samlex_integration.py --scenario ac_disconnect
python tests/test_samlex_integration.py --scenario low_battery
python tests/test_samlex_integration.py --scenario heavy_load

# Verbose output
python tests/test_samlex_integration.py -v
```

### Scenarios

| Scenario | Description |
|----------|-------------|
| `normal` | Standard operation (default) |
| `fault` | Simulates inverter fault condition |
| `low_battery` | Low SOC (15%) |
| `ac_disconnect` | AC input disconnected, running on battery |
| `heavy_load` | High power output (3800W) |

## Approach 2: TCP Modbus Tests (True Protocol)

Runs a real Modbus TCP server that the driver connects to. This tests the actual Modbus protocol implementation.

```bash
# Run TCP tests (auto-starts server)
python tests/test_samlex_tcp_integration.py

# Connect to existing server
python tests/test_samlex_tcp_integration.py --server localhost:5020

# Different scenario
python tests/test_samlex_tcp_integration.py --scenario fault

# Custom port
python tests/test_samlex_tcp_integration.py --port 15020
```

### Running TCP Server Manually

```bash
# Start the TCP server
python tests/samlex_tcp_server.py

# Or with options
python tests/samlex_tcp_server.py --port 15020 --identity 8722 --scenario fault
```

**Using with Driver (requires config.ini.samlexTCP):**

```bash
# 1. Copy the TCP test config (has matching placeholder addresses)
cp etc/dbus-serialinverter/config.ini.samlexTCP etc/dbus-serialinverter/config.ini

# 2. Run the driver
python dbus-serialinverter/dbus-serialinverter.py tcp://localhost:5020
```

The `config.ini.samlexTCP` file contains placeholder register addresses (4000-4150 range)
that match the test server. These are NOT real Samlex addresses - they only work with
the TCP test server for protocol testing!

## Approach 3: Real Hardware Testing

### Prerequisites

1. Samlex EVO inverter connected via RS485-to-USB adapter
2. Inverter powered on and communicating
3. `config.ini.private` populated with your register map

### Configuration

Before testing with real hardware, ensure your private config is complete:

```ini
# etc/dbus-serialinverter/config.ini.private
[INVERTER]
TYPE=Samlex
MAX_AC_POWER=4000

[SAMLEX_REGISTERS]
REG_IDENTITY=0
IDENTITY_VALUE=16420
# ... all other registers from your Modbus guide
```

### Running Hardware Tests

```bash
# Run mock client tests against real hardware
python tests/test_samlex_integration.py --real-device /dev/ttyUSB0 --identity 16420 -v

# Or use TCP if you have a TCP-to-RS485 gateway
python tests/test_samlex_tcp_integration.py --server gateway-ip:502
```

## Test Coverage

### Mock Client Tests (14 tests)

| Test | Description |
|------|-------------|
| `test_connection` | Identity register verification |
| `test_get_settings` | Configuration loading |
| `test_refresh_data_basic` | Single poll cycle |
| `test_ac_output_values` | AC voltage/current/power scaling |
| `test_dc_battery_values` | DC voltage/current/SOC reading |
| `test_ac_input_values` | AC input (shore power) reading |
| `test_status_mapping` | Fault → status code mapping |
| `test_charge_state` | Charger state register |
| `test_multiple_poll_cycles` | Stability over multiple polls |
| `test_energy_data_structure` | Data structure validation |
| `test_fault_condition` | Simulated fault detection |
| `test_ac_input_disconnect` | AC input loss handling |
| `test_register_read_failure` | Error handling on read failures |
| `test_mock_client_call_history` | Verify all Modbus calls |

### TCP Modbus Tests (9 tests)

| Test | Description |
|------|-------------|
| `test_tcp_connection` | TCP mode detection |
| `test_identity_verification` | Identity register over TCP |
| `test_get_settings` | Settings load over TCP |
| `test_refresh_data` | Full poll cycle over TCP |
| `test_ac_output_values` | AC values via TCP |
| `test_dc_battery_values` | DC values via TCP |
| `test_ac_input_values` | AC input via TCP |
| `test_status_mapping` | Status via TCP |
| `test_multiple_polls` | Multiple polls via TCP |

## Using the Mock Client in Your Tests

```python
from samlex_mock_client import MockModbusClient, create_evo_4024_registers
from samlex import Samlex

# Create mock with default EVO-4024 registers
registers = create_evo_4024_registers()
mock_client = MockModbusClient(registers=registers)

# Create driver and inject mock
samlex = Samlex.__new__(Samlex)
samlex.client = mock_client

# Use driver normally
samlex.test_connection()
samlex.get_settings()
samlex.refresh_data()

# Verify calls were made
print(mock_client.get_call_history())

# Simulate failures
mock_client.add_fail_address(20)  # Make register 20 fail
result = samlex.refresh_data()  # Returns False (read failed)
```

## Using the TCP Server

```python
from samlex_tcp_server import SamlexModbusServer
from samlex_tcp import SamlexTCP

# Start server
server = SamlexModbusServer(host="localhost", port=5020, scenario="fault")
server.start(blocking=False)

# Connect driver
samlex = SamlexTCP("tcp://localhost:5020", slave=1)
samlex.test_connection()

# Clean up
server.stop()
```

## Expected Register Values

The mock/TCP server uses these default values for EVO-4024:

| Register | Address | Raw Value | Scaled Value |
|----------|---------|-----------|--------------|
| Identity | 0 | 16420 | EVO-4024 |
| DC Voltage | 10 | 264 | 26.4V |
| DC Current | 11 | 520 | 5.2A |
| AC Out Voltage | 20 | 1200 | 120.0V |
| AC Out Current | 21 | 833 | 8.33A |
| AC Out Power | 22 | 1000 | 1000W |
| SOC | 30 | 85 | 85% |
| Charge State | 31 | 2 | Absorption |
| AC In Voltage | 40 | 1200 | 120.0V |
| AC In Current | 41 | 417 | 4.17A |
| AC In Connected | 42 | 1 | Yes |
| Fault | 2 | 0 | No fault |

## Troubleshooting

### Mock client tests fail

```bash
# Check Python path
python -c "import sys; print(sys.path)"

# Verify imports work
python -c "from samlex_mock_client import MockModbusClient; print('OK')"
```

### TCP tests fail to connect

```bash
# Check if port is available
lsof -i :5020

# Use different port
python tests/test_samlex_tcp_integration.py --port 15020
```

### Hardware tests fail to connect

1. Verify port exists: `ls -la /dev/ttyUSB*`
2. Check permissions: `sudo usermod -aG dialout $USER` (then re-login)
3. Test with pymodbus directly
4. Verify `config.ini.private` is complete

### Identity mismatch

Identity values differ by model:

| Model | Identity Value (hex) | Identity Value (decimal) |
|-------|---------------------|--------------------------|
| EVO-2212 | 0x2212 | 8722 |
| EVO-2224 | 0x2224 | 8740 |
| EVO-4024 | 0x4024 | 16420 |
| EVO-4048 | 0x4048 | 16584 |

Use `--identity` flag to match your model:

```bash
python tests/test_samlex_integration.py --identity 8722
```

## Continuous Integration

The mock client tests can run in CI without hardware:

```yaml
# Example GitHub Actions
- name: Run Samlex Integration Tests
  run: |
    python tests/test_samlex_integration.py
    python tests/test_samlex_integration.py --scenario fault
    python tests/test_samlex_integration.py --scenario ac_disconnect

- name: Run TCP Modbus Tests
  run: |
    python tests/test_samlex_tcp_integration.py
    python tests/test_samlex_tcp_integration.py --scenario fault
```

## Summary

| Approach | Speed | Hardware | Modbus Protocol | Best For |
|----------|-------|----------|-----------------|----------|
| Mock Client | Fast | No | Simulated | CI, unit testing |
| TCP Server | Medium | No | Real | Protocol validation |
| Real Hardware | Slow | Yes | Real | End-to-end validation |
