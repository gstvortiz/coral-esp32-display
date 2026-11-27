#include "bird_monitor.h"
#include "bird_config.h"
#include "rms_direction.h"
#include "direction_history.h"
#include "display_service.h"
#include <SPI.h>
#include <SD.h>
#include <esp_timer.h>
#include <esp_system.h>
#include <atomic>
#include <time.h>
namespace {
using namespace BirdConfig;
struct State {
  char name[129]={}, scientific[129]={};
  float score=0,rms[4]={},mean[4]={};
  uint64_t epoch=0, syncUs=0, deadlineUs=0, measurementUs=0;
  uint32_t windowUs=0;
  bool active=false,muted=false;
  uint64_t windowStartMs=0,windowEndMs=0;
  DirectionWindow matched;
};
State state;
DirectionHistory history;
SemaphoreHandle_t mutex=nullptr;
QueueHandle_t records=nullptr;
SPIClass adc(VSPI),card(HSPI);
std::atomic<bool> sdOk(false);
std::atomic<unsigned> saved(0),lost(0);
uint32_t session;
bool beepPending=false;
uint64_t lastBeep=0;
struct Guard { Guard(){xSemaphoreTake(mutex,portMAX_DELAY);} ~Guard(){xSemaphoreGive(mutex);} };
State snapshot() {
  Guard guard;
  State copy=state;
  uint64_t now=esp_timer_get_time();
  if(now>=copy.deadlineUs) { copy.active=false; copy.score=0; copy.name[0]=copy.scientific[0]=0; }
  if(copy.epoch) copy.epoch+=(now-copy.syncUs)/1000;
  return copy;
}
void fields(JsonObject out,const State &s) {
  out["active"]=s.active; out["name"]=String(s.name); out["scientific_name"]=String(s.scientific);
  out["score"]=s.score; out["epoch_ms"]=s.epoch;
  out["direction"]=s.active && s.matched.direction>=0 ? DIRECTIONS[s.matched.direction] : "";
  out["direction_valid"]=s.active && s.matched.direction>=0 && !s.muted;
  out["window_start_ms"]=s.windowStartMs;out["window_end_ms"]=s.windowEndMs;
  out["direction_coverage"]=s.matched.coverage;
  out["direction_sync"]=!s.windowStartMs ? "missing_window" : s.matched.coverage<0.95f ? "history_incomplete" : "matched";
  JsonArray windowRms=out.createNestedArray("window_rms");
  for(int i=0;i<4;++i) windowRms.add(s.matched.rms[i]);
  out["muted"]=s.muted; out["window_us"]=s.windowUs;
  JsonArray rms=out.createNestedArray("rms"),mean=out.createNestedArray("mean");
  for(int i=0;i<4;++i) {rms.add(s.rms[i]);mean.add(s.mean[i]);}
}
uint16_t readAdc(unsigned channel) {
  digitalWrite(ADC_CS,LOW);
  adc.transfer(1);
  uint16_t high=adc.transfer((8+channel)<<4)&3;
  uint16_t low=adc.transfer(0);
  digitalWrite(ADC_CS,HIGH);
  return (high<<8)|low;
}
bool mountCard() {
  // An MCU reset does not power-cycle the card. Retry its SPI initialization before
  // consuming a record, so a transient first handshake does not lose that record.
  for(int attempt=0;attempt<2;++attempt) {
    SD.end();
    if(SD.begin(SD_CS,card,1000000,"/sd",5,false) && SD.cardType()!=CARD_NONE) return true;
    vTaskDelay(pdMS_TO_TICKS(200));
  }
  return false;
}
void storage(void *) {
  card.begin(SD_SCK,SD_MISO,SD_MOSI,SD_CS);
  sdOk=mountCard();
  State record;
  for(;;) {
    if(xQueueReceive(records,&record,portMAX_DELAY)!=pdTRUE) continue;
    if(!sdOk.load()) {
      sdOk=mountCard();
    }
    DynamicJsonDocument doc(2048);
    fields(doc.to<JsonObject>(),record);
    doc["session"]=session; doc["uptime_ms"]=millis();
    char date[20]="unsynced",stamp[32]="";
    if(record.epoch) {
      time_t seconds=record.epoch/1000; struct tm utc; gmtime_r(&seconds,&utc);
      strftime(date,sizeof(date),"%Y-%m-%d",&utc);
      strftime(stamp,sizeof(stamp),"%Y-%m-%dT%H:%M:%SZ",&utc);
    }
    doc["timestamp_utc"]=stamp;
    char path[64]; snprintf(path,sizeof(path),"/birds-%s.jsonl",date);
    String line;serializeJson(doc,line);line+='\n';
    bool ok=false;
    if(sdOk.load()) {
      File file=SD.open(path,FILE_APPEND);
      size_t offset=file ? file.size() : 0;
      if(file && file.print(line)==line.length()) {
        file.flush();file.close();
        // Verify the appended record by reopening it before reporting success.
        File verify=SD.open(path,FILE_READ);
        if(verify && verify.seek(offset)) ok=verify.readStringUntil('\n')+'\n'==line;
        verify.close();
      } else file.close();
      if(!ok) sdOk=false;
    }
    if(ok) ++saved; else ++lost;
    // Compact event includes the record and the actual storage outcome.
    doc["saved"]=ok; doc["path"]=path;
    doc.remove("mean");doc.remove("window_us");
    String event;serializeJson(doc,event);
    CoralDisplay::postEvent("bird_record",event.c_str(),"microSD");
  }
}
void sampling(void *) {
  adc.begin(ADC_SCK,ADC_MISO,ADC_MOSI,ADC_CS);
  pinMode(ADC_CS,OUTPUT);digitalWrite(ADC_CS,HIGH);
  if(BUZZER_ENABLED) {pinMode(BUZZER,OUTPUT);digitalWrite(BUZZER,LOW);}
  uint64_t nextLog=esp_timer_get_time()+uint64_t(LOG_MS)*1000;
  for(;;) {
    bool beep=false;
    { Guard guard; beep=beepPending; beepPending=false; }
    if(BUZZER_ENABLED && beep) {
      { Guard guard; state.muted=true;state.matched.direction=-1; }
      digitalWrite(BUZZER,HIGH);vTaskDelay(pdMS_TO_TICKS(BEEP_MS));digitalWrite(BUZZER,LOW);
      vTaskDelay(pdMS_TO_TICKS(SETTLE_MS));
      { Guard guard;state.muted=false; }
    }
    RmsWindow window;
    const uint64_t start=esp_timer_get_time();
    adc.beginTransaction(SPISettings(1000000,MSBFIRST,SPI_MODE0));
    for(unsigned sample=0;sample<SAMPLES;++sample) {
      uint64_t before=esp_timer_get_time();
      uint16_t values[4];for(unsigned ch=0;ch<4;++ch) values[ch]=readAdc(ch);
      window.add(values);
      int remaining=int(SAMPLE_US)-int(esp_timer_get_time()-before);
      if(remaining>0) delayMicroseconds(remaining);
      if(sample%32==31) vTaskDelay(1); // Watchdog/other tasks; actual window reported.
    }
    adc.endTransaction();
    float rms[4],mean[4];window.finish(rms,mean,GAINS);
    { Guard guard;
      memcpy(state.rms,rms,sizeof(rms));memcpy(state.mean,mean,sizeof(mean));
      state.measurementUs=esp_timer_get_time();state.windowUs=state.measurementUs-start;
      history.add(start,state.measurementUs,rms,mean);
    }
    uint64_t now=esp_timer_get_time();
    if(now>=nextLog) {
      State copy=snapshot();
      if(xQueueSend(records,&copy,0)!=pdTRUE) ++lost;
      nextLog+=uint64_t(LOG_MS)*1000;
      if(nextLog<=now) nextLog=now+uint64_t(LOG_MS)*1000;
    }
    vTaskDelay(1);
  }
}
}
namespace BirdMonitor {
bool begin() {
  session=esp_random();
  mutex=xSemaphoreCreateMutex();records=xQueueCreate(8,sizeof(State));
  if(!mutex || !records) return false;
  if(xTaskCreate(storage,"bird-storage",8192,nullptr,1,nullptr)!=pdPASS) return false;
  return xTaskCreate(sampling,"bird-rms",6144,nullptr,1,nullptr)==pdPASS;
}
void detection(const char *name,const char *scientific,float score,bool active,uint64_t epochMs,unsigned ttlMs,
               uint64_t windowStartMs,uint64_t windowEndMs) {
  if(!mutex) return;
  Guard guard;
  uint64_t now=esp_timer_get_time();
  // Resolve once and freeze until a new audio window arrives. Retries cannot make
  // the old bird name follow a new sound source.
  if(windowStartMs!=state.windowStartMs || windowEndMs!=state.windowEndMs || !windowStartMs) {
    state.matched=DirectionWindow();
    uint64_t startUs=0,endUs=0;
    if(mapAudioWindow(now,epochMs,windowStartMs,windowEndMs,startUs,endUs))
      state.matched=history.select(startUs,endUs,MIN_RMS,WINNER_RATIO);
    state.windowStartMs=windowStartMs;state.windowEndMs=windowEndMs;
  }
  bool fresh=active && (!state.active || now>=state.deadlineUs || strcmp(name,state.name));
  if(BUZZER_ENABLED && fresh && (!lastBeep || now-lastBeep>=uint64_t(BEEP_COOLDOWN_MS)*1000)) {beepPending=true;lastBeep=now;}
  strlcpy(state.name,active?name:"",sizeof(state.name));
  strlcpy(state.scientific,active?scientific:"",sizeof(state.scientific));
  state.score=active?score:0;state.active=active;
  state.epoch=epochMs;state.syncUs=now;state.deadlineUs=now+uint64_t(ttlMs)*1000;
}
void cancel() { if(mutex) {Guard guard;state.active=false;state.name[0]=state.scientific[0]=0;state.score=0;beepPending=false;} }
void view(char *direction,size_t size,bool &active) {
  if(!mutex) {active=false;strlcpy(direction,"",size);return;}
  State copy=snapshot();active=copy.active;
  strlcpy(direction,!active?"":copy.muted?"...":copy.matched.direction<0?"Indef.":DIRECTIONS[copy.matched.direction],size);
}
void status(JsonObject out) {
  if(!mutex) {out["ready"]=false;return;}
  fields(out,snapshot());out["log_interval_ms"]=LOG_MS;out["buzzer_enabled"]=BUZZER_ENABLED;out["sd_ok"]=sdOk.load();out["records_saved"]=saved.load();out["records_lost"]=lost.load();
}
}
