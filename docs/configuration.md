# Configuration Guide

On a device installed from the release tarball, edit `/data/etc/dbus-serialinverter/config.ini` to configure the driver (for a local source checkout, the corresponding file is `etc/dbus-serialinverter/config.ini`).

## Quick-Start Templates

### Solis (recommended first real-hardware setup)

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

### Samlex EVO (requires register map — see [docs/samlex.md](samlex.md))

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

### Dummy (local testing without hardware)

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

## Config Reference

### `[DEFAULT]` Section

| Key | Values | Notes |
|-----|--------|-------|
| `PUBLISH_CONFIG_VALUES` | `1` or `0` | Publish config constants to D-Bus under `/Info/Config/*`. Default to `1`. |
| `LOG_LEVEL` | `DEBUG`, `INFO`, `WARNING`, `ERROR` | Invalid values fall back to `INFO`. Use `DEBUG` only when troubleshooting. |

### `[INVERTER]` Section

| Key | Values | Notes |
|-----|--------|-------|
| `TYPE` | `Solis`, `Samlex`, `Dummy`, or empty | Empty = auto-detect. Unknown values cause startup failure. |
| `ADDRESS` | Integer | Reserved for future use. Keep at `1`. |
| `POLL_INTERVAL` | Integer (ms) | Poll period. Typical: `500`–`2000`. |
| `MAX_AC_POWER` | Integer > 0 (watts) | Inverter rated output. Used for D-Bus `/Ac/MaxPower` and power-limit conversions. |
| `PHASE` | `L1`, `L2`, `L3` | Which AC phase gets populated. Single-phase inverters: use `L1`. |
| `POSITION` | `0`, `1`, `2` | `0` = AC input 1, `1` = AC output, `2` = AC input 2. Ignored for Samlex vebus service. |

## Validation

Startup exits immediately if:
- `config.ini` is missing or has no `[INVERTER]` section
- `MAX_AC_POWER` is non-numeric or ≤ 0
- `POLL_INTERVAL` is non-integer
- `POSITION` is non-integer

## Samlex Register Map

Samlex requires a complete `[SAMLEX_REGISTERS]` section with numeric values before the driver will connect. Any key left as `???` causes Samlex detection to be skipped. See [docs/samlex.md](samlex.md) for full details.

## Recommended Setup Flow

1. Start with `TYPE=Dummy` — verify the driver/service starts
2. Switch to your real type (`Solis` or `Samlex`)
3. Set `MAX_AC_POWER`, `POLL_INTERVAL`, `PHASE`, `POSITION`
4. For Samlex: complete all `[SAMLEX_REGISTERS]` values
5. Use `LOG_LEVEL=DEBUG` during first validation, then switch to `INFO`
