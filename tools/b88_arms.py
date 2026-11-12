#!/usr/bin/env python3
"""B88 の事前登録済みの入口・入力条件を列挙する。"""
import json

ENTRIES = ((0x0010, 'call'), (0x0010, 'rst'),
           (0x0018, 'call'), (0x0018, 'rst'),
           (0x0020, 'call'), (0x0020, 'rst'),
           (0x00ed, 'jp'), (0x048f, 'jp'), (0x06a6, 'call'),
           (0x0263, 'call'), (0x02a4, 'call'), (0x02b4, 'call'),
           (0x035b, 'call'), (0x02a7, 'jp'),
           (0x07d6, 'call'), (0x07d6, 'jp'))
VARIANTS = ('base', 'a', 'bc', 'de', 'hl', 'f', 'mem_hl', 'mem_de')


def arms():
    for address, mode in ENTRIES:
        for variant in VARIANTS:
            yield {'name': f'{address:04x}-{mode}-{variant}',
                   'address': address, 'mode': mode, 'variant': variant}
    for kind in ('negative', 'positive'):
        yield {'name': kind, 'address': None, 'mode': 'call', 'variant': 'base'}


if __name__ == '__main__':
    print(json.dumps(list(arms()), ensure_ascii=False, indent=2))
