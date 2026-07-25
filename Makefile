PY_DEPS = -p 3.11 --with pytest --with "bleak>=0.22,<3"
FQBN ?= Seeeduino:nrf52:xiaonRF52840Sense

.PHONY: test test-e2e firmware flash lite

# Host tests: CLI units + firmware decode logic (compiled natively) + shared vectors
test:
	uv run $(PY_DEPS) pytest -q tests

# Adds the BLE round-trip against real hardware (beacon in range, Bluetooth on)
test-e2e:
	BEACON_E2E=1 uv run $(PY_DEPS) pytest -q tests

# Zero-dependency client for hosts that cannot install libraries (ADR 0005)
lite:
	swiftc -O cli/beaconctl_lite.swift -o cli/beaconctl-lite

firmware:
	arduino-cli compile --fqbn $(FQBN) firmware/agent_beacon

flash: firmware
	arduino-cli upload -p $$(arduino-cli board list --format json | uv run python -c "import json,sys; bs=[p['port']['address'] for p in json.load(sys.stdin).get('detected_ports',[]) if p.get('matching_boards')]; print(bs[0])") --fqbn $(FQBN) firmware/agent_beacon
