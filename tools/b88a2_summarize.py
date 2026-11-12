#!/usr/bin/env python3
"""B88追補2。境界状態、入力との関係、配置候補だけを公開する。"""
import argparse
from collections import Counter
import json
from pathlib import Path

from b88a2_arms import arms
from b88a1_arms import inputs
from b88_summarize import summarize_run as base_summarize, REGS
from b88_run import dump

COUNTS = {'media', 'media_ok', 'prepare', 'prepared', 'entered', 'sent', 'recv',
          'command', 'command_match', 'data', 'data_match', 'result', 'overflow', 'ei_delay'}
BOOLS = {'media', 'media_ok', 'prepare', 'prepared', 'entered', 'command_match', 'data_match', 'overflow'}


def natural(x, limit=100000000):
    if type(x) is not int or not 0 <= x <= limit:
        raise ValueError('追加記録の整数不正')


def read_extra(path):
    x = json.loads(path.read_text())
    if set(x) != COUNTS | {'states', 'irq', 'steps', 'recv_match', 'events'}:
        raise ValueError('追加記録の列不正')
    for k in COUNTS:
        natural(x[k], 1 if k in BOOLS else 100000000)
    if len(x['states']) != 3 or len(x['irq']) != 3 or len(x['steps']) != 11 or len(x['recv_match']) != 2:
        raise ValueError('追加記録の長さ不正')
    for state in x['states']:
        if state is not None:
            if len(state) != 3: raise ValueError('境界状態不正')
            for value, limit in zip(state, (1, 1, 2)): natural(value, limit)
    for n in x['irq'] + x['recv_match']: natural(n)
    for step in x['steps']:
        if len(step) != 2: raise ValueError('準備段階不正')
        for n in step: natural(n)
    if not isinstance(x['events'], list) or len(x['events']) > 280:
        raise ValueError('追跡容量超過')
    counts = [0, 0, 0]
    for e in x['events']:
        if set(e) not in ({'kind', 'index', 'overflow', 'candidates'},
                          {'kind', 'index', 'overflow', 'candidates', 'fdc_result'},
                          {'kind', 'index', 'overflow', 'candidates', 'sent_match'}):
            raise ValueError('配置記録の列不正')
        natural(e['kind'], 2); natural(e['index']); natural(e['overflow'], 1)
        k = e['kind']
        if e['index'] != counts[k]: raise ValueError('配置記録の順序不正')
        counts[k] += 1
        if not isinstance(e['candidates'], list) or len(e['candidates']) > 16:
            raise ValueError('候補容量超過')
        for c in e['candidates']:
            if len(c) != 2: raise ValueError('候補不正')
            natural(c[0], 0x7fff); natural(c[1], 1)
            if c[0] < 0x4000: raise ValueError('RAM外')
        if 'sent_match' in e:
            if k != 2 or len(e['sent_match']) != 2: raise ValueError('通信関係不正')
            for v in e['sent_match']: natural(v, 1)
        elif k == 2: raise ValueError('通信関係欠落')
        if 'fdc_result' in e:
            natural(e['fdc_result'], 255)
            if k != 1 or x['command'] != 9 or not x['command_match'] or x['result'] != 7 or not x['media_ok']:
                raise ValueError('許可外の値列')
    if not x['overflow'] and counts != [x['data'], x['result'], x['recv']]:
        raise ValueError('追跡件数不一致')
    return x


def placement(e):
    candidates = e['candidates']
    # 1読出し区間内で一致する書込みが1回だけ、かつ終端まで維持されたもの。
    unique = not e['overflow'] and len(candidates) == 1 and candidates[0][1] == 1
    return {'順番': e['index'], '候補番地': [f'{a:04X}' for a, _ in candidates],
            '終端まで維持': [bool(v) for _, v in candidates],
            '対応': '単一候補' if unique else '不明',
            '単一候補番地': f'{candidates[0][0]:04X}' if unique else None,
            '容量超過': bool(e['overflow'])}


def summarize_run(directory, arm):
    row, values = base_summarize(directory, arm, inputs(arm))
    try:
        x = read_extra(directory / 'extra')
    except (OSError, ValueError, TypeError, KeyError):
        return {'判定': '欠測', '戻り': '欠測', '理由': '記録不足・実行失敗'}, None
    row['準備'] = {'媒体交換確認': bool(x['media'] and x['media_ok']),
                   '前処理開始': bool(x['prepare']), '前処理完了': bool(x['prepared']),
                   '入口到達': bool(x['entered']),
                   '段階': [{'開始': a, '完了': b} for a, b in x['steps']] if arm['kind'] == 'read' else []}
    row['割り込み'] = {
        label: None if state is None else dict(zip(('IFF1', 'IFF2', 'IM'), state))
        for label, state in zip(('呼出し直前', '入口', '戻り直後'), x['states'])}
    row['割り込み'].update({'EI遅延確認回数': x['ei_delay'],
        '前処理の受理回数': x['irq'][0], '入口前の受理回数': x['irq'][1], '区間の受理回数': x['irq'][2]})
    states = x['states']
    row['割り込み']['入口から戻りの変化'] = None if states[1] is None or states[2] is None else {
        k: a != b for k, a, b in zip(('IFF1', 'IFF2', 'IM'), states[1], states[2])}
    events = [[placement(e) for e in x['events'] if e['kind'] == k] for k in range(3)]
    row['通信'] = {'main送信完了数': x['sent'], 'サブ受信数': x['recv'],
                   '送信値との一致回数': x['recv_match'][:len(arm.get('sent', (0x35,)))],
                   '配置候補': events[2],
                   '受信順の入力一致': [[bool(v) for v in e['sent_match'][:len(arm.get('sent', (0x35,)))]] for e in x['events'] if e['kind'] == 2],
                   '戻りAと入力一致': None if values is None else [values['A'] == v for v in arm.get('sent', (0x35,))]}
    addresses = [e['単一候補番地'] for e in events[0]]
    contiguous = len(addresses) == 256 and all(a is not None for a in addresses) and all(
        int(a, 16) == int(addresses[0], 16) + i for i, a in enumerate(addresses))
    results = [e['fdc_result'] for e in x['events'] if 'fdc_result' in e]
    row['読出し'] = {'コマンド受理数': x['command'],
        '9バイト入力と一致': bool(x['command'] == 9 and x['command_match']),
        'データ受信数': x['data'], '自作セクタ全体と一致': bool(x['data'] == 256 and x['data_match']),
        'データ配置候補範囲': [addresses[0], addresses[-1]] if contiguous and x['data_match'] and not x['overflow'] else None,
        'データ対応': '全256バイトの単一候補が連続' if contiguous and x['data_match'] and not x['overflow'] else '不明',
        '結果受信数': x['result'], 'FDC結果7バイト': results if len(results) == 7 else None,
        '結果配置候補': events[1], '追跡容量超過': bool(x['overflow'])}
    if not row['準備']['媒体交換確認']:
        row.update(判定='欠測', 戻り='欠測', 理由='媒体条件不成立'); values = None
    elif not x['entered']:
        reason = '先行処理未帰還' if x['prepare'] and not x['prepared'] else '入口未到達'
        row.update(判定='欠測', 戻り='欠測', 理由=reason); values = None
    if row['判定'] != '取得': values = None
    return row, values


def report(root):
    manifest = json.loads((root / 'manifest.json').read_text())
    catalog = [a for a in arms() if a['name'] in manifest['腕']]
    rows, vals = {}, {}
    for arm in catalog:
        runs, values = [], []
        for n in (1, 2):
            d = root / 'raw' / arm['name'] / str(n)
            try: row = json.loads((d / 'row.json').read_text())
            except (OSError, ValueError): row = {'判定': '欠測', '戻り': '欠測', '理由': '未実行'}
            runs.append(row)
            values.append(json.loads((d / 'values.tmp').read_text()) if (d / 'values.tmp').exists() else None)
        rows[arm['name']] = {'走': runs, '2走一致': runs[0] == runs[1] if all(r['判定'] == '取得' for r in runs) else None}
        vals[arm['name']] = values
    cache = root / 'relations.json'
    if any(root.glob('raw/*/*/values.tmp')):
        relations, baselines = {}, {}
        for arm in catalog:
            baseline = baselines.setdefault(arm['address'], arm['name'])
            v = vals[arm['name']]
            relations[arm['name']] = {'基準腕': baseline,
                '2走のレジスタ一致': None if any(x is None for x in v) else v[0] == v[1],
                '基準腕との一致': [None if x is None or y is None else {k: x[k] == y[k] for k in REGS}
                                for x, y in zip(v, vals[baseline])]}
        dump(cache, relations)
    else:
        relations = json.loads(cache.read_text()) if cache.exists() else {}
    counts = Counter(r['戻り'] if r['判定'] == '取得' else '欠測' for v in rows.values() for r in v['走'])
    result = {'腕数': len(rows), '走数': len(rows)*2, '集計': {k: counts[k] for k in ('確認', '戻らない', '欠測')},
              '関係': relations, '腕': rows}
    dump(root / 'summary.json', result)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('out', type=Path)
    report(parser.parse_args().out.resolve())
