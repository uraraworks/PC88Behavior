#!/usr/bin/env python3
"""追補3の自作入力。応答長の未測定項目は None とし、推測で埋めない。"""
import json

REQUESTS = (0x00, 0x01, 0x02, 0x06, 0x09, 0x0c, 0x0d, 0x0e, 0x12, 0x15, 0x16)
DATA = tuple((i * 37 + 19) & 255 for i in range(256))
READ_DATA = (0x46, 0, 0, 0, 4, 1, 16, 27, 255)
BASE = dict(A=0, B=1, C=0, D=2, E=4)


def inputs(arm):
    r = dict(SP=0x7e00, HL=0x6157, DE=0x0204, BC=0x0100, A=arm.get('request', 0), F=arm.get('f', 1))
    v = arm.get('registers', {})
    r.update(A=v.get('A', r['A']), BC=(v.get('B', r['BC'] >> 8) << 8) | v.get('C', r['BC'] & 255),
             DE=(v.get('D', r['DE'] >> 8) << 8) | v.get('E', r['DE'] & 255))
    return r


def protocol(request):
    # 1.35・1.35a: 書込みの4引数＋256バイト本体（2バイトずつ）。
    # 01単独の応答長は未確定。別要求06を測定区間に混ぜない。
    args = {0: (), 1: (1, 0, 0, 4), 2: (1, 0, 0, 4), 6: (),
            9: (0x68, 0, 0x68, 16), 12: (0x68, 0, 0, 16),
            13: (0x7c, 0), 14: (1, 0, 0, 4, 0x68, 0),
            18: (), 21: (0x68, 0, 0, 16), 22: (0x68, 0, 0, 16)}[request]
    body = DATA if request == 1 else DATA[:16] if request in (12, 22) else ()
    return dict(args=args, body=body, sent=args + body,
                send_pair=request in (1, 22), receive_pair=request in (18, 21),
                expected={0: None, 1: None, 2: 0, 6: 1, 9: 16, 12: None,
                          13: 0, 14: 0, 18: 256, 21: 16, 22: 0}[request])


def arms():
    for request in REQUESTS:
        for iff in ('di', 'ei'):
            yield dict(name=f'00ed-{request:02x}-{iff}', address=0xed, mode='jp',
                       kind='request', request=request, iff=iff, disk1=True, disk2=True,
                       **protocol(request))
    for case in ('normal', 'missing-r', 'missing-cylinder', 'no-media'):
        command = list(READ_DATA)
        if case == 'missing-r': command[4] = command[6] = 63
        if case == 'missing-cylinder': command[2] = 79
        if case == 'no-media': command[1] = 1
        for iff in ('di', 'ei'):
            yield dict(name=f'0263-{case}-{iff}', address=0x263, mode='call', kind='result',
                       case=case, command=tuple(command), iff=iff, disk1=True, disk2=case != 'no-media')
    variants = [('base', BASE)]
    for reg in BASE:
        for value in (0, 1, 2, 3, 4, 7, 16, 63, 127, 128, 255):
            if value != BASE[reg]: variants.append((f'{reg.lower()}-{value:02x}', {**BASE, reg: value}))
    variants += [('mixed-1', dict(A=1, B=3, C=4, D=7, E=16)),
                 ('mixed-2', dict(A=4, B=2, C=1, D=16, E=3))]
    for name, registers in variants:
        for iff in ('di', 'ei'):
            yield dict(name=f'07d6-{name}-{iff}', address=0x7d6, mode='call', kind='seek',
                       registers=registers, iff=iff, disk1=True, disk2=True)
    for kind in ('negative', 'positive'):
        yield dict(name=kind, address=None, mode='call', kind=kind, iff='di', disk1=True, disk2=True)


if __name__ == '__main__':
    print(json.dumps(list(arms()), ensure_ascii=False, indent=2))
