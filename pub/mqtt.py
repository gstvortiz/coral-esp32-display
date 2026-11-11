#!/usr/bin/env python3
"""Publish an OLED message over MQTT; wait for the Coral/ESP32 acknowledgment."""
import argparse
import json
import os
import sys
import threading
import uuid

import paho.mqtt.client as mqtt

from .messages import COMMAND_TOPIC, STATE_TOPIC, display_text, region_messages


def exchange(command=None, host=None, port=1883, timeout=15):
    host = host or os.environ.get('CORAL_MQTT_HOST', '127.0.0.1')
    request = dict(command, id=uuid.uuid4().hex) if command is not None else None
    ready, done = threading.Event(), threading.Event()
    results, errors = [], []
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.connect_timeout = min(timeout, 5)

    def connected(c, userdata, flags, reason, properties):
        if reason.is_failure:
            errors.append(str(reason)); ready.set()
        else:
            c.subscribe(STATE_TOPIC, qos=1)

    def subscribed(c, userdata, mid, reasons, properties):
        if any(reason.is_failure for reason in reasons):
            errors.append('Assinatura MQTT recusada')
        ready.set()

    def received(c, userdata, message):
        try:
            state = json.loads(message.payload)
        except (ValueError, UnicodeError):
            return
        if isinstance(state, dict) and (request is None or state.get('id') == request['id']):
            results.append(state); done.set()

    client.on_connect, client.on_subscribe, client.on_message = connected, subscribed, received
    try:
        client.connect(host, port, keepalive=30)
        client.loop_start()
        if not ready.wait(timeout):
            raise TimeoutError('Broker MQTT nao confirmou a assinatura.')
        if errors:
            raise RuntimeError(errors[0])
        if request is not None:
            info = client.publish(COMMAND_TOPIC, json.dumps(request, ensure_ascii=False), qos=1, retain=True)
            info.wait_for_publish(timeout)
            if not info.is_published():
                raise TimeoutError('Broker MQTT nao confirmou a publicacao.')
        if not done.wait(timeout):
            raise TimeoutError('Publicado, mas a Coral nao confirmou a exibicao (servico offline ou mensagem substituida).')
        result = results[-1]
        if request is not None and result.get('ok') is not True:
            raise RuntimeError('Coral: ' + str(result.get('error', result)))
        return result
    finally:
        client.disconnect()
        client.loop_stop()


def publish(text, host=None, port=1883, timeout=15):
    if not isinstance(text, str):
        raise ValueError('A mensagem precisa ser texto.')
    # Validate before retaining a new desired state.
    display_text(text)
    return exchange({'cmd': 'text', 'text': text}, host, port, timeout)


def publish_regions(blue, yellow, host=None, port=1883, timeout=15):
    return exchange(dict(region_messages(blue, yellow), cmd='regions'), host, port, timeout)


def main():
    parser = argparse.ArgumentParser(description='Publicar mensagem para o servico OLED da Coral.')
    parser.add_argument('text', nargs='*', help='Mensagem, ou - para ler stdin.')
    parser.add_argument('--host', help='Broker MQTT; padrao 127.0.0.1 ou CORAL_MQTT_HOST.')
    parser.add_argument('--port', type=int, default=1883)
    parser.add_argument('--blue', action='append', help='Mensagem azul; repita para alternar mensagens.')
    parser.add_argument('--yellow', action='append', help='Mensagem amarela; repita para alternar mensagens.')
    action = parser.add_mutually_exclusive_group()
    action.add_argument('--status', action='store_true')
    action.add_argument('--clear', action='store_true')
    action.add_argument('--clock', action='store_true')
    action.add_argument('--regions-json', action='store_true', help='Ler objeto blue/yellow do stdin.')
    args = parser.parse_args()
    regions = args.blue is not None or args.yellow is not None
    if (args.status or args.clear or args.clock or args.regions_json) and (args.text or regions):
        parser.error('Nao combine mensagem e comando.')
    if regions and args.text:
        parser.error('Use texto simples ou --blue/--yellow.')
    if not (args.status or args.clear or args.clock or args.regions_json or args.text or regions):
        parser.error('Informe uma mensagem ou --status/--clear/--clock.')
    try:
        if args.regions_json:
            values = json.load(sys.stdin)
            if not isinstance(values, dict) or 'blue' not in values or 'yellow' not in values:
                raise ValueError('Informe um objeto com blue e yellow.')
            result = publish_regions(values['blue'], values['yellow'], args.host, args.port)
        elif regions:
            result = publish_regions(args.blue or [''], args.yellow or [''], args.host, args.port)
        elif args.status:
            result = exchange(host=args.host, port=args.port)
        elif args.clear or args.clock:
            result = exchange({'cmd': 'clear' if args.clear else 'clock'}, args.host, args.port)
        else:
            value = sys.stdin.read() if args.text == ['-'] else ' '.join(args.text)
            result = publish(value, args.host, args.port)
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except (OSError, ValueError, RuntimeError) as error:
        print(str(error), file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
