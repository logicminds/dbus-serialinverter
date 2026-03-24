#!/usr/bin/env python3
"""Quick cable and communication test for Samlex EVO.

Uses Modbus Function Code 03 (Read Holding Registers) starting at address 100.

Usage:
    python test_cable.py /dev/ttyUSB0
    python test_cable.py /dev/ttyUSB0 --baud 19200
    python test_cable.py /dev/ttyUSB0 --slave 2
"""
import sys
import os
import argparse
import time

# Use the vendored pymodbus (must come before system pymodbus)
_DRIVER_DIRS = [
    os.path.join(os.path.dirname(__file__), "..", "etc", "dbus-serialinverter"),
    "/opt/victronenergy/dbus-serialinverter",
]
for _d in _DRIVER_DIRS:
    if os.path.isdir(_d) and _d not in sys.path:
        sys.path.insert(0, _d)

# Remove any cached system pymodbus so the vendored version loads
for _key in list(sys.modules):
    if _key.startswith("pymodbus"):
        del sys.modules[_key]

from pymodbus.client import ModbusSerialClient


def test_cable(port, baudrate, slave, count=50):
    print(f"=== Samlex EVO Cable Test ===")
    print(f"Port:     {port}")
    print(f"Baudrate: {baudrate}")
    print(f"Slave:    {slave}")
    print()

    # Step 1: Open the serial port
    print("[1] Opening serial port...", end=" ")
    try:
        client = ModbusSerialClient(
            method="rtu", port=port, baudrate=baudrate,
            stopbits=1, parity="N", bytesize=8, timeout=2
        )
        result = client.connect()
        if result:
            print("OK")
        else:
            print("FAILED — could not open port")
            print("    Check: is the USB adapter plugged in?")
            print(f"    Check: does {port} exist? (ls /dev/ttyUSB*)")
            return False
    except Exception as e:
        print(f"FAILED — {e}")
        return False

    BASE_ADDR = 100

    # Step 2: Try identity register (FC03, address 100)
    print(f"[2] Reading identity register (FC03, addr {BASE_ADDR})...", end=" ")
    resp = client.read_holding_registers(address=BASE_ADDR, count=1, slave=slave)
    if hasattr(resp, "isError") and not resp.isError():
        val = resp.registers[0]
        print(f"OK — value: {val}")
        if val == 16420:
            print("    ✓ Identity confirmed: Samlex EVO")
        else:
            print(f"    ✗ Expected 16420, got {val} — may be a different model")
    else:
        print(f"FAILED — {resp}")
        print("    No response from inverter. Check:")
        print("    • Wiring: Purple→Pin4(D+), Brown→Pin5(D-), Yellow→Pin8(GND)")
        print("    • Try swapping D+ and D- wires")
        print("    • Is the inverter powered on?")
        print("    • Is this the correct slave address?")

        # Step 2b: Try other baud rates
        print()
        print("[2b] Trying other baud rates...", end=" ")
        client.close()
        found = False
        for try_baud in [9600, 19200, 38400, 115200]:
            if try_baud == baudrate:
                continue
            c2 = ModbusSerialClient(method="rtu", port=port, baudrate=try_baud, stopbits=1, parity="N", bytesize=8, timeout=1)
            c2.connect()
            r2 = c2.read_holding_registers(address=BASE_ADDR, count=1, slave=slave)
            if hasattr(r2, "isError") and not r2.isError():
                print(f"RESPONDED at {try_baud} baud!")
                print(f"    Update config.ini.private or re-run with --baud {try_baud}")
                found = True
                c2.close()
                break
            c2.close()
        if not found:
            print("no response at any baud rate")

        # Step 2c: Try other slave addresses
        print("[2c] Trying slave addresses 1-10...", end=" ")
        client = ModbusSerialClient(method="rtu", port=port, baudrate=baudrate, stopbits=1, parity="N", bytesize=8, timeout=1)
        client.connect()
        found = False
        for try_slave in range(1, 11):
            if try_slave == slave:
                continue
            r3 = client.read_holding_registers(address=BASE_ADDR, count=1, slave=try_slave)
            if hasattr(r3, "isError") and not r3.isError():
                print(f"RESPONDED at slave {try_slave}!")
                print(f"    Update ADDRESS in config.ini.private to {try_slave}")
                found = True
                break
        if not found:
            print("no response from any address")
        client.close()
        return False

    # Step 3: Read a batch of registers (FC03, addresses BASE_ADDR to BASE_ADDR+count-1)
    print(f"[3] Reading holding registers {BASE_ADDR}–{BASE_ADDR + count - 1} (FC03, count={count})...", end=" ")
    resp = client.read_holding_registers(address=BASE_ADDR, count=count, slave=slave)
    if hasattr(resp, "isError") and not resp.isError():
        print("OK")
        print()
        print("    Addr  Raw      Description")
        print("    ----  -------  -----------")
        # Keys are array offsets (0-based); absolute address = BASE_ADDR + offset
        labels = {
            0: "Identity",
            1: "Working Status (0=PwrSave, 1=AC normal, 2=AC abnormal, 3=Inverting, 4=Fault)",
            2: "Fault Code (0=no fault)",
            5: "AC Out Voltage (×0.1)",
            7: "AC Out Current (×0.1)",
            8: "Charge State (0=Standby, 1=Eq, 2=Abs, 3=Float, 4=Storage, 9=Inv)",
            9: "AC Out Power (×1.0)",
            10: "AC In Voltage (×1.0)",
            11: "AC In Current (×0.1)",
            12: "DC Current / Charger (×0.1)",
            14: "DC Voltage / Bus (×0.1)",
        }
        for i, val in enumerate(resp.registers):
            label = labels.get(i, "")
            print(f"    {BASE_ADDR + i:4d}  {val:7d}  {label}")
    else:
        print(f"FAILED — {resp}")
        print("    Single register worked but batch read failed.")
        client.close()
        return False

    # Step 4: Sanity check values (only when enough registers were read)
    # regs[n] = holding register at address BASE_ADDR+n
    print()
    regs = resp.registers
    print("[4] Sanity checks:")

    if len(regs) > 14:
        dc_v = regs[14] * 0.1  # addr 114
        print(f"    DC Voltage:  {dc_v:.1f} V", end="")
        if 10 < dc_v < 60:
            print(" ✓")
        else:
            print(f" ✗ (unusual — expected 10-60V)")
    else:
        print("    DC Voltage:  (skipped — need count > 14)")

    if len(regs) > 5:
        ac_out_v = regs[5] * 0.1  # addr 105
        print(f"    AC Out:      {ac_out_v:.1f} V", end="")
        if 100 < ac_out_v < 140:
            print(" ✓")
        else:
            print(f" ({'off/standby' if ac_out_v == 0 else 'unusual'})")
    else:
        print("    AC Out:      (skipped — need count > 5)")

    if len(regs) > 1:
        status = regs[1]  # addr 101
        status_names = {0: "Power Save", 1: "AC Normal", 2: "AC Abnormal", 3: "Inverting", 4: "Fault"}
        print(f"    Status:      {status} ({status_names.get(status, 'unknown')})")

    if len(regs) > 2:
        fault = regs[2]  # addr 102
        print(f"    Fault Code:  {fault}", end="")
        if fault == 0:
            print(" ✓ (no fault)")
        else:
            print(f" ✗ (active fault!)")

    print()
    print("=== Cable test PASSED — communication is working ===")

    client.close()
    return True


def _udev_prop(dev, key):
    """Read a single udev property for a device, or return empty string."""
    try:
        import subprocess
        out = subprocess.check_output(
            ["udevadm", "info", "--query=property", f"--name={dev}"],
            stderr=subprocess.DEVNULL, text=True
        )
        for line in out.splitlines():
            if line.startswith(key + "="):
                return line.split("=", 1)[1]
    except Exception:
        pass
    return ""


def select_port():
    """List available USB serial devices and let the user pick one."""
    import glob
    devices = sorted(glob.glob("/dev/ttyUSB*"))
    if not devices:
        print("Error: No /dev/ttyUSB* devices found.")
        print("Please plug in your USB-to-Serial converter.")
        sys.exit(1)

    print("Available USB serial devices:")
    print()
    for i, dev in enumerate(devices):
        vendor = _udev_prop(dev, "ID_VENDOR")
        model = _udev_prop(dev, "ID_MODEL")
        serial = _udev_prop(dev, "ID_SERIAL_SHORT")
        print(f"  [{i}] {dev}  —  {vendor or 'unknown'} / {model or 'unknown'} (serial: {serial or 'unknown'})")
    print()

    choice = input(f"Select device number [0]: ").strip()
    choice = int(choice) if choice else 0
    if not (0 <= choice < len(devices)):
        print("Error: Invalid selection.")
        sys.exit(1)
    return devices[choice]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Test Samlex EVO RS485 cable and communication")
    parser.add_argument("port", nargs="?", default=None, help="Serial port (e.g. /dev/ttyUSB0). Omit to select interactively.")
    parser.add_argument("--baud", type=int, default=9600, help="Baud rate (default: 9600)")
    parser.add_argument("--slave", type=int, default=1, help="Modbus slave address (default: 1)")
    parser.add_argument("--count", type=int, default=50, help="Number of holding registers to read from address 100 (default: 50)")
    args = parser.parse_args()

    port = args.port if args.port else select_port()
    ok = test_cable(port, args.baud, args.slave, args.count)
    sys.exit(0 if ok else 1)
