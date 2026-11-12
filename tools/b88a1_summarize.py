#!/usr/bin/env python3
"""追補1の公開用集計。返り値の列は一時ファイルから読み、関係だけを保存。"""
import argparse
from collections import Counter
import json
from pathlib import Path

from b88a1_arms import arms, inputs
from b88a1_relations import classify_calc
from b88_summarize import summarize_run as base_summarize, REGS

BYTE_REGS = ('A', 'B', 'C', 'D', 'E', 'H', 'L', '(HL)')
COUNTS = {'media', 'prepare', 'prepared', 'entered', 'sent', 'received', 'fdc_count', 'f7_count'}
BOOLS = {'media_ok', 'f7_input', 'f7_return', 'work_same', 'work_plus', 'work_minus'}
ARRAYS = {'received_match', 'first_match', 'fdc_match', 'work_match'}


def dump(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def read_extra(path):
    value = json.loads(path.read_text())
    if set(value) != COUNTS | BOOLS | ARRAYS:
        raise ValueError('追加記録の形式不正')
    for key in COUNTS | BOOLS:
        if type(value[key]) is not int or value[key] < 0:
            raise ValueError('追加記録の型不正')
    if any(value[key] not in (0, 1) for key in BOOLS):
        raise ValueError('真偽以外の追加記録')
    for key in ARRAYS:
        v = value[key]
        limit = value['received'] if key == 'received_match' else 1
        if not isinstance(v, list) or len(v) != 8 or any(type(x) is not int or not 0 <= x <= limit for x in v):
            raise ValueError('追加関係の形式不正')
    return value


def matches(values):
    return dict(zip(BYTE_REGS, map(bool, values)))


def summarize_run(directory, arm):
    row, values = base_summarize(directory, arm, inputs(arm))
    try:
        extra = read_extra(directory / 'extra')
    except (OSError, ValueError, TypeError):
        return {'判定': '欠測', '戻り': '欠測', '理由': '記録不足・実行失敗'}, None
    preparation = {'媒体交換確認': bool(extra['media'] and extra['media_ok']),
                   '前処理開始': extra['prepare'] > 0, '前処理完了': extra['prepared'] > 0,
                   '入口到達': extra['entered'] > 0}
    row['準備'] = preparation
    if not preparation['媒体交換確認']:
        row.update(判定='欠測', 戻り='欠測', 理由='媒体条件不成立')
        return row, None
    if not extra['entered']:
        if extra['prepare'] and not extra['prepared']:
            row.update(判定='欠測', 戻り='欠測', 理由='先行処理未帰還')
        return row, None
    if row['判定'] != '取得':
        return row, None
    relation = {}
    if arm['kind'] == 'recv':
        relation['main送信完了'] = extra['sent'] == 1
        relation['戻りAと送信値が一致'] = None if values is None or extra['sent'] != 1 else values['A'] == arm['sent']
    if arm['kind'] == 'send':
        n = extra['received']
        relation['main受信'] = {'件数': n,
            '先頭と入力との一致': matches(extra['first_match']) if n else None,
            '全受信と入力との一致': matches([x == n for x in extra['received_match']]) if n else None}
    if arm['kind'] == 'fdc':
        relation['FDC受理'] = {'件数': extra['fdc_count'],
            '先頭と入力との一致': matches(extra['fdc_match']) if extra['fdc_count'] else None}
        relation['7F0C'] = None if values is None else {
            '前後一致': bool(extra['work_same']), '前値に1加算': bool(extra['work_plus']),
            '前値から1減算': bool(extra['work_minus']), '入力との一致': matches(extra['work_match'])}
    if arm['kind'] == 'out':
        relation['OUT F7'] = {'件数': extra['f7_count'],
            '全出力と入力Aが一致': bool(extra['f7_input']) if extra['f7_count'] else None,
            '最終出力と戻りAが一致': bool(extra['f7_return']) if values and extra['f7_count'] else None}
    row['追加関係'] = relation
    row['フラグ入力と一致'] = None if values is None else {
        str(bit): bool((values['F'] & (1 << bit)) == (inputs(arm)['F'] & (1 << bit))) for bit in range(8)}
    return row, values


def report(root):
    manifest = json.loads((root / 'manifest.json').read_text())
    catalog = [a for a in arms() if a['name'] in manifest['腕']]
    rows, values = {}, {}
    for arm in catalog:
        name = arm['name']
        runs, vals = [], []
        for repeat in (1, 2):
            path = root / 'raw' / name / str(repeat)
            try:
                row = json.loads((path / 'row.json').read_text())
            except (OSError, ValueError):
                row = {'判定': '欠測', '戻り': '欠測', '理由': '未実行'}
            val = json.loads((path / 'values.tmp').read_text()) if (path / 'values.tmp').exists() else None
            runs.append(row); vals.append(val)
        rows[name] = {'走': runs, '2走一致': runs[0] == runs[1] if all(r['判定'] == '取得' for r in runs) else None}
        values[name] = vals
    cache = root / 'relations.json'
    if any((root / 'raw').glob('*/*/values.tmp')):
        relations = {'計算': [], '00ED一定値': {}, '腕間': {}}
        for repeat in (0, 1):
            records = [(a['a'], a['f'], values[a['name']][repeat]['A'], values[a['name']][repeat]['F'])
                       for a in catalog if a['kind'] == 'calc' and values[a['name']][repeat] is not None]
            relations['計算'].append(classify_calc(records))
        init = [v for a in catalog if a['kind'] == 'init' for v in values[a['name']]]
        # 全4条件×2走が揃った場合だけ、許可された一定値を出す。
        if len(init) == 8 and all(v is not None for v in init):
            relations['00ED一定値'] = {k: init[0][k] for k in ('A', 'F') if all(v[k] == init[0][k] for v in init)}
        baselines = {}
        for arm in catalog:
            key = (arm['address'], arm['mode'], arm['kind'])
            baseline = baselines.setdefault(key, arm['name'])
            vals = values[arm['name']]
            relations['腕間'][arm['name']] = {
                '基準腕': baseline,
                '基準腕との一致': [None if x is None or y is None else {k: x[k] == y[k] for k in REGS}
                                   for x, y in zip(vals, values[baseline])],
                '2走のレジスタ一致': None if any(v is None for v in vals) else vals[0] == vals[1]}
        dump(cache, relations)
    elif cache.exists():
        relations = json.loads(cache.read_text())
    else:
        relations = {'計算': [{'判定': '欠測'}] * 2, '00ED一定値': {}, '腕間': {}}
    totals = Counter(r['戻り'] if r['判定'] == '取得' else '欠測' for row in rows.values() for r in row['走'])
    result = {'腕数': len(rows), '走数': len(rows) * 2,
              '集計': {k: totals[k] for k in ('確認', '戻らない', '欠測')}, '関係': relations, '腕': rows}
    dump(root / 'summary.json', result)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('out', type=Path)
    report(parser.parse_args().out.resolve())
