#pragma once
#include <ArduinoJson.h>
namespace BirdMonitor {
bool begin();
// Called by the display owner. Validated, copied; no SD/ADC work in this call.
void detection(const char *name,const char *scientific,float score,bool active,
               uint64_t epochMs,unsigned ttlMs,uint64_t windowStartMs=0,uint64_t windowEndMs=0);
void cancel();
void status(JsonObject out);
// Empty when gated off, '?' when quiet/ambiguous, otherwise a cardinal label.
void view(char *direction,size_t size,bool &active);
}
