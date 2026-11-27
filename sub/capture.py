"""Cancellable ALSA capture; bounded queues keep classification on fresh audio."""
import queue
import subprocess
import tempfile
import threading
import time


def latest(target, item):
    try:
        target.put_nowait(item)
    except queue.Full:
        try:
            target.get_nowait()
        except queue.Empty:
            pass
        target.put_nowait(item)


class AudioSession:
    def __init__(self, classifier, device, every=3):
        self.classifier, self.device, self.every = classifier, device, every
        self.stopped = threading.Event()
        self.frames, self.results = queue.Queue(maxsize=1), queue.Queue(maxsize=1)
        self.error = None
        self.dropped = 0
        self.errors = tempfile.TemporaryFile()  # stderr only; never persist audio.
        self.process = subprocess.Popen(['arecord', '-q', '-D', device, '-t', 'raw',
                                         '-f', 'S16_LE', '-c', '1', '-r', '48000'],
                                        stdout=subprocess.PIPE, stderr=self.errors)
        self.reader = threading.Thread(target=self._capture, daemon=True)
        self.worker = threading.Thread(target=self._classify, daemon=True)
        self.last_audio = time.monotonic()
        self.reader.start()
        self.worker.start()

    def _capture(self):
        previous, total, first = b'', 0, True
        try:
            while not self.stopped.is_set():
                needed = 288000 if first else round(self.every * 48000) * 2
                data = bytearray()
                while len(data) < needed and not self.stopped.is_set():
                    block = self.process.stdout.read(needed-len(data))
                    if not block:
                        raise RuntimeError('Microfone desconectado ou captura encerrada')
                    data.extend(block)
                if self.stopped.is_set():
                    break
                total += len(data)
                previous = (previous + bytes(data))[-288000:]
                first = False
                captured_at = time.monotonic()
                self.last_audio = captured_at
                if self.frames.full():
                    self.dropped += 1
                latest(self.frames, (previous, total/96000, captured_at))
        except Exception as error:
            if not self.stopped.is_set():
                self.error = error

    def _classify(self):
        try:
            while not self.stopped.is_set():
                try:
                    pcm, end, captured_at = self.frames.get(timeout=.1)
                except queue.Empty:
                    continue
                result = self.classifier.predict_pcm(pcm)
                if self.stopped.is_set():
                    break
                result.update(mode='microphone', device=self.device, start_seconds=end-3,
                              audio_end_seconds=end, cadence_seconds=self.every,
                              dropped_windows=self.dropped, captured_monotonic=captured_at)
                latest(self.results, result)
        except Exception as error:
            if not self.stopped.is_set():
                self.error = error

    def get(self):
        if self.error:
            raise RuntimeError(str(self.error))
        if time.monotonic()-self.last_audio > max(10, self.every*2):
            raise RuntimeError('Microfone deixou de fornecer audio')
        try:
            result = self.results.get_nowait()
        except queue.Empty:
            return None
        # Recompute after delivery to include any time waiting for main-loop work.
        result['result_age_seconds'] = time.monotonic()-result.pop('captured_monotonic')
        return result

    def close(self):
        self.stopped.set()
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.process.kill(); self.process.wait(timeout=2)
        self.reader.join(timeout=3)
        self.worker.join(timeout=10)
        if self.reader.is_alive() or self.worker.is_alive():
            raise RuntimeError('Captura anterior nao encerrou; reinicio necessario')
        self.process.stdout.close()
        self.errors.close()
