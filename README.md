# dbus-serialinverter

A VenusOS driver that connects serial inverters (RS232/RS485/TTL UART) to the Victron D-Bus system. Runs on any Victron GX device or Raspberry Pi with VenusOS Large.

## Supported Inverters

- **Solis** mini series (Modbus RTU)
- **Samlex EVO** series inverter/chargers (Modbus RTU over RS485) — see [docs/samlex.md](docs/samlex.md)
- **Dummy** inverter (for testing without hardware)

## Quick Start

SSH into your VenusOS device and run:

```bash
# Download the latest release
wget -O /tmp/dbus-serialinverter.tar.gz https://github.com/logicminds/dbus-serialinverter/releases/latest/download/dbus-serialinverter.tar.gz

# Extract into /data (creates /data/conf and /data/etc)
tar -xzf /tmp/dbus-serialinverter.tar.gz -C /data

# Configure and install
vi /data/etc/dbus-serialinverter/config.ini   # set TYPE, MAX_AC_POWER, PHASE
cd /data/etc/dbus-serialinverter
chmod +x install.sh && ./install.sh
```

Reboot and check logs: `tail -f /var/log/dbus-serialinverter.<TTY>/current`

See the [Installation Guide](docs/installation.md) for udev setup and detailed steps.

## Documentation

| Doc | Covers |
|-----|--------|
| [Installation Guide](docs/installation.md) | Prerequisites, udev setup, step-by-step install |
| [Configuration Guide](docs/configuration.md) | All config.ini options, templates, validation rules |
| [Samlex Guide](docs/samlex.md) | Samlex-specific setup and register map |

## Credits

Based on [dbus-serialbattery](https://github.com/Louisvdw/dbus-serialbattery) and [dbus-solax-x1-pvinverter](https://github.com/fabian-lauer/dbus-solax-x1-pvinverter).
