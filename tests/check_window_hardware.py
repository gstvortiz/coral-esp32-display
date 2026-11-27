"""Run on Coral with both services stopped. Synthetic label, real ADC history."""
import json
import time
from sub.serial_display import Display


def main():
    events = []
    with Display(on_event=events.append) as display:
        initial = display.status()
        assert initial['firmware'] in ('coral-display/1.5', 'coral-display/1.6', 'coral-display/1.7'), initial
        display.poll_events(4)  # Fill a complete historical window after any reset.
        end = int(time.time()*1000)-700
        fields = dict(active=True, name='TESTE SYNC', scientific_name='synthetic', score=.9,
                      epoch_ms=int(time.time()*1000), ttl_ms=10000,
                      window_start_ms=end-3000, window_end_ms=end)
        first = display.request('bird', **fields)
        if initial['firmware'] == 'coral-display/1.7':
            assert first['bird_confidence'] == '90%', first
        assert first['bird']['direction_sync'] == 'matched', first
        assert first['bird']['direction_coverage'] >= .95, first
        frozen = {k: first['bird'][k] for k in ('window_rms', 'direction', 'direction_coverage',
                                                'window_start_ms', 'window_end_ms')}
        for _ in range(3):
            display.poll_events(.8)
            current = display.status()
            assert current['boot_id'] == initial['boot_id'], current
            assert current['yellow'] == first['yellow'], current
            assert all(current['bird'][k] == v for k, v in frozen.items()), current
        fields['epoch_ms'] = int(time.time()*1000)
        retry = display.request('bird', **fields)
        assert all(retry['bird'][k] == v for k, v in frozen.items()), retry
        stored = [e['data'] for e in events if e.get('event') == 'bird_record'
                  and e['data'].get('name') == 'TESTE SYNC']
        assert len(stored) >= 3, events
        assert all(all(r[k] == v for k, v in frozen.items()) for r in stored), stored
        # Unknown historical intervals must not fall back to the current RMS.
        fields.update(window_start_ms=end-603000, window_end_ms=end-600000)
        missing = display.request('bird', **fields)
        assert not missing['bird']['direction_valid'], missing
        assert missing['bird']['direction_sync'] == 'history_incomplete', missing
        assert missing['yellow'] == ['Indef.'], missing
        # Legacy commands may show a name, but cannot invent a synchronized direction.
        fields.pop('window_start_ms'); fields.pop('window_end_ms')
        missing = display.request('bird', **fields)
        assert missing['bird']['direction_sync'] == 'missing_window', missing
        assert missing['yellow'] == ['Indef.'], missing
        # Expiry clears both regions even though the window result itself is frozen.
        fields.update(ttl_ms=400)
        display.request('bird', **fields)
        display.poll_events(1)
        expired = display.status()
        assert expired['blue'] == ['Ouvindo...'] and expired['yellow'] == [''], expired
        if initial['firmware'] == 'coral-display/1.7':
            assert expired['bird_confidence'] == '', expired
        assert expired['bird']['buzzer_enabled'] is False, expired
        assert expired['queue_rejected'] == 0, expired
        print(json.dumps(dict(window_test='passed', frozen=frozen, records=len(stored),
                              records_saved=sum(bool(r['saved']) for r in stored),
                              stack_free_min=expired['stack_free_min'])))


if __name__ == '__main__':
    main()
