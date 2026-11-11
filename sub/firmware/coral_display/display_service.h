#pragma once
#include <Arduino.h>
#include <freertos/FreeRTOS.h>
#include <freertos/task.h>
#include <freertos/queue.h>
#include <freertos/semphr.h>

namespace CoralDisplay {
// Call once from setup(), before starting producer tasks. No stop/restart API.
bool begin();

// Thread-safe, copied into a bounded queue (8 entries). true means queued, not
// displayed/delivered. false means invalid input, full queue or unavailable service.
// These functions are for task context, not interrupt handlers. Default: no wait.
// ASCII display text, 1024 characters total. Empty string clears that region.
bool postRegions(const char *blue, const char *yellow, const char *requestId = "local",
                 TickType_t wait = 0);
// Event name / taskId <= 64 bytes, JSON object data <= 768 bytes. UTF-8 permitted.
bool postEvent(const char *name, const char *dataJson = "{}", const char *taskId = "",
               TickType_t wait = 0);

// Every other user of Wire must acquire this mutex. Keep transactions short;
// do not wait on queues while holding it. Do not reinitialize Wire or touch OLED.
bool lockI2c(TickType_t wait = pdMS_TO_TICKS(100));
void unlockI2c();
}
