# ADR 0003: Test Strategy (dual-target TDD)

- Status: Accepted
- Date: 2026-07-24

## Context

We want to work test-first as on the web, but in embedded work the final
check — "did the LED light?" — lives in the physical world, and the naive
approach degenerates into endless eyeball debugging. We adopt the embedded
staple of **dual-target development** (logic tested on the host, the
hardware-dependent layer kept razor thin), reducing what must be verified by
eye to "are the wiring and the LED physically alive?".

## Decision

### Test layers

| Layer | What it verifies | Runs on | Command |
|---|---|---|---|
| 1. Protocol conformance | State-byte decode (firmware) and encode (CLI) match the spec and cannot drift apart | Host (pytest + native C++) | `make test` |
| 2. CLI units | Pure logic: advertisement parsing, target resolution, state display | Host (pytest) | `make test` |
| 3. BLE round-trip | write → read-back via `beaconctl status` agrees (real BLE, GATT, firmware wiring) | Hardware + Bluetooth | `make test-e2e` |
| 4. Photons | The LED really lights in that color | Human eyes | manual |

With layers 1-3 green, layer 4 only confirms "the LED element and wiring are
alive." Spec misunderstandings (e.g. the BLE status LED blinking blue) are
caught in layers 1-3.

### Mechanics

- **Extracted pure logic**: protocol interpretation lives in the pure
  function `attention_decode()` in `firmware/agent_beacon/attention_state.h`.
  Zero Arduino dependencies, so the host C++ compiler builds it directly
  (`tests/firmware_harness.cpp`). The `.ino` holds only pin glue and
  Bluefruit wiring — **no protocol decision may be written in the `.ino`**
- **Shared test vectors**: `tests/protocol_vectors.json` is the executable
  copy of the spec (docs/protocol.md). The firmware decode test and the CLI
  encode test read the same file, so the two protocol interpretations cannot
  diverge. **To change the protocol, update protocol.md and the vectors
  first, watch both sides' tests fail, then implement** (this is the
  repository's TDD entry point)
- **Fail-safe invariant**: "only `0x00` is dark" is guaranteed by an
  exhaustive test over all 256 values
- **pytest as the single runner**: the C++ harness is compiled inside
  pytest, so one `make test` runs every host test. Hardware tests are gated
  behind `BEACON_E2E=1` and auto-skip where no hardware exists (CI etc.)

### Rules from M2 onward

M2 (the Claude Code integration) follows the same structure:

1. The mapping from hook events to beacon state (session aggregation, "ON if
   any session is waiting", color assignment, …) is written as **pure
   functions** and developed test-first with pytest. BLE writes (`beaconctl`
   invocation) and file I/O are separated behind injectable seams
2. Write the test first when changing a state transition
3. `make test` must pass without hardware. Hardware verification happens
   last, as acceptance: `make test-e2e` plus a visual check

### Not built

- HIL (reading the LED mechanically with a color sensor): production-test
  territory, overkill at prototype scale
- Emulating the BLE stack (Renode etc.): setup cost isn't worth it
- Mocking frameworks (CMock etc.): unnecessary for testing extracted pure
  functions

## Consequences

- The firmware flash cycle (~30s) drops out of the test loop; host tests run
  in seconds
- The `.ino` and the hardware remain the only untestable area, but since no
  decisions live there, failures skew toward "nothing works at all" (easy to
  spot)
- Protocol changes cost slightly more (protocol.md + vectors + both
  implementations) — a deliberate price for structurally preventing
  spec/implementation drift
