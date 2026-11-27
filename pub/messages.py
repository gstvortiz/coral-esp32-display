"""Message validation shared by publisher and serial subscriber."""
import unicodedata

COMMAND_TOPIC = "coral/display/text"
STATE_TOPIC = "coral/display/state"
EVENT_TOPIC = "coral/esp32/events"
NOTICE_TOPIC = "coral/display/notice"
MICROPHONE_TOPIC = "coral/birds/microphone"


def notice_message(blue, yellow='', duration_ms=4000):
    if not isinstance(blue, str) or not isinstance(yellow, str):
        raise ValueError('Aviso precisa conter texto.')
    blue, yellow = display_text(blue), display_text(yellow)
    if len(blue)>128 or len(yellow)>42 or type(duration_ms) is not int or not 1000<=duration_ms<=10000:
        raise ValueError('Aviso fora dos limites.')
    return dict(cmd='notice', blue=blue, yellow=yellow, duration_ms=duration_ms)


def region_messages(blue, yellow):
    """Normalize a complete two-region screen before retaining it in MQTT."""
    result = {}
    for name, value in (('blue', blue), ('yellow', yellow)):
        if isinstance(value, str):
            value = [value]
        if not isinstance(value, list) or not 1 <= len(value) <= 8:
            raise ValueError('Cada area precisa de 1 a 8 mensagens.')
        if any(not isinstance(item, str) for item in value):
            raise ValueError('Cada mensagem precisa ser texto.')
        result[name] = [display_text(item) for item in value]
    if sum(len(item) for items in result.values() for item in items) > 1024:
        raise ValueError('Limite total de 1024 caracteres nas duas areas.')
    return result


def display_text(value):
    """The built-in OLED font uses ASCII; transliterate Portuguese accents."""
    value = value.replace('\r\n', '\n').replace('\r', '\n').replace('\t', '    ')
    value = ''.join(c for c in unicodedata.normalize('NFKD', value)
                    if not unicodedata.combining(c))
    value = value.encode('ascii', 'replace').decode('ascii')
    if any(ord(c) < 32 and c != '\n' or ord(c) == 127 for c in value):
        raise ValueError('Texto contem caracteres de controle.')
    if len(value) > 1024:
        raise ValueError('Limite de 1024 caracteres apos conversao para o OLED.')
    return value
