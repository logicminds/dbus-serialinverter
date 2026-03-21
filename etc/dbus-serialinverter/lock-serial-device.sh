#!/bin/bash
#
# Lock or unlock a USB serial converter for dbus-serialinverter via udev rules.
# Lists all /dev/ttyUSB* devices so you can identify the right one
# when multiple adapters are connected (e.g. Victron VE.Bus + RS485).
#
# Usage:
#   ./lock-serial-device.sh            # Lock a device (interactive)
#   ./lock-serial-device.sh --unlock   # Remove the lock rule
#

set -euo pipefail

RULE_FILE="/etc/udev/rules.d/serial-starter.rules"

# --- Unlock mode ---
if [ "${1:-}" = "--unlock" ]; then
    if [ ! -f "$RULE_FILE" ]; then
        echo "No lock rule found at $RULE_FILE — nothing to remove."
        exit 0
    fi

    echo "Current rule:"
    cat "$RULE_FILE"
    echo

    read -rp "Remove this rule? [y/N]: " confirm
    if [ "${confirm,,}" != "y" ]; then
        echo "Cancelled."
        exit 0
    fi

    sudo rm "$RULE_FILE"
    sudo udevadm control --reload-rules
    sudo udevadm trigger

    echo "Done. Udev rule removed — serial device is no longer locked."
    exit 0
fi

# --- Lock mode ---

# Show existing rule if present
if [ -f "$RULE_FILE" ]; then
    echo "Existing lock rule found:"
    cat "$RULE_FILE"
    echo
    read -rp "Replace it? [y/N]: " confirm
    if [ "${confirm,,}" != "y" ]; then
        echo "Cancelled."
        exit 0
    fi
    echo
fi

# Discover all USB serial devices
DEVICES=()
for dev in /dev/ttyUSB*; do
    [ -e "$dev" ] || continue
    DEVICES+=("$dev")
done

if [ ${#DEVICES[@]} -eq 0 ]; then
    echo "Error: No /dev/ttyUSB* devices found. Please plug in your USB-to-Serial converter."
    exit 1
fi

echo "Available USB serial devices:"
echo
for i in "${!DEVICES[@]}"; do
    dev="${DEVICES[$i]}"
    model=$(udevadm info --query=property --name="$dev" 2>/dev/null | grep 'ID_MODEL=' | cut -d'=' -f2)
    serial=$(udevadm info --query=property --name="$dev" 2>/dev/null | grep 'ID_SERIAL_SHORT=' | cut -d'=' -f2)
    vendor=$(udevadm info --query=property --name="$dev" 2>/dev/null | grep 'ID_VENDOR=' | cut -d'=' -f2)
    printf "  [%d] %s  —  %s / %s (serial: %s)\n" "$i" "$dev" "${vendor:-unknown}" "${model:-unknown}" "${serial:-unknown}"
done
echo

read -rp "Select device number [0]: " choice
choice="${choice:-0}"

if ! [[ "$choice" =~ ^[0-9]+$ ]] || [ "$choice" -ge ${#DEVICES[@]} ]; then
    echo "Error: Invalid selection."
    exit 1
fi

DEV_NAME="${DEVICES[$choice]}"

# Extract hardware IDs
ID_MODEL=$(udevadm info --query=property --name="$DEV_NAME" | grep 'ID_MODEL=' | cut -d'=' -f2)
ID_SERIAL=$(udevadm info --query=property --name="$DEV_NAME" | grep 'ID_SERIAL_SHORT=' | cut -d'=' -f2)

if [ -z "$ID_MODEL" ] || [ -z "$ID_SERIAL" ]; then
    echo "Error: Could not retrieve hardware ID for $DEV_NAME."
    exit 1
fi

# Write the udev rule
RULE_LINE="ACTION==\"add\", ENV{ID_BUS}==\"usb\", ENV{ID_MODEL}==\"$ID_MODEL\", ENV{ID_SERIAL_SHORT}==\"$ID_SERIAL\", ENV{VE_SERVICE}=\"sinv\""

echo
echo "Selected: $DEV_NAME"
echo "  Vendor: ${ID_MODEL}"
echo "  Serial: ${ID_SERIAL}"
echo "Writing rule to $RULE_FILE..."

echo "$RULE_LINE" | sudo tee "$RULE_FILE" > /dev/null

sudo udevadm control --reload-rules
sudo udevadm trigger

echo "Done. Your serial converter is now locked to this hardware ID."
