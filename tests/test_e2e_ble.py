"""Hardware-in-the-loop round-trip: write a state over BLE, read it back via
`beaconctl status`. Needs a flashed beacon in range and Bluetooth on, so it is
gated behind BEACON_E2E=1 (run with `make test-e2e`).

This verifies the full chain except the photons; whether the LED physically
lights stays a manual check (docs/adr/0003-test-strategy.md)."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

CTL = Path(__file__).resolve().parents[1] / "cli" / "beaconctl.py"

pytestmark = pytest.mark.skipif(
    os.environ.get("BEACON_E2E") != "1",
    reason="hardware test; set BEACON_E2E=1 with a beacon in range",
)


def ctl(*args: str) -> str:
    result = subprocess.run([sys.executable, str(CTL), *args],
                            capture_output=True, text=True, timeout=90)
    assert result.returncode == 0, result.stderr
    return result.stdout


def check(*args: str, expect: str) -> None:
    ctl(*args)
    assert ctl("status").strip() == expect


def test_multi_host_read_modify_write_round_trip():
    """Plays both hosts of the ADR 0004 scenario from one Mac: on/off are
    read-modify-write, so the second host's wait must survive the first
    host's clear."""
    check("off", "--color", "white", expect="0x00 off")  # reset all hosts
    check("on", "--color", "red", expect="0x01 on red")
    check("on", "--color", "green", expect="0x03 on red+green (cycle)")
    check("off", "--color", "red", expect="0x02 on green")
    check("off", "--color", "green", expect="0x00 off")


def test_last_host_out_also_clears_the_blink_bit():
    check("off", "--color", "white", expect="0x00 off")
    check("on", "--color", "red", "--blink", expect="0x09 on red blink")
    check("off", "--color", "red", expect="0x00 off")
