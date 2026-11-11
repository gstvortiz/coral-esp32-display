import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sub.subscriber import DesiredScreen, parse_message, screen_matches, needs_replay, forward_event
from unittest.mock import Mock
from pub.messages import EVENT_TOPIC
from pub.messages import region_messages


class PubSubTests(unittest.TestCase):
    def test_local_display_change_is_preserved_until_reset(self):
        desired = {'cmd': 'regions', 'blue': ['MQTT'], 'yellow': ['Online']}
        local = {'mode': 'regions', 'blue': ['Local'], 'yellow': ['Fila'], 'boot_id': 'one'}
        self.assertFalse(needs_replay(local, desired, 'one'))
        self.assertTrue(needs_replay(dict(local, boot_id='two'), desired, 'one'))
        self.assertTrue(needs_replay(dict(local, boot_id=None), desired, None))

    def test_events_are_not_retained_as_screen_state(self):
        mqtt_client = Mock()
        mqtt_client.publish.return_value.rc = 0
        event = {'type': 'event', 'event': 'finished', 'boot_id': 'one', 'seq': 2}
        forward_event(mqtt_client, event)
        args, kwargs = mqtt_client.publish.call_args
        self.assertEqual(args[0], EVENT_TOPIC)
        self.assertEqual(json.loads(args[1]), event)
        self.assertEqual(kwargs, {'qos': 1, 'retain': False})

    def test_regions_normalize_and_detect_reset(self):
        request = parse_message(json.dumps({'cmd': 'regions', 'blue': ['Ação', 'Coral'],
                                           'yellow': 'Pronta'}).encode())
        self.assertEqual(request['blue'], ['Acao', 'Coral'])
        self.assertEqual(request['yellow'], ['Pronta'])
        state = dict(request, mode='regions', blue_index=1, blue_page_offset=10)
        self.assertTrue(screen_matches(state, request))
        self.assertFalse(screen_matches(dict(state, yellow=['Errado']), request))
        self.assertFalse(screen_matches(dict(state, mode='text'), request))

    def test_regions_limits_and_blank_area(self):
        self.assertEqual(region_messages('', '')['yellow'], [''])
        self.assertEqual(len(region_messages('a' * 1024, '')['blue'][0]), 1024)
        for blue, yellow in (([], 'ok'), (['x'] * 9, 'ok'), ('ok', None),
                             ([1], 'ok'), ('a' * 1024, 'b'), ('ok', '\x00')):
            with self.assertRaises(ValueError):
                region_messages(blue, yellow)

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
