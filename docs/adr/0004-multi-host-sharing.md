# ADR 0004: Sharing One Beacon Across Multiple Macs (M3)

- Status: Implemented (2026-07-25)
- Date: 2026-07-24

## Context

We want several Macs to share a single beacon (Mac A/B/C → one beacon).

```
Mac A ─┐
Mac B ─┼── BLE ──→ ● Agent Beacon
Mac C ─┘
```

Two problems with the current state:

1. **BLE connections**: Bluefruit defaults to one concurrent connection;
   while one Mac is connected, advertising stops and the beacon becomes
   invisible to the other Macs
2. **State semantics**: if every Mac writes the same single byte, the result
   is last-write-wins — the instant Mac A writes its own OFF, Mac B's "wait"
   disappears

Also, the XIAO's onboard RGB LED is three elements in one package: lighting
several colors at once blends them into a single hue, making it impossible
to tell which Mac is calling.

## Decision

### 1. Color bit = host assignment (convention)

Use the protocol's color bits (bits 0-2) as **per-host assignments**:
Mac A = red (bit 0), Mac B = green (bit 1), Mac C = blue (bit 2).

Each Mac manipulates only its own bit via **read-modify-write**:

- Attention raised: read the current value → set your bit → write back
- Attention cleared: read the current value → clear **only your bit** →
  write back

The state byte thus always represents "the set of hosts currently waiting."
Neither the protocol (one byte) nor the firmware state needs changing, and
the separation from ADR 0001 — the beacon just displays the byte it
receives — is preserved.

**No queue.** This product's notification is "a state that must stay visible
until a human responds," not "an event consumed once displayed." The
set-based approach is idempotent (writing twice changes nothing), so lost
notifications, double-counting, and cleanup problems structurally cannot
exist.

### 2. Display: cycle through colors instead of blending

When several color bits are set, show **the set bits one color at a time in
rotation** (about 800ms per color) rather than blending (unreadable):

| State byte | Display |
|---|---|
| `0x01` | solid red |
| `0x03` | red → green → red → … |
| `0x07` | red → green → blue → red → … |

The blink bit (bit 3) applies orthogonally to the whole display (if anyone
requests blink, the entire display blinks). A single bit displays as before.

How it behaves:

```
t0  everyone working                     0x00  dark
t1  Mac A starts waiting                 0x01  solid red
t2  Mac B starts waiting too            0x03  red → green → …
t3  human replies on Mac A (A clears)    0x02  only green remains
```

The display is always recomputed from the current byte, so it never depends
on the timing or order of raises and clears.

Implementation: add a pure function "state byte + phase number → the one
color for that instant" to `attention_state.h`, following the ADR 0003
procedure (update protocol.md and the test vectors first).

### 3. Firmware: accept concurrent connections

Findings (confirmed against official sources):

- SoftDevice S140 supports up to 20 concurrent connections in the peripheral
  role (`BLE_GAP_ROLE_COUNT_COMBINED_MAX = 20`). Bluefruit's default is
  `Bluefruit.begin(1, 0)` = one concurrent connection
- Advertising stops automatically on connection and the library does not
  restart it
- `restartOnDisconnect(true)` restarts advertising only when **all**
  connections are gone (the restart condition is
  `0 == Bluefruit.Periph.connected()`). Pitfall: with one central still
  connected, a freed slot is never advertised

Changes (same shape as the official `bleuart_multi` example):

1. `Bluefruit.begin(4, 0)` — four concurrent connection slots (3 Macs +
   slack)
2. In the connect callback, `Bluefruit.Advertising.start(0)` — keep
   advertising until slots are full, so other Macs can see the beacon while
   one is connected
3. In the disconnect callback, also check `isRunning()` and restart
   advertising

The short-lived connection model (connect → one-byte write → disconnect,
ADR 0001) is kept. Typical simultaneous occupancy is 0-1, so four slots are
plenty.

## Known limitations (accepted)

- **Read-modify-write races**: if two Macs read and write almost
  simultaneously, one update can be lost (lost update). Accepted because
  writes are infrequent. If it ever matters, add "set/clear only my bit"
  commands to the protocol and let the beacon do the merge
- **Three hosts max**: there are three color bits. Four or more hosts need a
  host-ID protocol (v0.3)
- **Blink is shared**: there is one blink bit, so blinking cannot be
  per-host

## References

- S140 spec: https://www.nordicsemi.com/Products/Development-software/s140
- `ble_gap.h` (S140 v7.3.0): https://github.com/adafruit/Adafruit_nRF52_Arduino/blob/master/cores/nRF5/nordic/softdevice/s140_nrf52_7.3.0_API/include/ble_gap.h
- Bluefruit multi-connection example: https://github.com/adafruit/Adafruit_nRF52_Arduino/blob/master/libraries/Bluefruit52Lib/examples/Peripheral/bleuart_multi/bleuart_multi.ino
- Advertising restart behavior: https://github.com/adafruit/Adafruit_nRF52_Arduino/blob/master/libraries/Bluefruit52Lib/src/BLEAdvertising.cpp
