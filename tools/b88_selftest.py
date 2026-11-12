#!/usr/bin/env python3
"""全腕実走の判定と、実機コードへの故障注入・値漏れ対照。"""
import copy
import json
import os
from pathlib import Path
import re
import subprocess
import sys

from b88_arms import arms
from b88_boot import generate_boot, ROOT
from b88_run import run_one, clean_run, dump
from b88_summarize import REGS, report, summarize_run


def relations(value):
    assert value is None or (set(value) == set(REGS) and all(type(v) is bool for v in value.values()))


def value_free(row):
    """公開スキーマを許可列挙。任意の値・レジスタ列・PCの追加を許さない。"""
    minimal = {'判定', '戻り', '理由'}
    if set(row) == minimal:
        assert row['判定'] == '欠測' and row['戻り'] == '欠測'
        assert row['理由'] in ('入口未到達', '未実行', '記録不足・実行失敗')
        return
    assert set(row) == minimal | {'再起動', '起動回数', '開始回数', 'I/O', 'FDC', 'RAM',
                                  '呼出し直前SP', '結果搬送一致', '入力との一致'}
    assert row['判定'] in ('取得', '欠測')
    assert row['戻り'] in ('確認', '戻らない')
    assert row['理由'] in ('戻り印', '再起動', '時間上限', '結果搬送不一致')
    assert type(row['再起動']) is bool
    assert all(type(row[k]) is int and row[k] >= 1 for k in ('起動回数', '開始回数'))
    assert row['呼出し直前SP'] in ('入力から戻り先1語分減少', '入力と一致')
    assert row['結果搬送一致'] is None or type(row['結果搬送一致']) is bool
    relations(row['入力との一致'])
    for item in row['I/O']:
        assert set(item) == {'方向', 'ポート', '件数'}
        assert item['方向'] in ('IN', 'OUT') and re.fullmatch('[0-9A-F]{2}', item['ポート'])
        assert type(item['件数']) is int and item['件数'] > 0
    from b88_summarize import FDC
    for item in row['FDC']:
        assert set(item) == {'種類', '件数'} and item['種類'] in set(FDC.values()) | {'INVALID'}
        assert type(item['件数']) is int and item['件数'] > 0
    assert set(row['RAM']) == {'比較終端', '変化番地', '値変化回数'}
    assert row['RAM']['比較終端'] in ('戻り', '再起動', '時間上限')
    for addr in row['RAM']['変化番地']:
        assert re.fullmatch('[4-7][0-9A-F]{3}', addr)
    for item in row['RAM']['値変化回数']:
        assert set(item) == {'番地', '件数'} and re.fullmatch('[4-7][0-9A-F]{3}', item['番地'])
        assert type(item['件数']) is int and item['件数'] > 0


def main():
    root = Path(sys.argv[1])
    assert not any(k.startswith('PC88_REF_') for k in os.environ)
    catalog = list(arms())
    assert len(catalog) == 130 and len({a['name'] for a in catalog}) == 130
    summary = json.loads((root / 'summary.json').read_text())
    assert summary['腕数'] == 130 and summary['走数'] == 260
    assert set(summary['腕']) == {a['name'] for a in catalog}
    assert summary['集計']['欠測'] == 0, '開始前の欠測が存在する'
    for arm in catalog:
        image, disk, labels = generate_boot(arm)
        assert len(image) == 768 and len(disk) < 10000
        assert 0xc000 <= labels['main']['BOOT'] < 0xc100 <= labels['main']['DONE'] < 0xc300
        row = summary['腕'][arm['name']]
        assert len(row['走']) == 2 and row['2走一致'] is True, '2走の不一致'
        for index, run in enumerate(row['走'], 1):
            assert run['開始回数'] >= 1 and run['判定'] == '取得', '全腕実走の欠測'
            assert json.loads((root / 'raw' / arm['name'] / str(index) / 'status.json').read_text()) == {'成功': True}
            value_free(run)
        for relation in row['基準腕との一致']: relations(relation)
    neg = summary['腕']['negative']['走'][0]
    pos = summary['腕']['positive']['走'][0]
    assert neg['戻り'] == pos['戻り'] == '確認'
    assert neg['結果搬送一致'] and pos['結果搬送一致']
    assert all(neg['入力との一致'].values())
    assert pos['入力との一致'] == {k: k != 'A' for k in REGS}
    assert '6400' not in neg['RAM']['変化番地'] and '6400' in pos['RAM']['変化番地']
    assert neg['I/O'] == pos['I/O'] == [] and neg['FDC'] == pos['FDC'] == []
    assert all(p.name not in {'values.tmp', 'mem', 'capture', 'stderr', 'rom', 'probe.bin', 'probe.d88'}
               and p.suffix.upper() != '.ROM' for p in (root / 'raw').rglob('*'))
    assert sum(p.stat().st_size for p in root.rglob('*') if p.is_file()) < 512 * 1024 * 1024
    # 生値削除後も同じ値なし集計を再生成できる。
    assert report(root) == summary
    # 検査自体の陰性対照: 生値フィールドを混ぜた出力を必ず拒否する。
    bad = copy.deepcopy(neg); bad['AF値'] = 0xd00d
    try:
        value_free(bad)
    except AssertionError:
        pass
    else:
        raise AssertionError('値漏れ検査の検出力がない')
    print('B88: 全130腕×2走・対照・値なし・後片付け PASS', flush=True)

    sys.path.insert(0, str(ROOT))
    from src.l3_service.make_subrom import build
    sub = build()[0]
    core = next(p for p in root.glob('quasi88_libretro.*') if p.suffix in ('.so', '.dylib', '.dll'))
    front = root / 'b88_frontend'
    arm = next(a for a in catalog if a['name'] == 'negative')
    for fault in ('result', 'restart', 'hang', 'same_write', 'restore', 'io'):
        path = root / 'faults' / fault
        try:
            run_one(path, arm, core, front, sub, 120, 120, fault)
            row, values = summarize_run(path, arm)
            value_free(row)
            if fault == 'result':
                assert row['戻り'] == '確認' and row['判定'] == '欠測' and row['結果搬送一致'] is False
                assert values is None
            elif fault in ('restart', 'hang'):
                assert row['判定'] == '取得' and row['戻り'] == '戻らない'
                assert row['再起動'] == (fault == 'restart')
                assert row['理由'] == ('再起動' if fault == 'restart' else '時間上限')
            elif fault in ('same_write', 'restore'):
                assert row['結果搬送一致'] and '6100' not in row['RAM']['変化番地']
                changes = {x['番地']: x['件数'] for x in row['RAM']['値変化回数']}
                assert changes.get('6100', 0) == (2 if fault == 'restore' else 0)
            elif fault == 'io':
                assert row['結果搬送一致']
                assert row['FDC'] == [{'種類': 'SPECIFY', '件数': 1}]
                assert {'方向': 'OUT', 'ポート': 'FB', '件数': 3} in row['I/O']
            dump(path / 'row.json', row)
        finally:
            clean_run(path)
    print('B88: 実走故障注入・再起動・未帰還・同値書込・復元・FDC分類 PASS', flush=True)

    path = root / 'faults' / 'logs'
    try:
        run_one(path, arm, core, front, sub, 120, 120)
        original = (path / 'mem').read_text()
        capture = (path / 'capture').read_text()
        # 欠落・取りこぼしを戻らないと誤認しない。
        for corrupt in (original.replace('取りこぼし: 0件', '取りこぼし: 1件'),
                        '\n'.join(x for x in original.splitlines() if not re.match(r'\s*2\s+\d+\s+', x))):
            (path / 'mem').write_text(corrupt)
            row, _ = summarize_run(path, arm)
            assert row['判定'] == row['戻り'] == '欠測'
        (path / 'mem').write_text(original)
        for corrupt in (capture.removesuffix('END\n'), capture.replace('END\n', 'SECRET-DO-NOT-LEAK\nEND\n')):
            (path / 'capture').write_text(corrupt)
            row, _ = summarize_run(path, arm)
            assert row['判定'] == '欠測' and 'SECRET' not in json.dumps(row)
        (path / 'capture').write_text(capture)
        # 入口前で時間切れになった実走も欠測。
        short = root / 'faults' / 'short'
        run_one(short, arm, core, front, sub, 1, 120)
        row, _ = summarize_run(short, arm)
        assert row['判定'] == row['戻り'] == '欠測'
        clean_run(short)
    finally:
        clean_run(path)
    print('B88: ログ欠落・取りこぼし・入口未到達・漏洩対照 PASS', flush=True)


if __name__ == '__main__':
    main()
