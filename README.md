# agent-beacon

**A physical light for when AI agents need your attention.**

A device that lights a physical LED on your desk when an AI agent needs human
input, approval, or judgment.

The beacon itself knows nothing about AI agents, hooks, or webhooks. It exposes
a tiny BLE protocol, while integrations live entirely on the host side. Claude
Code is the first integration, but anything that can invoke `beaconctl` can use
it.

It displays no message content — the only thing it projects into the physical
world is a single state: **"attention required."**

## Architecture

```
Claude Code → Hooks → beaconctl (CLI) → BLE → XIAO nRF52840 → LED
```

| Directory | Responsibility |
|---|---|
| `firmware/` | Firmware for the XIAO nRF52840 (Arduino + Bluefruit). Knows nothing about AI agents or integrations |
| `cli/` | Mac-side CLI `beaconctl` (Python + bleak) |
| `integrations/claude-code/` | Claude Code hook settings and the hook script |
| `docs/` | Protocol spec and design decisions (ADRs) |

## Usage

See [firmware/README.md](firmware/README.md) for flashing the firmware and
[integrations/claude-code/README.md](integrations/claude-code/README.md) for
the Claude Code integration.

```sh
uv run cli/beaconctl.py scan                        # list nearby beacons with their short IDs
uv run cli/beaconctl.py use 5e6f7a8b                # save the target beacon ID to config
uv run cli/beaconctl.py on                          # raise this host's attention bit
uv run cli/beaconctl.py off                         # clear this host's attention bit
uv run cli/beaconctl.py status                      # read back the current state
```

Beacons are identified by the nRF52840's factory-unique ID, never by device
name or scan order ([ADR 0002](docs/adr/0002-beacon-identity.md)).
The first run will ask you to grant Bluetooth permission to your terminal.

### Sharing one beacon across multiple Macs (M3)

Each Mac is assigned one color bit (red/green/blue,
[ADR 0004](docs/adr/0004-multi-host-sharing.md)). `on`/`off` use
read-modify-write to touch **only this host's bit**, so one Mac clearing its
wait never hides another Mac's.

```sh
# Mac A (the default red is fine)
uv run cli/beaconctl.py use 5e6f7a8b

# Mac B
uv run cli/beaconctl.py use 5e6f7a8b --color green
```

When several hosts are waiting at once, the beacon cycles through their
colors, 800ms each.

## Development and testing

Development is test-driven (see [ADR 0003](docs/adr/0003-test-strategy.md)).
To change the protocol, update `docs/protocol.md` and
`tests/protocol_vectors.json` first, watch the tests fail, then implement.

```sh
make test        # host tests: CLI units + firmware decode logic + shared vectors
make test-e2e    # + BLE round-trip against real hardware (beacon in range, Bluetooth on)
make firmware    # build the firmware
make flash       # build and flash
```

Visually checking that the LED actually lights is done only as the final
acceptance test.

## Documentation

- Design decisions: [docs/adr/0001-minimal-e2e-architecture.md](docs/adr/0001-minimal-e2e-architecture.md)
- Beacon identity: [docs/adr/0002-beacon-identity.md](docs/adr/0002-beacon-identity.md)
- Test strategy: [docs/adr/0003-test-strategy.md](docs/adr/0003-test-strategy.md)
- Multi-Mac sharing (M3): [docs/adr/0004-multi-host-sharing.md](docs/adr/0004-multi-host-sharing.md)
- BLE protocol: [docs/protocol.md](docs/protocol.md)
