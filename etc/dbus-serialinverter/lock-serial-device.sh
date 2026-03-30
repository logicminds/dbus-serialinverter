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

# These are the VenusOS-standard baseline rules for serial-starter.
# udev creates the /dev/serial-starter/%k symlink directly (SYMLINK+=) on add,
# and calls cleanup.sh on remove. Do NOT overwrite or remove them.
TTY_ADD_RULE='ACTION=="add", SUBSYSTEM=="tty", SUBSYSTEMS=="platform|usb-serial", SYMLINK+="serial-starter/%k"'
TTY_REMOVE_RULE='ACTION=="remove", SUBSYSTEM=="tty", SUBSYSTEMS=="platform|usb-serial", RUN+="/opt/victronenergy/serial-starter/cleanup.sh %k"'

# Ensure the baseline TTY rules are present in the file (prepend if missing).
ensure_triggers() {
    local needs_add=0 needs_remove=0
    grep -qF 'SYMLINK+="serial-starter/%k"' "$RULE_FILE" 2>/dev/null || needs_add=1
    grep -qF 'cleanup.sh'                   "$RULE_FILE" 2>/dev/null || needs_remove=1

    if [ $needs_add -eq 1 ] || [ $needs_remove -eq 1 ]; then
        local tmp
        tmp=$(mktemp)
        {
            [ $needs_add    -eq 1 ] && printf '%s\n' "$TTY_ADD_RULE"
            [ $needs_remove -eq 1 ] && printf '%s\n' "$TTY_REMOVE_RULE"
            cat "$RULE_FILE" 2>/dev/null || true
        } > "$tmp"
        mv "$tmp" "$RULE_FILE"
    fi
}

# Return the current sinv VE_SERVICE lock line, if any.
current_lock_line() {
    grep 'VE_SERVICE.*sinv' "$RULE_FILE" 2>/dev/null || true
}

# --- Unlock mode ---
if [ "${1:-}" = "--unlock" ]; then
    existing=$(current_lock_line)
    if [ -z "$existing" ]; then
        echo "No sinv lock rule found in $RULE_FILE — nothing to remove."
        exit 0
    fi

    echo "Current lock rule:"
    echo "  $existing"
    echo

    read -rp "Remove this rule? [y/N]: " confirm
    if [ "${confirm,,}" != "y" ]; then
        echo "Cancelled."
        exit 0
    fi

    # Remove only the sinv VE_SERVICE line; leave TTY trigger rules intact.
    sed -i '/VE_SERVICE.*sinv/d' "$RULE_FILE"
    udevadm control --reload-rules
    udevadm trigger

    echo "Done. sinv lock rule removed — device will fall through to auto-detect."
    exit 0
fi

# --- Lock mode ---

existing=$(current_lock_line)
if [ -n "$existing" ]; then
    echo "Existing lock rule found:"
    echo "  $existing"
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
    model=$(udevadm info --query=property --name="$dev" 2>/dev/null | grep 'ID_MODEL='        | cut -d'=' -f2)
    serial=$(udevadm info --query=property --name="$dev" 2>/dev/null | grep 'ID_SERIAL_SHORT=' | cut -d'=' -f2)
    vendor=$(udevadm info --query=property --name="$dev" 2>/dev/null | grep 'ID_VENDOR='       | cut -d'=' -f2)
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
ID_MODEL=$(udevadm info --query=property --name="$DEV_NAME" | grep 'ID_MODEL='        | cut -d'=' -f2)
ID_SERIAL=$(udevadm info --query=property --name="$DEV_NAME" | grep 'ID_SERIAL_SHORT=' | cut -d'=' -f2)

if [ -z "$ID_MODEL" ] || [ -z "$ID_SERIAL" ]; then
    echo "Error: Could not retrieve hardware ID for $DEV_NAME."
    exit 1
fi

RULE_LINE="ACTION==\"add\", ENV{ID_BUS}==\"usb\", ENV{ID_MODEL}==\"$ID_MODEL\", ENV{ID_SERIAL_SHORT}==\"$ID_SERIAL\", ENV{VE_SERVICE}=\"sinv\""

echo
echo "Selected: $DEV_NAME"
echo "  Model:  $ID_MODEL"
echo "  Serial: $ID_SERIAL"
echo "Writing rule to $RULE_FILE..."

# Remove any existing sinv lock line, then append the new one.
sed -i '/VE_SERVICE.*sinv/d' "$RULE_FILE" 2>/dev/null || true
printf '\n%s\n' "$RULE_LINE" >> "$RULE_FILE"

# Ensure the TTY trigger rules are in the file (safe to call repeatedly).
ensure_triggers

udevadm control --reload-rules
udevadm trigger

echo "Done. Your serial converter is now locked to this hardware ID."
