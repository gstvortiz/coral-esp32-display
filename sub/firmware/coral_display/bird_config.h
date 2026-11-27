#pragma once
// Esquema_Ilustrado_ESP32.pdf. Orientation is provisional; change names/gains here.
namespace BirdConfig {
constexpr int MIC_BUTTON=32; // Normally open to GND, pull-up; schematic supplied.
constexpr int ADC_SCK=18, ADC_MISO=19, ADC_MOSI=23, ADC_CS=4;
constexpr int SD_SCK=14, SD_MISO=27, SD_MOSI=26, SD_CS=13;
constexpr bool BUZZER_ENABLED=false; // Disabled at user request; do not drive pin.
constexpr int BUZZER=33; // Module polarity not verified; keep disabled.
constexpr const char *DIRECTIONS[4] = {"Norte", "Leste", "Sul", "Oeste"};
constexpr float GAINS[4] = {1, 1, 1, 1};
constexpr float MIN_RMS=3.0f; // ADC counts, after DC removal; calibrate in quiet room.
constexpr float WINNER_RATIO=1.10f; // Below this ratio, direction is ambiguous.
constexpr unsigned SAMPLES=512, SAMPLE_US=250;
constexpr unsigned LOG_MS=500, BEEP_MS=80, SETTLE_MS=500, BEEP_COOLDOWN_MS=10000;
}
