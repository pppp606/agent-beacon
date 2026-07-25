# Agent Beacon BLE Protocol v0.2

The beacon device acts as a BLE peripheral and receives exactly one piece of
state: "is attention needed?". The host (Mac) is the central.

## Beacon ID

Every beacon has a permanent unique ID (design rationale in
[ADR 0002](adr/0002-beacon-identity.md)).

- **Full ID**: the nRF52840 FICR DEVICEID (64 bit) as 16 lowercase hex digits
- **Short ID**: the low 32 bits of the Full ID (last 8 digits). Used for
  identification during advertising

## Advertising

| Field | Content |
|---|---|
| Flags | LE General Discoverable |
| 128-bit Service UUID | Attention Service (product discovery; shared by all units) |
| Manufacturer data | Company ID `0xFFFF` (2 bytes, LE) + Short ID (4 bytes, LE) |
| Device name (scan response) | `AgentBeacon` (display only — **never used for identification**) |

Hosts discover "this is an Agent Beacon" via the Service UUID and identify
"which unit" via the Short ID in the manufacturer data.

Company ID `0xFFFF` is the Bluetooth SIG's reserved test value. It is for the
prototype phase only and will be revisited before productization (ADR 0002).

## GATT

### Attention Service

- Service UUID: `7b1f0001-9f02-4c60-b0f7-a9f6a4b0beac`

### Attention State Characteristic

- Characteristic UUID: `7b1f0002-9f02-4c60-b0f7-a9f6a4b0beac`
- Properties: Read, Write
- Length: fixed 1 byte

Bit assignment:

| bit | Meaning |
|---|---|
| 0 | red |
| 1 | green |
| 2 | blue |
| 3 | blink (~2Hz) |
| 4-7 | reserved |

- `0x00` = no attention needed (LED off). **`0x00` remains the only
  dark value in every future version**
- Non-zero = attention needed (lit or blinking)
- Examples: `0x01` = solid red, `0x09` = blinking red

### Display (v0.2: cycling)

When several color bits are set, the beacon does not blend them — it shows
**one color at a time, cycling through the set bits in bit order
(bit0 → bit1 → bit2), 800ms per color**. A single color bit is shown as a
steady light.

| State byte | Display |
|---|---|
| `0x01` | solid red |
| `0x03` | red → green → red → … (800ms per color) |
| `0x07` | red → green → blue → red → … |

The blink bit (bit 3) applies orthogonally to the whole display (the entire
cycle blinks at ~2Hz).

The display is defined as a pure function of (state byte, phase number) →
one color for that instant (`attention_display` in `attention_state.h`), so
it never depends on write order or timing.

### Host assignment and read-modify-write (v0.2 convention)

To share one beacon across several hosts, the color bits are used as
**per-host assignments** ([ADR 0004](adr/0004-multi-host-sharing.md)): e.g.
Mac A = red (bit 0), Mac B = green (bit 1), Mac C = blue (bit 2). The state
byte is then "the set of hosts currently waiting for a human."

Every host operates on its own bit only, via **read-modify-write**:

- **Attention raised**: read the current value → set your color bit (and the
  blink bit if desired) → write
- **Attention cleared**: read the current value → clear only your color bit →
  write. **If that leaves no color bit set, write `0x00`** (dropping the
  blink and reserved bits too) — a leftover blink bit would fail-safe to red
  and become a phantom light nobody can turn off

This is a host-side convention; the beacon is oblivious and simply displays
whatever byte it receives. If two hosts read-modify-write at the same moment
the lost update is accepted (ADR 0004).

**Unknown / invalid values (fail-safe)**: any non-zero value must light up.
A non-zero value with no color bits set (e.g. reserved bits only) **falls
back to solid red**. This is deliberate fail-safe design: if a
future-version host writes an attention state that an older beacon does not
understand, the notification must not be lost. For this product a missed
notification (false negative) is the worst failure mode, so unknown values
lean toward lighting up rather than being ignored.

- Read returns the current state (for debugging).
- The state after power-up is `0x00` (off).
- The state survives disconnection (disconnect ≠ off).

### Device ID Characteristic

- Characteristic UUID: `7b1f0003-9f02-4c60-b0f7-a9f6a4b0beac`
- Properties: Read
- Length: fixed 16 bytes (ASCII, the Full ID as 16 lowercase hex digits)

For debugging and as the final check in case of a Short ID collision.

## Security

v0.1 has no pairing/bonding (open write). Acceptable under the prototype's
threat model; to be re-evaluated when moving to a custom board.
