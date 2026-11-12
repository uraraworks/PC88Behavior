#!/usr/bin/env python3
"""B88 追補1の事前登録済み入力。値はすべて自作。"""
import itertools
import json


def inputs(arm):
    """自作の入力値。FDC 腕では七つの8ビットレジスタを区別する。"""
    v = arm.get('variant', 'base')
    r = dict(SP=0x7e00, HL=0x6157, DE=0x2345, BC=0x6789,
             A=arm.get('a', 0x08), F=arm.get('f', 0))
    if arm['kind'] == 'fdc' and v == 'rotate':
        r.update(A=0x89, BC=0x0823, DE=0x4567, HL=0x5761)
    elif arm['kind'] == 'send':
        for variant, key, value in [('a', 'A', 0xa6), ('hl', 'HL', 0x625b),
                                    ('bc', 'BC', 0x1234), ('de', 'DE', 0x5678)]:
            if v == variant:
                r[key] = value
    return r


def memory_inputs(arm):
    r = inputs(arm)
    return {r['HL']: 0xb6 if arm.get('variant') == 'mem' else 0x3d,
            0x7f0c: 0xc3 if arm.get('variant') == 'work1' else
                    0 if arm.get('variant') == 'work0' else 0x5c}


def arms():
    for address, mode in ((0x10, 'call'), (0x10, 'rst'), (0x6a6, 'call')):
        for value in (0x00, 0x35, 0xa6, 0xff):
            yield dict(name=f'{address:04x}-{mode}-recv-{value:02x}', address=address,
                       mode=mode, kind='recv', sent=value)
    for mode in ('call', 'rst'):
        for variant in ('base', 'a', 'hl', 'bc', 'de', 'mem'):
            yield dict(name=f'0018-{mode}-send-{variant}', address=0x18,
                       mode=mode, kind='send', variant=variant)
    for address, mode in ((0x20, 'call'), (0x20, 'rst'), (0x2a4, 'call'), (0x2a7, 'jp')):
        for variant in ('base', 'rotate', 'work0', 'work1'):
            yield dict(name=f'{address:04x}-{mode}-fdc-{variant}', address=address,
                       mode=mode, kind='fdc', variant=variant)
    for a, f in itertools.product(range(256), (0, 1)):
        yield dict(name=f'02b4-call-calc-{a:02x}-{f}', address=0x2b4,
                   mode='call', kind='calc', a=a, f=f)
    for a, f in itertools.product((0, 1, 0x35, 0x80, 0xff), (0, 1, 0x40, 0xff)):
        yield dict(name=f'035b-call-out-{a:02x}-{f:02x}', address=0x35b,
                   mode='call', kind='out', a=a, f=f)
    for a, disk2 in itertools.product((0, 1), (False, True)):
        yield dict(name=f'00ed-jp-init-{a}-{int(disk2)}', address=0xed,
                   mode='jp', kind='init', a=a, disk1=True, disk2=disk2)
    for address, mode in ((0x48f, 'jp'), (0x7d6, 'call'), (0x7d6, 'jp')):
        for a, disk1, disk2, preinit in itertools.product((0, 1), repeat=4):
            yield dict(name=f'{address:04x}-{mode}-ready-{a}{disk1}{disk2}{preinit}',
                       address=address, mode=mode, kind='ready', a=a,
                       disk1=bool(disk1), disk2=bool(disk2), preinit=bool(preinit))
    for command in ('none', 'sense_interrupt'):
        yield dict(name=f'0263-call-status-{command}', address=0x263,
                   mode='call', kind='status', command=command)
    for kind in ('negative', 'positive'):
        yield dict(name=kind, address=None, mode='call', kind=kind)


if __name__ == '__main__':
    print(json.dumps(list(arms()), ensure_ascii=False, indent=2))
