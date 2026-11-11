"""Listen for spontaneous ESP32 events forwarded by the Coral bridge."""
import argparse
import json
import os
import sys
import threading

import paho.mqtt.client as mqtt
from .messages import EVENT_TOPIC


def listen(handler, host=None, port=1883, count=0, timeout=None):
    """Call handler(event) on the MQTT thread. Events are not retained/history."""
    if count < 0 or (timeout is not None and timeout <= 0):
        raise ValueError('count deve ser >= 0 e timeout deve ser > 0.')
    ready, done = threading.Event(), threading.Event()
    errors = []
    received = 0
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.connect_timeout = 5

    def connected(c, userdata, flags, reason, properties):
        if reason.is_failure:
            errors.append(RuntimeError(str(reason))); ready.set(); done.set()
        else:
            c.subscribe(EVENT_TOPIC, qos=1)

    def subscribed(c, userdata, mid, reasons, properties):
        if any(reason.is_failure for reason in reasons):
            errors.append(RuntimeError('Assinatura MQTT recusada')); done.set()
        ready.set()

    def message(c, userdata, msg):
        nonlocal received
        if msg.retain or done.is_set():
            return
        try:
            event = json.loads(msg.payload)
        except (ValueError, UnicodeError):
            return
        if not isinstance(event, dict) or event.get('type') != 'event':
            return
        try:
            handler(event)
        except Exception as error:
            errors.append(error); done.set(); return
        # Only a counter is kept, so an unlimited listener does not grow in memory.
        received += 1
        if count and received >= count:
            done.set()

    client.on_connect, client.on_subscribe, client.on_message = connected, subscribed, message
    try:
        client.connect(host or os.environ.get('CORAL_MQTT_HOST', '127.0.0.1'), port, 30)
        client.loop_start()
        if not ready.wait(10):
            raise TimeoutError('Broker nao confirmou a assinatura de eventos.')
        if errors:
            raise errors[0]
        if not done.wait(timeout):
            raise TimeoutError('Tempo limite aguardando eventos do ESP32.')
        if errors:
            raise errors[0]
        return received
    finally:
        client.disconnect()
        client.loop_stop()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host')
    parser.add_argument('--port', type=int, default=1883)
    parser.add_argument('--count', type=int, default=0, help='Sair apos N eventos; 0 escuta continuamente.')
    parser.add_argument('--timeout', type=float, help='Limite de espera em segundos.')
    args = parser.parse_args()
    try:
        listen(lambda event: print(json.dumps(event, ensure_ascii=False), flush=True),
               args.host, args.port, args.count, args.timeout)
        return 0
    except KeyboardInterrupt:
        return 130
    except (OSError, RuntimeError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
