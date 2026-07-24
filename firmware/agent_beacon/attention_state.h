#pragma once
#include <stdint.h>

// Decodes an attention state byte (docs/protocol.md) into LED intent.
// Pure logic with no hardware or Arduino dependencies, so the host can
// unit-test it (tests/firmware_harness.cpp). Keep every protocol decision
// here; the sketch only moves pins.

struct AttentionLed {
  bool red;
  bool green;
  bool blue;
  bool blink;
};

const uint8_t ATTENTION_COLOR_MASK = 0x07;
const uint8_t ATTENTION_BLINK_BIT = 0x08;

inline AttentionLed attention_decode(uint8_t state) {
  AttentionLed led = {false, false, false, false};
  if (state == 0x00) return led;
  uint8_t color = state & ATTENTION_COLOR_MASK;
  // Fail-safe: any non-zero state must light up; default to red when no
  // color bit is set (docs/protocol.md)
  if (color == 0x00) color = 0x01;
  led.red = (color & 0x01) != 0;
  led.green = (color & 0x02) != 0;
  led.blue = (color & 0x04) != 0;
  led.blink = (state & ATTENTION_BLINK_BIT) != 0;
  return led;
}
