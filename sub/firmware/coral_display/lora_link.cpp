#include "lora_link.h"
#include <freertos/FreeRTOS.h>
#include <freertos/task.h>
#include <freertos/semphr.h>

namespace {
// The module keeps its own configuration (factory default: 433 MHz, UART 9600 8N1,
// 2.4 kbps on air, maximum power).
constexpr int PIN_E32_TXD = 35;  // ESP32 RX, input-only pin
constexpr int PIN_E32_RXD = 2;   // ESP32 TX
constexpr int PIN_E32_AUX = 34;  // HIGH = module idle
constexpr int PIN_E32_MODE = 5;  // M0 and M1 bridged: LOW = normal (transparent) mode
constexpr uint32_t MIN_GAP_MS = 1000;  // at most one screen per second
constexpr uint32_t REPEAT_MS = 5000;   // silence between repeats of an unchanged screen
constexpr size_t SCREEN_MAX = 1280;
constexpr size_t CHUNK = 45;      // "#<seq> " (up to 12) + 45 + "\n" fit one 58-byte packet
constexpr int MAX_CHUNKS = 12;    // about 3 s on air at 2.4 kbps per screen

HardwareSerial radio(2);
SemaphoreHandle_t lock = nullptr;
char screen[SCREEN_MAX] = "(iniciando)";
uint32_t version = 1, sentVersion = 0, sequence = 0;

bool waitAux(uint32_t timeoutMs) {
  uint32_t start = millis();
  while (digitalRead(PIN_E32_AUX) == LOW) {
    if (millis() - start >= timeoutMs) return false;
    vTaskDelay(pdMS_TO_TICKS(2));
  }
  return true;
}

void sendLine(const char *text, size_t length) {
  char packet[64];
  int head = snprintf(packet, sizeof(packet), "#%lu ", (unsigned long)++sequence);
  memcpy(packet + head, text, length);
  packet[head + length] = '\n';
  waitAux(1500);  // the module buffer is drained into the radio
  radio.write(reinterpret_cast<const uint8_t *>(packet), head + length + 1);
  radio.flush();
  vTaskDelay(pdMS_TO_TICKS(20));  // a pause on the UART closes the packet
}

void sendScreen() {
  static char copy[SCREEN_MAX];
  xSemaphoreTake(lock, portMAX_DELAY);
  memcpy(copy, screen, SCREEN_MAX);
  sentVersion = version;
  xSemaphoreGive(lock);
  int chunks = 0;
  for (const char *line = copy; *line && chunks < MAX_CHUNKS;) {
    const char *end = strchr(line, '\n');
    size_t length = end ? size_t(end - line) : strlen(line);
    for (size_t offset = 0; offset < length && chunks < MAX_CHUNKS; offset += CHUNK, ++chunks)
      sendLine(line + offset, min(CHUNK, length - offset));
    line += length + (end ? 1 : 0);
  }
}

void run(void *) {
  waitAux(2000);  // power-on self check of the module
  uint32_t lastSend = 0;
  bool first = true;
  for (;;) {
    while (radio.available()) radio.read();  // this link only transmits
    xSemaphoreTake(lock, portMAX_DELAY);
    bool changed = version != sentVersion;
    xSemaphoreGive(lock);
    uint32_t idle = millis() - lastSend;
    if (first || (changed && idle >= MIN_GAP_MS) || idle >= REPEAT_MS) {
      first = false;
      sendScreen();
      lastSend = millis();
    }
    vTaskDelay(pdMS_TO_TICKS(50));
  }
}
}  // namespace

namespace LoraLink {
bool begin() {
  if (lock) return true;
  pinMode(PIN_E32_AUX, INPUT);
  pinMode(PIN_E32_MODE, OUTPUT);
  digitalWrite(PIN_E32_MODE, LOW);
  radio.begin(9600, SERIAL_8N1, PIN_E32_TXD, PIN_E32_RXD);
  lock = xSemaphoreCreateMutex();
  return lock && xTaskCreate(run, "lora-link", 4096, nullptr, 1, nullptr) == pdPASS;
}

void setScreen(const char *lines) {
  if (!lock || !lines) return;
  const char *value = *lines ? lines : "(tela vazia)";
  xSemaphoreTake(lock, portMAX_DELAY);
  if (strncmp(screen, value, SCREEN_MAX - 1) != 0) {
    strlcpy(screen, value, SCREEN_MAX);
    ++version;
  }
  xSemaphoreGive(lock);
}
}  // namespace LoraLink
