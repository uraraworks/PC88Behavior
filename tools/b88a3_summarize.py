#!/usr/bin/env python3
"""追補3。生レジスタは関係へ縮約し、自作媒体のFDC値だけを例外とする。"""
import argparse
from collections import Counter
import json
from pathlib import Path
from b88a3_arms import arms, inputs
from b88_summarize import summarize_run as base_summarize, REGS, FDC
from b88_run import dump

COUNTS = {'media', 'media_ok', 'prepare', 'prepared', 'entered', 'landing', 'pre_read',
          'sent', 'received', 'replies', 'reply_done', 'stream_ok', 'data_count', 'overflow', 'ei_delay',
          'ready_msr', 'entry_msr'}
BOOLS = {'media', 'media_ok', 'prepare', 'prepared', 'entered', 'pre_read', 'stream_ok', 'overflow'}
MISSING = {'判定': '欠測', '戻り': '欠測', '理由': '記録不足・実行失敗'}
COMMAND_LENGTH = {2:9, 3:3, 4:2, 5:9, 6:9, 7:2, 8:1, 9:9, 10:2, 12:9, 13:6, 15:3, 17:9, 25:9, 29:9}


def natural(x, limit=100000000):
    if type(x) is not int or not 0 <= x <= limit: raise ValueError('整数の範囲不正')


def sequence(x, n=None, limit=255):
    if not isinstance(x, list) or (n is not None and len(x) != n): raise ValueError('列の長さ不正')
    for v in x: natural(v, limit)


def read_extra(path):
    x = json.loads(path.read_text())
    if set(x) != COUNTS | {'states', 'irq', 'steps', 'result_match', 'motors', 'commands'}:
        raise ValueError('追加記録の列不正')
    for k in COUNTS: natural(x[k], 1 if k in BOOLS else 255 if k.endswith('msr') else 100000000)
    if not isinstance(x['states'], list) or len(x['states']) != 3: raise ValueError('状態不正')
    for state in x['states']:
        if state is not None:
            sequence(state, 3, 2)
            for v in state[:2]: natural(v, 1)
    sequence(x['irq'], 3, 100000000)
    if not isinstance(x['steps'], list) or len(x['steps']) != 9: raise ValueError('段階不正')
    for step in x['steps']: sequence(step, 2, 100000000)
    sequence(x['result_match'], limit=1)
    if len(x['result_match']) not in (0, 7): raise ValueError('結果配置不正')
    sequence(x['motors'])
    if len(x['motors']) > 128 or not isinstance(x['commands'], list) or len(x['commands']) > 128:
        raise ValueError('容量超過')
    if not x['media_ok'] and (x['commands'] or x['motors']): raise ValueError('許可外のFDC値')
    for t in x['commands']:
        if set(t) != {'scope', 'bytes', 'result', 'data_in', 'data_out'}: raise ValueError('FDC列不正')
        natural(t['scope'], 1); natural(t['data_in']); natural(t['data_out'])
        sequence(t['bytes']); sequence(t['result'])
        if not 1 <= len(t['bytes']) <= 9 or len(t['result']) > 7: raise ValueError('FDC容量超過')
    return x


def candidate_values(r):
    """測定前に固定する候補群。複数成立時は一意と主張しない。"""
    v = dict(A=r['A'], B=r['BC'] >> 8, C=r['BC'] & 255, D=r['DE'] >> 8, E=r['DE'] & 255)
    out = {'定数0': 0, '定数1': 1, '定数7': 7}
    for name, value in v.items():
        out[name] = value
        for mask in (1, 3, 7, 15, 192): out[f'{name}&{mask:02X}'] = value & mask
        for shift in (1, 2): out[f'{name}>>{shift}'] = value >> shift
        out[f'({name}&1)<<2'] = (value & 1) << 2
    for unit in v:
        for head in v:
            if unit != head: out[f'({unit}&3)|(({head}&1)<<2)'] = (v[unit]&3) | ((v[head]&1)<<2)
    return out


def matches(value, candidates):
    return {name: value == candidate for name, candidate in candidates.items()}


def result_relations(values, result):
    if values is None or result is None: return None
    st0, st1, st2 = result[:3]
    candidates = {'ST0': st0, 'ST1': st1, 'ST2': st2, 'ST0&C0': st0 & 0xc0,
                  'ST0&3F': st0 & 0x3f, 'ST0|ST1|ST2': st0 | st1 | st2,
                  '定数0': 0, '定数1': 1}
    flags = {}
    masked = st0 & 0xc0
    # AND命令の公開Z80フラグ規則との照合。値自体は残さない。
    and_flags = (masked & 0xa8) | 0x10 | (0x40 if masked == 0 else 0) | (4 if masked.bit_count() % 2 == 0 else 0)
    for bit, name in enumerate(('C', 'N', 'PV', 'X', 'H', 'Y', 'Z', 'S')):
        candidates_bit = {'0': 0, '1': 1, 'ST0の同位bit': (st0 >> bit)&1, 'ST1の同位bit': (st1 >> bit)&1,
                          'ST2の同位bit': (st2 >> bit)&1,
                          'AND(ST0,C0)の同位bit': (and_flags >> bit)&1}
        flags[name] = matches((values['F'] >> bit)&1, candidates_bit)
    return {'A': matches(values['A'], candidates),
            'F各ビット': flags, 'FはAND(ST0,C0)と一致': values['F'] == and_flags,
            **{name: matches(values[name], candidates) for name in ('BC', 'DE', 'HL')}}


def summarize_run(directory, arm):
    row, values = base_summarize(directory, arm, inputs(arm))
    try: x = read_extra(directory / 'extra')
    except (OSError, ValueError, TypeError, KeyError): return dict(MISSING), None
    row['準備'] = {'媒体交換確認': bool(x['media'] and x['media_ok']),
        '前処理開始': bool(x['prepare']), '前処理完了': bool(x['prepared']), '入口到達': bool(x['entered']),
        '読出し要求の準備完了': bool(x['pre_read']) if arm.get('request') == 18 else None,
        '段階': [{'開始': a, '完了': b} for a,b in x['steps']] if arm['kind'] == 'result' else []}
    row['割り込み'] = {label: None if state is None else dict(zip(('IFF1','IFF2','IM'),state))
        for label,state in zip(('呼出し直前','入口','戻り直後'),x['states'])}
    row['割り込み'].update(EI遅延確認回数=x['ei_delay'], 受理回数=x['irq'])
    state1, state2 = x['states'][1:]
    row['割り込み']['入口から戻りの変化'] = None if state1 is None or state2 is None else {
        k: a != b for k,a,b in zip(('IFF1','IFF2','IM'),state1,state2)}
    reason = None
    if not row['準備']['媒体交換確認']: reason = '媒体条件不成立'
    elif not x['prepared']: reason = '先行処理未帰還'
    elif not x['entered']: reason = '入口未到達'
    elif arm.get('request') == 18 and not x['pre_read']: reason = '読出し準備未完了'
    elif x['overflow']: reason = '追跡容量超過'
    elif arm['kind'] == 'result' and any((x[k]&0xf0) != 0xd0 for k in ('ready_msr','entry_msr')):
        reason = '結果相未確認'
    if reason:
        row.update(判定='欠測', 戻り='欠測', 理由=reason); values = None
    if row['判定'] != '取得': values = None
    expected = arm.get('expected')
    returned = row['判定'] == '取得' and row['戻り'] == '確認'
    comm_complete = (returned and x['sent'] == x['received'] == len(arm.get('sent', ())) and x['stream_ok'] and
                     x['replies'] == x['reply_done'] * (2 if arm.get('receive_pair') else 1))
    row['通信'] = {'main送信完了数': x['sent'], 'サブ受信数': x['received'],
        '受信順に入力と一致': bool(x['stream_ok']), 'main応答受信数': x['replies'],
        '応答ハンドシェイク完了数': x['reply_done'], '引数と応答の通信完了': bool(comm_complete),
        '応答長の仕様と一致': x['replies'] == expected if expected is not None and comm_complete else None,
        '自作移動先到達回数': x['landing']}
    row['FDC取引'] = [{'区間': '入口から戻り' if t['scope'] else '前処理',
        '種類': FDC.get(t['bytes'][0]&31, 'INVALID'), 'コマンドと引数': t['bytes'],
        '引数完了': len(t['bytes']) == COMMAND_LENGTH.get(t['bytes'][0]&31, 1),
        '結果': t['result'], 'データ受信数': t['data_in'], 'データ送信数': t['data_out']} for t in x['commands']]
    reads = [t for t in x['commands'] if (t['bytes'][0]&31) == 6]
    command_match = len(reads) == 1 and reads[0]['bytes'] == list(arm.get('command', ()))
    result = reads[0]['result'] if command_match and len(reads[0]['result']) == 7 and not reason else None
    row['結果相'] = {'前処理末尾で確認': (x['ready_msr']&0xf0) == 0xd0 if arm['kind']=='result' else None,
        '入口で確認': (x['entry_msr']&0xf0) == 0xd0 if arm['kind']=='result' else None,
        'READ入力と一致': command_match if arm['kind']=='result' else None,
        'データ受信数': x['data_count'], '結果7バイト': result,
        '7F0Dから7F13との位置別一致': [bool(v) for v in x['result_match']] if result is not None and len(x['result_match']) == 7 else None,
        '戻りとの関係': result_relations(values, result)}
    candidates = candidate_values(inputs(arm))
    targets = []
    for t in x['commands']:
        if not t['scope']: continue
        kind = t['bytes'][0]&31
        if kind in (4, 7, 15) and len(t['bytes']) >= 2:
            targets.append((FDC[kind]+'装置', t['bytes'][1]))
        if kind == 15 and len(t['bytes']) == 3: targets.append(('SEEKシリンダ', t['bytes'][2]))
    row['シーク'] = {'OUT F8': x['motors'], '入力との関係': [
        {'対象': name, '候補の真偽': matches(v, candidates)} for name,v in
        targets + [('OUT F8', v) for v in x['motors']]]}
    return row, values


def report(root):
    manifest = json.loads((root/'manifest.json').read_text())
    catalog = [a for a in arms() if a['name'] in manifest['腕']]
    if len(catalog) != len(manifest['腕']): raise ValueError('腕目録不正')
    rows, vals = {}, {}
    for arm in catalog:
        runs, values = [], []
        for n in (1,2):
            path = root/'raw'/arm['name']/str(n)
            try: row = json.loads((path/'row.json').read_text())
            except (OSError, ValueError): row = dict(MISSING)
            runs.append(row)
            values.append(json.loads((path/'values.tmp').read_text()) if (path/'values.tmp').exists() else None)
        rows[arm['name']] = {'走': runs, '2走一致': runs[0] == runs[1] if all(r['判定']=='取得' for r in runs) else None}
        vals[arm['name']] = values
    cache = root/'relations.json'
    if any(root.glob('raw/*/*/values.tmp')):
        relations, baselines = {}, {}
        for arm in catalog:
            baseline = baselines.setdefault((arm['address'],arm.get('iff')),arm['name'])
            v = vals[arm['name']]
            relations[arm['name']] = {'基準腕': baseline,
                '2走のレジスタ一致': None if any(x is None for x in v) else v[0] == v[1],
                '基準腕との一致': [None if x is None or y is None else {k:x[k]==y[k] for k in REGS}
                                  for x,y in zip(v,vals[baseline])]}
        dump(cache,relations)
    else: relations = json.loads(cache.read_text()) if cache.exists() else {}
    seek = {}
    seek_arms = [a for a in catalog if a['kind']=='seek']
    full_seek = len(seek_arms) == sum(a['kind']=='seek' for a in arms())
    for name in ('SEEK装置','SEEKシリンダ','SENSE DRIVE STATUS装置','OUT F8'):
        observations = []
        for a in seek_arms:
            for r in rows[a['name']]['走']:
                found = [t['候補の真偽'] for t in r.get('シーク',{}).get('入力との関係',[]) if t['対象']==name]
                observations.append(found if r['判定']=='取得' and r['戻り']=='確認' else [])
        complete = full_seek and bool(observations) and all(observations)
        passed = [key for key in candidate_values(inputs(seek_arms[0])) if all(v[key] for obs in observations for v in obs)] if complete else []
        seek[name] = {'全腕で観測完了': complete, '成立候補': passed,
                      '判定': '単一候補' if len(passed)==1 else '複数候補' if passed else '不明'}
    counts = Counter(r['戻り'] if r['判定']=='取得' else '欠測' for v in rows.values() for r in v['走'])
    result = {'腕数':len(rows), '走数':len(rows)*2,
              '集計':{k:counts[k] for k in ('確認','戻らない','欠測')}, '関係':relations, 'シーク規則':seek, '腕':rows}
    dump(root/'summary.json',result)
    return result


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('out',type=Path)
    report(parser.parse_args().out.resolve())
