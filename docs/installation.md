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

# Extract into /data (creates /data/conf and /data/etc)
tar -xzf /tmp/dbus-serialinverter.tar.gz -C /data
```

> **Warning:** If `/data/conf/serial-starter.d` already exists on your device, do NOT overwrite it. Back up first and merge the contents manually.

Edit `config.ini` for your inverter (see [configuration guide](configuration.md)):

```bash
vi /data/etc/dbus-serialinverter/config.ini
```

### 2. Lock your USB serial converter

To prevent other VenusOS services from claiming your serial port, create a udev rule. SSH into your VenusOS device and run:

```bash
#!/bin/bash

# Identify the target device (change if not ttyUSB0)
DEV_NAME="/dev/ttyUSB0"

if [ ! -e "$DEV_NAME" ]; then
    echo "Error: $DEV_NAME not found. Please plug in your USB-to-Serial converter."
    exit 1
fi

# Extract hardware IDs
ID_MODEL=$(udevadm info --query=property --name="$DEV_NAME" | grep 'ID_MODEL=' | cut -d'=' -f2)
ID_SERIAL=$(udevadm info --query=property --name="$DEV_NAME" | grep 'ID_SERIAL_SHORT=' | cut -d'=' -f2)

if [ -z "$ID_MODEL" ] || [ -z "$ID_SERIAL" ]; then
    echo "Error: Could not retrieve hardware ID for $DEV_NAME."
    exit 1
fi

# Write the udev rule
RULE_LINE="ACTION==\"add\", ENV{ID_BUS}==\"usb\", ENV{ID_MODEL}==\"$ID_MODEL\", ENV{ID_SERIAL_SHORT}==\"$ID_SERIAL\", ENV{VE_SERVICE}=\"sinv\""
RULE_FILE="/etc/udev/rules.d/serial-starter.rules"

echo "Found Device: $ID_MODEL ($ID_SERIAL)"
echo "Writing rule to $RULE_FILE..."

echo "$RULE_LINE" | sudo tee "$RULE_FILE" > /dev/null

sudo udevadm control --reload-rules
sudo udevadm trigger

echo "Done. Your serial converter is now locked to this hardware ID."
```

### 3. Install and reboot

```bash
cd /data/etc/dbus-serialinverter
chmod +x install.sh
./install.sh
```

Reboot your device.

### 4. Verify

Check logs after reboot:

```bash
tail -f /var/log/dbus-serialinverter.<TTY>
```

## Local Testing (no hardware)

You can run the driver locally with the dummy inverter:

```bash
cd etc/dbus-serialinverter
python dbus-serialinverter.py /dev/null
```
