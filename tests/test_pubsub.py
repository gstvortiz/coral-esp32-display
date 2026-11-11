import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sub.subscriber import DesiredScreen, parse_message


class PubSubTests(unittest.TestCase):
    def test_plain_text(self):
        result = parse_message('Olá, Coral'.encode())
        self.assertEqual(result['text'], 'Ola, Coral')
        self.assertEqual(result['cmd'], 'text')

    def test_envelope_keeps_id_and_text_is_not_a_command(self):
        result = parse_message(json.dumps({'id': '1', 'cmd': 'text',
                                          'text': '{"cmd":"clear"}'}).encode())
        self.assertEqual(result['id'], '1')
        self.assertEqual(result['text'], '{"cmd":"clear"}')

    def test_invalid_messages(self):
        for value in (b'\xff', b'x' * 8193, b'{"cmd":"reboot"}',
                      b'{"cmd":"text","text":1}', b'x' * 1025):
            with self.assertRaises(ValueError):
                parse_message(value)

    def test_latest_screen_replaces_pending(self):
        desired = DesiredScreen()
        desired.set({'text': 'antiga'})
        desired.set({'text': 'nova'})
        revision, request = desired.get(0, timeout=0)
        self.assertEqual(revision, 2)
        self.assertEqual(request['text'], 'nova')


if __name__ == '__main__':
    unittest.main()
