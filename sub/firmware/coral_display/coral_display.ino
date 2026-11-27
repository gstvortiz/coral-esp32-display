#include "display_service.h"
#include "bird_monitor.h"

void setup() {
  if (!CoralDisplay::begin() || !BirdMonitor::begin()) {
    for (;;) delay(1000);
  }
}

void loop() {
  // Application extensions may run here. Serial/OLED, RMS and SD have own tasks.
  delay(1000);
}
