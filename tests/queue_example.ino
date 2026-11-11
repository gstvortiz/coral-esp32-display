// Hardware-only fixture: replace the sketch's .ino in a TEMPORARY copy.
#include "display_service.h"

void setup() {
  if (!CoralDisplay::begin()) for (;;) delay(1000);
}

void loop() {
  static bool tested = false;
  delay(5000);
  if (!tested) {
    bool invalid = !CoralDisplay::postEvent("invalid", "not-json");
    bool queued = CoralDisplay::postRegions("Fila", "Local", "queue-smoke");
    char data[96];
    snprintf(data, sizeof(data), "{\"invalid_rejected\":%s,\"queued\":%s}",
             invalid ? "true" : "false", queued ? "true" : "false");
    CoralDisplay::postEvent("queue_test", data, "queue-smoke");
    tested = true;
  }
}
