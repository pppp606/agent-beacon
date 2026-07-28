# agent-beacon

**A physical light for when AI agents need your attention.**

A device that lights a physical LED on your desk when an AI agent needs human
input, approval, or judgment.

Unlike USB busylights that are wired to a single computer, an Agent Beacon is
a wireless BLE device that **multiple machines share at once**: give each Mac
its own color, and one beacon tells you *which* machine is waiting for you —
without any Mac being able to erase another's wait. One beacon on the desk
covers your laptop, your desktop, and the machine in the other room.

The beacon itself knows nothing about AI agents, hooks, or webhooks. It exposes
a tiny BLE protocol, while integrations live entirely on the host side. Claude
Code is the first integration, but anything that can invoke `beaconctl` can use
it.

It displays no message content — the only thing it projects into the physical
world is a single state: **"attention required."**

## What it does

- **Lights up when an agent hands control back to you** — questions, approval
  requests, or a finished task — and goes dark while agents work autonomously
- **One beacon, several machines**: each host owns a color (red/green/blue).
  When several are waiting, the LED cycles through their colors (800ms each)
  instead of blending them, so you can always tell who is calling
- **Display timeout**: a wait that has been lit for 10 minutes means nobody
  is around to see it — the light goes dark on its own, per color. The state
  survives: `beaconctl status` still reports every waiting host
- **Double-tap to dismiss** (Sense boards): tap the beacon twice to turn the
  display off immediately — same semantics as the timeout firing early
- **Every new wait re-lights** the display, even after a tap or timeout
- **Fail-safe by design**: a missed notification is the worst failure mode,
  so unknown protocol values light red instead of being ignored, and state
  survives disconnects and host crashes

## Supported hardware

| Board | Status | Notes |
|---|---|---|
| Seeed XIAO nRF52840 | ✅ | Everything except tap-to-dismiss |
| Seeed XIAO nRF52840 **Sense** | ✅ | Adds double-tap dismiss via the onboard IMU |

Both run the **same firmware binary** — the IMU is probed at boot and the tap
feature enables itself only where the hardware exists. Note that the
bootloader's USB name is not a reliable way to tell the two boards apart;
when in doubt, the Sense has a metal-shielded microphone with a tiny hole on
the board face.

## Architecture

```
Claude Code → Hooks → beaconctl (CLI) → BLE → XIAO nRF52840 → LED
```

| Directory | Responsibility |
|---|---|
| `firmware/` | Firmware for the XIAO nRF52840 (Arduino + Bluefruit). Knows nothing about AI agents or integrations |
| `cli/` | Mac-side CLI `beaconctl` (Python + bleak) |
| `integrations/claude-code/` | Claude Code hook settings, hook script, and installer |
| `docs/` | Protocol spec and design decisions (ADRs) |

## Getting started

**1. Flash the firmware** (once per beacon): see
[firmware/README.md](firmware/README.md).

**2. Set up each Mac** — the guided way: open Claude Code in this repository
and run

```
/beacon-setup
```

It scans for the beacon, assigns this Mac's color, verifies the BLE
round-trip, and installs the Claude Code hooks.

Or manually:

```sh
uv run cli/beaconctl.py scan                 # find the beacon's short ID
uv run cli/beaconctl.py use <short-id>       # save it (add --color green|blue on extra Macs)
uv run cli/beaconctl.py on                   # verify: LED lights in your color
uv run cli/beaconctl.py off
python3 integrations/claude-code/install.py  # install the Claude Code hooks
```

Requirements: `python3` (ships with macOS) and [`uv`](https://docs.astral.sh/uv/)
(fetches the BLE library automatically — nothing else to install). The first
run asks you to grant Bluetooth permission to your terminal. Beacons are
identified by the nRF52840's factory-unique ID broadcast in advertising —
never by device name or scan order ([ADR 0002](docs/adr/0002-beacon-identity.md))
— so the same `use <short-id>` works from any machine.

## Everyday operation

With the hooks installed there is nothing to operate: the LED lights in this
Mac's color when Claude Code stops for you, and goes dark when you respond.

| You see | It means |
|---|---|
| Dark | Every agent is working (or waits timed out / were dismissed) |
| One color, steady | That machine is waiting for you |
| Colors cycling | Several machines are waiting — one color per host |
| Blinking | A host raised the shared blink flag (urgent, opt-in) |

Things you can do:

- **Double-tap the beacon** (Sense): display off now — "I saw it." Any new
  wait from any machine lights it again
- `uv run cli/beaconctl.py status` — read the truth over BLE at any time,
  including waits whose display timed out
- `uv run cli/beaconctl.py on --blink` — manual raise with the blink flag
  (also available to integrations for high-priority waits)

## Sharing one beacon across multiple Macs

Each Mac is assigned one color bit (red/green/blue,
[ADR 0004](docs/adr/0004-multi-host-sharing.md)). `on`/`off` use
read-modify-write to touch **only this host's bit**, so one Mac clearing its
wait never hides another Mac's. The beacon accepts several concurrent
connections and keeps advertising while connected, so every Mac can reach it
at any time.

```sh
# Mac A (the default red is fine)
uv run cli/beaconctl.py use 5e6f7a8b

# Mac B
uv run cli/beaconctl.py use 5e6f7a8b --color green

# Mac C
uv run cli/beaconctl.py use 5e6f7a8b --color blue
```

No beacon-side work is needed — run `/beacon-setup` (or the two commands
above plus the hook installer) on each additional Mac and you are done.

**Three hosts per beacon is a deliberate ceiling**, not a technical one: on
a tiny LED, red/green/blue are the only colors a human reliably tells apart
at a glance, and a light you have to think about defeats its purpose. To go
beyond three machines, add beacons and let *placement* do the identifying —
machine identity becomes (beacon position × color), and both are things you
perceive without thinking:

```
desk left           desk right
● beacon L          ● beacon R
red   = laptop      red   = build server
green = desktop     green = test rig
blue  = home lab    blue  = spare
```

Each beacon is addressed by its factory-unique ID, so any Mac can point at
any beacon with one `use` command — grouping is purely a matter of which ID
each Mac is configured to write to.

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
- Multi-Mac sharing: [docs/adr/0004-multi-host-sharing.md](docs/adr/0004-multi-host-sharing.md)
- BLE protocol: [docs/protocol.md](docs/protocol.md)
