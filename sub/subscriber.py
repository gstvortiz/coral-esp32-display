#!/usr/bin/env python3
"""MQTT subscriber owning the serial port. Latest desired screen wins."""
import json
import logging
import os
import signal
import threading
import uuid

import paho.mqtt.client as mqtt
from .serial_display import Display
from pub.messages import display_text
from pub.messages import COMMAND_TOPIC, STATE_TOPIC


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
    if request.get('cmd') not in ('text', 'clear', 'clock'):
        raise ValueError('unknown_command')
    if request['cmd'] == 'text':
        if not isinstance(request.get('text'), str):
            raise ValueError('text_required')
        request['text'] = display_text(request['text'])
    return request


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
                with Display() as display:
                    applied_revision = -1
                    while not stopping.is_set():
                        revision, request = desired.get(applied_revision)
                        if request is None:
                            applied_revision = revision
                            display.status()
                            continue
                        if revision == applied_revision:
                            status = display.status()  # Detect USB loss or an MCU reset while idle.
                            if status.get('mode') != request['cmd'] or (
                                    request['cmd'] == 'text' and status.get('text') != request['text']):
                                applied_revision = -1
                            continue
                        if request['cmd'] == 'text':
                            result = display.show(request['text'], remember=False)
                        else:
                            result = getattr(display, request['cmd'])(remember=False)
                        result['serial_id'] = result['id']
                        result.update(id=request['id'], online=True)
                        report(result)
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
