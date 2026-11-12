#!/usr/bin/env python3
"""計算腕の一時値から、値の列を含まない関係だけを生成する。"""


def bit_relation(samples, output_bit):
    """各出力ビットを入力ビット・その反転・定数と照合する。"""
    ys = [(out >> output_bit) & 1 for _, _, out in samples]
    matches = []
    for name, bits in [('0', [0] * len(samples)), ('1', [1] * len(samples))]:
        if ys == bits:
            matches.append(name)
    for name, index in [('A', i) for i in range(8)] + [('F', i) for i in range(8)]:
        bits = [((a if name == 'A' else f) >> index) & 1 for a, f, _ in samples]
        if ys == bits:
            matches.append(f'{name}{index}')
        if ys == [1 - bit for bit in bits]:
            matches.append(f'NOT {name}{index}')
    return matches


def classify_calc(records):
    """完全な256×2直積を要求し、不完全な結果から規則を主張しない。"""
    expected = {(a, f) for a in range(256) for f in (0, 1)}
    if len(records) != len(expected) or {(a, f) for a, f, _, _ in records} != expected:
        return {'判定': '欠測'}
    if any(not (0 <= ao <= 255 and 0 <= fo <= 255) for _, _, ao, fo in records):
        raise ValueError('出力がバイト範囲外')
    result = {'判定': '取得'}
    for name, column in [('A', 2), ('F', 3)]:
        samples = [(r[0], r[1], r[column]) for r in records]
        matches = [bit_relation(samples, i) for i in range(8)]
        result[name] = {'入力Aと恒等': all(a == out for a, _, out in samples),
                        '入力Fと恒等': all(f == out for _, f, out in samples),
                        '各ビットの関係': matches,
                        '単一入力ビットまたは定数で全ビットを表せる': all(matches)}
        result[name]['関係の形'] = ('恒等' if result[name]['入力Aと恒等'] or result[name]['入力Fと恒等']
                                   else '定数' if len({out for _, _, out in samples}) == 1
                                   else 'ビット写像' if all(matches)
                                   else '表引き的（候補規則では表せない）')
    return result
