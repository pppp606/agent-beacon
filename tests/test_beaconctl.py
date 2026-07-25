"""Unit tests for beaconctl's pure logic: advertisement parsing, target
resolution, and state display. No BLE hardware involved."""

from types import SimpleNamespace

import beaconctl


def adv(manufacturer_data, name="AgentBeacon"):
    return SimpleNamespace(manufacturer_data=manufacturer_data,
                           local_name=name, rssi=-40)


def beacon(short_id_int, name="AgentBeacon"):
    payload = short_id_int.to_bytes(4, "little")
    device = object()
    a = adv({beaconctl.MANUFACTURER_ID: payload}, name)
    return (device, a, beaconctl.short_id_from_adv(a))


class TestShortIdFromAdv:
    def test_parses_little_endian_short_id(self):
        a = adv({beaconctl.MANUFACTURER_ID: bytes.fromhex("d124a346")})
        assert beaconctl.short_id_from_adv(a) == "46a324d1"

    def test_none_without_our_manufacturer_id(self):
        assert beaconctl.short_id_from_adv(adv({0x004C: b"\x01\x02\x03\x04"})) is None
        assert beaconctl.short_id_from_adv(adv({})) is None

    def test_none_when_payload_too_short(self):
        assert beaconctl.short_id_from_adv(
            adv({beaconctl.MANUFACTURER_ID: b"\x01\x02"})) is None


class TestPickTarget:
    def test_explicit_id_found(self):
        b1, b2 = beacon(0x11111111), beacon(0x22222222)
        device, message = beaconctl.pick_target([b1, b2], "22222222")
        assert device is b2[0]
        assert message is None

    def test_explicit_id_not_found(self):
        device, message = beaconctl.pick_target([beacon(0x11111111)], "deadbeef")
        assert device is None
        assert "deadbeef" in message and "11111111" in message

    def test_no_id_single_beacon_is_used_with_hint(self):
        b1 = beacon(0x11111111)
        device, message = beaconctl.pick_target([b1], None)
        assert device is b1[0]
        assert "beaconctl use 11111111" in message

    def test_no_id_multiple_beacons_is_an_error(self):
        device, message = beaconctl.pick_target(
            [beacon(0x11111111), beacon(0x22222222)], None)
        assert device is None
        assert "11111111" in message and "22222222" in message

    def test_never_matches_by_device_name(self):
        b1 = beacon(0x11111111, name="deadbeef")
        device, _ = beaconctl.pick_target([b1], "deadbeef")
        assert device is None


class TestDescribeState:
    def test_off(self):
        assert beaconctl.describe_state(0x00) == "off"

    def test_single_host_colors(self):
        assert beaconctl.describe_state(0x01) == "on red"
        assert beaconctl.describe_state(0x02) == "on green"
        assert beaconctl.describe_state(0x0C) == "on blue blink"

    def test_multiple_hosts_read_as_cycle(self):
        """v0.2: several color bits mean several waiting hosts, shown cycling."""
        assert beaconctl.describe_state(0x03) == "on red+green (cycle)"
        assert beaconctl.describe_state(0x07) == "on red+green+blue (cycle)"
        assert beaconctl.describe_state(0x0B) == "on red+green (cycle) blink"

    def test_fail_safe_values_read_as_red(self):
        assert beaconctl.describe_state(0x10) == "on red (fail-safe)"
        assert beaconctl.describe_state(0x08) == "on red (fail-safe) blink"
