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


def firmware_display(harness, state: int, phase: int) -> dict:
    out = subprocess.run([str(harness), str(state), str(phase)], check=True,
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


# ---------- v0.2: cycling display (ADR 0004) ----------

@pytest.mark.parametrize("case", VECTORS["display"],
                         ids=lambda c: f"0x{c['state']:02x}-p{c['phase']}")
def test_firmware_display(harness, case):
    got = firmware_display(harness, case["state"], case["phase"])
    expected = {k: case[k] for k in ("red", "green", "blue", "blink")}
    assert got == expected


def test_display_shows_one_color_at_a_time_and_covers_all(harness):
    """For any state, each phase lights at most one color, non-zero states
    always light exactly one, and a full cycle visits every active bit."""
    for state in range(16):
        decoded = firmware_decode(harness, state)
        active = {c for c in ("red", "green", "blue") if decoded[c]}
        seen = set()
        for phase in range(4):
            got = firmware_display(harness, state, phase)
            lit = {c for c in ("red", "green", "blue") if got[c]}
            assert len(lit) == (1 if state != 0 else 0), \
                f"state 0x{state:02x} phase {phase} lights {lit}"
            assert got["blink"] == decoded["blink"]
            seen |= lit
        assert seen == active, f"state 0x{state:02x} cycle missed a color"


# ---------- v0.2: host read-modify-write (ADR 0004) ----------

@pytest.mark.parametrize("case", VECTORS["rmw"],
                         ids=lambda c: f"{c['op']}-0x{c['current']:02x}-bit{c['bit']}")
def test_cli_rmw(case):
    if case["op"] == "set":
        got = beaconctl.rmw_set(case["current"], case["bit"], case["blink"])
    else:
        got = beaconctl.rmw_clear(case["current"], case["bit"])
    assert got == case["result"]


def test_rmw_never_touches_other_hosts_color_bits():
    for current in range(256):
        for bit in (0x01, 0x02, 0x04):
            others = current & beaconctl.COLOR_MASK & ~bit
            after_set = beaconctl.rmw_set(current, bit, False)
            assert after_set & beaconctl.COLOR_MASK & ~bit == others
            after_clear = beaconctl.rmw_clear(current, bit)
            assert after_clear & beaconctl.COLOR_MASK & ~bit == others


def test_rmw_clear_never_leaves_a_lit_byte_without_color():
    """Invariant: a clear either leaves a color bit set or writes exactly
    0x00 — never a non-zero byte that fail-safes to red (docs/protocol.md)."""
    for current in range(256):
        for bit in (0x01, 0x02, 0x04):
            got = beaconctl.rmw_clear(current, bit)
            if got & beaconctl.COLOR_MASK == 0:
                assert got == 0x00, f"0x{current:02x} clear bit{bit} -> 0x{got:02x}"
