#include "display_service.h"
#include "bird_monitor.h"
#include "lora_link.h"

void setup() {
  // Radio first: it only takes UART2 and GPIO 2, 5, 34 and 35, and the display service
  // hands it every new screen. The display keeps working if the radio does not start.
  LoraLink::begin();
  if (!CoralDisplay::begin() || !BirdMonitor::begin()) {
    for (;;) delay(1000);
  }
}

void loop() {
  // Application extensions may run here. Serial/OLED, RMS and SD have own tasks.
  delay(1000);
}
