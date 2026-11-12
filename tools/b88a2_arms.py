#!/usr/bin/env python3
"""B88追補2の事前登録入力。すべて自作値。"""
import json

ENTRIES = ((0x0010, 'call', 'recv'), (0x0018, 'call', 'send'),
           (0x0020, 'call', 'fdc'), (0x00ed, 'jp', 'init'),
           (0x02a4, 'call', 'fdc'), (0x02a7, 'jp', 'fdc'),
           (0x02b4, 'call', 'calc'), (0x035b, 'call', 'out'),
           (0x048f, 'jp', 'ready'), (0x07d6, 'call', 'ready'))
# 256バイトセクタ、C/H/R/N=0/0/4/1、EOT=4。
READ_DATA = (0x06, 0x00, 0x00, 0x00, 0x04, 0x01, 0x04, 0x1b, 0xff)


def arms():
    for address, mode, kind in ENTRIES:
        for iff in ('di', 'ei'):
            yield dict(name=f'iff-{address:04x}-{iff}', address=address,
                       mode=mode, kind=kind, iff=iff)
    for iff in ('di', 'ei'):
        yield dict(name=f'0263-read-{iff}', address=0x0263, mode='call',
                   kind='read', iff=iff, command=READ_DATA)
    for sent in ((0x35,), (0x35, 0xa6), (0xa6, 0x35)):
        yield dict(name='06a6-recv-' + '-'.join(f'{x:02x}' for x in sent),
                   address=0x06a6, mode='call', kind='recv', sent=sent)
    for kind in ('negative', 'positive'):
        yield dict(name=kind, address=None, mode='call', kind=kind)


if __name__ == '__main__':
    print(json.dumps(list(arms()), ensure_ascii=False, indent=2))
