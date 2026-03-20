#!/bin/bash
set -x

# run-service.sh expects two positional args: tty name and baud rate.
# If serial-starter only passes the tty name (one arg), supply a default
# baud rate so the shift 2 inside run-service.sh does not fail on boot.
[ -z "$2" ] && set -- "$1" 9600

. /opt/victronenergy/serial-starter/run-service.sh

app="python /opt/victronenergy/dbus-serialinverter/dbus-serialinverter.py"
args="/dev/$tty"
start $args