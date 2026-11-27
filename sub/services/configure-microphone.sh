#!/usr/bin/env bash
# Coral Dev Board RT5645 input path, based on its shipped ALSA HiFi.conf.
# Configure capture explicitly: a boot service cannot depend on PulseAudio login.
set -euo pipefail
# Only the onboard microphone needs the RT5645 mixer setup.
config_path="${1:-$(dirname "$0")/birds.json}"
device="${CORAL_AUDIO_DEVICE:-}"
if [[ -z "$device" ]]; then
device=$(python3 - "$config_path" <<'PYCONFIG'
import json
import sys
with open(sys.argv[1]) as source:
    print(json.load(source)['device'])
PYCONFIG
)
fi
case "$device" in
    *CARD=edgetpuaudiocar,*) ;;
    *) echo "Captura externa: $device; sem configuracao do RT5645."; exit 0 ;;
esac
# HiFi resets the capture mixers before Speaker selects the onboard DMIC route.
# This selects a codec route only; no sound is played.
alsaucm -c edgetpu-audio-card set _verb HiFi set _enadev Speaker
card=edgetpuaudiocar
amixer -q -c "$card" cset name='Internal Mic Switch' on
amixer -q -c "$card" cset name='ADC Capture Volume' 39,39
amixer -q -c "$card" cset name='ADC Boost Capture Volume' 0,0
amixer -q -c "$card" cset name='ADC Capture Switch' on
amixer -q -c "$card" cset name='Stereo1 ADC2 Mux' DMIC
amixer -q -c "$card" cset name='Stereo1 DMIC Mux' DMIC1
amixer -q -c "$card" cset name='Sto1 ADC MIXL ADC1 Switch' off
amixer -q -c "$card" cset name='Sto1 ADC MIXR ADC1 Switch' off
amixer -q -c "$card" cset name='Sto1 ADC MIXL ADC2 Switch' on
amixer -q -c "$card" cset name='Sto1 ADC MIXR ADC2 Switch' on
amixer -q -c "$card" cset name='RT5645 IF1 ADC Mux' IF_ADC1/IF_ADC2/VAD_ADC
amixer -q -c "$card" cset name='RT5645 IF1 ADC1 Swap Mux' L/R
