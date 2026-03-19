# Samlex EVO Series Driver

VenusOS D-Bus driver for Samlex EVO series multi-mode inverter/chargers over Modbus RTU (RS485).

Tested against the EVO-4024 (24 V, 4000 W). Other EVO models share the same Modbus register map and work with only a few config changes. See [Supported Models](#supported-models).

---

## Supported Models

All models in the Samlex EVO series use the same Modbus register addresses. The driver tells them apart at runtime using the identity register. The battery voltage of the unit determines the expected DC voltage range on D-Bus and must be matched by your physical battery bank.

### Reading the model number

The EVO model number directly encodes both the rated power and the battery system voltage:

```
EVO - 40 24
      │   └─ battery voltage: 12, 24, or 48 V
      └───── rated power class: 22 = 2200 W, 40 = 4000 W
```

So for an **EVO-4024**: the last two digits are `24` → 24 V battery system. For an **EVO-2212**: last two digits are `12` → 12 V battery system. You can always read the required battery voltage straight off the model number without consulting any datasheet.

| Model | Battery voltage | Rated power | `MAX_AC_POWER` | Expected DC range | `IDENTITY_VALUE` |
|-------|-----------------|-------------|----------------|-------------------|------------------|
| EVO-2212 | **12 V** | 2200 W | `2200` | 10–15 V | *(from guide)* |
| EVO-2224 | **24 V** | 2200 W | `2200` | 20–30 V | *(from guide)* |
| EVO-4024 | **24 V** | 4000 W | `4000` | 20–30 V | *(from guide)* |
| EVO-4048 | **48 V** | 4000 W | `4000` | 40–60 V | *(from guide)* |

**Battery voltage is fixed by the model** — the EVO-4024 is a 24 V unit and must be paired with a 24 V battery bank. You cannot use it with a 12 V or 48 V bank. The driver does not enforce this; it simply publishes whatever DC voltage the inverter reports. If your `/Dc/0/Voltage` reading looks wrong, verify the model matches your battery bank voltage.

`IDENTITY_VALUE` is the model-specific integer returned by `REG_IDENTITY`. Find both the register address and the expected value for your model in the Samlex Modbus Protocol Guide (see [Getting the Register Map](#getting-the-register-map)).

### Adjusting config for your model

Three settings in `config.ini` must match your specific unit:

| Setting | Where | What to set |
|---------|-------|-------------|
| `MAX_AC_POWER` | `[INVERTER]` | Rated output watts — `2200` for EVO-22xx, `4000` for EVO-40xx |
| `IDENTITY_VALUE` | `[SAMLEX_REGISTERS]` | Model-specific ID from the Modbus Protocol Guide |
| `SCALE_DC_VOLTAGE` | `[SAMLEX_REGISTERS]` | Scale factor from the guide — verify by checking that `/Dc/0/Voltage` on D-Bus reads close to your known battery voltage |

The battery voltage itself is read from the inverter and published directly to D-Bus — there is no "system voltage" setting in the driver. Use the expected DC range in the table above to sanity-check that the register address and scale factor are correct for your unit.

---

## Table of Contents

1. [Supported Models](#supported-models)
2. [Hardware Setup](#hardware-setup)
3. [Getting the Register Map](#getting-the-register-map)
4. [Configuration](#configuration)
5. [Register Map Reference](#register-map-reference)
6. [D-Bus Paths](#d-bus-paths)
7. [Status and Charger State Codes](#status-and-charger-state-codes)
8. [How the Driver Works](#how-the-driver-works)
9. [Troubleshooting](#troubleshooting)

---

## Hardware Setup

### What you need

- **USB-to-RS485 adapter** — a standard FTDI or CH340-based USB-to-RS485 dongle. Any adapter that exposes a `/dev/ttyUSB*` device on Linux will work. Recommended: adapters with terminal block screw connectors for reliable wiring (e.g., DSD TECH SH-U10, DTECH DT-5019, or similar).
- **RS485 cable** — twisted-pair wire (e.g., Cat5e, Belden 9841, or simple two-conductor twisted pair). Keep it under 10 m where possible; longer runs may require a 120 Ω termination resistor across A and B at the far end.
- **GX device or Raspberry Pi** running VenusOS Large.

### Wiring

The EVO 4024 has an RS485 communication port (refer to your unit's manual for the physical connector type). Connect it to the USB adapter as follows:

```
EVO series                    USB-to-RS485 adapter
────────────────────────────────────────────────────
RS485 A (+)  ──────────────── A (+) / DATA+
RS485 B (−)  ──────────────── B (−) / DATA-
GND          ──────────────── GND  (if adapter has a GND terminal)
```

- Use the **A (+)** and **B (−)** labels on both ends — do not swap them.
- Keep the cable away from power wiring to reduce noise.
- If the connection is unreliable, add a **120 Ω resistor** across A and B at the adapter end.

Plug the USB adapter into a USB port on the GX device or Raspberry Pi. It will appear as `/dev/ttyUSB0` (or `/dev/ttyUSB1` etc. if other adapters are present). Run `ls /dev/ttyUSB*` to confirm.

### Serial parameters (fixed in the driver)

| Parameter | Value |
|-----------|-------|
| Baud rate | 9600  |
| Data bits | 8     |
| Stop bits | 1     |
| Parity    | None  |
| Modbus slave address | 1 (default) |

The slave address can be changed in `config.ini` under `[INVERTER] ADDRESS` if your unit is configured differently.

---

## Getting the Register Map

The EVO series Modbus register addresses are protected by a Samlex NDA and cannot be published in this repository. The driver ships with all register values set to `???` so the code can be shared openly while the actual addresses stay private in your local `config.ini`.

### How to request the guide

Contact Samlex technical support:

| Method | Details |
|--------|---------|
| **Phone** | 604-525-3836 |
| **Email** | techsupport@samlexamerica.com |

**What to say:** Introduce yourself, state your model (e.g., "I have an EVO-4024"), and explain that you are integrating it into a custom monitoring system (e.g., VenusOS on a Victron GX device or Raspberry Pi). Ask for the **"Modbus Communication Protocol Guide"** for the EVO series. The same guide covers all EVO models, so one request covers you even if you later add a second unit of a different voltage. Samlex technical support is generally helpful for legitimate integration requests.

**What to expect:** Samlex may ask you to sign a Non-Disclosure Agreement (NDA) before releasing the register map. This is standard practice — the NDA covers the register addresses and protocol details, not the integration code itself (which is why this driver can be open source). Once signed, they will send the guide as a PDF.

**What the guide contains:** A table of Modbus input register addresses (in hex), their data types (`uint16`, `int16`), scaling factors, and descriptions of each value — exactly what you need to fill in `config.ini`.

### Filling in `config.ini`

Once you have the guide:

1. Open `etc/dbus-serialinverter/config.ini`.
2. In the `[SAMLEX_REGISTERS]` section, replace each `???` with the register address (converted from hex to decimal) or scale factor from the guide.
3. Save the file and restart the driver.

The driver validates all values at startup. As long as any key still reads `???`, the Samlex driver is silently skipped during auto-detection and no Modbus traffic is sent.

---

## Configuration

All configuration lives in `etc/dbus-serialinverter/config.ini`.

### `[INVERTER]` section

```ini
[INVERTER]
TYPE=           # Leave blank for auto-detect, or set to "Samlex" to force it
ADDRESS=1       # Modbus slave address of the inverter (default 1)
POLL_INTERVAL=1000   # How often to poll the inverter, in milliseconds
MAX_AC_POWER=4000    # Rated output power of your EVO model in watts (2200 for EVO-22xx, 4000 for EVO-40xx)
PHASE=L1             # AC phase: L1, L2, or L3
POSITION=1           # 0=AC input 1, 1=AC output, 2=AC input 2
```

### `[SAMLEX_REGISTERS]` section

```ini
[SAMLEX_REGISTERS]
# AC output ── register addresses are decimal integers; scales are float multipliers
REG_AC_OUT_VOLTAGE    = ???   # uint16, AC volts out — e.g. raw 1200 × 0.1 = 120.0 V
REG_AC_OUT_CURRENT    = ???   # uint16, AC amps out  — e.g. raw 150  × 0.1 = 15.0 A
REG_AC_OUT_POWER      = 5     # uint16, AC watts out — e.g. raw 600  × 1.0 = 600 W
SCALE_AC_OUT_VOLTAGE  = ???   # float, e.g. 0.1 or 0.01
SCALE_AC_OUT_CURRENT  = ???   # float, e.g. 0.1 or 0.01
SCALE_AC_OUT_POWER    = 1.0   # float, usually 1.0 (already in watts)

# DC / battery
REG_DC_VOLTAGE        = 1     # uint16, battery volts    — e.g. raw 264 × 0.1 = 26.4 V
REG_DC_CURRENT        = 2     # int16,  battery amps (+charge/-discharge) — e.g. raw 65286 × 0.1 = -25.0 A
REG_SOC               = ???   # uint16, state of charge 0-100 % (no scaling)
SCALE_DC_VOLTAGE      = 0.1   # float, e.g. 0.1
SCALE_DC_CURRENT      = 0.1   # float, e.g. 0.1 (sign handled in code)

# AC input / shore power
REG_AC_IN_VOLTAGE     = 10    # uint16, grid/gen volts  — e.g. raw 120 × 1.0 = 120 V
REG_AC_IN_CURRENT     = ???   # uint16, grid/gen amps   — e.g. raw 30  × 0.1 = 3.0 A
REG_AC_IN_CONNECTED   = ???   # uint16, 1 = connected, 0 = disconnected (no scaling)
SCALE_AC_IN_VOLTAGE   = 1.0   # float, e.g. 1.0 or 0.1
SCALE_AC_IN_CURRENT   = ???   # float, e.g. 0.1 or 0.01

# Status / fault
REG_FAULT             = ???   # uint16, 0 = no fault; any non-zero → Victron status Error (10)
REG_CHARGE_STATE      = 8     # uint16, charger state code → published to /VebusChargeState

# Identity — read by test_connection() to confirm a Samlex EVO is on this port
REG_IDENTITY          = ???   # uint16, register that holds a device model/ID value
IDENTITY_VALUE        = ???   # integer, expected value in REG_IDENTITY for your specific EVO model (differs per model)
```

---

## Register Map Reference

This table describes every key the driver reads from `[SAMLEX_REGISTERS]`. Register addresses are **decimal integers** (convert hex from the Modbus guide: `0x0005` → `5`). Scale factors are **float multipliers** applied to the raw uint16 register value before the result is stored or published.

### AC Output

| Key | Type | Description | Example |
|-----|------|-------------|---------|
| `REG_AC_OUT_VOLTAGE` | Register address | AC voltage on the inverter output (load side) | `0x000B` → `11` |
| `SCALE_AC_OUT_VOLTAGE` | Scale factor | Multiplier to convert raw → volts | `0.1` (raw 1200 → 120.0 V) |
| `REG_AC_OUT_CURRENT` | Register address | AC current drawn by the load, in amps | `0x000C` → `12` |
| `SCALE_AC_OUT_CURRENT` | Scale factor | Multiplier to convert raw → amps | `0.1` (raw 150 → 15.0 A) |
| `REG_AC_OUT_POWER` | Register address | Total AC watts delivered to the load | `0x0005` → `5` |
| `SCALE_AC_OUT_POWER` | Scale factor | Multiplier to convert raw → watts | `1.0` (raw already in watts) |

### DC / Battery

| Key | Type | Description | Example |
|-----|------|-------------|---------|
| `REG_DC_VOLTAGE` | Register address | Battery bank voltage | `0x0001` → `1` |
| `SCALE_DC_VOLTAGE` | Scale factor | Multiplier to convert raw → volts | `0.1` (raw 264 → 26.4 V) |
| `REG_DC_CURRENT` | Register address | Battery current. **int16** — positive = charging, negative = discharging. Raw values > 32767 are two's-complement negatives: `value = raw - 65536` | `0x0002` → `2` |
| `SCALE_DC_CURRENT` | Scale factor | Multiplier applied to the absolute value; sign is handled in code | `0.1` (raw 65286 → −25.0 A) |
| `REG_SOC` | Register address | State of charge, 0–100 %. No scaling applied. | `0x0010` → `16` |

### AC Input (Shore / Generator)

| Key | Type | Description | Example |
|-----|------|-------------|---------|
| `REG_AC_IN_VOLTAGE` | Register address | Voltage on the AC input from grid or generator | `0x000A` → `10` |
| `SCALE_AC_IN_VOLTAGE` | Scale factor | Multiplier to convert raw → volts | `1.0` (raw 120 → 120 V) |
| `REG_AC_IN_CURRENT` | Register address | Current drawn from the AC input, in amps | `0x000D` → `13` |
| `SCALE_AC_IN_CURRENT` | Scale factor | Multiplier to convert raw → amps | `0.1` (raw 30 → 3.0 A) |
| `REG_AC_IN_CONNECTED` | Register address | Whether AC input is present. `1` = connected, `0` = disconnected. No scaling. | `0x0009` → `9` |

### Status and Fault

| Key | Type | Description | Example |
|-----|------|-------------|---------|
| `REG_FAULT` | Register address | Fault/alarm register. `0` = no fault. Any non-zero value triggers Victron status **Error (10)**. | `0x0020` → `32` |
| `REG_CHARGE_STATE` | Register address | Raw charger state code. Published directly to `/VebusChargeState` on D-Bus. See [Charger State Codes](#charger-state-codes) below. | `0x0008` → `8` |

### Identity

| Key | Type | Description | Example |
|-----|------|-------------|---------|
| `REG_IDENTITY` | Register address | A register that holds a fixed device model or product ID value, used to confirm an EVO series inverter is on this port before the driver registers on D-Bus. The same register address is used across all EVO models. | `0x0000` → `0` |
| `IDENTITY_VALUE` | Expected value | The model-specific integer the driver expects to read back from `REG_IDENTITY`. **This differs per EVO model.** Find the value for your unit in the Modbus Protocol Guide. If the register returns anything else, `test_connection()` returns `False` and the port is skipped. | EVO-4024: *(from guide)* |

---

## D-Bus Paths

The Samlex driver registers as `com.victronenergy.vebus.<port>` (e.g., `com.victronenergy.vebus.ttyUSB0`). This is a **vebus** service type, which is required for multi-mode inverter/chargers that expose AC input, battery, and charger state paths. (Grid-tie PV inverters like the Solis use `com.victronenergy.pvinverter` instead.)

### Published paths

| D-Bus path | Source | Notes |
|------------|--------|-------|
| `/State` | `inverter.status` | See [Status Codes](#status-codes) |
| `/Mode` | Fixed `3` | 3 = On (invert + charge) |
| `/VebusChargeState` | `REG_CHARGE_STATE` | See [Charger State Codes](#charger-state-codes) |
| `/Ac/Out/L1/V` | `REG_AC_OUT_VOLTAGE × SCALE_AC_OUT_VOLTAGE` | Volts |
| `/Ac/Out/L1/I` | `REG_AC_OUT_CURRENT × SCALE_AC_OUT_CURRENT` | Amps |
| `/Ac/Out/L1/P` | `REG_AC_OUT_POWER × SCALE_AC_OUT_POWER` | Watts |
| `/Ac/ActiveIn/L1/V` | `REG_AC_IN_VOLTAGE × SCALE_AC_IN_VOLTAGE` | Volts |
| `/Ac/ActiveIn/L1/I` | `REG_AC_IN_CURRENT × SCALE_AC_IN_CURRENT` | Amps |
| `/Ac/ActiveIn/Connected` | `REG_AC_IN_CONNECTED` | 1 = connected, 0 = disconnected |
| `/Dc/0/Voltage` | `REG_DC_VOLTAGE × SCALE_DC_VOLTAGE` | Volts |
| `/Dc/0/Current` | `REG_DC_CURRENT × SCALE_DC_CURRENT` | Amps (negative = discharging) |
| `/Soc` | `REG_SOC` | Percent (0–100) |
| `/UpdateIndex` | Auto-incremented 0–255 | Wraps at 255; consumers use this to detect stale data |
| `/Connected` | Fixed `1` | Set to 1 when driver is running |
| `/DeviceInstance` | VRM instance | Defaults to 257 (vebus range) |
| `/ProductName` | `"SerialInverter (Samlex)"` | |
| `/Serial` | Port basename | e.g., `ttyUSB0` |

### Paths not published (intentionally)

| D-Bus path | Reason |
|------------|--------|
| `/StatusCode` | pvinverter-only path; not part of the vebus schema |
| `/Ac/PowerLimit` | EVO series does not support remote power limit writes over Modbus |
| `/Ac/L1/Voltage` etc. | pvinverter AC paths; vebus uses `/Ac/Out/` and `/Ac/ActiveIn/` instead |

---

## Status and Charger State Codes

### Status codes (`/State`)

The driver maps EVO series fault and power readings to the standard Victron vebus state values:

| `/State` value | Meaning | When set |
|----------------|---------|----------|
| `7` | Running | `REG_FAULT == 0` and AC output power > 0 |
| `8` | Standby | `REG_FAULT == 0` and AC output power == 0 |
| `10` | Error | `REG_FAULT != 0`, or the fault register read failed |

### Charger state codes (`/VebusChargeState`)

The raw value from `REG_CHARGE_STATE` is published directly. The standard Victron charger state values are:

| Value | Meaning |
|-------|---------|
| `0` | Initialising |
| `1` | Bulk |
| `2` | Absorption |
| `3` | Float |
| `4` | Storage |
| `5` | Equalise |
| `9` | Inverting |
| `11` | Power assist |
| `245` | Wake-up |
| `252` | External control |

Refer to the EVO series Modbus Protocol Guide to confirm which values your firmware version uses — they may vary between EVO models or firmware revisions.

---

## How the Driver Works

### Integration architecture

The driver follows the same plugin pattern as all other inverter types in this project:

```
dbus-serialinverter.py          ← entry point, GLib mainloop
    │
    ├── tries each inverter type in order
    │       Solis.test_connection()    → False (wrong device)
    │       Samlex.test_connection()   → True  (EVO series unit found)
    │
    └── DbusHelper(samlex_instance)
            │
            ├── setup_vedbus()          ← registers D-Bus service once
            │       com.victronenergy.vebus.ttyUSB0
            │
            └── every POLL_INTERVAL ms:
                    samlex.refresh_data()   ← reads Modbus registers
                    dbushelper.publish_dbus() ← writes to D-Bus
```

The Samlex driver registers as a **vebus** service (`com.victronenergy.vebus`), not a pvinverter. This is required because all EVO series models are multi-mode inverter/chargers: they have an AC input (shore/generator), a DC bus (battery), and AC output (loads). The vebus schema exposes all three. The pvinverter schema (used by Solis) only handles AC output from a grid-tie PV inverter and has no AC input or battery paths.

### Startup and auto-detection

On startup, `dbus-serialinverter.py` iterates through all registered inverter types and calls `test_connection()` on each. For the Samlex driver this proceeds in two steps:

**Step 1 — Config validation**

Before touching the serial port, the driver checks that every key in `[SAMLEX_REGISTERS]` is present and is a valid number (not `???` or non-numeric). If any key fails, `test_connection()` returns `False` immediately and logs:

```
Samlex: register map not configured, skipping
```

This means the Samlex driver is safely inert when the register map has not been filled in — it does not open the port or interfere with other driver types being tried on the same port.

**Step 2 — Identity probe**

Once the config is valid, the driver opens the serial connection and reads `REG_IDENTITY`. If the returned value matches `IDENTITY_VALUE`, the EVO series unit is confirmed and the driver claims the port. Because each model returns a different identity value, `IDENTITY_VALUE` is also what distinguishes an EVO-4024 from an EVO-2212 or EVO-4048. If the register does not match (e.g., a Solis inverter is on this port instead), `test_connection()` returns `False` and the next driver type is tried.

### D-Bus registration (`setup_vedbus`)

Once `test_connection()` succeeds, `DbusHelper.setup_vedbus()` is called once to:

1. Call `get_settings()` on the inverter to populate model info, phase, max power, and serial number.
2. Register the D-Bus service as `com.victronenergy.vebus.ttyUSB0` (port basename appended).
3. Claim a device instance in the vebus range (default 257) via `SettingsDevice`.
4. Register all vebus D-Bus paths: `/State`, `/Mode`, `/VebusChargeState`, `/Ac/Out/L1/*`, `/Ac/ActiveIn/*`, `/Dc/0/*`, `/Soc`.

After this, the service is visible to VenusOS (and to the VRM portal if connected).

### Poll cycle

Every `POLL_INTERVAL` milliseconds, `DbusHelper.publish_inverter()` is called by the GLib timer:

1. `samlex.refresh_data()` → `read_status_data()` reads each register individually over Modbus RTU:
   - AC output: voltage, current, power
   - DC battery: voltage, current, SOC, charge state
   - AC input: voltage, current, connected flag
   - Fault register → maps to Victron status code
2. `publish_dbus()` writes every value to D-Bus in a single pass.
3. `/UpdateIndex` is incremented (0–255, wrapping). VenusOS consumers use this to detect when new data has arrived.

If any register read fails, `refresh_data()` returns `False`:
- Error counter increments.
- After **10 consecutive failures** the inverter is flagged offline.
- After **60 consecutive failures** the driver exits. VenusOS restarts it automatically.

### DC current sign handling

EVO series models report battery current as a signed **int16** but Modbus transmits raw **uint16**. Values above 32 767 represent negative numbers (two's complement). For example:

```
raw = 65 286
65 286 > 32 767  →  65 286 − 65 536 = −250
−250 × 0.1 = −25.0 A  (discharging)
```

The current `read_status_data()` implementation stores the raw scaled value. If your register returns negative values as large uint16 numbers, apply this conversion when reading `REG_DC_CURRENT`:

```python
raw = regs[0]
if raw > 32767:
    raw -= 65536
self.energy_data["dc"]["current"] = round(raw * self._scale("SCALE_DC_CURRENT"), 2)
```

### Status mapping

The driver maps two sources to the Victron `/State` value each poll cycle:

```
REG_FAULT != 0              →  /State = 10  (Error)
REG_FAULT == 0, power > 0  →  /State = 7   (Running)
REG_FAULT == 0, power == 0 →  /State = 8   (Standby)
fault register read fails   →  /State = 10  (Error, conservative)
```

---

## Troubleshooting

### Driver does not appear on D-Bus / auto-detect skips Samlex

The most common cause is unfilled `???` values in `[SAMLEX_REGISTERS]`. Check the log:

```
tail -f /var/log/dbus-serialinverter.ttyUSB0/current
```

You should see:

```
Samlex: register map not configured, skipping
```

Fill in all 20 register keys in `config.ini` and restart the driver.

### `test_connection()` returns False after registers are filled

The identity check failed. Confirm:

- `REG_IDENTITY` is the correct register address (decimal, not hex).
- `IDENTITY_VALUE` matches exactly what the EVO 4024 returns from that register.
- The Modbus slave address in `[INVERTER] ADDRESS` matches the inverter's configured address.
- RS485 wiring is correct (A/B not swapped).

You can test the raw Modbus read with `pymodbus`:

```python
from pymodbus.client import ModbusSerialClient
c = ModbusSerialClient(method="rtu", port="/dev/ttyUSB0", baudrate=9600, stopbits=1, parity="N", bytesize=8, timeout=1)
c.connect()
r = c.read_input_registers(address=<REG_IDENTITY>, count=1, slave=1)
print(r.registers)
```

### DC voltage reads completely wrong for my battery bank

First, confirm the EVO model matches your battery bank voltage. The **last two digits of the model number are the battery voltage** — EVO-22**12** = 12 V, EVO-22**24** = 24 V, EVO-40**24** = 24 V, EVO-40**48** = 48 V. A 24 V bank connected to an EVO-4024 should read 20–30 V on `/Dc/0/Voltage`. If it reads ~2.4 V, your `SCALE_DC_VOLTAGE` is likely `0.01` instead of `0.1`. If it reads ~240 V, the register address is probably pointing at AC voltage instead of DC voltage.

Use a multimeter on the battery terminals to get the true voltage, then compare to the raw register value to derive the correct scale:

```
scale = known_voltage ÷ raw_register_value
# e.g. 26.4 V ÷ 264 raw = 0.1
```

### Values look wrong (off by 10×)

The scale factor is incorrect. Cross-reference the raw register value against the known physical measurement (e.g., use a multimeter on battery voltage) to determine the correct multiplier. Common values are `0.1`, `0.01`, and `1.0`.

### Battery current shows a large positive number instead of negative

The register is `int16` but stored as `uint16`. See [DC current sign handling](#dc-current-sign-handling) above.

### Driver exits after 60 poll failures

The inverter stopped responding. Check:

- The RS485 cable is connected and not damaged.
- The inverter is powered on.
- No other software is opening the same serial port.
