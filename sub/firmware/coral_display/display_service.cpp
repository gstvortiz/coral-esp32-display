#include "display_service.h"
#include "bird_monitor.h"
#include "bird_config.h"
#include "button.h"
#include <esp_system.h>
#include <atomic>
#include <Arduino.h>
#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include <ArduinoJson.h>
#include <Preferences.h>
#include "text_layout.h"
#include "lora_link.h"

namespace {
QueueHandle_t inbox = nullptr;
SemaphoreHandle_t i2cMutex = nullptr;
SemaphoreHandle_t ready = nullptr;
TaskHandle_t serviceTask = nullptr;
std::atomic<uint32_t> rejected(0);
char bootId[17];
uint32_t eventSequence = 0;
bool localRequest = false;
bool birdMode = false;
String birdConfidence;
DebouncedButton micButton;
String noticeBlue,noticeYellow;
uint32_t noticeUntil=0;
bool noticeVisible=false;
bool hasNotice() {return noticeVisible && int32_t(noticeUntil-millis())>0;}
unsigned long lastBirdDraw = 0, lastRegionPage = 0;
enum class Kind : uint8_t { Command, Event };
struct Message { Kind kind; char json[2305]; };

struct I2cGuard {
  I2cGuard() { xSemaphoreTakeRecursive(i2cMutex, portMAX_DELAY); }
  ~I2cGuard() { xSemaphoreGiveRecursive(i2cMutex); }
};

bool probe(uint8_t addr);
bool rtcInfo(char *date, char *clock, float &temperature);

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
constexpr uint8_t MAX_MESSAGES = 8;
String blue[MAX_MESSAGES], yellow[MAX_MESSAGES];
uint8_t blueCount = 1, yellowCount = 1;
RegionCursor blueCursor, yellowCursor;

bool validText(const char *value) {
  for (; *value; ++value) {
    if (*value != '\n' && (uint8_t(*value) < 32 || uint8_t(*value) > 126)) return false;
  }
  return true;
}

bool validRegions(JsonVariantConst b, JsonVariantConst y) {
  size_t length = 0;
  for (JsonVariantConst value : {b, y}) {
    if (!value.is<JsonArrayConst>() || !value.size() || value.size() > MAX_MESSAGES) return false;
    for (JsonVariantConst item : value.as<JsonArrayConst>()) {
      if (!item.is<const char *>()) return false;
      const char *s = item.as<const char *>();
      if (!validText(s)) return false;
      length += strlen(s);
    }
  }
  return length <= MAX_TEXT;
}

void loadRegions(JsonVariantConst b, JsonVariantConst y) {
  blueCount = b.size(); yellowCount = y.size();
  for (uint8_t i = 0; i < MAX_MESSAGES; ++i) {
    blue[i] = i < blueCount ? b[i].as<const char *>() : "";
    yellow[i] = i < yellowCount ? y[i].as<const char *>() : "";
  }
}

void regionFields(JsonDocument &doc) {
  JsonArray b = doc.createNestedArray("blue"), y = doc.createNestedArray("yellow");
  for (uint8_t i = 0; i < blueCount; ++i) b.add(blue[i]);
  for (uint8_t i = 0; i < yellowCount; ++i) y.add(yellow[i]);
}

size_t drawText(const String &value, size_t start, int top, int height) {
  int scale = textScale(value.c_str(), height);
  TextPage page = layoutPage(value.c_str(), start, scale, height);
  oled.setTextSize(scale);
  for (int row = 0; row < page.count; ++row) {
    oled.setCursor(centeredX(page.lines[row], scale), centeredY(row, page.count, scale, height, top));
    oled.print(page.lines[row]);
  }
  return page.next;
}

bool probe(uint8_t addr) {
  I2cGuard guard;
  Wire.beginTransmission(addr);
  return Wire.endTransmission() == 0;
}

bool readRegisters(uint8_t reg, uint8_t *data, uint8_t count) {
  I2cGuard guard;
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

// Hands what the OLED shows to the LoRa link: one line per message, region first.
// Only copies text under the link's mutex; the radio task does the slow sending.
void forwardScreen() {
  String lines;
  auto add = [&lines](const char *label, String value) {
    value.replace("\n", " / ");
    lines += label; lines += value; lines += '\n';
  };
  if (hasNotice()) {
    if (noticeBlue.length()) add("azul: ", noticeBlue);
    if (noticeYellow.length()) add("amarelo: ", noticeYellow);
  } else if (mode == "regions") {
    const bool showConfidence = birdMode && birdConfidence.length();
    for (uint8_t i = 0; i < blueCount; ++i) {
      if (!blue[i].length()) continue;
      add("azul: ", showConfidence && i == 0 ? blue[i] + " " + birdConfidence : blue[i]);
    }
    for (uint8_t i = 0; i < yellowCount; ++i) if (yellow[i].length()) add("amarelo: ", yellow[i]);
  } else if (mode == "text" && text.length()) {
    add("texto: ", text);
  } else if (mode == "clock") {
    lines = "(relogio na tela)";
  }
  LoraLink::setScreen(lines.c_str());
}

void draw() {
  forwardScreen();
  I2cGuard guard;
  lastDraw = millis();
  if (!displayReady) return;
  oled.clearDisplay();
  oled.setTextColor(SSD1306_WHITE);
  oled.setTextWrap(false);
  oled.setTextSize(1);
  oled.setCursor(0, 0);
  if (hasNotice()) {
    drawText(noticeBlue,0,BLUE_TOP,BLUE_HEIGHT);
    drawText(noticeYellow,0,YELLOW_TOP,YELLOW_HEIGHT);
  } else if (mode == "clock") {
    char date[16], clock[12]; float temperature;
    if (rtcInfo(date, clock, temperature)) {
      drawText(String(date) + "\n" + clock, 0, BLUE_TOP, BLUE_HEIGHT);
      drawText(String(temperature, 1) + " C", 0, YELLOW_TOP, YELLOW_HEIGHT);
    } else {
      drawText("RTC indisponivel", 0, BLUE_TOP, BLUE_HEIGHT);
    }
  } else if (mode == "text") {
    nextPage = drawText(text, pageStart, BLUE_TOP, BLUE_HEIGHT);
  } else if (mode == "regions") {
    const bool showConfidence = birdMode && birdConfidence.length();
    blueCursor.next = drawText(blue[blueCursor.index], blueCursor.start, BLUE_TOP,
                               showConfidence ? BIRD_NAME_HEIGHT : BLUE_HEIGHT);
    if (showConfidence) drawText(birdConfidence, 0, BIRD_CONFIDENCE_TOP, BIRD_CONFIDENCE_HEIGHT);
    yellowCursor.next = drawText(yellow[yellowCursor.index], yellowCursor.start, YELLOW_TOP, YELLOW_HEIGHT);
  }
  oled.display();
}

void emitEvent(JsonDocument &event) {
  event["type"] = "event";
  event["boot_id"] = bootId;
  event["seq"] = ++eventSequence;
  event["uptime_ms"] = millis();
  serializeJson(event, Serial); Serial.println();
}

void respond(const char *id, bool ok, const char *error = nullptr) {
  DynamicJsonDocument out(4096);
  out["id"] = id;
  out["ok"] = ok;
  out["type"] = "ack";
  out["firmware"] = "coral-display/1.7";
  JsonObject overlay=out.createNestedObject("overlay");
  overlay["active"]=hasNotice();
  overlay["blue"]=hasNotice() ? noticeBlue : "";
  overlay["yellow"]=hasNotice() ? noticeYellow : "";
  overlay["remaining_ms"]=hasNotice() ? noticeUntil-millis() : 0;
  out["mic_button_gpio"]=BirdConfig::MIC_BUTTON;
  out["mic_button_pressed"]=digitalRead(BirdConfig::MIC_BUTTON)==LOW;
  out["boot_id"] = bootId;
  out["service_task"] = pcTaskGetName(nullptr);
  out["stack_free_min"] = uxTaskGetStackHighWaterMark(nullptr);
  out["queue_rejected"] = rejected.load();
  BirdMonitor::status(out.createNestedObject("bird"));
  out["alignment"] = "center";
  out["rotation"] = 180;
  out["oled"] = displayReady && probe(address);
  out["address"] = address;
  out["mode"] = mode;
  out["text"] = text;
  out["page_offset"] = pageStart;
  out["bird_confidence"] = birdMode ? birdConfidence : "";
  out["blue_height"] = BLUE_HEIGHT;
  out["yellow_height"] = YELLOW_HEIGHT;
  if (mode == "regions") {
    regionFields(out);
    out["blue_index"] = blueCursor.index; out["yellow_index"] = yellowCursor.index;
    out["blue_page_offset"] = blueCursor.start; out["yellow_page_offset"] = yellowCursor.start;
  }
  if (error) out["error"] = error;
  char date[16], clock[12]; float temperature;
  if (rtcInfo(date, clock, temperature)) {
    out["rtc_date"] = date; out["rtc_time"] = clock;
    out["rtc_temperature"] = temperature;
  }
  if (localRequest) {
    DynamicJsonDocument event(6144);
    event["event"] = "display_applied";
    event["task_id"] = id;
    event["data"].set(out.as<JsonVariantConst>());
    emitEvent(event);
  } else {
    serializeJson(out, Serial); Serial.println();
  }
}

void handle() {
  DynamicJsonDocument doc(4096);
  if (deserializeJson(doc, input)) { respond("", false, "invalid_json"); return; }
  const char *id = doc["id"] | "";
  const char *cmd = doc["cmd"] | "";
  if (strlen(id) > 64) { respond("", false, "id_too_long"); return; }
  if (!strcmp(cmd, "status")) { respond(id, true); return; }
  if (!strcmp(cmd,"notice")) {
    const char *b=doc["blue"] | "", *y=doc["yellow"] | "";
    unsigned duration=doc["duration_ms"] | 0U;
    if(!doc["blue"].is<const char*>() || !doc["yellow"].is<const char*>() ||
       !validText(b) || !validText(y) || strlen(b)>128 || strlen(y)>42 ||
       duration<1000 || duration>10000) {respond(id,false,"invalid_notice");return;}
    noticeBlue=b;noticeYellow=y;noticeUntil=millis()+duration;noticeVisible=true;
    draw();respond(id,true);return;
  }
  if (!strcmp(cmd, "bird")) {
    const char *name=doc["name"] | "", *scientific=doc["scientific_name"] | "";
    double score=doc["score"] | -1.0;
    unsigned ttl=doc["ttl_ms"] | 0U;
    uint64_t epoch=doc["epoch_ms"] | uint64_t(0);
    uint64_t windowStart=doc["window_start_ms"] | uint64_t(0), windowEnd=doc["window_end_ms"] | uint64_t(0);
    if ((doc.containsKey("window_start_ms") || doc.containsKey("window_end_ms")) &&
        (!doc["window_start_ms"].is<uint64_t>() || !doc["window_end_ms"].is<uint64_t>() ||
         !windowStart || windowEnd<=windowStart || windowEnd>epoch || windowEnd-windowStart>10000)) {
      respond(id,false,"invalid_audio_window");return;
    }
    if (!doc["active"].is<bool>() || !validText(name) || !validText(scientific) ||
        strlen(name)>128 || strlen(scientific)>128 || !isfinite(score) || score<0 || score>1 ||
        ttl<1 || ttl>30000 || epoch<1577836800000ULL || epoch>4102444800000ULL ||
        (doc["active"].as<bool>() && !*name)) {
      respond(id,false,"invalid_bird");return;
    }
    BirdMonitor::detection(name,scientific,score,doc["active"],epoch,ttl,windowStart,windowEnd);
    birdConfidence = doc["active"].as<bool>() ? String(int(score * 100.0 + 0.5)) + "%" : "";
    String label=doc["active"].as<bool>() ? name : "Ouvindo...";
    if(!birdMode || blueCount!=1 || blue[0]!=label) {
      blue[0]=label;blueCursor=RegionCursor();lastRegionPage=millis();
    }
    char direction[24];bool active;
    BirdMonitor::view(direction,sizeof(direction),active);
    if(!birdMode || yellowCount!=1 || yellow[0]!=direction) {
      yellow[0]=direction;yellowCursor=RegionCursor();
    }
    birdMode=true;mode="regions";text="";blueCount=yellowCount=1;
    draw();respond(id,true);return;
  }
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
  } else if (!strcmp(cmd, "regions")) {
    if (!validRegions(doc["blue"], doc["yellow"])) { respond(id, false, "invalid_regions"); return; }
    if (!displayReady || !probe(address)) { respond(id, false, "oled_unavailable"); return; }
    loadRegions(doc["blue"], doc["yellow"]);
    text = ""; mode = "regions";
  } else if (!strcmp(cmd, "clear") || !strcmp(cmd, "clock")) {
    if (!displayReady || !probe(address)) { respond(id, false, "oled_unavailable"); return; }
    mode = !strcmp(cmd, "clear") ? "clear" : "clock";
  } else { respond(id, false, "unknown_command"); return; }
  birdMode=false;BirdMonitor::cancel();
  // Persist only when requested and changed. Streaming clients can disable this.
  if (doc["remember"] | true) {
    bool saved = true;
    if (mode == "regions") {
      DynamicJsonDocument stored(4096); regionFields(stored);
      String encoded; serializeJson(stored, encoded);
      if (prefs.getString("regions", "") != encoded) {
        prefs.putString("regions", encoded);
        saved &= prefs.getString("regions", "") == encoded;
      }
    }
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
  lastRegionPage=millis();
  pageStart = nextPage = 0;
  blueCursor = RegionCursor(); yellowCursor = RegionCursor();
  draw();
  respond(id, probe(address), probe(address) ? nullptr : "oled_disconnected");
}

void initialize() {
  I2cGuard guard;
  pinMode(BirdConfig::MIC_BUTTON,INPUT_PULLUP);
  micButton.begin(digitalRead(BirdConfig::MIC_BUTTON)==LOW,millis());
  snprintf(bootId, sizeof(bootId), "%08lx%08lx", (unsigned long)esp_random(), (unsigned long)esp_random());
  // Hold a complete incoming command while an event or I2C transfer is sent.
  Serial.setRxBufferSize(4096);
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
  if (mode == "regions") {
    DynamicJsonDocument saved(4096);
    if (!deserializeJson(saved, prefs.getString("regions", "")) && validRegions(saved["blue"], saved["yellow"]))
      loadRegions(saved["blue"], saved["yellow"]);
    else { mode = "text"; text = "Coral"; }
  }
  input.reserve(MAX_FRAME);
  draw();
  respond("boot", displayReady, displayReady ? nullptr : "oled_unavailable");
}

void tick() {
  if(micButton.update(digitalRead(BirdConfig::MIC_BUTTON)==LOW,millis())) {
    noticeBlue="Microfone";noticeYellow="Trocando...";
    noticeUntil=millis()+4000;noticeVisible=true;draw();
    StaticJsonDocument<256> event;
    event["event"]="microphone_next";event["task_id"]="button";
    event.createNestedObject("data")["gpio"]=BirdConfig::MIC_BUTTON;
    emitEvent(event);
  }
  if(noticeVisible && !hasNotice()) {noticeVisible=false;draw();}
  // Bound serial work so a continuous sender cannot starve pagination or the queue.
  for (int bytes = 0; bytes < 512 && Serial.available(); ++bytes) {
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
  if (birdMode && millis()-lastBirdDraw>=200) {
    lastBirdDraw=millis();char direction[24];bool active;
    BirdMonitor::view(direction,sizeof(direction),active);
    bool changed=yellow[0]!=direction;
    if(changed) {yellow[0]=direction;yellowCursor=RegionCursor();}
    if(!active && (blue[0]!="Ouvindo..." || birdConfidence.length())) {
      blue[0]="Ouvindo...";birdConfidence="";blueCursor=RegionCursor();changed=true;
    }
    if(changed) draw();
  }
  if (mode == "clock" && millis() - lastDraw >= 1000) draw();
  if (mode == "text" && (nextPage || pageStart) && millis() - lastDraw >= 3000) {
    pageStart = nextPage; draw();
  }
  if (mode == "regions" && millis() - lastRegionPage >= 3000) {
    lastRegionPage=millis();
    bool changed = blueCursor.advance(blueCount);
    changed |= yellowCursor.advance(yellowCount);
    if (changed) draw();
  }
}

void service(void *) {
  initialize();
  xSemaphoreGive(ready);
  Message message;
  for (;;) {
    tick();
    // One queued message per iteration; serial commands remain responsive under load.
    if (xQueueReceive(inbox, &message, pdMS_TO_TICKS(10)) == pdTRUE) {
      if (message.kind == Kind::Event) {
        DynamicJsonDocument event(4096);
        if (!deserializeJson(event, message.json)) emitEvent(event);
      } else {
        // Keep a partially received UART frame intact while handling an internal request.
        String pending = input;
        input = message.json; localRequest = true;
        handle();
        localRequest = false; input = pending;
      }
    }
    // Yield even when producers keep the queue permanently full.
    vTaskDelay(1);
  }
}

bool enqueue(Kind kind, JsonDocument &doc, TickType_t wait) {
  Message message;
  message.kind = kind;
  if (!inbox || doc.overflowed() || measureJson(doc) > MAX_FRAME) {
    ++rejected; return false;
  }
  serializeJson(doc, message.json, sizeof(message.json));
  if (xQueueSend(inbox, &message, wait) != pdTRUE) { ++rejected; return false; }
  return true;
}
}  // namespace

namespace CoralDisplay {
bool begin() {
  if (serviceTask) return true;
  i2cMutex = xSemaphoreCreateRecursiveMutex();
  inbox = xQueueCreate(8, sizeof(Message));
  ready = xSemaphoreCreateBinary();
  if (i2cMutex && inbox && ready && xTaskCreate(service, "coral-display", 12288, nullptr, 1, &serviceTask) == pdPASS) {
    xSemaphoreTake(ready, portMAX_DELAY);
    return true;
  }
  if (ready) { vSemaphoreDelete(ready); ready = nullptr; }
  if (inbox) { vQueueDelete(inbox); inbox = nullptr; }
  if (i2cMutex) { vSemaphoreDelete(i2cMutex); i2cMutex = nullptr; }
  return false;
}

bool postRegions(const char *blueText, const char *yellowText, const char *requestId, TickType_t wait) {
  if (!blueText || !yellowText || !requestId || strlen(requestId) > 64 ||
      strlen(blueText) + strlen(yellowText) > MAX_TEXT || !validText(blueText) || !validText(yellowText)) {
    ++rejected; return false;
  }
  DynamicJsonDocument doc(4096);
  doc["cmd"] = "regions"; doc["remember"] = false; doc["id"] = requestId;
  doc.createNestedArray("blue").add(blueText);
  doc.createNestedArray("yellow").add(yellowText);
  return enqueue(Kind::Command, doc, wait);
}

bool postEvent(const char *name, const char *dataJson, const char *taskId, TickType_t wait) {
  if (!name || !*name || strlen(name) > 64 || !taskId || strlen(taskId) > 64 ||
      !dataJson || strlen(dataJson) > 1536) { ++rejected; return false; }
  DynamicJsonDocument doc(4096);
  if (deserializeJson(doc, dataJson) || !doc.is<JsonObject>()) { ++rejected; return false; }
  DynamicJsonDocument event(4096);
  event["event"] = name; event["task_id"] = taskId;
  event["data"].set(doc.as<JsonVariantConst>());
  return enqueue(Kind::Event, event, wait);
}

bool lockI2c(TickType_t wait) {
  return i2cMutex && xSemaphoreTakeRecursive(i2cMutex, wait) == pdTRUE;
}
void unlockI2c() { xSemaphoreGiveRecursive(i2cMutex); }
}  // namespace CoralDisplay
