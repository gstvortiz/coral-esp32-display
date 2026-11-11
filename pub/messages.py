"""Message validation shared by publisher and serial subscriber."""
import unicodedata

COMMAND_TOPIC = "coral/display/text"
STATE_TOPIC = "coral/display/state"


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
