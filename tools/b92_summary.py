#!/usr/bin/env python3
"""B92 のリポジトリ外の生記録を値なしの比較に縮約する。"""
import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def outside(path):
    p = Path(path).resolve()
    if p == ROOT or ROOT in p.parents:
        raise ValueError('生記録はリポジトリ外に置く')
    return p


def check(run):
    if set(run) != {'out', 'screen', 'returned', 'sp', 'frames', 'interventions',
                    'reached', 'complete', 'escaped', 'prior_out31', 'prior_e6c2', 'error'}:
        raise ValueError('記録形式不正')
    def number(x, lo, hi):
        return type(x) is int and lo <= x <= hi
    if not isinstance(run['out'], list) or not all(
        isinstance(x, list) and len(x) == 2 and number(x[0], 0, 255) and number(x[1], 0, 255)
        for x in run['out']):
        raise ValueError('OUT 形式不正')
    if not isinstance(run['screen'], list) or not all(number(x, 0, 65535) for x in run['screen']):
        raise ValueError('画面書き込み形式不正')
    if type(run['returned']) is not bool or not number(run['frames'], 0, 10000000) or not number(run['interventions'], 0, 1):
        raise ValueError('区間形式不正')
    if run['returned'] != (run['sp'] is not None) or (run['sp'] is not None and not number(run['sp'], 0, 65535)):
        raise ValueError('SP 形式不正')
    if any(type(run[k]) is not bool for k in ('reached', 'complete', 'escaped', 'prior_out31', 'prior_e6c2')):
        raise ValueError('状態形式不正')
    if run['error'] not in (None, 'ハーネス実行失敗', '生記録の欠落または形式不正', '書込み先がRAMでない'):
        raise ValueError('失敗理由不正')
    if (run['returned'] and not run['escaped']) or (run['escaped'] and not run['reached']):
        raise ValueError('状態不整合')
    return run


def screen(addresses):
    ranges = []
    for addr in sorted(set(addresses)):
        if ranges and ranges[-1][1] + 1 == addr:
            ranges[-1][1] = addr
        else:
            ranges.append([addr, addr])
    return {'件数': len(addresses), '範囲': ranges}


def compare(base, run):
    a, b = base['out'], run['out']
    aligned = len(a) == len(b) and all(x[0] == y[0] for x, y in zip(a, b))
    return {'OUT順序一致': aligned,
            'OUT対応': '同じポート列' if aligned else '追加・欠落・順序変化（対応推測なし）',
            'OUT値一致': [x[1] == y[1] for x, y in zip(a, b)] if aligned else None,
            '基準OUT件数': len(a), 'OUT件数': len(b),
            'OUTポート列': [f'{p:02X}' for p, _ in b],
            '画面件数変化': len(run['screen']) - len(base['screen']),
            '画面範囲変化': screen(base['screen'])['範囲'] != screen(run['screen'])['範囲'],
            '画面': screen(run['screen']), '帰還': run['returned'], '帰還時SP': run['sp'],
            'フレーム数': run['frames'], '介入回数': run['interventions'],
            '入口到達': run['reached'], '記録完備': run['complete'],
            '区間から脱出': run['escaped'], '先行RAM_OUT31': run['prior_out31'],
            'その後RAM_E6C2書込': run['prior_e6c2'], '欠測理由': run['error']}


def relation(inputs, outputs):
    candidates = []
    if outputs == inputs:
        candidates.append('そのまま')
    mapping = []
    for ob in range(8):
        matches = []
        for ib in range(8):
            for invert in (0, 1):
                if all(((y >> ob) & 1) == (((x >> ib) & 1) ^ invert) for x, y in zip(inputs, outputs)):
                    matches.append(f'入力bit{ib}' + ('反転' if invert else ''))
        mapping.append(matches or (['固定（値はリポジトリ外）']
                                  if len({(y >> ob) & 1 for y in outputs}) == 1 else []))
    if all(mapping) and len(set(outputs)) > 1:
        candidates.append({'ビット対応': mapping})
    if len(set(outputs)) == 1:
        candidates.append('定数（値はリポジトリ外）')
    return candidates or ['未分類']


def summarize(data):
    if set(data) != {'baseline', 'arms'} or len(data['baseline']) != 2 or not isinstance(data['arms'], list):
        raise ValueError('腕の形式不正')
    bases = [check(x) for x in data['baseline']]
    if any(x['interventions'] for x in bases):
        raise ValueError('基準に介入あり')
    inputs = [0, 1, 2, 4, 8, 16, 32, 64, 128, 255]
    grouped = {}
    for arm in data['arms']:
        if set(arm) != {'address', 'input', 'run'} or type(arm['address']) is not int or not 0 <= arm['address'] <= 65535 or arm['input'] not in inputs or type(arm['input']) is not int:
            raise ValueError('腕の形式不正')
        run = check(arm['run'])
        if arm['input'] in grouped.setdefault(arm['address'], {}):
            raise ValueError('腕の重複が不正')
        grouped[arm['address']][arm['input']] = run
    def usable(run, interventions):
        return (run['complete'] and run['reached'] and run['returned'] and
                run['error'] is None and run['interventions'] == interventions and
                run['prior_out31'] and run['prior_e6c2'])
    stable = all(usable(r, 0) for r in bases) and bases[0] == bases[1]
    report = {'基準2回比較': compare(*bases), '基準安定': stable, '腕': {}, '関係': {}}
    for addr, arms in sorted(grouped.items()):
        key = f'{addr:04X}'
        report['腕'][key] = {f'{v:02X}': compare(bases[0], run) for v, run in sorted(arms.items())}
        if not stable or set(arms) != set(inputs) or not all(usable(r, 1) for r in arms.values()):
            report['関係'][key] = None
            continue
        runs = [arms[v] for v in inputs]
        ports = [[p for p, _ in r['out']] for r in runs]
        if any(p != ports[0] for p in ports) or ports[0] != [p for p, _ in bases[0]['out']]:
            report['関係'][key] = None
            continue
        report['関係'][key] = [relation(inputs, [r['out'][i][1] for r in runs]) for i in range(len(ports[0]))]
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('raw')
    parser.add_argument('output')
    args = parser.parse_args()
    try:
        raw = outside(args.raw)
        result = summarize(json.loads(raw.read_text()))
        Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    except (ValueError, TypeError, KeyError, OSError, json.JSONDecodeError):
        parser.exit(1, 'B92: 記録の読み込みまたは検証に失敗\n')


if __name__ == '__main__':
    main()
