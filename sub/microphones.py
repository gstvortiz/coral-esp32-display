"""Discover capture devices, persist a confirmed choice, and receive ESP button clicks."""
import collections
import json
import os
from pathlib import Path
import queue
import re
import subprocess
import threading

import paho.mqtt.client as mqtt
from pub.messages import EVENT_TOPIC, MICROPHONE_TOPIC


def parse_devices(output):
    devices = []
    for line in output.splitlines():
        m = re.match(r'card \d+: (\S+) \[([^]]+)\], device (\d+): (.*)', line)
        if not m:
            continue
        card, title, number, description = m.groups()
        if card == 'Header' or 'dummy' in description.lower():
            continue  # The bare I2S header is not a microphone.
        label = 'Coral' if card == 'edgetpuaudiocar' else 'Camera C920' if card.startswith('C920') else title
        devices.append(dict(device='plughw:CARD={},DEV={}'.format(card, number), label=label[:80]))
    return sorted(devices, key=lambda d: (not d['device'].startswith('plughw:CARD=edgetpuaudiocar,'), d['device']))


def discover():
    proc = subprocess.run(['arecord', '-l'], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          universal_newlines=True, env=dict(os.environ, LC_ALL='C'), timeout=5)
    if proc.returncode:
        return []
    return parse_devices(proc.stdout)


def choose(devices, current=None, steps=0):
    if not devices:
        raise RuntimeError('Nenhum microfone disponivel')
    keys = [d['device'] for d in devices]
    index = keys.index(current) if current in keys else (-1 if steps else 0)
    return devices[(index + steps) % len(devices)]


def is_native(device):
    return device.startswith('plughw:CARD=edgetpuaudiocar,')


class SelectionPolicy:
    """Prefer external capture, respecting manual choice until a USB arrival."""
    def __init__(self, preferred=None):
        self.preferred = preferred
        self.seen = set()
        self.manual = None
        self.retry_after = {}

    def failed(self, device, now):
        # A listed USB device may be busy or broken. Avoid retrying every scan.
        self.retry_after[device] = now + 30
        if self.manual == device:
            self.manual = None

    def select(self, devices, current=None, steps=0, now=0):
        keys = {d['device'] for d in devices}
        arrived = keys - self.seen
        for removed in self.seen - keys:
            self.retry_after.pop(removed, None)
        if self.manual not in keys or any(not is_native(k) for k in arrived):
            self.manual = None
        self.seen = keys
        available = [d for d in devices if now >= self.retry_after.get(d['device'], 0)]
        if not available:
            return None
        if steps:
            target = choose(available, current, steps)
            self.manual = target['device']
            return target
        manual = next((d for d in available if d['device'] == self.manual), None)
        if manual:
            return manual
        external = [d for d in available if not is_native(d['device'])]
        pool = external or available
        # Keep an active external device stable when another USB mic appears.
        return choose(pool, current if current in [d['device'] for d in pool] else self.preferred)


def state_path():
    return Path.home() / '.config' / 'coral-birds' / 'microphone.json'


def load_choice(path=None):
    try:
        value = json.loads((path or state_path()).read_text())
        return value.get('device') if isinstance(value, dict) else None
    except (OSError, ValueError):
        return None


def save_choice(device, path=None):
    path = path or state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(dict(device=device)) + '\n')
    os.replace(str(temporary), str(path))


def prepare(device):
    if device.startswith('plughw:CARD=edgetpuaudiocar,'):
        subprocess.run(['bash', str(Path(__file__).parent / 'services' / 'configure-microphone.sh')],
                       env=dict(os.environ, CORAL_AUDIO_DEVICE=device), check=True, timeout=15)


class ButtonEvents:
    """The MQTT callback only queues clicks; no audio operations on its thread."""
    def __init__(self):
        self.clicks = queue.Queue(maxsize=64)
        self.seen = collections.deque(maxlen=256)
        self.connected = threading.Event()
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        self.client.on_connect = self._connect
        self.client.on_disconnect = lambda *_: self.connected.clear()
        self.client.on_message = self._message
        self.client.reconnect_delay_set(1, 10)
        self.client.max_queued_messages_set(8)

    def _connect(self, client, userdata, flags, reason, properties):
        if not reason.is_failure:
            client.subscribe(EVENT_TOPIC, qos=1)
            self.connected.set()

    def accept(self, event, retained=False):
        if retained or not isinstance(event, dict) or event.get('event') != 'microphone_next':
            return False
        if event.get('type') != 'event' or not isinstance(event.get('data'), dict) or event['data'].get('gpio') != 32:
            return False
        key = (event.get('boot_id'), event.get('seq'))
        if not isinstance(key[0], str) or type(key[1]) is not int or key in self.seen:
            return False
        self.seen.append(key)
        try:
            self.clicks.put_nowait(key)
            return True
        except queue.Full:
            return False

    def _message(self, client, userdata, msg):
        try:
            self.accept(json.loads(msg.payload), msg.retain)
        except (ValueError, TypeError, AttributeError):
            pass

    def start(self):
        self.client.connect_async(os.environ.get('CORAL_MQTT_HOST', '127.0.0.1'), 1883, 30)
        self.client.loop_start()

    def pending(self):
        count = 0
        while True:
            try:
                self.clicks.get_nowait()
                count += 1
            except queue.Empty:
                return count

    def status(self, current, devices, status='active', error=None):
        payload = dict(current or {}, available=devices, status=status, error=error)
        self.client.publish(MICROPHONE_TOPIC, json.dumps(payload, ensure_ascii=False), qos=1, retain=True)

    def close(self):
        self.client.disconnect()
        self.client.loop_stop()
