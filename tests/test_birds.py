import json
import tempfile
import time
import unittest
from unittest.mock import patch
from pub.birds import observation, validate_bird, serial_fields
from sub.subscriber import parse_message
from sub.birds import load_config


class BirdTests(unittest.TestCase):
    def test_gate_only_fresh_high_confidence_detections(self):
        bird = {'name': 'sabiá-laranjeira', 'scientific_name': 'Turdus rufiventris', 'score': .94}
        with patch('pub.birds.time.time', return_value=100):
            request = parse_message(json.dumps(observation({'detections': [bird], 'result_age_seconds': 2})).encode())
        self.assertTrue(request['active'])
        self.assertEqual(request['name'], 'sabia-laranjeira')
        self.assertEqual(serial_fields(request, now=103)['ttl_ms'], 3000)
        expired = serial_fields(request, now=107)
        self.assertFalse(expired['active'])
        self.assertEqual(expired['name'], '')
        self.assertEqual(expired['score'], 0)
        self.assertFalse(observation({'detections': [bird], 'result_age_seconds': 9})['active'])
        self.assertFalse(observation({'candidates': [bird]})['active'])

    def test_invalid_payloads(self):
        base = observation({})
        for key, value in [('active', 1), ('score', float('nan')), ('score', 1.1),
                           ('score', True), ('expires_at', float('inf')),
                           ('expires_at', time.time()+100), ('name', 'x'*129)]:
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                validate_bird(dict(base, **{key: value}))

    def test_retries_never_refresh_an_old_detection(self):
        request = dict(active=True, name='bird', scientific_name='bird', score=.9, expires_at=100)
        self.assertEqual(serial_fields(request, now=98)['ttl_ms'], 2000)
        self.assertEqual(serial_fields(request, now=99)['ttl_ms'], 1000)
        self.assertFalse(serial_fields(request, now=101)['active'])

    def test_config(self):
        self.assertEqual(load_config(None)['threshold'], .85)
        with tempfile.NamedTemporaryFile(mode='w') as source:
            json.dump({'lifetime': 3, 'every': 3}, source); source.flush()
            with self.assertRaises(ValueError):
                load_config(source.name)

    def test_audio_window_excludes_inference_and_transport_delay(self):
        result = dict(mode='microphone', start_seconds=12, audio_end_seconds=15,
                      result_age_seconds=.7,
                      detections=[dict(name='bem-te-vi', scientific_name='bird', score=.9)])
        request = observation(result, now=100)
        self.assertEqual(request['window_start_ms'], 96300)
        self.assertEqual(request['window_end_ms'], 99300)
        for now in (101, 102, 109):
            fields = serial_fields(request, now=now)
            self.assertEqual(fields['window_start_ms'], 96300)
            self.assertEqual(fields['window_end_ms'], 99300)
            self.assertEqual(fields['epoch_ms'], now*1000)
        self.assertFalse(serial_fields(request, now=109)['active'])

    def test_invalid_window_is_rejected(self):
        base = observation({})
        for start, end in [(1, 1), (10, 9), (1, 10002), (True, 10), (1, 2.0), (0, 3)]:
            with self.subTest(start=start, end=end), self.assertRaises(ValueError):
                validate_bird(dict(base, window_start_ms=start, window_end_ms=end))
        with self.assertRaises(ValueError):
            validate_bird(dict(base, window_start_ms=1))
        result = dict(mode='microphone', start_seconds=0, audio_end_seconds=3,
                      result_age_seconds=float('nan'))
        with self.assertRaises(ValueError):
            observation(result)


if __name__ == '__main__':
    unittest.main()
