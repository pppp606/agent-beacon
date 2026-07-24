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


@pytest.mark.parametrize("on_args,expected", [
    (["on"], "0x01 on red"),
    (["on", "--color", "yellow", "--blink"], "0x0b on yellow blink"),
    (["on", "--color", "cyan"], "0x06 on cyan"),
    (["off"], "0x00 off"),
])
def test_write_then_read_back(on_args, expected):
    ctl(*on_args)
    assert ctl("status").strip() == expected
