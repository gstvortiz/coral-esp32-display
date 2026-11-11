#!/usr/bin/env python3
"""Publish from a PC through SSH, without installing Python packages on the PC."""
import argparse
import json
import os
import shlex
import subprocess
import sys
from .messages import region_messages


def publish(text, host=None, remote_dir=None):
    """Send message on stdin; never interpolate it in a remote shell command."""
    if not isinstance(text, str):
        raise ValueError('A mensagem precisa ser texto.')
    return _send(text, '-', host, remote_dir)


def publish_regions(blue, yellow, host=None, remote_dir=None):
    return _send(json.dumps(region_messages(blue, yellow)), '--regions-json', host, remote_dir)


def _send(payload, action, host, remote_dir):
    directory = remote_dir or os.environ.get('CORAL_REMOTE_DIR')
    directory_arg = shlex.quote(directory) if directory else '"$HOME/coral-esp32-display"'
    command = 'cd {} && python3 -m pub {}'.format(directory_arg, action)
    result = subprocess.run(
        ['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=8',
         host or os.environ.get('CORAL_SSH_HOST', 'coral-dev-board'), command],
        input=payload, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60)
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or 'Falha na publicacao remota.')
    return json.loads(result.stdout)


def listen_events(host=None, remote_dir=None, count=0, timeout=None):
    if count < 0 or (timeout is not None and timeout <= 0):
        raise ValueError('count deve ser >= 0 e timeout deve ser > 0.')
    directory = remote_dir or os.environ.get('CORAL_REMOTE_DIR')
    directory_arg = shlex.quote(directory) if directory else '"$HOME/coral-esp32-display"'
    command = 'cd {} && python3 -u -m pub.events --count {}'.format(directory_arg, int(count))
    if timeout is not None:
        command += ' --timeout {}'.format(float(timeout))
    # Inherit stdout so events appear as they arrive, without local MQTT packages.
    return subprocess.call(['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=8',
                            host or os.environ.get('CORAL_SSH_HOST', 'coral-dev-board'), command])


def main():
    parser = argparse.ArgumentParser(description='Publicar no OLED da Coral a partir do PC via SSH.')
    parser.add_argument('text', nargs='*', help='Mensagem, ou - para ler stdin.')
    parser.add_argument('--blue', action='append', help='Mensagem azul; pode repetir.')
    parser.add_argument('--yellow', action='append', help='Mensagem amarela; pode repetir.')
    parser.add_argument('--events', action='store_true', help='Escutar eventos espontaneos do ESP32.')
    parser.add_argument('--count', type=int, default=0, help='Com --events: sair apos N eventos.')
    parser.add_argument('--timeout', type=float, help='Com --events: limite de espera em segundos.')
    parser.add_argument('--host', help='Host/alias SSH; padrao coral-dev-board.')
    parser.add_argument('--remote-dir', help='Diretorio do repositorio na Coral; padrao ~/coral-esp32-display.')
    args = parser.parse_args()
    regions = args.blue is not None or args.yellow is not None
    if args.events and (regions or args.text):
        parser.error('Nao combine --events com mensagens.')
    if not args.events and (args.count or args.timeout is not None):
        parser.error('--count e --timeout exigem --events.')
    if not args.events and regions == bool(args.text):
        parser.error('Informe texto simples ou --blue/--yellow.')
    try:
        if args.events:
            return listen_events(args.host, args.remote_dir, args.count, args.timeout)
        elif regions:
            result = publish_regions(args.blue or [''], args.yellow or [''], args.host, args.remote_dir)
        else:
            message = sys.stdin.read() if args.text == ['-'] else ' '.join(args.text)
            result = publish(message, args.host, args.remote_dir)
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except KeyboardInterrupt:
        return 130
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as error:
        print(str(error), file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
