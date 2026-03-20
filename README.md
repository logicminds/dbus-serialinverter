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
```
udevadm info --query=property --name=/dev/ttyUSB0 | sed -n s/^ID_MODEL=//p
udevadm info --query=property --name=/dev/ttyUSB0 | sed -n s/^ID_SERIAL_SHORT=//p
```
- To prevent other services from bugging your serial converter, modify /etc/udev/rules.d/serial-starter.rules and add following line (replace XXXXXXXX with the values you got in previous step):
```
ACTION=="add", ENV{ID_BUS}=="usb", ENV{ID_MODEL}=="XXXXXXXX", ENV{ID_SERIAL_SHORT}=="XXXXXXXX", ENV{VE_SERVICE}="sinv"
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