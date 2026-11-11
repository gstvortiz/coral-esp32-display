#!/usr/bin/env python3
"""Send text from Coral to the ESP32 SSD1306, with a matching JSON acknowledgment."""
import argparse
import glob
import json
import os
import sys
import time
import uuid

import serial
from pub.messages import display_text


def default_port():
    if os.environ.get('CORAL_DISPLAY_PORT'):
        return os.environ['CORAL_DISPLAY_PORT']
    ports = glob.glob('/dev/serial/by-id/*CP210*')
    if len(ports) == 1:
        return ports[0]
    if len(ports) > 1:
        raise ValueError('Mais de um CP210 encontrado; informe --port.')
    return '/dev/ttyUSB0'


class Display:
    """Reusable connection. Context manager closes the serial port on exit."""
    def __init__(self, port=None, timeout=6, boot_wait=2.5):
        self.timeout = timeout
        self.serial = serial.Serial(port=None, baudrate=115200, timeout=0.15,
                                    write_timeout=2, exclusive=True)
        self.serial.dtr = False
        self.serial.rts = False
        self.serial.port = port or default_port()
        try:
            self.serial.open()
            # Some USB-UART boards pulse reset when the port opens.
            time.sleep(boot_wait)
            self.serial.reset_input_buffer()
        except Exception:
            self.serial.close()
            raise

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.serial.close()

    def request(self, command, **fields):
        request_id = uuid.uuid4().hex
        payload = dict(fields, cmd=command, id=request_id)
        packet = json.dumps(payload, ensure_ascii=True, separators=(',', ':')).encode() + b'\n'
        if len(packet) > 2305:
            raise ValueError('Quadro serial excede 2304 bytes.')
        self.serial.write(packet)
        deadline = time.monotonic() + self.timeout
        buffer = bytearray()
        while time.monotonic() < deadline:
            buffer.extend(self.serial.read(self.serial.in_waiting or 1))
            if len(buffer) > 16384:
                raise RuntimeError('Resposta serial excede o limite.')
            while b'\n' in buffer:
                line, _, tail = buffer.partition(b'\n')
                buffer = bytearray(tail)
                try:
                    result = json.loads(line)
                except (ValueError, UnicodeError):
                    continue
                if not isinstance(result, dict) or result.get('id') != request_id:
                    continue
                if result.get('ok') is not True:
                    raise RuntimeError('ESP32: ' + str(result.get('error', result)))
                return result
        raise TimeoutError('ESP32 nao confirmou o comando. Verifique o firmware coral-display.')

    def show(self, text, remember=True):
        return self.request('text', text=display_text(text), remember=remember)

    def status(self):
        return self.request('status')

    def clear(self, remember=True):
        return self.request('clear', remember=remember)

    def clock(self, remember=True):
        return self.request('clock', remember=remember)


def main():
    parser = argparse.ArgumentParser(description='Enviar texto ao OLED conectado ao ESP32.')
    parser.add_argument('text', nargs='*', help='Mensagem; use - para ler da entrada padrao.')
    parser.add_argument('--port', help='Porta serial (ou CORAL_DISPLAY_PORT).')
    parser.add_argument('--volatile', action='store_true', help='Nao salvar na flash do ESP32.')
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument('--status', action='store_true')
    actions.add_argument('--clear', action='store_true')
    actions.add_argument('--clock', action='store_true')
    args = parser.parse_args()
    action = 'status' if args.status else 'clear' if args.clear else 'clock' if args.clock else 'text'
    if action != 'text' and args.text:
        parser.error('Nao combine mensagem com --status, --clear ou --clock.')
    if action == 'text' and not args.text:
        parser.error('Informe uma mensagem ou --status/--clear/--clock.')
    try:
        text = sys.stdin.read() if args.text == ['-'] else ' '.join(args.text)
        if action == 'text':
            text = display_text(text)  # Validate before opening/resetting hardware.
        with Display(args.port) as display:
            if action == 'text':
                result = display.show(text, remember=not args.volatile)
            elif action == 'status':
                result = display.status()
            else:
                result = getattr(display, action)(remember=not args.volatile)
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except (OSError, serial.SerialException, RuntimeError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
