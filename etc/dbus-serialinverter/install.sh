#!/bin/bash
set -x

DRIVERNAME=dbus-serialinverter
SERIAL_STARTER_FILE=/data/conf/serial-starter.d
SERIAL_STARTER_SERVICE_LINE="service sinverter		dbus-serialinverter"
SERIAL_STARTER_ALIAS_LINE="alias	sinv		sinverter"

# handle read only mounts
sh /opt/victronenergy/swupdate-scripts/remount-rw.sh

# set permissions
chmod 755 /data/etc/$DRIVERNAME/start-serialinverter.sh
chmod 755 /data/etc/$DRIVERNAME/service/run
chmod 755 /data/etc/$DRIVERNAME/service/log/run

# ensure serial-starter knows how to resolve VE_SERVICE=sinv
mkdir -p /data/conf
if [ ! -f "$SERIAL_STARTER_FILE" ]; then
    printf '%s\n%s\n' "$SERIAL_STARTER_SERVICE_LINE" "$SERIAL_STARTER_ALIAS_LINE" > "$SERIAL_STARTER_FILE"
else
    grep -qxF "$SERIAL_STARTER_SERVICE_LINE" "$SERIAL_STARTER_FILE" || printf '\n%s\n' "$SERIAL_STARTER_SERVICE_LINE" >> "$SERIAL_STARTER_FILE"
    grep -qxF "$SERIAL_STARTER_ALIAS_LINE" "$SERIAL_STARTER_FILE" || printf '\n%s\n' "$SERIAL_STARTER_ALIAS_LINE" >> "$SERIAL_STARTER_FILE"
fi

grep -qxF "$SERIAL_STARTER_SERVICE_LINE" "$SERIAL_STARTER_FILE" || {
    echo "Missing required serial-starter service mapping in $SERIAL_STARTER_FILE"
    exit 1
}
grep -qxF "$SERIAL_STARTER_ALIAS_LINE" "$SERIAL_STARTER_FILE" || {
    echo "Missing required serial-starter alias mapping in $SERIAL_STARTER_FILE"
    exit 1
}

# ── Map serial device to this driver via udev ────────────────────────────────
# serial-starter reads VE_SERVICE from udev to route devices to services.
# lock-serial-device.sh creates a udev rule that sets VE_SERVICE=sinv for
# the selected USB-RS485 adapter. Prompt the user if no rule exists yet.
UDEV_RULE_FILE="/etc/udev/rules.d/serial-starter.rules"
if [ ! -f "$UDEV_RULE_FILE" ] || ! grep -q 'VE_SERVICE.*sinv' "$UDEV_RULE_FILE"; then
    echo
    echo "=== Serial Device Setup ==="
    echo "No udev rule found to route your USB-RS485 adapter to this driver."
    echo "Running lock-serial-device.sh to set up the device mapping..."
    echo

    LOCK_SCRIPT="/data/etc/$DRIVERNAME/lock-serial-device.sh"
    if [ -x "$LOCK_SCRIPT" ]; then
        "$LOCK_SCRIPT"
    else
        chmod +x "$LOCK_SCRIPT" 2>/dev/null && "$LOCK_SCRIPT" || {
            echo "Warning: Could not run lock-serial-device.sh"
            echo "Run it manually after install:"
            echo "  cd /data/etc/$DRIVERNAME && ./lock-serial-device.sh"
        }
    fi
else
    echo "Udev device mapping already configured."
fi

# install
rm -rf /opt/victronenergy/service/$DRIVERNAME
rm -rf /opt/victronenergy/service-templates/$DRIVERNAME
rm -rf /opt/victronenergy/$DRIVERNAME

mkdir /opt/victronenergy/$DRIVERNAME
cp -f /data/etc/$DRIVERNAME/* /opt/victronenergy/$DRIVERNAME &>/dev/null
cp -rf /data/etc/$DRIVERNAME/pymodbus /opt/victronenergy/$DRIVERNAME/ &>/dev/null
cp -rf /data/etc/$DRIVERNAME/service /opt/victronenergy/service-templates/$DRIVERNAME

# restart if running
pkill -f "python .*/$DRIVERNAME.py"

# add install-script to rc.local to be ready for firmware update
filename=/data/rc.local
if [ ! -f $filename ]; then
    echo "#!/bin/bash" >> $filename
    chmod 755 $filename
fi
grep -qxF "sh /data/etc/$DRIVERNAME/install.sh" $filename || printf '\n%s' "sh /data/etc/$DRIVERNAME/install.sh" >> $filename
# reset back to RO to prevent accidental changes to the system
sed -i 's|\(/dev/root\s\+\/\s\+auto\s\+\)defaults|\1ro|' /etc/fstab
mount -o remount,ro /