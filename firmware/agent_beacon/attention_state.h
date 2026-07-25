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

// Display timeout (docs/protocol.md): a wait shown this long means the human
// is not around to see it, so each color bit's display expires independently,
// this many ms after that bit was last raised. Display-only: the state byte
// (and what Read returns) is untouched.
const uint32_t ATTENTION_TIMEOUT_MS = 10UL * 60UL * 1000UL;

// Maps the state byte to the byte actually displayed, given how long ago
// each color bit was last raised. A colorless non-zero value (the fail-safe
// case) expires on its own clock, counted from the last state change. Once
// everything is stale the result is 0x00 — dark, never fail-safe red: that
// rule is for unknown values, not stale ones.
inline uint8_t attention_effective_state(uint8_t state,
                                         uint32_t elapsed_red,
                                         uint32_t elapsed_green,
                                         uint32_t elapsed_blue,
                                         uint32_t elapsed_failsafe,
                                         uint32_t timeout_ms) {
  if (state == 0x00) return 0x00;
  uint8_t color = state & ATTENTION_COLOR_MASK;
  if (color == 0x00) {
    return elapsed_failsafe < timeout_ms ? state : 0x00;
  }
  uint8_t visible = 0;
  if ((color & 0x01) && elapsed_red < timeout_ms) visible |= 0x01;
  if ((color & 0x02) && elapsed_green < timeout_ms) visible |= 0x02;
  if ((color & 0x04) && elapsed_blue < timeout_ms) visible |= 0x04;
  if (visible == 0x00) return 0x00;
  return visible | (state & ATTENTION_BLINK_BIT);
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
