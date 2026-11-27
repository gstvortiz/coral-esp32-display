import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from sub import microphones
from sub.capture import AudioSession
from pub.messages import notice_message
from sub.subscriber import parse_message

ALSA = '''card 0: edgetpuaudiocar [edgetpu-audio-card], device 0: Coral Edge TPU HiFi []
card 1: Header [40-pin Header], device 0: snd-soc-dummy-dai []
card 2: C920 [HD Pro Webcam C920], device 0: USB Audio []'''

class MicrophoneTests(unittest.TestCase):
    def test_discovery_and_cycle_stable_card_ids(self):
        devices=microphones.parse_devices(ALSA)
        self.assertEqual([d['label'] for d in devices], ['Coral','Camera C920'])
        self.assertEqual(devices,microphones.parse_devices(ALSA.replace('card 2:','card 7:')))
        self.assertEqual(microphones.choose(devices,devices[0]['device'],1),devices[1])
        self.assertEqual(microphones.choose(devices,devices[1]['device'],1),devices[0])
        self.assertEqual(microphones.choose(devices,devices[1]['device'],2),devices[1])
        self.assertEqual(microphones.choose(devices[:1],devices[1]['device'],1),devices[0])
        with self.assertRaises(RuntimeError): microphones.choose([])

    def test_choice_persistence(self):
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/'nested'/'microphone.json'
            self.assertIsNone(microphones.load_choice(path))
            microphones.save_choice('plughw:CARD=C920,DEV=0',path)
            self.assertEqual(microphones.load_choice(path),'plughw:CARD=C920,DEV=0')
            path.write_text('corrupt')
            self.assertIsNone(microphones.load_choice(path))

    def test_button_rejects_replay_and_accepts_new_boot(self):
        events=microphones.ButtonEvents()
        event=dict(type='event',event='microphone_next',boot_id='boot1',seq=1,data={'gpio':32})
        self.assertFalse(events.accept(event,retained=True))
        self.assertTrue(events.accept(event))
        self.assertFalse(events.accept(event))
        self.assertTrue(events.accept(dict(event,boot_id='boot2')))
        for invalid in (None,{},dict(event,data=None),dict(event,data={'gpio':33}),dict(event,seq=True)):
            self.assertFalse(events.accept(invalid))
        self.assertEqual(events.pending(),2)
        self.assertEqual(events.pending(),0)

    def test_notice_validation(self):
        notice=notice_message('Câmera','Microfone ativo',4000)
        self.assertEqual(parse_message(json.dumps(dict(notice,id='test')).encode())['blue'],'Camera')
        for duration in (True,0,999,10001,4.0):
            with self.assertRaises(ValueError): notice_message('Coral',duration_ms=duration)

class BlockingPipe:
    def __init__(self): self.first=True; self.closed=False; self.stop=threading.Event()
    def read(self,size):
        if self.first:
            self.first=False
            return b'\x00\x01'*(size//2)
        self.stop.wait(5)
        return b''
    def close(self): self.closed=True

class FakeProcess:
    def __init__(self,*args,**kwargs): self.stdout=BlockingPipe(); self.code=None
    def poll(self): return self.code
    def terminate(self): self.code=0; self.stdout.stop.set()
    def wait(self,timeout=None): return self.code

class FakeClassifier:
    def predict_pcm(self,pcm):
        assert len(pcm)==288000
        return dict(status='no_detection',detections=[])

class CaptureTests(unittest.TestCase):
    @patch('sub.capture.subprocess.Popen',FakeProcess)
    def test_cancel_unblocks_capture_and_ages_results(self):
        session=AudioSession(FakeClassifier(),'fake')
        deadline=time.monotonic()+2
        while session.results.empty() and time.monotonic()<deadline: time.sleep(.01)
        time.sleep(.02)
        result=session.get()
        self.assertIsNotNone(result)
        self.assertEqual((result['start_seconds'],result['audio_end_seconds']),(0,3))
        self.assertGreaterEqual(result['result_age_seconds'],.02)
        session.close()
        self.assertFalse(session.reader.is_alive())
        self.assertFalse(session.worker.is_alive())
        self.assertTrue(session.process.stdout.closed)

if __name__=='__main__': unittest.main()

class ServiceTests(unittest.TestCase):
    def test_switch_closes_previous_capture_and_confirms_each_source(self):
        import sys
        import types
        from sub import birds
        devices=microphones.parse_devices(ALSA)
        history=[]
        class Session:
            def __init__(self,classifier,device,every):
                self.device=device
                history.append(('open',device))
            def get(self): return dict(status='no_detection',detections=[],result_age_seconds=0)
            def close(self): history.append(('close',self.device))
        fake_runtime=types.ModuleType('bird_recognition.runtime')
        fake_runtime.BirdClassifier=lambda *a,**k: object()
        with tempfile.TemporaryDirectory() as root, \
             patch.dict(sys.modules,{'bird_recognition.runtime':fake_runtime}), \
             patch.object(sys,'argv',['sub.birds']), \
             patch('sub.birds.Path.home',return_value=Path(root)), \
             patch('sub.birds.signal.signal'), \
             patch('sub.birds.BirdNames') as names, \
             patch('sub.birds.AudioSession',Session), \
             patch('sub.birds.exchange',return_value={}), \
             patch('sub.microphones.discover',return_value=devices), \
             patch('sub.microphones.prepare'), \
             patch('sub.microphones.ButtonEvents') as button:
            names.return_value.localize.side_effect=lambda x:x
            button.return_value.pending.side_effect=[1,1,KeyboardInterrupt()]
            birds.main()
            self.assertEqual(history,[('open',devices[1]['device']),('close',devices[1]['device']),
                                      ('open',devices[0]['device']),('close',devices[0]['device']),
                                      ('open',devices[1]['device']),('close',devices[1]['device'])])
            self.assertEqual(microphones.load_choice(),devices[1]['device'])


class PriorityTests(unittest.TestCase):
    def setUp(self):
        self.devices = microphones.parse_devices(ALSA)
        self.native, self.usb = self.devices
        self.policy = microphones.SelectionPolicy(self.native['device'])

    def test_boot_external_over_saved_native(self):
        self.assertEqual(self.policy.select(self.devices), self.usb)

    def test_connect_after_boot_unplug_and_reconnect(self):
        self.assertEqual(self.policy.select([self.native]), self.native)
        self.assertEqual(self.policy.select(self.devices, self.native['device']), self.usb)
        self.assertEqual(self.policy.select([self.native], self.usb['device']), self.native)
        self.assertEqual(self.policy.select(self.devices, self.native['device']), self.usb)
        self.assertIsNone(self.policy.select([]))
        self.assertEqual(self.policy.select(self.devices), self.usb)

    def test_manual_native_stays_until_usb_reconnect(self):
        self.policy.select(self.devices)
        self.assertEqual(self.policy.select(self.devices, self.usb['device'], 1), self.native)
        for _ in range(3):
            self.assertEqual(self.policy.select(self.devices, self.native['device']), self.native)
        self.policy.select([self.native], self.native['device'])
        self.assertEqual(self.policy.select(self.devices, self.native['device']), self.usb)

    def test_failed_external_has_retry_backoff(self):
        self.policy.select(self.devices)
        self.policy.failed(self.usb['device'], 10)
        for now in (10, 20, 39):
            self.assertEqual(self.policy.select(self.devices, self.native['device'], now=now), self.native)
        self.assertEqual(self.policy.select(self.devices, self.native['device'], now=40), self.usb)
        self.policy.failed(self.native['device'], 10)
        self.assertIsNone(self.policy.select(self.devices, now=20))

    def test_external_preference_and_stability(self):
        other = dict(device='plughw:CARD=USB,DEV=0', label='USB')
        devices = self.devices + [other]
        policy = microphones.SelectionPolicy(other['device'])
        self.assertEqual(policy.select(devices), other)
        self.assertEqual(policy.select(devices, self.usb['device']), self.usb)
        policy.failed(self.usb['device'], 1)
        self.assertEqual(policy.select(devices, now=2), other)
