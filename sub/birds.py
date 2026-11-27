"""Boot-time BirdNET integration using the already installed, verified bundle."""
import argparse
import fcntl
import json
import logging
import math
from pathlib import Path
import signal
import sys
import threading
import time

from .capture import AudioSession
from . import microphones
from .bird_names import BirdNames
from pub.messages import notice_message

from pub.birds import observation
from pub.mqtt import exchange


def load_config(path):
    config = dict(bundle='/home/mendel/bird_recognition/current', threshold=0.85,
                  lifetime=8, every=3, threads=4,
                  device='plughw:CARD=edgetpuaudiocar,DEV=0')
    if path:
        with open(path) as source:
            custom = json.load(source)
        if not isinstance(custom, dict) or set(custom) - set(config):
            raise ValueError('Configuracao desconhecida')
        config.update(custom)
    for key, low, high in [('threshold', 0, 1), ('lifetime', 3, 30), ('every', 1, 10)]:
        value = config[key]
        if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value) or not low <= value <= high:
            raise ValueError('Configuracao invalida: ' + key)
    if config['lifetime'] <= config['every']:
        raise ValueError('lifetime deve superar every')
    if type(config['threads']) is not int or not 1 <= config['threads'] <= 8:
        raise ValueError('threads invalido')
    return config


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config')
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')
    config = load_config(args.config)
    stopped = threading.Event()
    def stop(*_):
        stopped.set()
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    # Same lock used by the original installer/runtime. Bundle files stay unchanged.
    lock = open(str(Path.home() / '.coral-birds.lock'), 'a+')
    fcntl.flock(lock, fcntl.LOCK_SH)
    sys.path.insert(0, config['bundle'])
    from bird_recognition.runtime import BirdClassifier
    names = BirdNames()
    names.check_labels(classifier_labels=Path(config['bundle']) / 'labels.txt')
    classifier = BirdClassifier(Path(config['bundle']), threshold=config['threshold'],
                                top_k=3, threads=config['threads'])
    buttons = microphones.ButtonEvents()
    buttons.start()
    session, current, confirmed = None, None, False
    no_signal_windows = 0
    next_scan = 0
    devices = []

    def send(command):
        try:
            return exchange(command, timeout=3)
        except (OSError, RuntimeError, ValueError) as error:
            logging.warning('ESP indisponivel; comando nao confirmado: %s', error)
            return {}

    def notify(label, detail):
        send(notice_message(label, detail, 4000))

    def select(target):
        nonlocal session, current, confirmed, no_signal_windows
        if session is not None:
            session.close()
            session = None
        # Clear the old source's bird before switching capture. Any pending result
        # belongs to the old session and is discarded when that session is closed.
        send(observation({}, config['lifetime']))
        current, confirmed, no_signal_windows = target, False, 0
        buttons.status(current, devices, 'switching')
        notify(target['label'], 'Selecionando...')
        microphones.prepare(target['device'])
        session = AudioSession(classifier, target['device'], config['every'])
        logging.info('Microfone selecionado: %s (%s)', target['label'], target['device'])

    try:
        preferred = microphones.load_choice() or config['device']
        policy = microphones.SelectionPolicy(preferred)
        devices = microphones.discover()
        target = policy.select(devices, now=time.monotonic())
        if target:
            select(target)
        while not stopped.is_set():
            clicks = buttons.pending()
            now = time.monotonic()
            if clicks or now >= next_scan:
                devices = microphones.discover()
                next_scan = now + 2
                key = current['device'] if current else None
                target = policy.select(devices, key, clicks, now=time.monotonic())
                if target is None:
                    if session is not None:
                        session.close(); session = None
                        send(observation({}, config['lifetime']))
                        notify('Sem microfone', 'Conecte um USB')
                    buttons.status(None, [], 'unavailable')
                    current = None
                else:
                    if session is None or not current or target['device'] != current['device']:
                        select(target)
                    elif clicks:
                        notify(current['label'], 'Microfone ativo' if confirmed else 'Selecionando...')
            if session is None:
                stopped.wait(.1)
                continue
            try:
                result = session.get()
                if result is None:
                    stopped.wait(.05)
                    continue
                received_at = time.monotonic()
                if not confirmed:
                    confirmed = True
                    microphones.save_choice(current['device'])
                    buttons.status(current, devices)
                    notify(current['label'], 'Microfone ativo')
                no_signal_windows = no_signal_windows + 1 if result['status'] == 'no_signal' else 0
                if no_signal_windows >= 3:
                    raise RuntimeError('Microfone sem sinal em 3 janelas')
                result = names.localize(result)
                # Notification/serialization may have taken time; preserve the capture
                # timestamp by ageing this result before computing its audio window.
                result['result_age_seconds'] += time.monotonic() - received_at
                command = observation(result, config['lifetime'])
                ack = send(command)
                logging.info('microfone=%s status=%s nome=%s score=%.3f atraso=%.2fs sd=%s direcao=%s sync=%s',
                             current['label'], result['status'], command['name'], command['score'],
                             result.get('result_age_seconds', 0), ack.get('bird', {}).get('sd_ok'),
                             ack.get('bird', {}).get('direction', ''), ack.get('bird', {}).get('direction_sync', ''))
            except (OSError, RuntimeError, ValueError) as error:
                logging.exception('Falha na captura; procurando outro microfone')
                failed = current['device']
                buttons.status(current, devices, 'error', str(error))
                session.close(); session = None
                send(observation({}, config['lifetime']))
                notify('Falha no microfone', current['label'])
                devices = microphones.discover()
                policy.failed(failed, time.monotonic())
                target = policy.select(devices, now=time.monotonic())
                if target:
                    select(target)
                else:
                    stopped.wait(2)
                    next_scan = 0
    except KeyboardInterrupt:
        pass
    finally:
        if session is not None:
            session.close()
        send(observation({}, config['lifetime']))
        buttons.status(current, devices, 'stopped')
        buttons.close()
        lock.close()


if __name__ == '__main__':
    main()
