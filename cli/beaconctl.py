#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["bleak>=0.22,<3"]
# ///
"""beaconctl — control an Agent Beacon over BLE.

Usage:
  beaconctl scan [--timeout N]              List nearby beacons (short ID, name, RSSI)
  beaconctl use <short-id> [--color C]      Save the target beacon ID (and this
                                            host's assigned color) to config
  beaconctl on [--color C] [--blink]        Raise this host's attention bit
  beaconctl off [--color C]                 Clear this host's attention bit
  beaconctl status                          Read back the current state

Target resolution: --id > config file > the single beacon found nearby.
Never depends on device name or scan order (docs/adr/0002-beacon-identity.md).

Several Macs can share one beacon (docs/adr/0004-multi-host-sharing.md): each
host owns one color bit and on/off read-modify-write only that bit, so one
host clearing its wait never hides another host's. Assign colors with
`use <id> --color green` (default: red).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from bleak import BleakClient, BleakScanner
from bleak.exc import BleakError

SERVICE_UUID = "7b1f0001-9f02-4c60-b0f7-a9f6a4b0beac"
ATTENTION_STATE_UUID = "7b1f0002-9f02-4c60-b0f7-a9f6a4b0beac"
MANUFACTURER_ID = 0xFFFF  # prototype only (ADR 0002)

CONFIG_PATH = Path.home() / ".config" / "agent-beacon" / "config.json"

COLOR_MASK = 0x07
BLINK_BIT = 0x08
COLORS = {
    "red": 0x01, "green": 0x02, "blue": 0x04,
    "yellow": 0x03, "magenta": 0x05, "cyan": 0x06, "white": 0x07,
}
HOST_COLOR_DEFAULT = "red"


def encode_state(color: str, blink: bool) -> int:
    """State byte per docs/protocol.md: bit0-2 = R/G/B, bit3 = blink."""
    return COLORS[color] | (BLINK_BIT if blink else 0)


def rmw_set(current: int, color_bits: int, blink: bool) -> int:
    """Raise this host's color bit(s) on top of the current state
    (docs/protocol.md v0.2). The blink bit is shared across hosts."""
    return current | (color_bits & COLOR_MASK) | (BLINK_BIT if blink else 0)


def rmw_clear(current: int, color_bits: int) -> int:
    """Clear this host's color bit(s) only — other hosts' waits survive.
    When no color bit is left the whole byte goes to 0x00: a leftover blink
    or reserved bit would fail-safe to red and never turn off."""
    state = current & ~(color_bits & COLOR_MASK)
    if state & COLOR_MASK == 0:
        return 0x00
    return state


def describe_state(state: int) -> str:
    if state == 0x00:
        return "off"
    color_bits = state & COLOR_MASK
    blink = " blink" if state & BLINK_BIT else ""
    if color_bits == 0x00:
        return f"on red (fail-safe){blink}"
    names = [n for n, v in (("red", 0x01), ("green", 0x02), ("blue", 0x04))
             if color_bits & v]
    if len(names) == 1:
        return f"on {names[0]}{blink}"
    return f"on {'+'.join(names)} (cycle){blink}"


def load_config() -> dict:
    try:
        return json.loads(CONFIG_PATH.read_text())
    except FileNotFoundError:
        return {}


def save_config(config: dict) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(config, indent=2) + "\n")


def short_id_from_adv(adv) -> str | None:
    payload = adv.manufacturer_data.get(MANUFACTURER_ID)
    if payload is None or len(payload) < 4:
        return None
    return f"{int.from_bytes(payload[:4], 'little'):08x}"


async def discover_beacons(timeout: float) -> list[tuple[object, object, str]]:
    """Return (device, adv, short_id) for every Agent Beacon in range.
    Waits the full timeout — use only when enumerating (scan / no target ID)."""
    found = await BleakScanner.discover(
        timeout=timeout, return_adv=True, service_uuids=[SERVICE_UUID]
    )
    beacons = []
    for device, adv in found.values():
        short_id = short_id_from_adv(adv)
        if short_id is not None:
            beacons.append((device, adv, short_id))
    return beacons


async def find_beacon_fast(target_id: str, timeout: float):
    """Stop scanning the moment the target beacon is seen (the beacon
    advertises every ~150ms, so this typically returns in well under a
    second, versus discover() which always waits the full timeout)."""
    found = asyncio.Event()
    result = []

    def on_advertisement(device, adv):
        if short_id_from_adv(adv) == target_id and not result:
            result.append(device)
            found.set()

    async with BleakScanner(detection_callback=on_advertisement,
                            service_uuids=[SERVICE_UUID]):
        try:
            await asyncio.wait_for(found.wait(), timeout)
        except asyncio.TimeoutError:
            return None
    return result[0]


async def cmd_scan(args) -> int:
    beacons = await discover_beacons(args.timeout)
    if not beacons:
        print("No Agent Beacon found.", file=sys.stderr)
        return 1
    configured = load_config().get("beacon_id")
    for device, adv, short_id in beacons:
        marker = " (configured)" if short_id == configured else ""
        print(f"{short_id}  {adv.local_name or '?'}  RSSI {adv.rssi}{marker}")
    return 0


async def cmd_use(args) -> int:
    config = load_config()
    config["beacon_id"] = args.short_id.lower()
    if args.color:
        config["host_color"] = args.color
    save_config(config)
    color = config.get("host_color", HOST_COLOR_DEFAULT)
    print(f"Target beacon set to {config['beacon_id']}, host color {color} "
          f"({CONFIG_PATH})")
    return 0


def pick_target(beacons, target_id: str | None):
    """Pure target-resolution logic: (device | None, message | None).

    beacons is a list of (device, adv, short_id). Never depends on scan order:
    an explicit/configured ID must match exactly; without one, only a single
    nearby beacon is acceptable.
    """
    nearby = ", ".join(b[2] for b in beacons)
    if target_id is not None:
        for device, _adv, short_id in beacons:
            if short_id == target_id:
                return device, None
        return None, f"Beacon {target_id} not found. Nearby: {nearby}"
    if len(beacons) == 1:
        device, _adv, short_id = beacons[0]
        return device, (f"No beacon configured; using the only one found: {short_id}. "
                        f"Run `beaconctl use {short_id}` to pin it.")
    return None, (f"Multiple beacons found: {nearby}\n"
                  "Run `beaconctl use <short-id>` or pass --id.")


async def resolve_target(target_id: str | None, timeout: float):
    if target_id is not None:
        device = await find_beacon_fast(target_id, timeout)
        if device is None:
            print(f"Beacon {target_id} not found.", file=sys.stderr)
        return device
    beacons = await discover_beacons(timeout)
    if not beacons:
        print("No Agent Beacon found.", file=sys.stderr)
        return None
    device, message = pick_target(beacons, target_id)
    if message:
        print(message, file=sys.stderr)
    return device


async def find_configured_device(args):
    target_id = (args.id or load_config().get("beacon_id"))
    if target_id is not None:
        target_id = target_id.lower()
    return await resolve_target(target_id, args.timeout)


def host_color_bits(args) -> int:
    color = args.color or load_config().get("host_color", HOST_COLOR_DEFAULT)
    return COLORS[color]


async def cmd_rmw(args, op: str) -> int:
    """on/off are read-modify-write on this host's color bit (protocol v0.2),
    so several Macs can share one beacon without erasing each other's state."""
    device = await find_configured_device(args)
    if device is None:
        return 1
    bits = host_color_bits(args)
    async with BleakClient(device) as client:
        current = (await client.read_gatt_char(ATTENTION_STATE_UUID))[0]
        if op == "on":
            # Always write, even when the byte is unchanged: the write itself
            # refreshes the beacon's display-timeout clocks (docs/protocol.md),
            # so a tap-dismissed or timed-out display re-lights on every raise.
            new = rmw_set(current, bits, args.blink)
            await client.write_gatt_char(ATTENTION_STATE_UUID,
                                         bytes([new]), response=True)
        else:
            new = rmw_clear(current, bits)
            if new != current:
                await client.write_gatt_char(ATTENTION_STATE_UUID,
                                             bytes([new]), response=True)
    return 0


async def cmd_status(args) -> int:
    device = await find_configured_device(args)
    if device is None:
        return 1
    async with BleakClient(device) as client:
        value = await client.read_gatt_char(ATTENTION_STATE_UUID)
    state = value[0]
    print(f"0x{state:02x} {describe_state(state)}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="beaconctl", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p_scan = sub.add_parser("scan", help="list nearby beacons")
    p_scan.add_argument("--timeout", type=float, default=5.0)

    p_use = sub.add_parser("use", help="save target beacon ID to config")
    p_use.add_argument("short_id")
    p_use.add_argument("--color", choices=("red", "green", "blue"),
                       help="this host's assigned color bit (ADR 0004)")

    for name in ("on", "off", "status"):
        p = sub.add_parser(name, help={"on": "raise this host's attention bit",
                                       "off": "clear this host's attention bit",
                                       "status": "read back current state"}[name])
        p.add_argument("--id", help="target beacon short ID (overrides config)")
        p.add_argument("--timeout", type=float, default=5.0)
        if name in ("on", "off"):
            p.add_argument("--color", choices=sorted(COLORS), default=None,
                           help="color bits to operate on "
                                "(default: configured host color)")
        if name == "on":
            p.add_argument("--blink", action="store_true")

    args = parser.parse_args()
    if args.command == "scan":
        coro = cmd_scan(args)
    elif args.command == "use":
        coro = cmd_use(args)
    elif args.command == "status":
        coro = cmd_status(args)
    else:
        coro = cmd_rmw(args, args.command)
    try:
        return asyncio.run(coro)
    except BleakError as e:
        print(f"Bluetooth error: {e}", file=sys.stderr)
        if "turned off" in str(e).lower() or "powered_off" in str(e).lower():
            print("Turn on Bluetooth in Control Center / System Settings and retry.",
                  file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
