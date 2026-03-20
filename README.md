# dbus-serialinverter
This is a driver for VenusOS devices (any GX device sold by Victron or a Raspberry Pi running the VenusOS image).

The driver will communicate with a inverter that supports serial communication (RS232, RS485 or TTL UART) and publish its data to the VenusOS system. 

## Inspiration
Based on https://github.com/Louisvdw/dbus-serialbattery and https://github.com/fabian-lauer/dbus-solax-x1-pvinverter

## Special remarks
- Early development stage, there's still some work to do
- Currently testing with https://www.waveshare.com/usb-to-rs485.htm and Solis mini 700 4G inverter
- Adding inverters like Growatt MIC (RS485) should be pretty easy

## Supported inverter types

- Solis mini series (Modbus RTU)
- Samlex EVO series inverter/chargers (Modbus RTU over RS485)
- Dummy inverter (for local testing)

### Samlex support notes

- The Samlex driver is included and can be selected with `TYPE=Samlex` in `etc/dbus-serialinverter/config.ini`.
- Samlex register addresses are NDA-protected, so `SAMLEX_REGISTERS` values ship as `???` until you fill them from the Samlex Modbus protocol guide.
- If the `SAMLEX_REGISTERS` section is incomplete, Samlex detection is skipped automatically.
- Full Samlex model/configuration guidance is available in `docs/samlex.md`.

## Configure config.ini (detailed)

The file to edit is `etc/dbus-serialinverter/config.ini`.

### 1) Quick-start templates

Use one of these as a starting point.

Solis (recommended first real-hardware setup):

```ini
[DEFAULT]
PUBLISH_CONFIG_VALUES=1
LOG_LEVEL=INFO

[INVERTER]
TYPE=Solis
ADDRESS=1
POLL_INTERVAL=1000
MAX_AC_POWER=700
PHASE=L1
POSITION=1
```

Samlex EVO (requires full register map in `[SAMLEX_REGISTERS]`):

```ini
[DEFAULT]
PUBLISH_CONFIG_VALUES=1
LOG_LEVEL=INFO

[INVERTER]
TYPE=Samlex
ADDRESS=1
POLL_INTERVAL=1000
MAX_AC_POWER=4000
PHASE=L1
POSITION=1
```

Dummy (local testing without inverter hardware):

```ini
[DEFAULT]
PUBLISH_CONFIG_VALUES=1
LOG_LEVEL=DEBUG

[INVERTER]
TYPE=Dummy
ADDRESS=1
POLL_INTERVAL=1000
MAX_AC_POWER=800
PHASE=L1
POSITION=1
```

### 2) What each key does

`[DEFAULT]`

- `PUBLISH_CONFIG_VALUES`
  - `1`: Publish all uppercase config constants to D-Bus under `/Info/Config/*`.
  - `0`: Do not publish those config paths.
  - Use `1` unless you have a reason to hide config on D-Bus.

- `LOG_LEVEL`
  - Supported Python logging names work (`DEBUG`, `INFO`, `WARNING`, `ERROR`, ...).
  - Invalid values fall back to `INFO`.
  - Recommended: `INFO` for normal use, `DEBUG` only when troubleshooting.

`[INVERTER]`

- `TYPE`
  - `Dummy`: only Dummy is tried.
  - Empty value (`TYPE=`): auto-detect tries real drivers in order (`Solis`, then `Samlex`).
  - `Solis` or `Samlex`: only that driver is tried.
  - Any unknown value: no matching driver is tried, startup fails with "No inverter connection".

- `ADDRESS`
  - Present in config, but currently not read by runtime code.
  - Current drivers use fixed slave IDs from code (both Solis and Samlex currently use slave `1`).
  - Keep this at `1` for now.

- `POLL_INTERVAL`
  - Poll period in milliseconds.
  - Must be an integer, or startup exits with `Config error`.
  - Typical values: `500` to `2000`.

- `MAX_AC_POWER`
  - Maximum AC power in watts used for D-Bus `/Ac/MaxPower` and power-limit conversions.
  - Must be numeric and `> 0`, or startup exits.
  - How to choose:
    - Solis: set to inverter rated output (nameplate value).
    - Samlex: set to model class (e.g. EVO-4024 -> `4000`, EVO-2212 -> `2200`).
    - Dummy: choose any positive test value.

- `PHASE`
  - Expected values: `L1`, `L2`, `L3`.
  - For single-phase Solis, this decides which phase gets populated with measured values.
  - For Samlex (vebus service), current implementation publishes AC output on `L1`; keep `L1`.

- `POSITION`
  - D-Bus PV inverter position value:
    - `0` = AC input 1
    - `1` = AC output
    - `2` = AC input 2
  - Relevant for PV inverter service types (Solis/Dummy).
  - Ignored for Samlex vebus service paths.

### 3) Required validation behavior (important)

Startup exits immediately if any of these are true:

- `config.ini` missing or missing `[INVERTER]` section
- non-numeric `MAX_AC_POWER`
- `MAX_AC_POWER <= 0`
- non-integer `POLL_INTERVAL`
- non-integer `POSITION`

This means syntax mistakes in `config.ini` are fail-fast by design.

### 4) Samlex register map: how values are gathered

Samlex needs a complete numeric `[SAMLEX_REGISTERS]` section before the driver will talk Modbus.

- Any required key left as `???` causes Samlex detection to be skipped.
- Register addresses must be integers in valid Modbus range (`0` to `65535`).
- Scale fields must be numeric floats.
- `REG_IDENTITY` and `IDENTITY_VALUE` must match your exact model.

How to populate safely:

1. Request the Samlex Modbus Protocol Guide (see `docs/samlex.md`).
2. Convert register addresses from hex to decimal if needed (example: `0x0010` -> `16`).
3. Copy the scale exactly from the guide (`0.1`, `1.0`, etc.).
4. Restart driver and verify values on D-Bus (`/Dc/0/Voltage`, `/Ac/Out/L1/P`, `/Soc`).

### 5) Practical setup flow

1. Set `TYPE=Dummy` and verify driver/service starts.
2. Switch to your real type (`Solis` or `Samlex`).
3. Set `MAX_AC_POWER`, `POLL_INTERVAL`, `PHASE`, `POSITION`.
4. For Samlex, complete all required `[SAMLEX_REGISTERS]` values.
5. Use `LOG_LEVEL=DEBUG` during first validation, then return to `INFO`.
6. If no device connects, temporarily set `TYPE=Solis` or `TYPE=Samlex` (avoid auto-detect ambiguity).

## Todo
- When TYPE is set in config, disable auto detection and use the specified type by default

## Installation
- Make sure you're running VenusOS Large, else you will get errors like:
> ModuleNotFoundError: No module named 'dataclasses'
- Grab a copy of the main branch
- Modify dbus-serialinverter\etc\config.ini
- Copy everything to /data on your VenusOS device (ATTENTION: If /data/conf/serial-starter.d is already there, DO NOT OVERWRITE and add the contents manually!)
- Connect to your VenusOS device via SSH
- Get model and serial of your USB-to-Serial-Converter. Example for /dev/ttyUSB0:
- To prevent other services from bugging your serial converter, modify /etc/udev/rules.d/serial-starter.rules by running this script:
```
#!/bin/bash

# 1. Identify the target device (defaults to ttyUSB0)
DEV_NAME="/dev/ttyUSB0"

if [ ! -e "$DEV_NAME" ]; then
    echo "Error: $DEV_NAME not found. Please plug in your USB-to-Serial converter."
    exit 1
fi

# 2. Extract properties using udevadm
ID_MODEL=$(udevadm info --query=property --name="$DEV_NAME" | grep 'ID_MODEL=' | cut -d'=' -f2)
ID_SERIAL=$(udevadm info --query=property --name="$DEV_NAME" | grep 'ID_SERIAL_SHORT=' | cut -d'=' -f2)

if [ -z "$ID_MODEL" ] || [ -z "$ID_SERIAL" ]; then
    echo "Error: Could not retrieve hardware ID for $DEV_NAME."
    exit 1
fi

# 3. Define the rule content
RULE_LINE="ACTION==\"add\", ENV{ID_BUS}==\"usb\", ENV{ID_MODEL}==\"$ID_MODEL\", ENV{ID_SERIAL_SHORT}==\"$ID_SERIAL\", ENV{VE_SERVICE}=\"sinv\""
RULE_FILE="/etc/udev/rules.d/serial-starter.rules"

# 4. Write the rule (requires sudo)
echo "Found Device: $ID_MODEL ($ID_SERIAL)"
echo "Writing rule to $RULE_FILE..."

echo "$RULE_LINE" | sudo tee "$RULE_FILE" > /dev/null

# 5. Reload udev to apply changes immediately
sudo udevadm control --reload-rules
sudo udevadm trigger

echo "Done. Your Samlex/Serial integration is now locked to this hardware ID."
```
- Call the installer:
```
cd /data/etc/dbus-serialinverter
chmod +x install.sh
./install.sh
```
- Reboot!

## Releases

- Pushing a tag that matches `v*` (for example `v0.2.0`) automatically creates or updates a GitHub Release.
- The release workflow publishes a single runtime artifact that contains only `conf/` and `etc/`:
  - `dbus-serialinverter-<tag>.tar.gz`
  - `dbus-serialinverter-<tag>.tar.gz.sha256`
- Release notes are generated from git commits since the previous tag.
- A generated changelog file is attached to each release as `CHANGELOG-<tag>.md`.