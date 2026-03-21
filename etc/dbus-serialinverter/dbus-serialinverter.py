#!/usr/bin/env python
import sys
import re

from time import sleep
from typing import Union
from threading import Lock

from dbus.mainloop.glib import DBusGMainLoop

from gi.repository import GLib

from dbushelper import DbusHelper
from utils import logger
import utils

from inverter import Inverter
from dummy import Dummy
from solis import Solis
from samlex import Samlex
from samlex_mock import SamlexMock

_REAL_INVERTER_TYPES = [
    {"inverter": Solis,   "baudrate": 9600, "slave": 1},
    {"inverter": Samlex,  "baudrate": 9600, "slave": 1},  # after Solis; silently skipped if registers not configured
]

# Dummy and SamlexMock are only included when explicitly configured — never in auto-detect.
if utils.INVERTER_TYPE == "Dummy":
    expected_inverter_types = [{"inverter": Dummy, "baudrate": 0, "slave": 0}]
elif utils.INVERTER_TYPE == "SamlexMock":
    expected_inverter_types = [{"inverter": SamlexMock, "baudrate": 0, "slave": 0}]
elif utils.INVERTER_TYPE == "":
    expected_inverter_types = _REAL_INVERTER_TYPES
else:
    expected_inverter_types = [
        t for t in _REAL_INVERTER_TYPES
        if t["inverter"].__name__ == utils.INVERTER_TYPE
    ]

def main():
    _poll_lock = Lock()

    def poll_inverter(loop):
        # Skip this tick if the previous poll is still running.
        if not _poll_lock.acquire(blocking=False):
            logger.warning("Poll skipped: previous poll still running")
            return True
        try:
            helper.publish_inverter(loop)
        finally:
            _poll_lock.release()
        return True

    def get_inverter(_port) -> Union[Inverter, None]:
        # all the different inverters the driver support and need to test for
        # try to establish communications with the inverter 3 times, else exit
        count = 3
        while count > 0:
            # create a new inverter object that can read the inverter and run connection test
            for test in expected_inverter_types:
                logger.info("Testing " + test["inverter"].__name__)
                inverterClass = test["inverter"]
                baudrate = test["baudrate"]
                inverter: Inverter = inverterClass(
                    port=_port, baudrate=baudrate, slave=test.get("slave")
                )
                if inverter.test_connection():
                    logger.info(
                        "Connection established to " + inverter.__class__.__name__
                    )
                    return inverter
            count -= 1
            sleep(0.5)

        return None

    def get_port() -> str:
        if len(sys.argv) < 2:
            logger.error("Usage: dbus-serialinverter.py <port>")
            sys.exit(1)
        port = sys.argv[1]
        if not re.match(r"^/dev/(tty[A-Za-z0-9_]+|null)$", port):
            logger.error("Invalid port path: %s", port)
            sys.exit(1)
        return port

    logger.info("Start dbus-serialinverter")

    port = get_port()
    inverter: Inverter = get_inverter(port)

    if inverter is None:
        logger.error("ERROR >>> No inverter connection at " + port)
        sys.exit(1)

    inverter.log_settings()

    # Have a mainloop, so we can send/receive asynchronous calls to and from dbus
    DBusGMainLoop(set_as_default=True)
    mainloop = GLib.MainLoop()

    # Get the initial values for the inverter used by setup_vedbus
    helper = DbusHelper(inverter)

    if not helper.setup_vedbus():
        logger.error("ERROR >>> Problem with inverter set up at " + port)
        sys.exit(1)

    # Poll the inverter at INTERVAL and run the main loop
    GLib.timeout_add(inverter.poll_interval, lambda: poll_inverter(mainloop))
    try:
        mainloop.run()
    except KeyboardInterrupt:
        pass

if __name__ == "__main__":
    main()
