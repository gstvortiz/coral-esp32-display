#!/usr/bin/env python3
"""MQTT subscriber owning the serial port. Latest desired screen wins."""
import json
import logging
import os
import signal
import threading
import time
import uuid

import paho.mqtt.client as mqtt
from .serial_display import Display
from pub.messages import display_text, region_messages
from pub.messages import COMMAND_TOPIC, STATE_TOPIC, EVENT_TOPIC


def parse_message(payload):
    if len(payload) > 8192:
        raise ValueError('payload_too_long')
    value = payload.decode('utf-8')
    try:
        decoded = json.loads(value)
    except ValueError:
        decoded = None
    request = decoded if isinstance(decoded, dict) and 'cmd' in decoded else {'cmd': 'text', 'text': value}
    request = dict(request)
    request.setdefault('id', uuid.uuid4().hex)
    if not isinstance(request['id'], str) or len(request['id']) > 64:
        raise ValueError('invalid_id')
    if request.get('cmd') not in ('text', 'regions', 'clear', 'clock'):
        raise ValueError('unknown_command')
    if request['cmd'] == 'text':
        if not isinstance(request.get('text'), str):
            raise ValueError('text_required')
        request['text'] = display_text(request['text'])
    if request['cmd'] == 'regions':
        request.update(region_messages(request.get('blue'), request.get('yellow')))
    return request


def screen_matches(status, request):
    if status.get('mode') != request['cmd']:
        return False
    keys = ('blue', 'yellow') if request['cmd'] == 'regions' else ('text',) if request['cmd'] == 'text' else ()
    return all(status.get(key) == request[key] for key in keys)


def needs_replay(status, request, boot_id):
    # Local firmware tasks may legitimately change the display. Replay only after
    # a reset; older firmware without boot IDs keeps its original recovery policy.
    if status.get('boot_id'):
        return boot_id is not None and status['boot_id'] != boot_id
    return not screen_matches(status, request)


def forward_event(client, event):
    # Events describe occurrences, not desired state: never retain/replay them.
    info = client.publish(EVENT_TOPIC, json.dumps(event, ensure_ascii=False), qos=1, retain=False)
    if info.rc != mqtt.MQTT_ERR_SUCCESS:
        logging.warning('Evento %s nao confirmado na fila MQTT: rc=%s', event.get('event'), info.rc)


class DesiredScreen:
    def __init__(self):
        self.condition = threading.Condition()
        self.revision = 0
        self.request = None

    def set(self, request):
        with self.condition:
            self.revision += 1
            self.request = request
            self.condition.notify_all()

    def get(self, after, timeout=5):
        with self.condition:
            self.condition.wait_for(lambda: self.revision != after, timeout)
            return self.revision, self.request


def run():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')
    desired, stopping = DesiredScreen(), threading.Event()
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id='coral-display-subscriber')
    client.max_queued_messages_set(20)
    client.reconnect_delay_set(1, 15)
    client.will_set(STATE_TOPIC, json.dumps({'online': False, 'ok': False, 'error': 'subscriber_offline'}), qos=1, retain=True)

    def report(state):
        client.publish(STATE_TOPIC, json.dumps(state, ensure_ascii=False), qos=1, retain=True)

    def connected(c, userdata, flags, reason, properties):
        if not reason.is_failure:
            c.subscribe(COMMAND_TOPIC, qos=1)
            report({'online': True, 'ok': False, 'status': 'waiting_for_message'})
            logging.info('Assinando %s', COMMAND_TOPIC)

    def received(c, userdata, message):
        try:
            desired.set(parse_message(message.payload))
        except (ValueError, UnicodeError) as error:
            request_id = ''
            try:
                value = json.loads(message.payload)
                if isinstance(value, dict):
                    request_id = value.get('id', '')
            except (ValueError, UnicodeError):
                pass
            report({'online': True, 'ok': False, 'id': request_id, 'error': str(error)})
            logging.warning('Mensagem recusada: %s', error)

    def stop(signum, frame):
        stopping.set()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    client.on_connect, client.on_message = connected, received
    client.connect_async(os.environ.get('CORAL_MQTT_HOST', '127.0.0.1'), 1883, 30)
    client.loop_start()
    request = None
    try:
        while not stopping.is_set():
            try:
                with Display(on_event=lambda event: forward_event(client, event)) as display:
                    applied_revision = -1
                    boot_id = None
                    next_health = 0
                    while not stopping.is_set():
                        revision, request = desired.get(applied_revision, timeout=0)
                        if request is None:
                            applied_revision = revision
                            display.poll_events()
                            if time.monotonic() >= next_health:
                                boot_id = display.status().get('boot_id')
                                next_health = time.monotonic() + 5
                            continue
                        if revision == applied_revision:
                            display.poll_events()
                            if time.monotonic() >= next_health:
                                status = display.status()
                                if needs_replay(status, request, boot_id):
                                    applied_revision = -1
                                boot_id = status.get('boot_id')
                                next_health = time.monotonic() + 5
                            continue
                        if request['cmd'] == 'text':
                            result = display.show(request['text'], remember=False)
                        elif request['cmd'] == 'regions':
                            result = display.show_regions(request['blue'], request['yellow'], remember=False)
                        else:
                            result = getattr(display, request['cmd'])(remember=False)
                        result['serial_id'] = result['id']
                        result.update(id=request['id'], online=True)
                        report(result)
                        boot_id = result.get('boot_id')
                        next_health = time.monotonic() + 5
                        applied_revision = revision
                        logging.info('Mensagem %s aplicada (%s)', request['id'], request['cmd'])
            except (OSError, RuntimeError, ValueError) as error:
                report({'id': request['id'] if request else '', 'online': True, 'ok': False,
                        'error': str(error), 'status': 'retrying_serial'})
                logging.warning('Serial indisponivel; tentando novamente: %s', error)
                stopping.wait(2)
    finally:
        if client.is_connected():
            info = client.publish(STATE_TOPIC, json.dumps({'online': False, 'ok': False}), qos=1, retain=True)
            info.wait_for_publish(2)
        client.disconnect()
        client.loop_stop()


if __name__ == '__main__':
    run()
