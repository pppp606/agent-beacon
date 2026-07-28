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

### 2. Slower advertising, lower TX power

- Advertising: 20ms for the first 30s after boot/disconnect (snappy setup),
  then **1s** instead of 152.5ms — about 6x less radio energy on standby
- TX power: **0dBm** instead of +4dBm; the beacon sits meters from its hosts

Accepted tradeoff: up to ~1s extra latency from hook event to LED. The
product's notification loop is human-scale (the display persists until
answered), so 2-3s worst-case is fine. `make test-e2e` passes unchanged.

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
