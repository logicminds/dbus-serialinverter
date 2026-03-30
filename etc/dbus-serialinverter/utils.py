# -*- coding: utf-8 -*-
import logging
import os
import sys

import configparser
from pathlib import Path

# VenusOS ships pymodbus 2.5.3 system-wide, but this driver requires the 3.x API
# (breaking changes in import paths and client interface). We vendor pymodbus 3.1.3
# alongside the driver and insert it at the front of sys.path so it takes precedence
# over the system copy regardless of where the driver is run from.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "pymodbus"))

# Constants
DRIVER_VERSION = 0.3
DRIVER_SUBVERSION = ".1"

# Logging (level configured below once config.ini is parsed)
logging.basicConfig()
logger = logging.getLogger("SerialInverter")

# Config
# Load template config first, then private config (which overrides template values)
_config_dir = Path(__file__).parent
config_file_path = str(_config_dir / "config.ini")
config_private_path = str(_config_dir / "config.ini.private")

config = configparser.ConfigParser()
# Read template first, then private (which overrides)
config.read([config_file_path, config_private_path])

if not config.has_section('INVERTER'):
    raise SystemExit("Config file missing or invalid: %s" % config_file_path)

try:
    PUBLISH_CONFIG_VALUES = int(config["DEFAULT"]["PUBLISH_CONFIG_VALUES"])
    _log_level_name = config.get("DEFAULT", "LOG_LEVEL", fallback="INFO").upper()
    logger.setLevel(getattr(logging, _log_level_name, logging.INFO))

    INVERTER_TYPE = config['INVERTER']['TYPE']
    INVERTER_MAX_AC_POWER = float(config['INVERTER']['MAX_AC_POWER'])
    if INVERTER_MAX_AC_POWER <= 0:
        raise SystemExit("INVERTER_MAX_AC_POWER must be greater than 0 (got %s)" % INVERTER_MAX_AC_POWER)
    INVERTER_PHASE = config['INVERTER']['PHASE'] # L1; L2; L3
    INVERTER_POLL_INTERVAL = int(config['INVERTER']['POLL_INTERVAL'])
    INVERTER_POSITION = int(config['INVERTER']['POSITION']) # 0 = AC input 1; 1 = AC output; 2 = AC input 2
    INVERTER_SOC_SOURCE = config.get('INVERTER', 'SOC_SOURCE', fallback='auto').lower()
    if INVERTER_SOC_SOURCE not in ('auto', 'inverter', 'none'):
        raise SystemExit("SOC_SOURCE must be 'auto', 'inverter', or 'none' (got %s)" % INVERTER_SOC_SOURCE)
except (KeyError, ValueError) as e:
    raise SystemExit("Config error: %s. Check %s" % (e, config_file_path))

# Snapshot of all uppercase config constants for publishing to D-Bus /Info/Config/
_CONFIG_VARS = {k: v for k, v in globals().items() if k.isupper()}

def publish_config_variables(dbusservice):
    for variable, value in _CONFIG_VARS.items():
        if isinstance(value, (float, int, str, list)):
            dbusservice.add_path(f"/Info/Config/{variable}", value)
