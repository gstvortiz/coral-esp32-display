#include <Arduino.h>
#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include <ArduinoJson.h>
#include <Preferences.h>
#include "text_layout.h"

// Esquema_Ilustrado_ESP32.pdf: SSD1306 and DS3231 share GPIO21/22.
constexpr int WIDTH = 128, HEIGHT = 64;
constexpr size_t MAX_TEXT = 1024, MAX_FRAME = 2304;
Adafruit_SSD1306 oled(WIDTH, HEIGHT, &Wire, -1);
Preferences prefs;
String text = "Coral", mode = "text", input;
uint8_t address = 0;
bool displayReady = false, dropping = false;
size_t pageStart = 0, nextPage = 0;
unsigned long lastDraw = 0;

bool probe(uint8_t addr) {
  Wire.beginTransmission(addr);
  return Wire.endTransmission() == 0;
}

bool readRegisters(uint8_t reg, uint8_t *data, uint8_t count) {
  Wire.beginTransmission(0x68);
  Wire.write(reg);
  if (Wire.endTransmission(false) != 0) return false;
  if (Wire.requestFrom(uint8_t(0x68), count) != count) return false;
  for (uint8_t i = 0; i < count; ++i) data[i] = Wire.read();
  return true;
}

int bcd(uint8_t v) { return (v >> 4) * 10 + (v & 15); }

bool rtcInfo(char *date, char *clock, float &temperature) {
  uint8_t r[7], t[2];
  if (!readRegisters(0, r, 7) || !readRegisters(0x11, t, 2)) return false;
  int hour = bcd(r[2] & 0x3f);
  if (r[2] & 0x40) hour = bcd(r[2] & 0x1f) % 12 + ((r[2] & 0x20) ? 12 : 0);
  snprintf(date, 16, "%02d/%02d/%04d", bcd(r[4]), bcd(r[5] & 31),
           2000 + bcd(r[6]) + ((r[5] & 0x80) ? 100 : 0));
  snprintf(clock, 12, "%02d:%02d:%02d", hour, bcd(r[1]), bcd(r[0] & 127));
  temperature = int8_t(t[0]) + (t[1] >> 6) * 0.25f;
  return true;
}

void draw() {
  lastDraw = millis();
  if (!displayReady) return;
  oled.clearDisplay();
  oled.setTextColor(SSD1306_WHITE);
  oled.setTextWrap(false);
  oled.setTextSize(1);
  oled.setCursor(0, 0);
  if (mode == "clock") {
    char date[16], clock[12]; float temperature;
    oled.print("CORAL / RTC");
    if (rtcInfo(date, clock, temperature)) {
      oled.setCursor(0, 16); oled.print(date);
      oled.setTextSize(2); oled.setCursor(0, 30); oled.print(clock);
      oled.setTextSize(1); oled.setCursor(0, 54);
      oled.print(temperature, 1); oled.print(" C");
    } else {
      oled.setCursor(0, 24); oled.print("RTC indisponivel");
    }
  } else if (mode == "text") {
    int size = textScale(text.c_str());
    TextPage page = layoutPage(text.c_str(), pageStart, size);
    oled.setTextSize(size);
    for (int row = 0; row < page.count; ++row) {
      oled.setCursor(centeredX(page.lines[row], size), centeredY(row, page.count, size));
      oled.print(page.lines[row]);
    }
    nextPage = page.next;
  }
  oled.display();
}

void respond(const char *id, bool ok, const char *error = nullptr) {
  StaticJsonDocument<1536> out;
  out["id"] = id;
  out["ok"] = ok;
  out["firmware"] = "coral-display/1.1";
  out["alignment"] = "center";
  out["rotation"] = 180;
  out["oled"] = displayReady && probe(address);
  out["address"] = address;
  out["mode"] = mode;
  out["text"] = text;
  out["page_offset"] = pageStart;
  if (error) out["error"] = error;
  char date[16], clock[12]; float temperature;
  if (rtcInfo(date, clock, temperature)) {
    out["rtc_date"] = date; out["rtc_time"] = clock;
    out["rtc_temperature"] = temperature;
  }
  serializeJson(out, Serial); Serial.println();
}

void handle() {
  StaticJsonDocument<3072> doc;
  if (deserializeJson(doc, input)) { respond("", false, "invalid_json"); return; }
  const char *id = doc["id"] | "";
  const char *cmd = doc["cmd"] | "";
  if (strlen(id) > 64) { respond("", false, "id_too_long"); return; }
  if (!strcmp(cmd, "status")) { respond(id, true); return; }
  if (!strcmp(cmd, "text")) {
    if (!doc["text"].is<const char *>()) { respond(id, false, "text_required"); return; }
    String value = doc["text"].as<String>();
    if (value.length() > MAX_TEXT) { respond(id, false, "text_too_long"); return; }
    for (size_t i = 0; i < value.length(); ++i) {
      if (value[i] != '\n' && (uint8_t(value[i]) < 32 || uint8_t(value[i]) > 126)) {
        respond(id, false, "ascii_text_required"); return;
      }
    }
    if (!displayReady || !probe(address)) { respond(id, false, "oled_unavailable"); return; }
    text = value; mode = "text";
  } else if (!strcmp(cmd, "clear") || !strcmp(cmd, "clock")) {
    if (!displayReady || !probe(address)) { respond(id, false, "oled_unavailable"); return; }
    mode = !strcmp(cmd, "clear") ? "clear" : "clock";
  } else { respond(id, false, "unknown_command"); return; }
  // Persist only when requested and changed. Streaming clients can disable this.
  if (doc["remember"] | true) {
    bool saved = true;
    if (prefs.getString("text", "Coral") != text) {
      prefs.putString("text", text);
      saved &= prefs.getString("text", "\x01") == text;
    }
    if (prefs.getString("mode", "text") != mode) {
      prefs.putString("mode", mode);
      saved &= prefs.getString("mode", "") == mode;
    }
    if (!saved) { respond(id, false, "storage_error"); return; }
  }
  pageStart = nextPage = 0;
  draw();
  respond(id, probe(address), probe(address) ? nullptr : "oled_disconnected");
}

void setup() {
  Serial.begin(115200);
  Wire.begin(21, 22);
  Wire.setTimeOut(100);
  for (uint8_t candidate : {uint8_t(0x3c), uint8_t(0x3d)}) {
    if (probe(candidate)) { address = candidate; break; }
  }
  displayReady = address && oled.begin(SSD1306_SWITCHCAPVCC, address, false, false);
  oled.setRotation(2);  // 180 degrees: orientation confirmed on the physical assembly.
  prefs.begin("coral-display", false);
  text = prefs.getString("text", "Coral");
  mode = prefs.getString("mode", "text");
  input.reserve(MAX_FRAME);
  draw();
  respond("boot", displayReady, displayReady ? nullptr : "oled_unavailable");
}

void loop() {
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\n') {
      if (dropping) respond("", false, "frame_too_long");
      else if (input.length()) handle();
      input = ""; dropping = false;
    } else if (c != '\r' && !dropping) {
      if (input.length() >= MAX_FRAME) { dropping = true; input = ""; }
      else input += c;
    }
  }
  if (mode == "clock" && millis() - lastDraw >= 1000) draw();
  if (mode == "text" && (nextPage || pageStart) && millis() - lastDraw >= 3000) {
    pageStart = nextPage; draw();
  }
  delay(1);
}
