"""Run on Coral, service stopped, with queue_example.ino installed temporarily."""
import json
import time
from sub.serial_display import Display


def main():
    events = []
    with Display(on_event=events.append) as display:
        # Internal queued display requests must not destroy a fragmented UART command.
        command = b'{"cmd":"status","id":"partial-queue"}\n'
        display.serial.write(command[:10])
        deadline = time.monotonic() + 7
        while time.monotonic() < deadline and not any(e.get('event') == 'queue_test' for e in events):
            display.poll_events()
        display.serial.write(command[10:])
        response = None
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            frame = display._read_frame(deadline)
            if frame is None or display._dispatch_event(frame):
                continue
            if frame.get('id') == 'partial-queue':
                response = frame
                break
        assert response and response['ok'], response
        assert response['blue'] == ['Fila'] and response['yellow'] == ['Local'], response
        applied = [e for e in events if e.get('event') == 'display_applied']
        report = [e for e in events if e.get('event') == 'queue_test']
        assert applied and applied[0]['data']['ok'] and applied[0]['task_id'] == 'queue-smoke', events
        assert report and report[0]['data'] == {'queued': True, 'invalid_rejected': True}, events
        assert applied[0]['seq'] < report[0]['seq'], events
        boot = response['boot_id']
        for i in range(10):
            state = display.status()
            assert state['boot_id'] == boot and state['blue'] == ['Fila'], state
            time.sleep(0.2)
        print(json.dumps({'queue_test': 'passed', 'partial_uart_preserved': True,
                          'task': state['service_task'], 'stack_free_min': state['stack_free_min'],
                          'events': events}, ensure_ascii=False))


if __name__ == '__main__':
    main()
