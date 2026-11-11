"""Hardware stress test: long serial commands while the loop emits events."""
import json
import time
from sub.serial_display import Display


def main():
    events = []
    with Display(on_event=events.append) as display:
        initial = display.status()
        assert initial['firmware'] == 'coral-display/1.3', initial
        started = time.monotonic()
        requests = 0
        while time.monotonic() - started < 12:
            # 2048 escaped characters plus envelope, near the maximum frame size.
            blue = '"' * 512
            yellow = '\\' * 512
            reply = display.show_regions(blue, yellow, remember=False)
            assert reply['blue'] == [blue] and reply['yellow'] == [yellow], reply
            assert reply['boot_id'] == initial['boot_id'], reply
            assert reply['service_task'] == 'coral-display', reply
            requests += 1
        display.poll_events(0.3)
        ticks = [e for e in events if e.get('event') == 'application_tick']
        assert ticks and all(e['data']['task'] == 'loopTask' for e in ticks), events
        assert reply['stack_free_min'] > 1024, reply
        display.show_regions('Coral', 'Pronta', remember=False)
        print(json.dumps({'duplex_test': 'passed', 'long_requests': requests,
                          'events': len(ticks), 'stack_free_min': reply['stack_free_min']}))


if __name__ == '__main__':
    main()
