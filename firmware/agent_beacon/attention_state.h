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

// v0.2 display (docs/protocol.md, ADR 0004): when several color bits are set
// they are shown one at a time, cycling in bit order (red, green, blue) as
// `phase` advances; the RGB package would otherwise blend them into a single
// unreadable color. Blink stays orthogonal: it gates the whole display.
inline AttentionLed attention_display(uint8_t state, uint32_t phase) {
  AttentionLed all = attention_decode(state);
  bool colors[3] = {all.red, all.green, all.blue};
  int active = (int)colors[0] + (int)colors[1] + (int)colors[2];
  if (active <= 1) return all;
  uint32_t target = phase % (uint32_t)active;
  AttentionLed led = {false, false, false, all.blink};
  uint32_t seen = 0;
  for (int i = 0; i < 3; i++) {
    if (!colors[i]) continue;
    if (seen++ == target) {
      led.red = (i == 0);
      led.green = (i == 1);
      led.blue = (i == 2);
      break;
    }
  }
  return led;
}
