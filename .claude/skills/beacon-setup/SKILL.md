---
name: beacon-setup
description: Set up this Mac to drive an Agent Beacon — scan for the beacon, assign a host color, verify the BLE round-trip, and install the Claude Code hooks. Use when connecting a new Mac, switching to a different beacon unit, or repairing a broken setup.
---

# Agent Beacon setup

Walk the user through connecting this Mac to an Agent Beacon. All commands
run from the repository root. Do the steps in order; each has a verification
before moving on.

## 1. Preflight

- `uv --version` — if missing, tell the user to `brew install uv` first.
- Ask the user to confirm the beacon is powered (USB plugged in).

## 2. Find the beacon

```sh
uv run cli/beaconctl.py scan
```

- First run may trigger a macOS Bluetooth permission prompt for the
  terminal — tell the user to allow it, then rerun.
- **No beacon found**: check Bluetooth is on (Control Center), beacon
  powered, and the terminal has Bluetooth permission (System Settings >
  Privacy & Security > Bluetooth). A beacon fresh from flashing needs a
  few seconds.
- **Multiple beacons**: ask the user which one (the closest has the RSSI
  nearest to 0; suggest powering only the target). Never guess.

## 3. Assign identity and color

Ask the user which color this Mac should own. Colors are per-host
assignments for sharing one beacon (ADR 0004): red / green / blue, each on
exactly one Mac. If this is the only Mac, recommend the default red. If
other Macs already use the beacon, ask which colors are taken.

```sh
uv run cli/beaconctl.py use <short-id> --color <color>
```

## 4. Verify the BLE round-trip

```sh
uv run cli/beaconctl.py on
uv run cli/beaconctl.py status   # expect the chosen color
uv run cli/beaconctl.py off
uv run cli/beaconctl.py status   # expect "0x00 off" (or other hosts' colors)
```

Ask the user to confirm the LED physically lit in their color. If `status`
is right but no light: another host's dismissed state may be involved —
run `off` then `on` again and recheck.

## 5. Install the Claude Code hooks

Ask whether to enable for all projects (default) or only this project:

```sh
python3 integrations/claude-code/install.py                       # global
python3 integrations/claude-code/install.py --settings .claude/settings.json  # this project only
```

The installer is idempotent and backs up the settings file; rerunning after
moving the repository fixes the hook paths.

## 6. Final check

- Hooks load at session start: already-running Claude Code sessions must be
  restarted to pick them up.
- After the next session event, `~/.local/state/agent-beacon/hook.log`
  should show the event and the write. The live test: end a turn (Stop) →
  the LED lights in this Mac's color; reply → it goes dark.

## Notes

- The Short ID is permanent (burned into the nRF52840), identical from
  every Mac, and broadcast in advertising — so `scan` on any Mac finds it.
- Multi-Mac sharing needs no beacon-side work at all; each Mac only needs
  its own `use <id> --color <c>` plus the hooks.
- Sense boards support double-tap to dismiss the display; a new wait from
  any Mac re-lights it (docs/protocol.md).
- Troubleshooting beyond this: integrations/claude-code/README.md.
