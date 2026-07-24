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
bool blinkPhase = true;

// Onboard RGB LED is active low
void applyLed(bool lit) {
  AttentionLed led = attention_decode(currentState);
  digitalWrite(LED_RED, (lit && led.red) ? LOW : HIGH);
  digitalWrite(LED_GREEN, (lit && led.green) ? LOW : HIGH);
  digitalWrite(LED_BLUE, (lit && led.blue) ? LOW : HIGH);
}

void attentionWriteCallback(uint16_t conn_hdl, BLECharacteristic* chr, uint8_t* data, uint16_t len) {
  (void)conn_hdl;
  (void)chr;
  if (len < 1) return;
  currentState = data[0];
  blinkPhase = true;
  applyLed(true);
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
  Bluefruit.Advertising.setInterval(32, 244);  // 20ms fast, 152.5ms slow
  Bluefruit.Advertising.setFastTimeout(30);
  Bluefruit.Advertising.start(0);  // advertise forever
}

void setup() {
  pinMode(LED_RED, OUTPUT);
  pinMode(LED_GREEN, OUTPUT);
  pinMode(LED_BLUE, OUTPUT);
  applyLed(true);

  // The LED means "attention", nothing else: disable the core's BLE status
  // LED (blue: blinks while advertising, solid while connected)
  Bluefruit.autoConnLed(false);
  Bluefruit.begin();
  digitalWrite(LED_BLUE, HIGH);
  Bluefruit.setTxPower(4);
  Bluefruit.setName("AgentBeacon");

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
}

void loop() {
  if (attention_decode(currentState).blink) {
    blinkPhase = !blinkPhase;
    applyLed(blinkPhase);
    delay(250);  // ~2Hz
  } else {
    applyLed(true);
    delay(100);
  }
}
