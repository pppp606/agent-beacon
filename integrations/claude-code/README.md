# integrations/claude-code

The bridge between official Claude Code hooks and the Agent Beacon.

## Behavior

State model (ADR 0001): **OFF while the agent works autonomously**, **ON
once it stops and hands control back to the human** (questions, approval
requests, and normal completion included).

| Hook event | Meaning | Session state |
|---|---|---|
| `Stop` | Turn ended (control returned to the human) | waiting |
| `Notification` (`idle_prompt`\|`permission_prompt`) | Waiting for input / approval | waiting |
| `UserPromptSubmit` | Human submitted a prompt | working |
| `PreToolUse` | Tool execution (incl. resuming after approval) | working |
| `SessionStart` | Session started/resumed | working |
| `SessionEnd` | Session ended | removed |

Multiple sessions are aggregated per `session_id`:
**the LED is ON if any one session is waiting, OFF once all are working**.

The hook itself only updates local files and exits immediately (never
blocking Claude Code); the BLE write is done by a detached `--sync` process
that converges to the latest state via a desired/applied file pair. An event
reaches the LED in about 1-2 seconds (scanning is cut short the moment the
target beacon's advertising is seen, then connect and write).

Every waiting transition writes ON even when the beacon is already on: the
write refreshes the beacon's display-timeout clocks, so a display dismissed
by a double-tap or by the 10-minute timeout re-lights whenever a new wait
appears. It also heals drift after a beacon power-cycle or a manual
`beaconctl off`.

## Install

Guided (recommended): open Claude Code in this repository and run
`/beacon-setup` — it scans for the beacon, assigns this Mac's color,
verifies the BLE round-trip, and installs the hooks.

Scripted:

1. Set up the beacon first (`beaconctl use <id>` done — see the root README)
2. `python3 integrations/claude-code/install.py` — merges the hooks into
   `~/.claude/settings.json` (add `--settings <path>` for a project-local
   file). Idempotent, backs up the file, and resolves this repository's
   absolute path automatically; rerun it after moving the checkout

`settings.example.json` documents the resulting hook entries for manual
setups.

Requirements: `python3` (standard library only) and `uv` (the BLE write
process runs `uv run cli/beaconctl.py`).

To share one beacon across several Macs, configure a distinct color on each
Mac with `beaconctl use <id> --color <red|green|blue>`, then install the
same hooks on every Mac (ADR 0004). Since `on`/`off` read-modify-write only
this host's color bit, answering Mac A never clears Mac B's wait.

## State & debugging

State directory: `~/.local/state/agent-beacon/` (override with
`AGENT_BEACON_STATE_DIR`)

- `sessions/<session_id>` — each session's waiting / working
- `desired` / `applied` — the aggregate we want, and what was last written
  to the beacon
- `hook.log` — one line per handled event / write

If something misbehaves, check `hook.log` and `beaconctl status`.
A failed BLE write (beacon out of range etc.) leaves `applied` untouched,
so the next event retries automatically.

Tests: `make test` (drives the whole flow against a fake beaconctl; no
hardware needed)
