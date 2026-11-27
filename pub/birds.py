"""Transient bird observations; never retain a detection as display state."""
import math
import time
from .messages import display_text


def validate_bird(request):
    result = dict(request)
    if not isinstance(result.get('active'), bool):
        raise ValueError('active_must_be_bool')
    for key in ('name', 'scientific_name'):
        value = result.get(key, '')
        if not isinstance(value, str) or len(value) > 128:
            raise ValueError('invalid_' + key)
        result[key] = display_text(value)
    if result['active'] and not result['name']:
        raise ValueError('bird_name_required')
    for key in ('score', 'expires_at'):
        value = result.get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError('invalid_' + key)
    if not 0 <= result['score'] <= 1:
        raise ValueError('invalid_score')
    if result['expires_at'] > time.time() + 31:
        raise ValueError('expiration_too_far')
    if 'window_start_ms' in result or 'window_end_ms' in result:
        start, end = result.get('window_start_ms'), result.get('window_end_ms')
        if (type(start) is not int or type(end) is not int or
                start <= 0 or not 0 < end - start <= 10000):
            raise ValueError('invalid_audio_window')
    return result


def serial_fields(request, now=None):
    """Recheck expiry on every retry/reconnect; expired observations close the gate."""
    now = time.time() if now is None else now
    remaining = min(30000, max(0, int((request['expires_at'] - now) * 1000)))
    active = request['active'] and remaining > 0
    fields = dict(active=active, name=request['name'] if active else '',
                scientific_name=request['scientific_name'] if active else '',
                score=request['score'] if active else 0,
                epoch_ms=int(now * 1000), ttl_ms=max(1, remaining))
    # Keep the original absolute window across MQTT delays and serial retries.
    for key in ('window_start_ms', 'window_end_ms'):
        if key in request:
            fields[key] = request[key]
    return fields


def observation(result, lifetime=8, now=None):
    now = time.time() if now is None else now
    age = result.get('result_age_seconds', 0)
    detections = result.get('detections', [])
    best = max(detections, key=lambda bird: bird['score']) if detections else None
    active = best is not None and age < lifetime
    command = dict(cmd='bird', active=active, name=best['name'] if active else '',
                scientific_name=best['scientific_name'] if active else '',
                score=best['score'] if active else 0,
                expires_at=now + max(0, lifetime - age))
    if result.get('mode') == 'microphone':
        duration = result['audio_end_seconds'] - result['start_seconds']
        if not math.isfinite(age) or age < 0 or not math.isfinite(duration) or not 0 < duration <= 10:
            raise ValueError('invalid_capture_timing')
        end_ms = round((now - age) * 1000)
        command.update(window_start_ms=end_ms - round(duration * 1000), window_end_ms=end_ms)
    return command
