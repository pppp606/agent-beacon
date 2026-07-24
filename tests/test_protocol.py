"""Protocol conformance: firmware decode (via compiled C++ harness) and CLI
encode are both tested against tests/protocol_vectors.json, so the two sides
of the BLE protocol cannot drift apart."""

import json
import subprocess
from pathlib import Path

import pytest

import beaconctl

ROOT = Path(__file__).resolve().parents[1]
VECTORS = json.loads((ROOT / "tests" / "protocol_vectors.json").read_text())


@pytest.fixture(scope="session")
def harness(tmp_path_factory):
    exe = tmp_path_factory.mktemp("harness") / "attention_decode"
    subprocess.run(
        ["c++", "-std=c++17", "-Wall", "-Wextra", "-Werror",
         str(ROOT / "tests" / "firmware_harness.cpp"), "-o", str(exe)],
        check=True,
    )
    return exe


def firmware_decode(harness, state: int) -> dict:
    out = subprocess.run([str(harness), str(state)], check=True,
                         capture_output=True, text=True).stdout.split()
    red, green, blue, blink = (x == "1" for x in out)
    return {"red": red, "green": green, "blue": blue, "blink": blink}


@pytest.mark.parametrize("case", VECTORS["decode"],
                         ids=lambda c: f"0x{c['state']:02x}-{c['note']}")
def test_firmware_decode(harness, case):
    got = firmware_decode(harness, case["state"])
    expected = {k: case[k] for k in ("red", "green", "blue", "blink")}
    assert got == expected


@pytest.mark.parametrize("case", VECTORS["encode"],
                         ids=lambda c: f"{c['color']}{'-blink' if c['blink'] else ''}")
def test_cli_encode(case):
    assert beaconctl.encode_state(case["color"], case["blink"]) == case["state"]


@pytest.mark.parametrize("case", VECTORS["encode"],
                         ids=lambda c: f"{c['color']}{'-blink' if c['blink'] else ''}")
def test_encode_decode_roundtrip(harness, case):
    """What the CLI encodes, the firmware must light as that exact color."""
    state = beaconctl.encode_state(case["color"], case["blink"])
    got = firmware_decode(harness, state)
    color_bits = beaconctl.COLORS[case["color"]]
    assert got == {
        "red": bool(color_bits & 0x01),
        "green": bool(color_bits & 0x02),
        "blue": bool(color_bits & 0x04),
        "blink": case["blink"],
    }


def test_off_is_the_only_dark_value(harness):
    """Fail-safe invariant (docs/protocol.md): every non-zero byte lights up."""
    for state in range(256):
        got = firmware_decode(harness, state)
        lit = got["red"] or got["green"] or got["blue"]
        assert lit == (state != 0), f"state 0x{state:02x}"
