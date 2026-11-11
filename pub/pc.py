#!/usr/bin/env python3
"""Publish from a PC through SSH, without installing Python packages on the PC."""
import argparse
import json
import os
import shlex
import subprocess
import sys


def publish(text, host=None, remote_dir=None):
    """Send message on stdin; never interpolate it in a remote shell command."""
    if not isinstance(text, str):
        raise ValueError('A mensagem precisa ser texto.')
    directory = remote_dir or os.environ.get('CORAL_REMOTE_DIR')
    directory_arg = shlex.quote(directory) if directory else '"$HOME/coral-esp32-display"'
    command = 'cd {} && python3 -m pub -'.format(directory_arg)
    result = subprocess.run(
        ['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=8',
         host or os.environ.get('CORAL_SSH_HOST', 'coral-dev-board'), command],
        input=text, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60)
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or 'Falha na publicacao remota.')
    return json.loads(result.stdout)


def main():
    parser = argparse.ArgumentParser(description='Publicar no OLED da Coral a partir do PC via SSH.')
    parser.add_argument('text', nargs='+', help='Mensagem, ou - para ler stdin.')
    parser.add_argument('--host', help='Host/alias SSH; padrao coral-dev-board.')
    parser.add_argument('--remote-dir', help='Diretorio do repositorio na Coral; padrao ~/coral-esp32-display.')
    args = parser.parse_args()
    try:
        message = sys.stdin.read() if args.text == ['-'] else ' '.join(args.text)
        print(json.dumps(publish(message, args.host, args.remote_dir), ensure_ascii=False))
        return 0
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as error:
        print(str(error), file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
