"""Run on Coral with both services stopped; synthetic display observations."""
import time
from sub.serial_display import Display


def main():
    with Display() as display:
        initial = display.status()
        assert initial['firmware'] == 'coral-display/1.7', initial
        assert initial['oled'], initial
        fields = dict(active=True, name='TESTE Bem-te-vi', scientific_name='synthetic',
                      epoch_ms=int(time.time()*1000), ttl_ms=15000)
        for score, expected in ((0, '0%'), (.15, '15%'), (.5, '50%'), (.556, '56%'), (1, '100%')):
            ack = display.request('bird', score=score, **fields)
            assert ack['bird_confidence'] == expected, ack
            assert ack['blue'] == [fields['name']], ack
            assert abs(ack['bird']['score'] - score) < .00001, ack
            assert not ack['bird']['buzzer_enabled'], ack
        fields['name'] = 'TESTE ' + 'nome longo ' * 11
        ack = display.request('bird', score=.6, **fields)
        assert ack['blue_page_offset'] == 0, ack
        display.poll_events(3.3)
        paged = display.status()
        assert paged['blue_page_offset'] > 0, paged
        assert paged['bird_confidence'] == '60%', paged
        fields['active'] = False
        cleared = display.request('bird', score=0, **fields)
        assert cleared['blue'] == ['Ouvindo...'] and cleared['bird_confidence'] == '', cleared
        fields.update(active=True, name='TESTE', ttl_ms=400)
        display.request('bird', score=.9, **fields)
        display.poll_events(1)
        expired = display.status()
        assert expired['blue'] == ['Ouvindo...'] and expired['bird_confidence'] == '', expired
        print('PASS confidence: rounding, long-name pagination, no detection, expiration, OLED present')


if __name__ == '__main__':
    main()
