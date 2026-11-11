#!/usr/bin/env bash
set -euo pipefail
project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cli="${ARDUINO_CLI:-arduino-cli}"
config_args=()
if [[ -n "${ARDUINO_CLI_CONFIG:-}" ]]; then
    config_args+=(--config-file "$ARDUINO_CLI_CONFIG")
fi
"$cli" "${config_args[@]}" compile --fqbn esp32:esp32:esp32 \
    --build-path "${ARDUINO_BUILD_PATH:-$project_dir/build/cache}" \
    --output-dir "$project_dir/build" "$project_dir/firmware/coral_display"
