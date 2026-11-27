"""Run on Coral with subscriber AND coral-birds stopped; exercises real serial/SD.
The detection is synthetic, explicitly named TESTE. Acoustic direction is not certified.
"""
import json
import time
from sub.serial_display import Display


def main():
    events = []
    with Display(on_event=events.append) as display:
        initial = display.status()
        assert initial['firmware'] == 'coral-display/1.5', initial
        assert initial['oled'], initial
        assert initial['bird']['buzzer_enabled'] is False, initial
        reply = display.request('bird', active=True, name='TESTE', scientific_name='synthetic test',
                                score=.99, epoch_ms=int(time.time()*1000), ttl_ms=12000)
        assert reply['blue'] == ['TESTE'] and reply['bird']['active'], reply
        assert reply['yellow'][0], reply  # No blank flash on observation updates.
        assert reply['bird']['name'] == 'TESTE' and reply['bird']['scientific_name'] == 'synthetic test', reply
        deadline = time.monotonic()+8
        while time.monotonic() < deadline:
            display.poll_events(.2)
            status = display.status()
            assert status['boot_id'] == initial['boot_id'], status
            assert status['blue'] == ['TESTE'], status
            assert status['bird']['active'], status
        assert len(status['bird']['rms']) == 4, status
        assert all(5 < x < 1018 for x in status['bird']['mean']), status
        records = [e['data'] for e in events if e.get('event') == 'bird_record' and e['data'].get('active')]
        assert records, events
        assert all(r['saved'] for r in records), records
        assert all(r['name'] == 'TESTE' for r in records), records
        # No further observations: gate must expire on its own, without Coral command.
        deadline = time.monotonic()+6
        while time.monotonic() < deadline:
            display.poll_events(.2)
        status = display.status()
        assert not status['bird']['active'] and status['yellow'] == [''], status
        assert status['blue'] == ['Ouvindo...'], status
        display.show_regions('Manual', 'Livre', remember=False)
        time.sleep(.5)
        status=display.status()
        assert status['blue'] == ['Manual'] and status['yellow'] == ['Livre'], status
        # Repeated updates of the same long name must not restart pagination.
        long_name='W'*128
        pages=[]
        for _ in range(4):
            display.request('bird', active=True, name=long_name, scientific_name='synthetic test',
                            score=.99, epoch_ms=int(time.time()*1000), ttl_ms=8000)
            display.poll_events(1.2)
            pages.append(display.status()['blue_page_offset'])
        assert any(p>0 for p in pages), pages
        display.request('bird', active=False, name='', scientific_name='', score=0,
                        epoch_ms=int(time.time()*1000), ttl_ms=1)
        assert status['stack_free_min']>1024, status
        print(json.dumps(dict(test='passed',status=status,records=records),ensure_ascii=False))


if __name__ == '__main__':
    main()
