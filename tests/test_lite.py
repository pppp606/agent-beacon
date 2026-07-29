"""beaconctl-lite (Swift, ADR 0005) must speak the exact same protocol as the
Python CLI: its RMW logic is checked against the shared vectors, and its state
description against the Python implementation for every possible byte. Driven
through the binary's test-only _rmw/_describe commands (pure logic, no
Bluetooth). Skipped where no Swift toolchain is installed."""

import shutil
import subprocess
from pathlib import Path

import pytest

import beaconctl
from test_protocol import VECTORS

ROOT = Path(__file__).resolve().parents[1]
SWIFTC = shutil.which("swiftc")

pytestmark = pytest.mark.skipif(
    SWIFTC is None, reason="swiftc not available (Xcode Command Line Tools)")


@pytest.fixture(scope="session")
def lite(tmp_path_factory):
    # The script ships uncompiled (shebang + `swift` script mode), but the
    # exhaustive tests below spawn it hundreds of times — compile once here.
    exe = tmp_path_factory.mktemp("lite") / "beaconctl-lite"
    subprocess.run(
        [SWIFTC, "-O", str(ROOT / "cli" / "beaconctl_lite.swift"), "-o", str(exe)],
        check=True,
    )
    return exe


def run(exe, *args: str) -> str:
    return subprocess.run([str(exe), *args], check=True,
                          capture_output=True, text=True).stdout.strip()


@pytest.mark.parametrize("case", VECTORS["rmw"],
                         ids=lambda c: f"{c['op']}-0x{c['current']:02x}-bit{c['bit']}")
def test_swift_rmw_matches_vectors(lite, case):
    got = run(lite, "_rmw", case["op"], str(case["current"]), str(case["bit"]),
              "1" if case.get("blink") else "0")
    assert got == str(case["result"])


def test_swift_rmw_matches_python_exhaustively(lite):
    for current in (0x00, 0x01, 0x03, 0x07, 0x0B, 0x0F, 0x11, 0x9A, 0xFF):
        for bit in (0x01, 0x02, 0x04):
            for blink in (False, True):
                got = run(lite, "_rmw", "set", str(current), str(bit),
                          "1" if blink else "0")
                assert got == str(beaconctl.rmw_set(current, bit, blink))
            got = run(lite, "_rmw", "clear", str(current), str(bit), "0")
            assert got == str(beaconctl.rmw_clear(current, bit))


def test_swift_describe_matches_python_for_every_state(lite):
    for state in range(256):
        assert run(lite, "_describe", str(state)) == beaconctl.describe_state(state)
