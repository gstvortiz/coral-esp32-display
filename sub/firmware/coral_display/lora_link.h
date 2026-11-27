#pragma once
#include <Arduino.h>

// Repeats what the OLED shows over an Ebyte E32 (LoRa 433 MHz, transparent mode) to a
// distant receiver (another E32 on a USB-serial adapter).
namespace LoraLink {
// Call once from setup(), before CoralDisplay::begin(). false means the radio task did
// not start; the display keeps working without it.
bool begin();

// Thread-safe. The screen as newline-separated ASCII lines. A new screen goes out within
// a second (latest state wins) and the current one is repeated every 5 s.
void setScreen(const char *lines);
}
