# firmware

Firmware for the Seeed XIAO nRF52840. Acts as a BLE peripheral exposing the
[Attention Service](../docs/protocol.md) and drives the onboard LED from a
single byte of state. Knows nothing about agents (Claude Code etc.).

## Setup (first time only)

```sh
brew install arduino-cli
arduino-cli config init
arduino-cli config add board_manager.additional_urls \
  https://files.seeedstudio.com/arduino/package_seeeduino_boards_index.json
arduino-cli core update-index
arduino-cli core install Seeeduino:nrf52
```

## Build

The FQBN depends on the board variant (`arduino-cli board list` shows it):

- Plain: `Seeeduino:nrf52:xiaonRF52840`
- Sense: `Seeeduino:nrf52:xiaonRF52840Sense`

```sh
arduino-cli compile --fqbn Seeeduino:nrf52:xiaonRF52840Sense firmware/agent_beacon
```

## Flash

Over serial with USB connected:

```sh
arduino-cli board list   # confirm the port (/dev/cu.usbmodemXXXX) and FQBN
arduino-cli upload -p /dev/cu.usbmodemXXXX --fqbn Seeeduino:nrf52:xiaonRF52840Sense firmware/agent_beacon
```

Serial DFU sometimes fails with `Timed out waiting for acknowledgement`.
A single retry usually gets through; if it keeps failing, use UF2 below.

If serial flashing fails, use UF2:

1. Double-tap the reset button → a mass-storage drive mounts under a name
   like `XIAO-SENSE`
2. Run `arduino-cli compile --fqbn Seeeduino:nrf52:xiaonRF52840 --export-binaries firmware/agent_beacon`
   and copy the generated `.uf2` onto the drive

## Behavior

- On boot: LED off, advertises as `AgentBeacon` (Short ID in manufacturer
  data)
- Writes to the Attention State characteristic: `0x00` turns the LED off,
  non-zero lights it. With several color bits set, colors cycle at 800ms
  each; the blink bit applies to the whole display
  ([docs/protocol.md](../docs/protocol.md) v0.2)
- Display timeout: each color bit goes dark 10 minutes after it was last
  raised (a wait lit that long means nobody is around). Display-only — the
  state byte and Read are untouched ([docs/protocol.md](../docs/protocol.md))
- Four concurrent connection slots (3 hosts + slack). Advertising continues
  while connected, so other Macs can still see the beacon (ADR 0004)
- State survives disconnection
