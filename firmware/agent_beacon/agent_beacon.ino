// Agent Beacon firmware for Seeed XIAO nRF52840
//
// BLE peripheral exposing a single 1-byte attention state (docs/protocol.md).
// Knows nothing about Claude Code or any agent — just state in, LED out.
//
// Build:  arduino-cli compile --fqbn Seeeduino:nrf52:xiaonRF52840 firmware/agent_beacon
// Flash:  arduino-cli upload -p /dev/cu.usbmodem* --fqbn Seeeduino:nrf52:xiaonRF52840 firmware/agent_beacon
//         (or double-tap reset and copy the UF2 to the mounted drive)

#include <bluefruit.h>

#include "attention_state.h"
#include "imu_tap.h"

// 128-bit UUIDs from docs/protocol.md, in little-endian byte order.
// Base: 7b1fXXXX-9f02-4c60-b0f7-a9f6a4b0beac
const uint8_t ATTENTION_SERVICE_UUID[16] = {
  0xac, 0xbe, 0xb0, 0xa4, 0xf6, 0xa9, 0xf7, 0xb0,
  0x60, 0x4c, 0x02, 0x9f, 0x01, 0x00, 0x1f, 0x7b
};
const uint8_t ATTENTION_STATE_UUID[16] = {
  0xac, 0xbe, 0xb0, 0xa4, 0xf6, 0xa9, 0xf7, 0xb0,
  0x60, 0x4c, 0x02, 0x9f, 0x02, 0x00, 0x1f, 0x7b
};
const uint8_t DEVICE_ID_UUID[16] = {
  0xac, 0xbe, 0xb0, 0xa4, 0xf6, 0xa9, 0xf7, 0xb0,
  0x60, 0x4c, 0x02, 0x9f, 0x03, 0x00, 0x1f, 0x7b
};

// Bluetooth SIG test Company ID — prototype only (docs/adr/0002-beacon-identity.md)
const uint16_t MANUFACTURER_ID = 0xFFFF;

BLEService attentionService(ATTENTION_SERVICE_UUID);
BLECharacteristic attentionState(ATTENTION_STATE_UUID);
BLECharacteristic deviceIdChr(DEVICE_ID_UUID);

uint8_t currentState = 0x00;

const uint32_t CYCLE_MS = 800;  // per color when several bits are set (ADR 0004)
const uint32_t BLINK_MS = 250;  // half-period, ~2Hz

// Display-timeout clocks (docs/protocol.md): when each color bit was last
// raised, plus the last state change for the colorless fail-safe case.
uint32_t colorRaisedAt[3] = {0, 0, 0};
uint32_t stateChangedAt = 0;

// Tap-to-dismiss (docs/protocol.md): probed once at boot; the IMU rail is
// then powered only while the display is lit (a tap means nothing in the
// dark, and 416Hz tap detection costs ~170µA — ADR 0006)
bool imuPresent = false;
bool imuArmed = false;

// LED brightness, 0-255. ~25% is indistinguishable indoors from full drive
// but cuts the lit current to roughly a quarter (ADR 0006)
const uint16_t LED_DUTY = 64;

// Onboard RGB LED is active low, dimmed by hardware PWM. The PWM peripheral
// is stopped whenever every element is dark so it costs nothing on standby.
void applyLed(const AttentionLed& led, bool lit) {
  bool any = lit && (led.red || led.green || led.blue);
  if (!any) {
    if (HwPWM0.enabled()) HwPWM0.stop();  // GPIO (driven HIGH) takes over
    digitalWrite(LED_RED, HIGH);
    digitalWrite(LED_GREEN, HIGH);
    digitalWrite(LED_BLUE, HIGH);
    return;
  }
  if (!HwPWM0.enabled()) HwPWM0.begin();
  // inverted: the LED is on while the pin is low, for `duty` of each period
  HwPWM0.writePin(LED_RED, led.red ? LED_DUTY : 0, true);
  HwPWM0.writePin(LED_GREEN, led.green ? LED_DUTY : 0, true);
  HwPWM0.writePin(LED_BLUE, led.blue ? LED_DUTY : 0, true);
}

void attentionWriteCallback(uint16_t conn_hdl, BLECharacteristic* chr, uint8_t* data, uint16_t len) {
  (void)conn_hdl;
  (void)chr;
  if (len < 1) return;
  uint32_t now = millis();
  uint8_t previous = currentState;
  currentState = data[0];  // loop() refreshes the LED within ~20ms
  // Any write carrying a set color bit refreshes that bit's timeout clock
  // (docs/protocol.md), so a future keepalive write could re-light a stale wait.
  for (int i = 0; i < 3; i++) {
    if (currentState & (1 << i)) colorRaisedAt[i] = now;
  }
  if (currentState != previous) stateChangedAt = now;
}

// Multi-connection (ADR 0004): connecting stops advertising and the library
// only auto-restarts it once ALL centrals are gone, so keep advertising
// ourselves while slots remain — otherwise a second Mac cannot even see the
// beacon while the first is connected.
void connectCallback(uint16_t conn_hdl) {
  (void)conn_hdl;
  Bluefruit.Advertising.start(0);
}

void disconnectCallback(uint16_t conn_hdl, uint8_t reason) {
  (void)conn_hdl;
  (void)reason;
  if (!Bluefruit.Advertising.isRunning()) {
    Bluefruit.Advertising.start(0);
  }
}

void startAdvertising() {
  Bluefruit.Advertising.addFlags(BLE_GAP_ADV_FLAGS_LE_ONLY_GENERAL_DISC_MODE);
  Bluefruit.Advertising.addService(attentionService);

  // Company ID (LE) + Short ID = low 32 bits of FICR DEVICEID (LE)
  uint32_t shortId = NRF_FICR->DEVICEID[0];
  uint8_t mfrData[6];
  mfrData[0] = MANUFACTURER_ID & 0xFF;
  mfrData[1] = (MANUFACTURER_ID >> 8) & 0xFF;
  memcpy(&mfrData[2], &shortId, sizeof(shortId));
  Bluefruit.Advertising.addManufacturerData(mfrData, sizeof(mfrData));

  Bluefruit.ScanResponse.addName();

  Bluefruit.Advertising.restartOnDisconnect(true);
  // 20ms fast for the first 30s (snappy setup), then 1s: the radio is the
  // dominant standby consumer and a slow interval cuts it ~6x, at the cost
  // of ≤1s extra latency from hook event to LED (ADR 0006)
  Bluefruit.Advertising.setInterval(32, 1600);
  Bluefruit.Advertising.setFastTimeout(30);
  Bluefruit.Advertising.start(0);  // advertise forever
}

void setup() {
  pinMode(LED_RED, OUTPUT);
  pinMode(LED_GREEN, OUTPUT);
  pinMode(LED_BLUE, OUTPUT);
  HwPWM0.takeOwnership(0xA6BEAC00);
  HwPWM0.addPin(LED_RED);
  HwPWM0.addPin(LED_GREEN);
  HwPWM0.addPin(LED_BLUE);
  HwPWM0.setResolution(8);
  applyLed(attention_decode(currentState), true);

  // The LED means "attention", nothing else: disable the core's BLE status
  // LED (blue: blinks while advertising, solid while connected)
  Bluefruit.autoConnLed(false);
  Bluefruit.begin(4, 0);  // up to 4 concurrent centrals: 3 hosts + slack (ADR 0004)
  digitalWrite(LED_BLUE, HIGH);
  // 0dBm reaches across a room; +4dBm only spends battery (ADR 0006)
  Bluefruit.setTxPower(0);
  Bluefruit.setName("AgentBeacon");
  Bluefruit.Periph.setConnectCallback(connectCallback);
  Bluefruit.Periph.setDisconnectCallback(disconnectCallback);

  attentionService.begin();

  attentionState.setProperties(CHR_PROPS_READ | CHR_PROPS_WRITE);
  attentionState.setPermission(SECMODE_OPEN, SECMODE_OPEN);
  attentionState.setFixedLen(1);
  attentionState.setWriteCallback(attentionWriteCallback);
  attentionState.begin();
  attentionState.write8(currentState);

  // Full ID: FICR DEVICEID as 16 lowercase hex chars (docs/protocol.md)
  char fullId[17];
  snprintf(fullId, sizeof(fullId), "%08lx%08lx",
           (unsigned long)NRF_FICR->DEVICEID[1],
           (unsigned long)NRF_FICR->DEVICEID[0]);
  deviceIdChr.setProperties(CHR_PROPS_READ);
  deviceIdChr.setPermission(SECMODE_OPEN, SECMODE_NO_ACCESS);
  deviceIdChr.setFixedLen(16);
  deviceIdChr.begin();
  deviceIdChr.write(fullId, 16);

  startAdvertising();

  imuPresent = imuTapProbe();  // rail stays off until the display lights
}

void loop() {
  // Display is a pure function of (state, time): stale bits drop out after
  // ATTENTION_TIMEOUT_MS, the cycle phase advances every CYCLE_MS, blink
  // gates the whole display. No ordering-dependent state.
  uint32_t now = millis();
  uint8_t effective = attention_effective_state(
      currentState, now - colorRaisedAt[0], now - colorRaisedAt[1],
      now - colorRaisedAt[2], now - stateChangedAt, ATTENTION_TIMEOUT_MS);

  // The IMU rail follows the display: powered while lit, dark means off
  if (imuPresent && effective != 0x00 && !imuArmed) {
    imuArmed = imuTapPowerOn();
  }

  // Double-tap = the human saw it: fast-forward every display clock to
  // expired, exactly as if the timeout had fired (docs/protocol.md). The
  // state byte stays untouched; the next write raising a bit re-lights.
  if (imuArmed && imuTapPending()) {
    uint32_t expired = now - ATTENTION_TIMEOUT_MS;
    colorRaisedAt[0] = colorRaisedAt[1] = colorRaisedAt[2] = expired;
    stateChangedAt = expired;
    effective = 0x00;
  }

  if (imuArmed && effective == 0x00) {
    imuTapPowerOff();
    imuArmed = false;
  }
  AttentionLed led = attention_display(effective, now / CYCLE_MS);
  bool lit = !led.blink || ((now / BLINK_MS) % 2 == 0);
  applyLed(led, lit);
  delay(20);
}
