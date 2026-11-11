#!/usr/bin/env python3
"""Explicit hardware smoke test. Changes the OLED, ending with persisted 'Coral'."""
import json
import time

from .serial_display import Display


def main():
    checks = []
    events = []
    with Display(on_event=events.append) as display:
        initial = display.status()
        assert initial['firmware'] == 'coral-display/1.3', initial
        assert initial['service_task'] == 'coral-display' and initial['boot_id'], initial
        boot_id = initial['boot_id']
        assert initial['oled'] and initial['address'] in (60, 61), initial
        checks.append('firmware e OLED respondem')
        result = display.show('Olá, Coral!\nTeste de conexão.', remember=False)
        assert result['text'] == 'Ola, Coral!\nTeste de conexao.', result
        checks.append('texto e acentos')
        result = display.show('a' * 1024, remember=False)
        assert len(result['text']) == 1024, result
        time.sleep(3.2)
        assert display.status()['page_offset'] > 0
        checks.append('1024 caracteres e paginacao')
        result = display.show_regions('Coral', 'Pronta', remember=False)
        assert result['blue_height'] == 48 and result['yellow_height'] == 16, result
        time.sleep(3.2)
        state = display.status()
        assert state['blue_index'] == state['yellow_index'] == 0, state
        assert state['blue_page_offset'] == state['yellow_page_offset'] == 0, state
        checks.append('duas mensagens curtas fixas')
        display.show_regions('Coral', ['Primeira', 'Segunda'], remember=False)
        time.sleep(3.2)
        state = display.status()
        assert state['blue_index'] == 0 and state['yellow_index'] == 1, state
        time.sleep(3.1)
        assert display.status()['yellow_index'] == 0
        checks.append('lista amarela alterna e azul permanece fixa')
        result = display.show_regions('a' * 512, 'b' * 512, remember=False)
        assert len(result['blue'][0]) == len(result['yellow'][0]) == 512, result
        time.sleep(3.2)
        state = display.status()
        assert state['blue_page_offset'] > 0 and state['yellow_page_offset'] > 0, state
        checks.append('paginacao nas duas areas e ACK com 1024 caracteres')
        # Worst-case escaping must fit the serial frame and ACK buffers too.
        result = display.show_regions(['\n' * 64] * 8, ['"' * 64] * 8, remember=False)
        assert len(result['blue']) == len(result['yellow']) == 8, result
        for blue, yellow in (([], ['ok']), (['a' * 1024], ['b'])):
            try:
                display.request('regions', blue=blue, yellow=yellow, remember=False)
            except RuntimeError as error:
                assert 'invalid_regions' in str(error), str(error)
            else:
                raise AssertionError('Firmware aceitou areas invalidas')
        checks.append('limites das listas e escapes')
        try:
            display.request('text', text='a' * 1025, remember=False)
        except RuntimeError as error:
            assert 'text_too_long' in str(error), str(error)
        else:
            raise AssertionError('Firmware aceitou texto acima do limite')
        display.serial.write(b'x' * 2400 + b'\n')
        assert display.status()['ok']
        checks.append('limites e recuperacao apos quadro invalido')
        assert display.clear(remember=False)['mode'] == 'clear'
        clock = display.clock(remember=False)
        assert clock['mode'] == 'clock' and 'rtc_time' in clock, clock
        checks.append('limpar tela e consultar RTC')
        deadline = time.monotonic() + 12
        while not any(e.get('event') == 'application_tick' for e in events) and time.monotonic() < deadline:
            display.poll_events()
        ticks = [e for e in events if e.get('event') == 'application_tick']
        assert ticks and ticks[0]['data']['task'] == 'loopTask', events
        assert all(e['boot_id'] == boot_id for e in ticks), ticks
        state = display.status()
        assert state['stack_free_min'] > 1024 and state['boot_id'] == boot_id, state
        checks.append('eventos do loop paralelo, ACKs e pilha da tarefa')
        assert display.show_regions('Coral', 'Pronta')['mode'] == 'regions'
    with Display() as display:
        state = display.status()
        assert state['mode'] == 'regions' and state['blue'] == ['Coral'] and state['yellow'] == ['Pronta'], state
        checks.append('duas areas preservadas ao reabrir serial')
        assert display.show('Coral')['text'] == 'Coral'
    with Display() as display:
        final = display.status()
        assert final['text'] == 'Coral' and final['mode'] == 'text', final
        checks.append('mensagem preservada ao reabrir serial')
    print(json.dumps({'checks': checks, 'final': final}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
