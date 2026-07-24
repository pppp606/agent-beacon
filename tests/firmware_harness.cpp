// Host-side harness for the firmware's pure decode logic.
// Usage: attention_decode_harness <state-byte>
// Prints "red green blue blink" as 0/1, e.g. "1 1 0 1" for yellow blink.
#include <cstdio>
#include <cstdlib>

#include "../firmware/agent_beacon/attention_state.h"

int main(int argc, char** argv) {
  if (argc != 2) {
    fprintf(stderr, "usage: %s <state-byte>\n", argv[0]);
    return 2;
  }
  long state = strtol(argv[1], nullptr, 0);
  if (state < 0 || state > 0xFF) {
    fprintf(stderr, "state must be 0-255\n");
    return 2;
  }
  AttentionLed led = attention_decode((uint8_t)state);
  printf("%d %d %d %d\n", led.red, led.green, led.blue, led.blink);
  return 0;
}
