# ADR 0002: Beacon Identity

- Status: Accepted
- Date: 2026-07-24

## Context

We expect setups that map a physical beacon to each Mac / AI environment
(Mac A → Beacon A, Mac B → Beacon B, …). If every unit carries only the same
device name (`AgentBeacon`) and the same service UUID, a host cannot reliably
identify "the beacon I am supposed to light." This is not a UI problem but an
identifier-design problem in the initial protocol, so it ships in v0.1.

Constraints:

- **macOS CoreBluetooth does not expose a peripheral's BLE MAC address to
  applications.** What the host sees is a per-Mac peripheral UUID generated
  by macOS, which cannot be shared between Macs and may be regenerated even
  on the same Mac. → Neither the MAC address nor the CoreBluetooth UUID can
  serve as a persistent ID saved in config.
- Identification must work before connecting (at scan time). Connecting to
  every candidate to read an ID is slow and flaky with several units around.

## Decision

### ID source: nRF52840 FICR DEVICEID

The beacon ID is the nRF52840's **FICR (Factory Information Configuration
Registers) DEVICEID (64 bit)**: factory-programmed, effectively unique,
read-only, and unchanged by firmware updates. No provisioning step (minting
and writing IDs) is needed.

- **Full ID**: the 64 bits as 16 lowercase hex digits (e.g. `1a2b3c4d5e6f7a8b`)
- **Short ID**: the low 32 bits = last 8 digits (e.g. `5e6f7a8b`).
  A shortened form for the advertising packet's 31-byte budget. At
  personal-to-team scale, 32-bit collisions are effectively negligible.

### Pre-connection identification: advertising manufacturer data

The Short ID is included in the advertising packet (details in
`docs/protocol.md`):

- Company ID `0xFFFF` (the Bluetooth SIG's reserved test value — revisit
  before productization) + 4 bytes of Short ID
- Service UUID (18 bytes) + Flags (3 bytes) + manufacturer data (8 bytes)
  = 29 bytes, within the 31-byte budget
- The device name rides in the scan response but is **display-only, never
  used for identification**

### Post-connection confirmation: Device ID characteristic

A read-only GATT characteristic returns the Full ID (`docs/protocol.md`).
For debugging and as the final check in case of a Short ID collision.

### Mac side: beacon ID kept in a config file

- `beaconctl scan` lists nearby beacons with their Short IDs
- `beaconctl use <short-id>` saves it to the config file
  (`~/.config/agent-beacon/config.json`)
- `beaconctl on|off` finds the target by matching the configured ID against
  manufacturer data. Never depends on scan order, device name, or the
  CoreBluetooth UUID
- With no ID configured, the single discovered beacon is used only when
  exactly one is found (so single-unit trial isn't blocked). Multiple
  discoveries are an error prompting `use`

## Alternatives considered

| Option | Why rejected |
|---|---|
| Embed a unit ID in the device name (e.g. `AgentBeacon-5e6f`) | Works, but mixes display and identity purposes in one field with tight length limits. Cleaner to keep identity in manufacturer data |
| BLE MAC address | Not exposed by macOS CoreBluetooth, so unusable |
| Save the CoreBluetooth peripheral UUID | Per-Mac and may be regenerated. Config can't be carried between Macs |
| Pairing/bonding | Excess complexity for v0.1; also inconsistent with the open-write policy (ADR 0001) |
| Mint an ID during first-time setup and write it to flash | FICR DEVICEID already suffices; no reason to add a write step and extra state |

## Consequences

- The same firmware binary can be flashed to every unit with no per-unit
  build differences
- A future custom nRF52840 board keeps using FICR DEVICEID as-is (likewise
  after a Zephyr migration)
- Company ID `0xFFFF` is a reserved test value, so shipping as a product
  requires obtaining a Bluetooth SIG company ID or moving to another scheme
  (service data etc.)
