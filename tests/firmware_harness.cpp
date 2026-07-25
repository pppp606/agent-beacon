// Host-side harness for the firmware's pure LED logic.
// Usage: attention_decode_harness <state-byte>          -> attention_decode
//        attention_decode_harness <state-byte> <phase>  -> attention_display
// Prints "red green blue blink" as 0/1, e.g. "1 1 0 1" for yellow blink.
#include <cstdio>
#include <cstdlib>

#include "../firmware/agent_beacon/attention_state.h"

int main(int argc, char** argv) {
  if (argc != 2 && argc != 3) {
    fprintf(stderr, "usage: %s <state-byte> [phase]\n", argv[0]);
    return 2;
  }
  long state = strtol(argv[1], nullptr, 0);
  if (state < 0 || state > 0xFF) {
    fprintf(stderr, "state must be 0-255\n");
    return 2;
  }
  AttentionLed led;
  if (argc == 3) {
    long phase = strtol(argv[2], nullptr, 0);
    if (phase < 0) {
      fprintf(stderr, "phase must be >= 0\n");
      return 2;
    }
    led = attention_display((uint8_t)state, (uint32_t)phase);
  } else {
    led = attention_decode((uint8_t)state);
  }
  printf("%d %d %d %d\n", led.red, led.green, led.blue, led.blink);
  return 0;
}
