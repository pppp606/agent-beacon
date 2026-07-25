# ADR 0001: Minimal End-to-End Architecture

- Status: Accepted
- Date: 2026-07-24

## Context

When an AI agent (Claude Code, to start) needs human attention, signal it
with a physical LED. No message content is displayed — only a single bit of
state, "is attention needed?", is projected into the physical world.

Prototype hardware: Seeed Studio XIAO nRF52840 (onboard RGB LED, BLE).

Milestones:

1. **M1**: Uniquely identify a specific beacon and switch **that beacon's**
   onboard LED on/off from a Mac over BLE
2. **M2**: On when Claude Code starts waiting for a human, off once the human
   responds and work resumes

## The attention state model (product spec)

"Attention" in this product does not mean only "the AI is asking a question
or requesting approval" — it means **any state in which the AI has stopped
and handed control back to the human**, including normal completion.

| Agent state | LED |
|---|---|
| Working autonomously | OFF |
| Stopped, waiting for the human's next action (questions, approval requests, normal completion) | ON |

Under this definition, using Claude Code's `Stop` hook (turn ended = control
returned to the human) for attention-ON is not a technical workaround — it is
the direct implementation of the state model.

## Decision

### Overall structure

```
Claude Code
  → Hooks (.claude/settings.json)          … integrations/claude-code/
  → beaconctl on|off (CLI)                  … cli/
  → BLE GATT write (1 byte)                 … docs/protocol.md
  → XIAO nRF52840 firmware                  … firmware/
  → onboard LED
```

The only contract between layers is one byte: "attention = ON / OFF".
The firmware knows nothing about Claude Code; the CLI knows nothing about
LED pins.

### Firmware: Arduino + Seeed nRF52 Boards (non-mbed) + Bluefruit

- BSP: **Seeed nRF52 Boards** (a fork of the Adafruit nRF52 core; FreeRTOS +
  SoftDevice + Bluefruit52Lib). Seeed's official wiki recommends this one for
  BLE work (the mbed variant targets TinyML).
- BLE: `bluefruit.h` peripheral + custom GATT service + writable
  characteristic. The official `custom_hrm.ino` example shows the same
  implementation pattern.
- Build/flash: `arduino-cli` (FQBN: `Seeeduino:nrf52:xiaonRF52840`). If
  serial flashing fails, UF2 is the fallback (double-tap reset → copy onto
  the mounted mass-storage drive).
- LED: onboard RGB LED (RED=P0.26, GREEN=P0.30, BLUE=P0.06). **Active low**
  (`digitalWrite(pin, LOW)` lights it). v0.1 uses red only.

Alternatives considered:

| Option | Why rejected |
|---|---|
| CircuitPython | Easy to start, but the worst position for the future move to battery power (deep sleep) |
| Zephyr / nRF Connect SDK | The favorite for the eventual custom board, but overkill for a one-characteristic prototype. The GATT design carries over as-is, so re-evaluate when the custom board happens |
| PlatformIO | XIAO nRF52840 support depends on a community fork with unreliable maintenance |

### BLE protocol: one characteristic, one byte

See `docs/protocol.md`. One custom service + one writable characteristic.
A single byte encodes color (bits 0-2) and blink (bit 3); only `0x00` is
dark. Unknown values fail safe (ON, falling back to red — rationale in
protocol.md). Color and blink exist so that when several Claude Code
sessions share one beacon their states can be told apart. Which session gets
which color/pattern is the integration layer's (M2's) responsibility; the
beacon just displays the byte it receives.

### Beacon identity

Every beacon carries a factory-programmed permanent unique ID (nRF52840 FICR
DEVICEID), and the Mac addresses a beacon by that ID — never by device name
or scan order. Details and rationale in [ADR 0002](0002-beacon-identity.md).

### Mac-side CLI: Python + bleak

- **bleak** is the BLE library with macOS (CoreBluetooth) support and the
  most active maintenance as of 2026 (v3.0.1 released 2026-03; the noble
  family breaks builds often and releases rarely).
- Only two commands: `beaconctl on` / `beaconctl off`. Scan by service UUID
  → connect → write one byte → disconnect.
- No resident daemon. State transitions (a human wait starting) are
  infrequent, so connect-per-write is enough. Consider a daemon only if
  connection latency ever becomes a felt problem.

### Claude Code integration: official Hooks

The LED is controlled from hooks in `.claude/settings.json`. No screen
parsing, no tmux watching.

| State | Hook event | Session state |
|---|---|---|
| Waiting for approval | `Notification` (matcher: `permission_prompt`) | waiting |
| Waiting for input (turn ended) | `Stop` | waiting |
| Waiting for input (idle notice) | `Notification` (matcher: `idle_prompt`) | waiting |
| Human submitted a prompt | `UserPromptSubmit` | working |
| Tool execution resumed after approval | `PreToolUse` | working |
| Session started/resumed | `SessionStart` | working |
| Session ended | `SessionEnd` | (removed) |

The LED reflects not a single session but the **aggregate over all sessions**
(ON if any one is waiting). Implementation:
`integrations/claude-code/attention_hook.py` — the hook itself only updates
session state files and exits immediately; a detached convergence process
does the BLE write (never blocking Claude Code).

Notes:

- Why `Stop`: the `idle_prompt` notification lags behind idle detection, so
  `Stop` is the reliable way to catch "waiting for input" the moment a turn
  ends. Enabling both is idempotent and harmless.
- Why `PreToolUse`: after a permission approval no `UserPromptSubmit` fires,
  so resumed tool execution is the OFF trigger.
- `PreToolUse` fires at high frequency, so BLE is written only when the
  aggregate changes (desired/applied comparison). A failed BLE write leaves
  `applied` untouched, so the next event retries automatically —
  convergence to the latest state is guaranteed.

## Non-goals

- General notifications (Slack etc.), displaying message content,
  UI/dashboards, cloud/account management
- BLE pairing/bonding (open write; acceptable under the prototype threat
  model, re-evaluated for the custom board)
- Multi-beacon management UI or simultaneous control (but **the identity
  mechanism itself ships in v0.1** — ADR 0002)
- A resident bridge daemon, battery-power tuning
- Zephyr migration (deferred until the custom board stage)

## Consequences

- Because the firmware and the integration are separated by a one-byte
  protocol, supporting agents other than Claude Code only means adding hooks.
- Arduino/Bluefruit makes the prototype fastest, but reaching µA-order power
  draw will require a rewrite in Zephyr. The GATT design (UUIDs, values)
  stays the same, so the CLI and hooks survive unchanged.
- Connect-per-write means roughly 1-2s from hook firing to LED change.
  Acceptable for an attention signal.

## References

- Claude Code Hooks: https://code.claude.com/docs/en/hooks.md / https://code.claude.com/docs/en/hooks-guide.md
- Seeed XIAO nRF52840 Wiki: https://wiki.seeedstudio.com/XIAO_BLE/
- Seeed nRF52 core (Adafruit fork): https://github.com/Seeed-Studio/Adafruit_nRF52_Arduino
- Bluefruit custom service example: https://github.com/adafruit/Adafruit_nRF52_Arduino/blob/master/libraries/Bluefruit52Lib/examples/Peripheral/custom_hrm/custom_hrm.ino
- bleak: https://bleak.readthedocs.io/
