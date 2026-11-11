#include "display_service.h"

void setup() {
  // Owns Serial, OLED, RTC and the shared I2C initialization in a separate task.
  if (!CoralDisplay::begin()) {
    // Do not continue with a partially initialized service.
    for (;;) delay(1000);
  }
}

void loop() {
  // Replace this example with your application's work. This delay blocks only
  // the Arduino loop task: USB commands and display pagination keep running.
  static unsigned long completed = 0;
  delay(10000);
  char data[96];
  snprintf(data, sizeof(data), "{\"count\":%lu,\"task\":\"%s\"}",
           completed + 1, pcTaskGetName(nullptr));
  if (CoralDisplay::postEvent("application_tick", data, "example-loop")) ++completed;
}
