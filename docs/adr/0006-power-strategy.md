# ADR 0006: Power Strategy for Battery Operation

- Status: Accepted
- Date: 2026-07-28

## Context

The beacon is moving from USB power to a LiPo battery (the XIAO has an
onboard charger). On the current firmware the standby current is dominated
by three consumers, in roughly this order:

1. **BLE advertising** — 152.5ms interval at +4dBm, forever
2. **The IMU** — tap detection needs the accelerometer at 416Hz (~170µA),
   and it ran continuously
3. **The LED while lit** — a few mA per element at full drive

CPU time is already negligible: the core sleeps inside `delay()` via
FreeRTOS/SoftDevice, so tuning loop cadence is noise and is not attempted.

## Decision

### 1. The IMU rail follows the display

A tap is only meaningful while the display is lit, so the IMU power rail
(GPIO P1.08) is switched on when the display lights and cut when it goes
dark. Standby IMU cost: zero. The tap engine's config registers are
volatile and are rewritten on every power-up (~55ms, invisible next to the
LED lighting). The boot-time presence probe stays, so plain boards still
run the same binary. Bus pins go no-pull while the rail is down — a pull-up
would leak into the unpowered chip through its I/O pins.

### 2. Adaptive advertising, lower TX power

Discovery latency is what the host pays before every write, and its cost is
asymmetric: while the display is **lit**, the next write is the OFF that a
human is about to trigger — they are watching the LED, so discovery must be
fast. While **dark** (the vast majority of battery life) the next write is
an ON the human is not watching for, so an extra second is invisible.

- **Lit: 152.5ms** interval (plus a 20ms burst for 10s after each start /
  connection). Lit time is bounded by the display timeout, so this profile
  costs almost nothing over a battery cycle
- **Dark: 500ms** — ~3x less standby radio than the old always-152.5ms.
  A first version used 1s here for ~6x, but macOS's duty-cycled scanner
  then took multi-second to discover the beacon and turning OFF felt
  sluggish; 500ms restores sub-second-ish discovery
- TX power: **0dBm** instead of +4dBm; the beacon sits meters from its hosts

The profile follows the effective display state, same as the IMU rail.
`make test-e2e` passes unchanged.

### 3. LED dimming via hardware PWM

The LED runs at ~25% duty (`LED_DUTY = 64/255`) through the nRF52's PWM
peripheral — indistinguishable indoors from full drive, roughly a quarter
of the lit current. The PWM peripheral is **stopped whenever every element
is dark** (plain GPIO holds the pins high), so dimming costs nothing on
standby. The 10-minute display timeout (already shipped) is the other half
of this: worst-case LED burn per wait is bounded.

## Not doing (yet)

- **Zephyr / System OFF sleep**: reserved for the custom-board phase
  (ADR 0001). With a LiPo in the hundreds of mAh, the measures above are
  expected to reach a standby of tens of µA — months to a year — without
  abandoning the Arduino/Bluefruit stack
- **Connection-parameter tuning**: connections are short-lived one-byte
  writes; not worth the complexity

## Consequences

- Standby expectation drops from ~0.3-0.5mA to tens of µA. **To be
  verified by measurement** (e.g. Nordic PPK2) when the battery arrives —
  per the project rule that power work is done against real numbers
- Hook-to-LED latency grows by ≤1s in the worst case
- Tap-to-dismiss now depends on the display being lit — which is the only
  time it ever did anything
