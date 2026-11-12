#!/usr/bin/env python3
"""登録腕・全腕走行・通信協力・故障注入・値なし集計の自己検査。"""
import json
from collections import Counter
from b88a1_arms import arms
from b88a1_relations import classify_calc

catalog = list(arms())
assert len(catalog) == 628 == len({x['name'] for x in catalog})
assert Counter(x['kind'] for x in catalog)['calc'] == 512
assert {(x['a'], x['f']) for x in catalog if x['kind'] == 'calc'} == {(a, f) for a in range(256) for f in (0, 1)}
records = [(a, f, a ^ 255, f) for a in range(256) for f in (0, 1)]
result = classify_calc(records)
assert result['判定'] == '取得'
assert not result['A']['入力Aと恒等'] and result['F']['入力Fと恒等']
assert all(f'NOT A{i}' in result['A']['各ビットの関係'][i] for i in range(8))
assert classify_calc(records[:-1]) == {'判定': '欠測'}
assert classify_calc(records[:-1] + records[:1]) == {'判定': '欠測'}
assert '255' not in json.dumps(result)
print('B88追補1: 腕一覧・関係判定の単体検査 PASS')

# ここからは run.sh の全腕実走と、独立した自作動作による器具検査。
import copy
import os
from pathlib import Path
import re
import shutil
import sys
from b88a1_run import run_one, clean_run
from b88a1_summarize import summarize_run, report, BYTE_REGS
from b88_boot import generate_boot, assemble, ROOT
from b88_selftest import value_free as base_value_free
from b88_run import dump


def booleans(value, keys):
    assert value is None or (set(value) == set(keys) and all(type(v) is bool for v in value.values()))


def value_free(row):
    base = dict(row)
    preparation = base.pop('準備', None)
    extra = base.pop('追加関係', None)
    flags = base.pop('フラグ入力と一致', None)
    if base['理由'] in ('媒体条件不成立', '先行処理未帰還'):
        base['理由'] = '入口未到達'
    base_value_free(base)
    booleans(preparation, ('媒体交換確認', '前処理開始', '前処理完了', '入口到達'))
    booleans(flags, map(str, range(8)))
    if extra is None:
        return
    assert isinstance(extra, dict)
    assert set(extra) <= {'main送信完了', '戻りAと送信値が一致', 'main受信', 'FDC受理', '7F0C', 'OUT F7'}
    for key, item in extra.items():
        if key in ('main送信完了', '戻りAと送信値が一致'):
            assert item is None or type(item) is bool
        elif key in ('main受信', 'FDC受理'):
            keys = {'件数', '先頭と入力との一致'} | ({'全受信と入力との一致'} if key == 'main受信' else set())
            assert set(item) == keys and type(item['件数']) is int and item['件数'] >= 0
            for k in keys - {'件数'}:
                booleans(item[k], BYTE_REGS)
        elif key == '7F0C':
            if item is not None:
                assert set(item) == {'前後一致', '前値に1加算', '前値から1減算', '入力との一致'}
                assert all(type(item[k]) is bool for k in ('前後一致', '前値に1加算', '前値から1減算'))
                booleans(item['入力との一致'], BYTE_REGS)
        else:
            assert set(item) == {'件数', '全出力と入力Aが一致', '最終出力と戻りAが一致'}
            assert type(item['件数']) is int and item['件数'] >= 0
            assert all(item[k] is None or type(item[k]) is bool for k in set(item) - {'件数'})


def relations_free(relations):
    assert set(relations) == {'計算', '00ED一定値', '腕間'}
    assert len(relations['計算']) == 2
    for calc in relations['計算']:
        if calc == {'判定': '欠測'}:
            continue
        assert set(calc) == {'判定', 'A', 'F'} and calc['判定'] == '取得'
        for key in ('A', 'F'):
            r = calc[key]
            assert set(r) == {'入力Aと恒等', '入力Fと恒等', '各ビットの関係',
                              '単一入力ビットまたは定数で全ビットを表せる', '関係の形'}
            assert all(type(r[k]) is bool for k in ('入力Aと恒等', '入力Fと恒等', '単一入力ビットまたは定数で全ビットを表せる'))
            assert len(r['各ビットの関係']) == 8
            assert all(isinstance(v, list) and all(re.fullmatch(r'0|1|(?:NOT )?[AF][0-7]', x) for x in v)
                       for v in r['各ビットの関係'])
            assert r['関係の形'] in ('恒等', '定数', 'ビット写像', '表引き的（候補規則では表せない）')
    assert set(relations['00ED一定値']) <= {'A', 'F'}
    assert all(type(v) is int and 0 <= v <= 255 for v in relations['00ED一定値'].values())
    names = {a['name'] for a in catalog}
    assert set(relations['腕間']) <= names
    for r in relations['腕間'].values():
        assert set(r) == {'基準腕', '基準腕との一致', '2走のレジスタ一致'}
        assert r['基準腕'] in names and len(r['基準腕との一致']) == 2
        for v in r['基準腕との一致']:
            booleans(v, ('SP', 'HL', 'DE', 'BC', 'A', 'F'))
        assert r['2走のレジスタ一致'] is None or type(r['2走のレジスタ一致']) is bool


def aggregate_controls(root, row):
    """既知の自作出力で全域集計・定数の全条件要求・再集計を検証。"""
    path = root / 'aggregate-controls'
    subset = [a for a in catalog if a['kind'] in ('calc', 'init')]
    path.mkdir()
    try:
        dump(path / 'manifest.json', {'腕': [a['name'] for a in subset]})
        for a in subset:
            for repeat in (1, 2):
                d = path / 'raw' / a['name'] / str(repeat)
                d.mkdir(parents=True)
                dump(d / 'row.json', row)
                dump(d / 'values.tmp', dict(SP=0x7e00, HL=0x6157, DE=0x2345, BC=0x6789,
                     A=(a['a'] ^ 255) if a['kind'] == 'calc' else 0x71,
                     F=a['f'] if a['kind'] == 'calc' else 0))
        complete = report(path)
        relations_free(complete['関係'])
        assert complete['関係']['計算'][0]['A']['関係の形'] == 'ビット写像'
        assert complete['関係']['計算'][1]['F']['入力Fと恒等']
        assert complete['関係']['00ED一定値'] == {'A': 0x71, 'F': 0}
        # 一つでも取得できない条件があれば定数も全域則も主張しない。
        for kind, key in [('calc', '計算'), ('init', '00ED一定値')]:
            a = next(a for a in subset if a['kind'] == kind)
            value_path = path / 'raw' / a['name'] / '1' / 'values.tmp'
            original = value_path.read_text()
            value_path.write_text('null\n')
            incomplete = report(path)['関係'][key]
            assert incomplete == {} if kind == 'init' else incomplete[0] == {'判定': '欠測'}
            value_path.write_text(original)
        assert report(path) == complete
        for p in path.glob('raw/*/*/values.tmp'):
            p.unlink()
        assert report(path) == complete
    finally:
        shutil.rmtree(path)


RECEIVER = '''
 LD A,11
 OUT (255),A
WAIT:
 IN A,(254)
 AND 1
 JR Z,WAIT
 LD A,10
 OUT (255),A
 IN A,(252)
 PUSH AF
 LD A,13
 OUT (255),A
CLEAR:
 IN A,(254)
 AND 1
 JR NZ,CLEAR
 LD A,12
 OUT (255),A
 POP AF
'''
SENDER = '''
 PUSH AF
WAIT:
 IN A,(254)
 AND 2
 JR Z,WAIT
 POP AF
 OUT (253),A
 PUSH AF
 LD A,9
 OUT (255),A
ACK:
 IN A,(254)
 AND 4
 JR Z,ACK
 LD A,8
 OUT (255),A
CLEAR:
 IN A,(254)
 AND 4
 JR NZ,CLEAR
 POP AF
'''


def main(root):
    assert not any(k.startswith('PC88_REF_') for k in os.environ)
    summary = json.loads((root / 'summary.json').read_text())
    assert summary['腕数'] == 628 and summary['走数'] == 1256
    assert set(summary['腕']) == {a['name'] for a in catalog}
    relations_free(summary['関係'])
    for arm in catalog:
        image, disk, labels = generate_boot(arm)
        assert len(image) == 768 and len(disk) < 10000
        assert 0xc100 <= labels['main']['DONE'] < 0xc300
        record = summary['腕'][arm['name']]
        assert len(record['走']) == 2
        for row in record['走']:
            value_free(row)
            assert row['準備']['媒体交換確認']
            if row['判定'] == '欠測':
                # 自作側の未実装入口を先行呼出しして戻らない場合だけ許す。
                assert arm.get('preinit') or arm.get('command') == 'sense_interrupt'
                assert row['理由'] == '先行処理未帰還'
            else:
                assert row['準備']['入口到達'] and row['開始回数'] >= 1
                assert record['2走一致'] is True
    neg = summary['腕']['negative']['走'][0]
    pos = summary['腕']['positive']['走'][0]
    assert neg['結果搬送一致'] and pos['結果搬送一致']
    assert all(neg['入力との一致'].values())
    assert not pos['入力との一致']['A'] and '6400' in pos['RAM']['変化番地']
    assert neg['I/O'] == pos['I/O'] == []
    assert report(root) == summary, '生値を削除した後の再集計が不一致'
    assert sum(p.stat().st_size for p in root.rglob('*') if p.is_file()) < 512 * 1024 * 1024
    forbidden = {'values.tmp', 'mem', 'capture', 'extra', 'stderr', 'rom', 'probe.bin', 'probe.d88'}
    assert all(p.name not in forbidden and p.suffix.upper() != '.ROM' for p in (root / 'raw').rglob('*'))
    for field in ('AF値', '画面本文', '内部PC'):
        bad = copy.deepcopy(neg); bad[field] = 'SECRET-DO-NOT-LEAK'
        try:
            value_free(bad)
        except AssertionError:
            pass
        else:
            raise AssertionError('値漏れ検査の検出力がない')
    bad = copy.deepcopy(summary['関係']); bad['計算'][0]['値列'] = [0xde, 0xad]
    try:
        relations_free(bad)
    except AssertionError:
        pass
    else:
        raise AssertionError('関係の値漏れ検査の検出力がない')
    aggregate_controls(root, neg)
    print('B88追補1: 全628腕×2走・媒体条件・再集計・後片付け PASS', flush=True)

    sys.path.insert(0, str(ROOT))
    from src.l3_service.make_subrom import build
    sub = build()[0]
    core = next(root.glob('quasi88_libretro.*')); front = root / 'b88_frontend'
    sequence = 0

    def run(arm, fault=None, frames=120, check=None):
        nonlocal sequence
        sequence += 1
        path = root / 'faults' / str(sequence)
        try:
            run_one(path, arm, core, front, sub, frames, 120, fault=fault)
            row, values = summarize_run(path, arm)
            value_free(row)
            if check:
                check(path, row, values)
            return row, values
        finally:
            clean_run(path)

    def control(kind, **kw):
        return dict(name='negative', address=None, mode='call', kind=kind, **kw)

    def machine(source):
        return assemble(' ORG 0\n' + source + '\n RET\n')[0]

    # main が入口到達後に送信することを、異なる自作値と破壊対照で検査。
    for sent in (0, 0x35, 0xa6, 0xff):
        for corrupt in (False, True):
            code = machine(RECEIVER + ('\n XOR 255' if corrupt else ''))
            row, values = run(control('recv', sent=sent), code)
            assert row['結果搬送一致'] and row['追加関係']['戻りAと送信値が一致'] is not corrupt
    # main 受信数・七レジスタ／HL指示先との一致をそれぞれ独立に検証。
    for reg in BYTE_REGS:
        source = ('' if reg == 'A' else f' LD A,{reg}\n') + SENDER
        row, _ = run(control('send'), machine(source))
        reception = row['追加関係']['main受信']
        assert row['結果搬送一致'] and reception['件数'] == 1
        assert reception['先頭と入力との一致'] == {k: k == reg for k in BYTE_REGS}
    row, _ = run(control('send'), machine(SENDER + SENDER.replace('WAIT', 'WAIT2').replace('ACK', 'ACK2').replace('CLEAR', 'CLEAR2')))
    assert row['追加関係']['main受信']['件数'] == 2
    row, _ = run(control('send'), machine(''))
    assert row['追加関係']['main受信']['件数'] == 0
    print('B88追補1: main協力通信・8種の入力比較・受信数・破壊対照 PASS', flush=True)

    for reg in BYTE_REGS[:-1]:
        source = ('' if reg == 'A' else f' LD A,{reg}\n') + ' OUT (251),A\n LD (32524),A'
        row, _ = run(control('fdc'), machine(source))
        relation = row['追加関係']
        assert row['結果搬送一致'] and relation['FDC受理']['件数'] == 1
        assert relation['FDC受理']['先頭と入力との一致'] == {k: k == reg for k in BYTE_REGS}
        assert not relation['7F0C']['前後一致'] and relation['7F0C']['入力との一致'][reg]
    for op, key in [('', '前後一致'), (' INC A', '前値に1加算'), (' DEC A', '前値から1減算')]:
        row, _ = run(control('fdc'), machine(' LD A,(32524)\n' + op + '\n LD (32524),A'))
        assert row['追加関係']['7F0C'][key]
        assert row['追加関係']['FDC受理']['先頭と入力との一致'] is None
    for corrupt in (False, True):
        row, _ = run(control('out', a=0x35), machine(' OUT (247),A\n' + (' XOR 255' if corrupt else '')))
        relation = row['追加関係']['OUT F7']
        assert relation['件数'] == 1 and relation['全出力と入力Aが一致']
        assert relation['最終出力と戻りAが一致'] is not corrupt
    for a in (0, 1, 0x7f, 0x80, 0xff):
        for f in (0, 1):
            row, values = run(control('calc', a=a, f=f), machine(' CPL'))
            assert row['結果搬送一致'] and values['A'] == (a ^ 255)
    print('B88追補1: FDC・7F0C・F7・計算戻り値・陰性対照 PASS', flush=True)

    for fault in ('result', 'restart', 'hang', 'prehang'):
        arm = control('negative', preinit=True) if fault == 'prehang' else control('negative')
        row, values = run(arm, fault)
        if fault == 'result':
            assert row['判定'] == '欠測' and row['結果搬送一致'] is False and values is None
        elif fault == 'prehang':
            assert row['判定'] == '欠測' and row['理由'] == '先行処理未帰還'
            assert not row['準備']['入口到達']
        else:
            assert row['判定'] == '取得' and row['戻り'] == '戻らない'
            assert row['再起動'] is (fault == 'restart')
    row, _ = run(control('negative'), frames=1)
    assert row['判定'] == row['戻り'] == '欠測'

    def corrupt_logs(path, row, values):
        assert row['結果搬送一致']
        for name, change in [('capture', lambda s: s.removesuffix('END\n')),
                             ('capture', lambda s: s.replace('END\n', 'SECRET-DO-NOT-LEAK\nEND\n')),
                             ('mem', lambda s: s.replace('取りこぼし: 0件', '取りこぼし: 1件')),
                             ('extra', lambda s: s.replace('{', '{"SECRET-DO-NOT-LEAK":42,', 1))]:
            p = path / name; original = p.read_text()
            p.write_text(change(original))
            rejected, val = summarize_run(path, control('negative'))
            assert rejected['判定'] == '欠測' and val is None
            assert 'SECRET' not in json.dumps(rejected)
            p.write_text(original)
        p = path / 'extra'; data = json.loads(p.read_text()); data['media_ok'] = 0
        p.write_text(json.dumps(data))
        rejected, val = summarize_run(path, control('negative'))
        assert rejected['判定'] == '欠測' and rejected['理由'] == '媒体条件不成立'
    run(control('negative'), check=corrupt_logs)
    assert all(p.name not in forbidden and p.suffix.upper() != '.ROM' for p in (root / 'faults').rglob('*'))
    print('B88追補1: 未帰還・先行処理・再起動・欠測・ログ破壊・漏洩対照 PASS', flush=True)


if __name__ == '__main__' and len(sys.argv) == 2:
    main(Path(sys.argv[1]))
