import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from pub.pc import publish


class RemotePublisherTests(unittest.TestCase):
    @patch('pub.pc.subprocess.run')
    def test_text_is_stdin_and_custom_directory_is_quoted(self, run):
        run.return_value = SimpleNamespace(returncode=0, stdout=json.dumps({'ok': True}), stderr='')
        text = 'Mensagem "com aspas"\n$(touch /tmp/never-run); `id`'
        result = publish(text, host='mendel@coral.local', remote_dir='/home/mendel/meu projeto')
        args, kwargs = run.call_args
        self.assertEqual(kwargs['input'], text)
        self.assertNotIn(text, args[0][-1])
        self.assertEqual(args[0][-1], "cd '/home/mendel/meu projeto' && python3 -m pub -")
        self.assertTrue(result['ok'])

    @patch('pub.pc.subprocess.run')
    def test_remote_failure_is_reported(self, run):
        run.return_value = SimpleNamespace(returncode=1, stdout='', stderr='MQTT indisponivel')
        with self.assertRaisesRegex(RuntimeError, 'MQTT indisponivel'):
            publish('Coral')


if __name__ == '__main__':
    unittest.main()
