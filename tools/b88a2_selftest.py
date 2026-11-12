#!/usr/bin/env python3
"""追補2の全腕、既知の自作動作、破壊対照、公開スキーマを実走検査。"""
import copy
import json
import os
from pathlib import Path
import re
import sys

from b88a2_arms import arms, ENTRIES, READ_DATA
from b88a2_boot import assemble, generate_boot, ROOT
from b88a2_run import run_one, clean_run
from b88a2_summarize import summarize_run, report
from b88_selftest import value_free as base_value_free


def integer(x, limit=100000000):
    assert type(x) is int and 0 <= x <= limit


def boolean(x):
    assert type(x) is bool


def address(x):
    assert isinstance(x, str) and re.fullmatch('[4-7][0-9A-F]{3}', x)


def placements(items):
    assert isinstance(items, list)
    for i, p in enumerate(items):
        assert set(p) == {'順番', '候補番地', '終端まで維持', '対応', '単一候補番地', '容量超過'}
        assert p['順番'] == i
        assert len(p['候補番地']) == len(p['終端まで維持']) <= 16
        for a in p['候補番地']: address(a)
        for v in p['終端まで維持']: boolean(v)
        boolean(p['容量超過'])
        assert p['対応'] in ('単一候補', '不明')
        if p['単一候補番地'] is not None: address(p['単一候補番地'])


def value_free(row):
    row = copy.deepcopy(row)
    if set(row) == {'判定', '戻り', '理由'}:
        base_value_free(row); return
    preparation, irq, comm, read = [row.pop(k) for k in ('準備', '割り込み', '通信', '読出し')]
    if row['理由'] in ('先行処理未帰還', '媒体条件不成立'):
        assert row['判定'] == row['戻り'] == '欠測'
        row['理由'] = '入口未到達'
    base_value_free(row)
    assert set(preparation) == {'媒体交換確認', '前処理開始', '前処理完了', '入口到達', '段階'}
    for k in set(preparation)-{'段階'}: boolean(preparation[k])
    assert len(preparation['段階']) in (0, 11)
    for x in preparation['段階']:
        assert set(x) == {'開始', '完了'}
        for n in x.values(): integer(n)
    assert set(irq) == {'呼出し直前', '入口', '戻り直後', 'EI遅延確認回数',
                        '前処理の受理回数', '入口前の受理回数', '区間の受理回数', '入口から戻りの変化'}
    for k in ('呼出し直前', '入口', '戻り直後', '入口から戻りの変化'):
        if irq[k] is not None:
            assert set(irq[k]) == {'IFF1', 'IFF2', 'IM'}
            for name, x in irq[k].items():
                if k == '入口から戻りの変化': boolean(x)
                else: integer(x, 2 if name == 'IM' else 1)
    for k in ('EI遅延確認回数', '前処理の受理回数', '入口前の受理回数', '区間の受理回数'): integer(irq[k])
    assert set(comm) == {'main送信完了数', 'サブ受信数', '送信値との一致回数', '配置候補', '受信順の入力一致', '戻りAと入力一致', '配置候補範囲', '受信順に入力と一致'}
    for k in ('main送信完了数', 'サブ受信数'): integer(comm[k])
    assert 1 <= len(comm['送信値との一致回数']) <= 256
    for n in comm['送信値との一致回数']: integer(n, comm['サブ受信数'])
    placements(comm['配置候補'])
    for x in comm['受信順の入力一致']:
        assert 1 <= len(x) <= 256
        for v in x: boolean(v)
    if comm['戻りAと入力一致'] is not None:
        assert 1 <= len(comm['戻りAと入力一致']) <= 256
        for v in comm['戻りAと入力一致']: boolean(v)
    if comm['配置候補範囲'] is not None:
        for a in comm['配置候補範囲']: address(a)
    if comm['受信順に入力と一致'] is not None: boolean(comm['受信順に入力と一致'])
    assert set(read) == {'コマンド受理数', '9バイト入力と一致', 'データ受信数', '自作セクタ全体と一致',
        'データ配置候補範囲', 'データ対応', '結果受信数', 'FDC結果7バイト', '結果配置候補', '追跡容量超過'}
    for k in ('コマンド受理数', 'データ受信数', '結果受信数'): integer(read[k])
    for k in ('9バイト入力と一致', '自作セクタ全体と一致', '追跡容量超過'): boolean(read[k])
    assert read['データ対応'] in ('全256バイトの単一候補が連続', '不明')
    if read['データ配置候補範囲'] is not None:
        assert len(read['データ配置候補範囲']) == 2
        for x in read['データ配置候補範囲']: address(x)
        assert read['自作セクタ全体と一致']
    if read['FDC結果7バイト'] is not None:
        assert len(read['FDC結果7バイト']) == 7 and read['9バイト入力と一致'] and preparation['媒体交換確認']
        for n in read['FDC結果7バイト']: integer(n, 255)
    placements(read['結果配置候補'])


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
 LD D,A
 LD (26624),A
 LD A,13
 OUT (255),A
CLEAR:
 IN A,(254)
 AND 1
 JR NZ,CLEAR
 LD A,12
 OUT (255),A
 LD A,D
'''
OUTPUT = '''
 PUSH AF
WAIT:
 IN A,(250)
 AND 192
 CP 128
 JR NZ,WAIT
 POP AF
 OUT (251),A
 RET
'''
READER = '''
 LD HL,28672
 LD B,0
READ:
 IN A,(250)
 AND 192
 CP 192
 JR NZ,READ
 IN A,(251)
 LD (HL),A
 INC HL
 DJNZ READ
 RET
'''


def machine(source, origin=0):
    return assemble(f' ORG {origin}\n' + source)[0]


def fdc_fixture(corrupt=False, duplicate=False, overwrite=False):
    reader = READER.replace(' LD (HL),A', (' XOR 255\n' if corrupt else '') + ' LD (HL),A')
    if duplicate: reader = reader.replace(' LD (HL),A', ' LD (26880),A\n LD (HL),A')
    if overwrite: reader = reader.replace(' RET', ' XOR A\n LD (28677),A\n RET')
    result = READER.replace('28672', '29184').replace('LD B,0', 'LD B,7')
    return {0x7d6: b'\xc9', 0x35b: b'\xc9', 0x2a4: b'\xc3\x00\x18',
            0x20: b'\xc3\x00\x18', 0x2a7: b'\xc3\x40\x18',
            0x263: machine(result), 0x1800: machine(OUTPUT),
            0x1840: machine(' CALL 6144\n' + reader, 0x1840)}


def main(root):
    assert not any(k.startswith('PC88_REF_') for k in os.environ)
    catalog = list(arms())
    assert len(catalog) == len({a['name'] for a in catalog}) == 64
    assert len(READ_DATA) == 9
    assert {(a['address'], a['iff']) for a in catalog if a['name'].startswith('iff-')} == {
        (a, iff) for a, _, _ in ENTRIES for iff in ('di', 'ei')}
    summary = json.loads((root / 'summary.json').read_text())
    assert summary['腕数'] == 64 and summary['走数'] == 128
    for a in catalog:
        image, disk, labels = generate_boot(a)
        assert len(image) == 768 and len(disk) < 10000
        assert labels['sub']['invoke'] == labels['sub']['start'] + 4
        record = summary['腕'][a['name']]
        for n, r in enumerate(record['走'], 1):
            value_free(r)
            assert json.loads((root / 'raw' / a['name'] / str(n) / 'status.json').read_text()) == {'成功': True}
            assert r['準備']['媒体交換確認']
            if r['判定'] == '欠測':
                assert a['kind'] == 'read' and r['理由'] == '先行処理未帰還'
            else:
                assert r['準備']['入口到達'] and record['2走一致']
                assert r['割り込み']['呼出し直前']['IFF1'] == int(a.get('iff') == 'ei')
    neg = summary['腕']['negative']['走'][0]; pos = summary['腕']['positive']['走'][0]
    assert neg['結果搬送一致'] and pos['結果搬送一致']
    assert all(neg['入力との一致'].values())
    assert not pos['入力との一致']['A'] and '6400' in pos['RAM']['変化番地']
    assert neg['I/O'] == pos['I/O'] == []
    assert report(root) == summary
    print('B88追補2: 全64腕×2走・独立走行・再集計 PASS', flush=True)

    sys.path.insert(0, str(ROOT))
    from src.l3_service.make_subrom import build
    sub = build()[0]
    core = next(root.glob('quasi88_libretro.*')); front = root / 'b88_frontend'
    sequence = 0

    def run(arm=None, fault=None, check=None, **kw):
        nonlocal sequence
        sequence += 1
        path = root / 'controls' / str(sequence)
        arm = arm or dict(name='negative', address=None, mode='call', kind='negative')
        options = dict(frames=120, timeout=120); options.update(kw)
        try:
            run_one(path, arm, core, front, sub, fault=fault, **options)
            assert (path / 'rom' / 'DISK.ROM').is_file() and not (path / 'rom').is_symlink()
            row, values = summarize_run(path, arm)
            value_free(row)
            if check: check(path, arm, row, values)
            return row, values
        finally:
            clean_run(path)

    # IFF2を独立に振り、IFF1と同じフィールドを誤読する器具を検出する。
    for iff in ('di', 'ei'):
        for im in (0, 1, 2):
            for iff2 in (0, 1):
                a = dict(name='negative', address=None, mode='call', kind='negative', iff=iff, im=im)
                code = machine(' DI\n IM 2\n RET\n')
                r, _ = run(a, fault=code, test_iff2=iff2)
                assert r['結果搬送一致']
                assert r['割り込み']['入口'] == dict(IFF1=int(iff=='ei'), IFF2=iff2, IM=im)
                assert r['割り込み']['戻り直後'] == dict(IFF1=0, IFF2=iff2, IM=2)
    # 保留IRQをEI直前に発生させ、遅延の後、入口前で受理したことを識別する。
    a = dict(name='negative', address=None, mode='call', kind='negative', iff='ei')
    r, _ = run(a, fixture={0x38: b'\xc9'}, test_irq=True)
    assert r['結果搬送一致'] and r['割り込み']['EI遅延確認回数'] == 1
    assert r['割り込み']['入口前の受理回数'] == 1 and r['割り込み']['区間の受理回数'] == 0
    assert r['割り込み']['呼出し直前']['IFF1'] == 1 and r['割り込み']['入口']['IFF1'] == 0
    print('B88追補2: IFF1・IFF2・IM・EI遅延・入口前IRQ PASS', flush=True)

    for sent in ((0x35,), (0x35, 0xa6), (0xa6, 0x35)):
        for receive in range(len(sent)+1):
            a = dict(name='negative', address=None, mode='call', kind='recv', sent=sent)
            source = ''
            for i in range(receive):
                source += RECEIVER.replace('WAIT', f'WAIT{i}').replace('CLEAR', f'CLEAR{i}').replace('26624', str(26624+i))
            r, _ = run(a, fault=machine(source+' RET\n'))
            assert r['結果搬送一致']
            c = r['通信']
            assert c['サブ受信数'] == c['main送信完了数'] == receive
            assert c['受信順の入力一致'] == [[sent[i] == v for v in sent] for i in range(receive)]
            assert [p['単一候補番地'] for p in c['配置候補']] == [f'{26624+i:04X}' for i in range(receive)]
        a = dict(name='negative', address=None, mode='call', kind='recv', sent=sent)
        r, _ = run(a, fault=machine(RECEIVER+' XOR 255\n RET\n'))
        assert not any(r['通信']['戻りAと入力一致'])
    for count in (3, 4, 8, 16, 256):
        a = dict(next(a for a in catalog if a['name'] == f'06a6-length-{count}-first-10'))
        a.update(name='negative', address=None)
        # 受信処理はループのBを変更しない。
        receiver = RECEIVER.replace(' LD (26624),A', ' LD (HL),A\n INC HL')
        code = machine(f' LD HL,26624\n LD B,{count & 255}\nLOOP:\n' + receiver + ' DJNZ LOOP\n RET\n')
        r, _ = run(a, fault=code)
        c = r['通信']
        assert r['結果搬送一致'] and c['サブ受信数'] == c['main送信完了数'] == count
        assert c['受信順に入力と一致'] and c['配置候補範囲'] == ['6800', f'{0x6800+count-1:04X}']
    print('B88追補2: 1・2バイト通信・順序反転・途中帰還・破壊対照 PASS', flush=True)

    a = next(a for a in catalog if a['name'] == '0263-read-di')
    for kind in ('normal', 'corrupt', 'duplicate', 'overwrite'):
        fixture = fdc_fixture(**({kind: True} if kind != 'normal' else {}))
        r, _ = run(a, fixture=fixture)
        assert r['結果搬送一致'] and all(s == {'開始': 1, '完了': 1} for s in r['準備']['段階'])
        read = r['読出し']
        assert read['9バイト入力と一致'] and read['データ受信数'] == 256
        assert read['自作セクタ全体と一致'] and read['結果受信数'] == 7
        assert len(read['FDC結果7バイト']) == 7
        assert [p['単一候補番地'] for p in read['結果配置候補']] == [f'{0x7200+i:04X}' for i in range(7)]
        assert read['データ配置候補範囲'] == (['7000', '70FF'] if kind == 'normal' else None)
        assert {'方向': 'IN', 'ポート': 'FB', '件数': 7} in r['I/O']
    # 結果フェーズの途中終了では7バイト列を公開しない。
    fixture = fdc_fixture(); fixture[0x263] = machine(READER.replace('28672','29184').replace('LD B,0','LD B,6'))
    r, _ = run(a, fixture=fixture)
    assert r['読出し']['結果受信数'] == 6 and r['読出し']['FDC結果7バイト'] is None
    for step in range(11):
        r, _ = run(a, fault=f'prehang-{step}', fixture=fdc_fixture())
        assert r['判定'] == '欠測' and r['理由'] == '先行処理未帰還'
        assert r['準備']['段階'][step] == {'開始': 1, '完了': 0}
        assert all(s == {'開始': 1, '完了': 1} for s in r['準備']['段階'][:step])
    print('B88追補2: FDC9バイト・256バイト配置・結果7バイト・11段階の未帰還 PASS', flush=True)

    for fault in ('result', 'restart', 'hang', 'prehang'):
        r, v = run(a if fault == 'prehang' else None, fault=fault)
        if fault == 'result': assert r['判定'] == '欠測' and r['結果搬送一致'] is False and v is None
        elif fault == 'prehang': assert r['理由'] == '先行処理未帰還'
        else: assert r['戻り'] == '戻らない' and r['再起動'] is (fault == 'restart')
    for options in ({'frames': 1}, {'timeout': 0.000001}):
        r, v = run(**options)
        assert r['判定'] == r['戻り'] == '欠測' and v is None

    def broken_logs(path, arm, row, values):
        assert row['結果搬送一致']
        for name, edit in (
            ('extra', lambda s: s.replace('{', '{"内部PC":42,', 1)),
            ('extra', lambda s: s.replace('"states":[', '"states":[[256,0,0],', 1)),
            ('capture', lambda s: s.removesuffix('END\n')),
            ('capture', lambda s: s.replace('END\n', 'SECRET-DO-NOT-LEAK\nEND\n')),
            ('mem', lambda s: s.replace('取りこぼし: 0件', '取りこぼし: 1件'))):
            p = path/name; original = p.read_text(); p.write_text(edit(original))
            r, v = summarize_run(path, arm)
            assert r['判定'] == '欠測' and v is None
            assert 'SECRET' not in json.dumps(r)
            p.write_text(original)
        p=path/'extra'; x=json.loads(p.read_text()); x['media_ok']=0; p.write_text(json.dumps(x))
        r, v = summarize_run(path, arm)
        assert r['理由'] == '媒体条件不成立' and v is None
    run(check=broken_logs)
    for key in ('画面本文', '内部PC', 'AF値'):
        bad=copy.deepcopy(neg); bad[key]='SECRET-DO-NOT-LEAK'
        try: value_free(bad)
        except AssertionError: pass
        else: raise AssertionError('漏洩検査の検出力不足')
    for section in ('割り込み', '通信', '読出し'):
        bad=copy.deepcopy(neg); bad[section]['値列']=[222,173]
        try: value_free(bad)
        except AssertionError: pass
        else: raise AssertionError('追加列の漏洩検査の検出力不足')
    forbidden = {'values.tmp', 'mem', 'capture', 'extra', 'stderr', 'rom', 'probe.bin', 'probe.d88', 'media.d88', 'media2.d88', 'fixture.bin'}
    assert all(p.name not in forbidden and p.suffix.upper() != '.ROM' for base in ('raw','controls') for p in (root/base).rglob('*'))
    assert not (root/'build').exists()
    assert sum(p.stat().st_size for p in root.rglob('*') if p.is_file()) < 512*1024*1024
    print('B88追補2: 時間上限・再起動・欠測・漏洩対照・後片付け PASS', flush=True)


if __name__ == '__main__':
    main(Path(sys.argv[1]))
