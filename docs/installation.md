# Installation Guide

## Prerequisites

- VenusOS **Large** (Python 3.8+ required)
- A USB-to-Serial converter (e.g. [Waveshare USB to RS485](https://www.waveshare.com/usb-to-rs485.htm))

## Steps

### 1. Download and extract

SSH into your VenusOS device and download the release tarball:

```bash
# Download the latest release
wget -qO /tmp/dbus-serialinverter.tar.gz https://github.com/logicminds/dbus-serialinverter/releases/latest/download/dbus-serialinverter.tar.gz

# Extract into /data (creates /data/dbus-serialinverter); preserves existing config
tar -xzf /tmp/dbus-serialinverter.tar.gz -C /data --skip-old-files
```

> **Warning:** If `/data/conf/serial-starter.d` already exists on your device, do NOT overwrite it. Back up first and merge the contents manually.

Edit `config.ini` for your inverter (see [configuration guide](configuration.md)):

```bash
vi /data/etc/dbus-serialinverter/config.ini
```

### 2. Lock your USB serial converter

To prevent other VenusOS services from claiming your serial port, create a udev rule.

If you have multiple USB serial devices (e.g. Victron VE.Bus adapters alongside your inverter's RS485 converter), the included script lists all connected devices so you can pick the right one.

```bash
cd /data/dbus-serialinverter/etc/dbus-serialinverter
chmod +x lock-serial-device.sh
./lock-serial-device.sh
```

Example output with three USB devices (two Victron VE.Direct cables and one RS485 converter):

```
Available USB serial devices:

  [0] /dev/ttyUSB0  —  VictronEnergy_BV / VE_Direct_cable (serial: VE61VZ7Z)
  [1] /dev/ttyUSB1  —  VictronEnergy_BV / VE_Direct_cable (serial: VE61VUG5)
  [2] /dev/ttyUSB2  —  FTDI / USB-RS485-WE (serial: FTALP3Z5)

Select device number [0]: 2

Selected: /dev/ttyUSB2
  Vendor: USB-RS485-WE
  Serial: FTALP3Z5
Writing rule to /etc/udev/rules.d/serial-starter.rules...
Done. Your serial converter is now locked to this hardware ID.
```

In this case, device `[2]` is the FTDI RS485 adapter connected to the inverter — the other two are Victron VE.Direct cables and should be left alone.

To switch to a different converter cable (or remove the lock entirely), run:

```bash
./lock-serial-device.sh --unlock
```

This removes the udev rule and reloads the rules. You can then re-run `./lock-serial-device.sh` to lock a different device. Re-running the lock script when a rule already exists will prompt you to replace it.

### 3. Install

```bash
cd /data/etc/dbus-serialinverter
chmod +x install.sh
./install.sh
```

If no udev rule exists yet, the installer will automatically run `lock-serial-device.sh` to detect USB serial devices and prompt you to select the one connected to your inverter. This creates a udev rule that tells VenusOS's serial-starter to route your RS485 adapter to this driver.

If you skip this step during install, run it manually later:

```bash
cd /data/etc/dbus-serialinverter
./lock-serial-device.sh
```

Reboot your device after installation.

### 4. Verify

Check logs after reboot:

```bash
tail -f /var/log/dbus-serialinverter.<TTY>/current
```

## Local Testing (no hardware)

You can run the driver locally with the dummy inverter:

```bash
cd etc/dbus-serialinverter
python dbus-serialinverter.py /dev/null
```
