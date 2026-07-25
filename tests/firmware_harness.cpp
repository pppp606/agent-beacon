// Host-side harness for the firmware's pure LED logic.
// Usage: attention_decode_harness <state-byte>          -> attention_decode
//        attention_decode_harness <state-byte> <phase>  -> attention_display
//        attention_decode_harness <state-byte> <elapsed-red> <elapsed-green>
//            <elapsed-blue> <elapsed-failsafe> <timeout>
//                                                       -> attention_effective_state
// The first two forms print "red green blue blink" as 0/1 (e.g. "1 1 0 1"
// for yellow blink); the timeout form prints the effective state byte.
#include <cstdio>
#include <cstdlib>

#include "../firmware/agent_beacon/attention_state.h"

int main(int argc, char** argv) {
  if (argc != 2 && argc != 3 && argc != 7) {
    fprintf(stderr,
            "usage: %s <state-byte> [phase | <er> <eg> <eb> <ef> <timeout>]\n",
            argv[0]);
    return 2;
  }
  long state = strtol(argv[1], nullptr, 0);
  if (state < 0 || state > 0xFF) {
    fprintf(stderr, "state must be 0-255\n");
    return 2;
  }
  if (argc == 7) {
    uint32_t v[5];
    for (int i = 0; i < 5; i++) {
      v[i] = (uint32_t)strtoul(argv[2 + i], nullptr, 0);
    }
    printf("%u\n", attention_effective_state((uint8_t)state,
                                             v[0], v[1], v[2], v[3], v[4]));
    return 0;
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
