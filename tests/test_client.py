import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sub.serial_display import Display, display_text


class Device:
    """Serial peer emits boot noise, a stale ACK and fragmented matching ACK."""
    def __init__(self, error=None, silent=False):
        self.pending = bytearray()
        self.error = error
        self.silent = silent

    @property
    def in_waiting(self):
        return min(3, len(self.pending))

    def write(self, packet):
        self.request = json.loads(packet)
        if self.silent:
            return len(packet)
        result = dict(id=self.request['id'], ok=self.error is None)
        if self.error:
            result['error'] = self.error
        self.pending.extend(b'boot log\n[]\n{"id":"stale","ok":true}\n')
        self.pending.extend(json.dumps(result).encode() + b'\n')
        return len(packet)

    def read(self, count):
        data = bytes(self.pending[:count])
        del self.pending[:count]
        return data


def client(peer):
    obj = Display.__new__(Display)
    obj.serial = peer
    obj.timeout = 0.03
    return obj


class ProtocolTests(unittest.TestCase):
    def test_fragments_and_stale_ack(self):
        peer = Device()
        result = client(peer).show('Olá, Coral!\nMedição', remember=False)
        self.assertTrue(result['ok'])
        self.assertEqual(peer.request['text'], 'Ola, Coral!\nMedicao')
        self.assertFalse(peer.request['remember'])
        self.assertEqual(result['id'], peer.request['id'])

    def test_error_from_device(self):
        with self.assertRaisesRegex(RuntimeError, 'oled_unavailable'):
            client(Device(error='oled_unavailable')).show('Coral')

    def test_no_ack_is_not_success(self):
        with self.assertRaises(TimeoutError):
            client(Device(silent=True)).show('Coral')

    def test_limits_and_control_characters(self):
        self.assertEqual(len(display_text('a' * 1024)), 1024)
        for value in ('a' * 1025, 'abc\x00', '\x1b[2J'):
            with self.assertRaises(ValueError):
                display_text(value)

    def test_command_like_text_is_only_text(self):
        peer = Device()
        value = '{"cmd":"clear"}\nCoral'
        client(peer).show(value)
        self.assertEqual(peer.request['cmd'], 'text')
        self.assertEqual(peer.request['text'], value)


if __name__ == '__main__':
    unittest.main()
