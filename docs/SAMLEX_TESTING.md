# Samlex EVO Testing Guide

This guide covers all testing options for the Samlex EVO series driver, from quick D-Bus testing to full Modbus protocol validation.

## Overview

| Type | Hardware | Modbus | Use Case |
|------|----------|--------|----------|
| `SamlexMock` | ❌ No | ❌ None | Quick D-Bus/GUI testing |
| `SamlexTCP` | ❌ No | ✅ TCP | Protocol stack testing |
| `Samlex` | ✅ Yes | ✅ RTU | Production with real inverter |

---

## SamlexMock - Zero Setup Testing

The fastest way to test Samlex EVO integration. Generates synthetic data without any Modbus communication.

### Usage

**config.ini:**
```ini
[INVERTER]
TYPE=SamlexMock
MAX_AC_POWER=4000
PHASE=L1
POSITION=1
POLL_INTERVAL=1000
```

**Run:**
```bash
# Port argument is ignored for SamlexMock
python dbus-serialinverter.py /dev/null
# or
python dbus-serialinverter.py /dev/ttyUSB0
```

### What It Simulates

SamlexMock generates realistic EVO-4024 data internally - **no register addresses are used**.
Data is computed directly in Python:

| Parameter | Value Range | Notes |
|-----------|-------------|-------|
| AC Output Voltage | 118-122V | Sine wave variation |
| AC Output Power | 1000-3000W | Cycles over 60 seconds |
| DC Voltage | ~26.4V | 24V nominal |
| DC Current | -15A to +7A | Negative = discharging |
| SOC | 0-100% | Slowly changes |
| AC Input | Connected/Disconnected | Toggles every 5 minutes |
| Charge State | Absorption/Inverting | Follows AC input |
| Status | 7/8/10 | Running/Standby/Error |

### D-Bus Service

SamlexMock registers as: `com.victronenergy.vebus.ttyUSB0` (or your port name)

Published paths (same as real Samlex):
- `/Ac/Out/L1/V` - AC output voltage
- `/Ac/Out/L1/I` - AC output current
- `/Ac/Out/L1/P` - AC output power
- `/Ac/ActiveIn/L1/V` - AC input voltage
- `/Ac/ActiveIn/Connected` - AC input status
- `/Dc/0/Voltage` - Battery voltage
- `/Dc/0/Current` - Battery current
- `/Soc` - State of charge
- `/State` - Inverter status (7=Running, 8=Standby, 10=Error)
- `/VebusChargeState` - Charger state

### When to Use

✅ Testing VenusOS GUI integration
✅ Testing VRM portal data flow
✅ Testing D-Bus path publishing
✅ CI/CD automated testing
✅ Development without hardware
✅ Quick smoke tests

### Logs

```bash
# Watch synthetic data generation
tail -f /var/log/dbus-serialinverter.ttyUSB0/current

# Expected output:
# SamlexMock: status=7, AC=1500W, DC=26.4V/3.2A, SOC=85.2%
```

---

## SamlexTCP - Protocol Testing

Tests the full Modbus TCP stack. Requires running a TCP server alongside the driver.

> **NOTE:** The TCP server uses **PLACEHOLDER register addresses (4000-4150 range)** for testing.
> These do NOT match real Samlex addresses (which are NDA-protected).
> Use `config.ini.samlexTCP` which has the matching placeholder addresses.

### Usage

**Quick Start (on your Pi):**

```bash
# Terminal 1: Start the TCP server
python tests/samlex_tcp_server.py --port 5020

# Terminal 2: Use the TCP test config
cd etc/dbus-serialinverter
cp config.ini.samlexTCP config.ini

# Run driver against TCP server
python dbus-serialinverter.py tcp://localhost:5020
```

The `config.ini.samlexTCP` file contains placeholder register addresses that match the test server.

### Manual Setup

**Terminal 1 - Start TCP Server:**
```bash
python tests/samlex_tcp_server.py --port 5020
```

**Terminal 2 - Use TCP Test Config:**
```bash
cp etc/dbus-serialinverter/config.ini.samlexTCP etc/dbus-serialinverter/config.ini
python dbus-serialinverter.py tcp://localhost:5020
```

Or use shorthand:
```bash
python dbus-serialinverter.py localhost:5020
```

### TCP Server Options

```bash
# Basic usage
python tests/samlex_tcp_server.py

# Custom port
python tests/samlex_tcp_server.py --port 15020

# Different model identity
python tests/samlex_tcp_server.py --identity 8722  # EVO-2212

# Test scenarios
python tests/samlex_tcp_server.py --scenario fault
python tests/samlex_tcp_server.py --scenario low_battery
python tests/samlex_tcp_server.py --scenario ac_disconnect
python tests/samlex_tcp_server.py --scenario heavy_load

# Verbose logging
python tests/samlex_tcp_server.py -v
```

### Scenarios

| Scenario | Effect |
|----------|--------|
| `normal` | Standard operation (default) |
| `fault` | Sets fault register, status becomes VE.Bus state 2 (Fault) |
| `low_battery` | Low SOC (15%), high discharge current |
| `ac_disconnect` | AC input disconnected, inverting mode |
| `heavy_load` | High power output (3800W) |

### When to Use

✅ Testing Modbus TCP client implementation
✅ Testing error handling and timeouts
✅ Testing register batch reading
✅ Testing TCP connection management
✅ Protocol conformance validation
✅ Network failure simulation
✅ Testing on Raspberry Pi without serial hardware

### Config File for TCP Testing

Use `config.ini.samlexTCP` when testing with the TCP server:

```bash
# On your Pi:
cp etc/dbus-serialinverter/config.ini.samlexTCP etc/dbus-serialinverter/config.ini
```

This config file contains:
- `TYPE=SamlexTCP` (required for tcp:// URLs; leaving TYPE empty will auto-select SamlexTCP when using a tcp:// port)
- Placeholder register addresses (4000-4150 range) that match the test server
- Example scale factors

**Important:** These are NOT real Samlex addresses - they only work with the test server!

### Architecture

```
dbus-serialinverter.py
    └── ModbusTcpClient
        └── TCP socket (localhost:5020)
            └── samlex_tcp_server.py
                └── ModbusTcpServer
                    └── synthetic register data
```

---

## Samlex (Production)

The real driver for physical Samlex EVO hardware.

### Prerequisites

1. RS485-to-USB adapter connected
2. Samlex EVO powered on
3. `config.ini.private` with register map

### Usage

**config.ini:**
```ini
[INVERTER]
TYPE=Samlex
ADDRESS=1
POLL_INTERVAL=1000
MAX_AC_POWER=4000
PHASE=L1
POSITION=1
```

**config.ini.private:**
```ini
[SAMLEX_REGISTERS]
REG_AC_OUT_VOLTAGE    = 11    # Your actual register from NDA doc
REG_AC_OUT_CURRENT    = 12
# ... etc
```

**Run:**
```bash
python dbus-serialinverter.py /dev/ttyUSB0
```

---

## Testing Workflows

### Workflow 1: Quick D-Bus Test (SamlexMock)

```bash
# 1. Edit config
sudo nano /etc/dbus-serialinverter/config.ini
# Change: TYPE=SamlexMock

# 2. Restart driver
sudo svc -t /service/dbus-serialinverter.ttyUSB0

# 3. Watch logs
tail -f /var/log/dbus-serialinverter.ttyUSB0/current

# 4. Check D-Bus
dbus-spy
# Look for: com.victronenergy.vebus.ttyUSB0
```

### Workflow 2: Protocol Test (SamlexTCP)

```bash
# Terminal 1: Start server
python tests/samlex_tcp_server.py --scenario fault

# Terminal 2: Connect driver
python dbus-serialinverter.py tcp://localhost:5020

# Terminal 3: Monitor
dbus-spy
# Watch status change to VE.Bus state 2 (Fault) due to fault scenario
```

### Workflow 3: Hardware Validation

```bash
# 1. Connect RS485 adapter to Samlex EVO
# 2. Verify config.ini.private exists with real values
ls -la /etc/dbus-serialinverter/config.ini.private

# 3. Test connection
python -c "
from pymodbus.client import ModbusSerialClient
c = ModbusSerialClient(port='/dev/ttyUSB0', baudrate=9600)
c.connect()
r = c.read_input_registers(address=0, count=1, slave=1)
print(f'Identity register: {r.registers}')
"

# 4. Run driver
python dbus-serialinverter.py /dev/ttyUSB0
```

---

## Config Files Reference

| Config File | Use With | Description |
|-------------|----------|-------------|
| `config.ini` (template) | Any | Template with `???` placeholders |
| `config.ini.samlexTCP` | SamlexTCP | Placeholder addresses for TCP testing |
| `config.ini.private` | Samlex (real) | Your real NDA-protected register values |

### Quick Config Switch

```bash
# For TCP testing:
cp etc/dbus-serialinverter/config.ini.samlexTCP etc/dbus-serialinverter/config.ini

# For real hardware:
cp etc/dbus-serialinverter/config.ini.private etc/dbus-serialinverter/config.ini

# For SamlexMock (no registers needed):
# Just set TYPE=SamlexMock in config.ini
```

## Comparison Matrix

| Aspect | SamlexMock | SamlexTCP | Samlex |
|--------|------------|-----------|--------|
| **Setup Time** | Seconds | Minutes | Hours (wiring) |
| **External Dependencies** | None | TCP server | Physical inverter |
| **Modbus Protocol** | None | TCP | RTU (serial) |
| **D-Bus Realism** | ✅ Full | ✅ Full | ✅ Full |
| **Network Testing** | ❌ | ✅ | ❌ (serial) |
| **Error Injection** | ❌ | ✅ | Physical only |
| **CI/CD Suitable** | ✅ Yes | ✅ Yes | ❌ No |
| **VRM Portal Testing** | ✅ Yes | ✅ Yes | ✅ Yes |
| **Config Needed** | Minimal (no registers) | config.ini.samlexTCP | config.ini.private |

---

## Troubleshooting

### SamlexMock: "Type not found"

```bash
# Ensure samlex_mock.py is in the driver directory
ls -la etc/dbus-serialinverter/samlex_mock.py

# Check dbus-serialinverter.py imports it
grep "samlex_mock" etc/dbus-serialinverter/dbus-serialinverter.py
```

### SamlexTCP: "Connection refused"

```bash
# Verify server is running
lsof -i :5020

# Try different port
python tests/samlex_tcp_server.py --port 15020
python dbus-serialinverter.py tcp://localhost:15020
```

### Samlex: "Identity mismatch"

```bash
# Check your IDENTITY_VALUE in config.ini.private
grep IDENTITY_VALUE etc/dbus-serialinverter/config.ini.private

# Read actual value from inverter
python -c "
from pymodbus.client import ModbusSerialClient
c = ModbusSerialClient(port='/dev/ttyUSB0', baudrate=9600)
c.connect()
r = c.read_input_registers(address=<REG_IDENTITY>, count=1, slave=1)
print(f'Actual identity: {r.registers[0]}')  # Match this in config
"
```

---

## Quick Reference

### Config Types

```ini
[INVERTER]
# Quick D-Bus testing
TYPE=SamlexMock

# Protocol testing (with TCP server)
TYPE=SamlexTCP  # or leave TYPE empty and use tcp:// URL for auto-detect

# Production hardware
TYPE=Samlex
```

### Command Lines

```bash
# SamlexMock - zero setup
python dbus-serialinverter.py /dev/null

# SamlexTCP - requires server
python tests/samlex_tcp_server.py &
python dbus-serialinverter.py tcp://localhost:5020

# Samlex - requires hardware + config.private
python dbus-serialinverter.py /dev/ttyUSB0
```

### Log Locations

```bash
# VenusOS / Raspberry Pi
tail -f /var/log/dbus-serialinverter.ttyUSB0/current

# Local development
# Logs to stdout unless redirected
python dbus-serialinverter.py /dev/null 2>&1 | tee samlex.log
```

---

## See Also

- `docs/samlex.md` - Full Samlex EVO driver documentation
- `tests/README_INTEGRATION_TESTS.md` - Automated testing guide
- `etc/dbus-serialinverter/config.ini` - Configuration template
