#!/usr/bin/env python3
"""l4-s9y追補1の固定143腕。元器具の操作・予測・関門を維持する。"""
import argparse
import copy
import csv
import json
import os
from pathlib import Path
import tempfile
import l4_dim_measure as d

HELD = {f'dims-{n}' for n in (48, 64, 96, 120, 127, 128, 254, 255, 256)}


def adopted():
    return {a['id']: a for a in d.arms() if a['id'] not in HELD}


def load_runs(path):
    runs = d.lm.read_runs(path)
    known = adopted()
    if set(runs) != set(known):
        raise ValueError('固定143腕の欠落/追加')
    for aid, rows in runs.items():
        if any(json.loads(r['plan']) != json.loads(json.dumps(d.plan(known[aid]))) for r in rows):
            raise ValueError('固定操作相違')
    return d.read_passed([path])


def expected(out, measured):
    values = load_runs(measured)
    d.lm.write_tsv(out, ['arm', 'observation'],
                   [(k, json.dumps(v)) for k, v in sorted(values.items())])
    return len(values)


def check(exp, measured):
    with exp.open(newline='') as f:
        rows = list(csv.DictReader(f, delimiter='\t'))
    want = {r['arm']: json.loads(r['observation']) for r in rows}
    known = adopted()
    if len(rows) != len(want) or set(want) != set(known):
        raise ValueError('固定143腕の期待値欠落/重複/追加')
    records = []
    for aid, value in want.items():
        if not d.valid(value, dict(known[aid], speed=False)):
            raise ValueError('期待値の数値形')
        records.append(dict(arm=known[aid], obs=[value, value], gate=True))
    if not d.calibrated(records):
        raise ValueError('期待値の較正')
    got = load_runs(measured)
    ok = [aid for aid in want if want[aid] == got[aid]]
    bad = [aid for aid in want if want[aid] != got[aid]]
    return ok, bad


def selftest(work):
    work.mkdir(parents=True, exist_ok=True)
    fixtures = []
    for a in adopted().values():
        o = dict(arm=a['id'], probes={str(k): [s['error'] or 0, s['prediction'] or 0]
                                     for k, s in enumerate(a['steps'])},
                 errors=3 if a['id'] == 'cal-error' else 0, sent=1)
        if a['speed']:
            o['marks'] = dict(n1=1, n2=1, frames=10, ordered=True)
        fixtures.append(dict(arm=a, obs=[copy.deepcopy(o), copy.deepcopy(o)], gate=True))
    with tempfile.TemporaryDirectory(prefix='results-fixture-', dir=work) as td:
        td = Path(td)
        good, exp, badpath = td/'good.tsv', td/'expected.tsv', td/'bad.tsv'
        d.emit(good, fixtures)
        assert expected(exp, good) == 143
        assert len(check(exp, good)[0]) == 143
        # 計時フレームのみ異なっても一致する。
        changed = copy.deepcopy(fixtures)
        for r in changed:
            if r['arm']['speed']:
                for o in r['obs']:
                    o['marks']['frames'] = 20
        d.emit(badpath, changed)
        assert len(check(exp, badpath)[0]) == 143
        for mode in ('value', 'error', 'count', 'sent', 'missing', 'duplicate',
                     'extra', 'plan', 'calibration', 'unequal', 'repeat', 'timing', 'gate'):
            changed = copy.deepcopy(fixtures)
            target = changed[2]
            if mode in ('value', 'error'):
                for o in target['obs']:
                    o['probes']['0'][1 if mode == 'value' else 0] += 1
            elif mode in ('count', 'sent'):
                for o in target['obs']:
                    o['errors' if mode == 'count' else 'sent'] += 1
            elif mode == 'missing':
                changed.pop(2)
            elif mode == 'duplicate':
                changed.append(copy.deepcopy(target))
            elif mode == 'extra':
                target['arm']['id'] = 'unknown'
                for o in target['obs']:
                    o['arm'] = 'unknown'
            elif mode == 'calibration':
                for o in changed[0]['obs']:
                    o['probes']['0'][1] += 1
            elif mode == 'unequal':
                target['obs'][0]['probes']['0'][1] += 1
            elif mode == 'timing':
                for o in changed[-1]['obs']:
                    o['marks']['frames'] = -1
            elif mode == 'gate':
                target['gate'] = False
            d.emit(badpath, changed, strict=False)
            if mode in ('plan', 'repeat'):
                with badpath.open(newline='') as f:
                    rows = list(csv.DictReader(f, delimiter='\t'))
                rows[4]['plan' if mode == 'plan' else 'repeat'] = '[]' if mode == 'plan' else '2'
                d.lm.write_tsv(badpath, list(rows[0]), [list(r.values()) for r in rows])
            try:
                assert check(exp, badpath)[1], mode
            except ValueError:
                pass
            if mode not in ('value', 'error', 'count'):
                try:
                    expected(td/'reject.tsv', badpath)
                except ValueError:
                    pass
                else:
                    raise AssertionError('不正測定から期待値生成')
        with exp.open(newline='') as f:
            rows = list(csv.DictReader(f, delimiter='\t'))
        for mode in ('missing', 'duplicate', 'extra', 'calibration'):
            bad = copy.deepcopy(rows)
            if mode == 'missing': bad.pop()
            elif mode == 'duplicate': bad.append(copy.deepcopy(bad[0]))
            elif mode == 'extra': bad[0]['arm'] = 'unknown'
            else:
                row = next(r for r in bad if r['arm'] == 'cal-num')
                o = json.loads(row['observation']); o['probes']['0'][1] += 1
                row['observation'] = json.dumps(o)
            d.lm.write_tsv(badpath, ['arm', 'observation'], [list(r.values()) for r in bad])
            try: check(badpath, good)
            except ValueError: pass
            else: raise AssertionError('不正期待値を受理')
    print('OK 固定143腕・計時除外・測定13種/期待値4種の陰性対照')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='command', required=True)
    m = sub.add_parser('measure')
    m.add_argument('--official', action='store_true')
    m.add_argument('--rom-dir', type=Path)
    m.add_argument('--work-dir', type=Path, required=True)
    m.add_argument('--out', type=Path, required=True)
    e = sub.add_parser('expected')
    e.add_argument('--measured', type=Path, required=True)
    e.add_argument('--out', type=Path, required=True)
    c = sub.add_parser('check')
    c.add_argument('--expected', type=Path, required=True)
    c.add_argument('--measured', type=Path, required=True)
    s = sub.add_parser('selftest')
    s.add_argument('--work-dir', type=Path, required=True)
    args = p.parse_args()
    if hasattr(args, 'work_dir') and not args.work_dir.is_absolute():
        p.error('作業先は絶対パス必須')
    if args.command == 'selftest': selftest(args.work_dir); return 0
    if args.command == 'expected':
        print(f'期待値 {expected(args.out, args.measured)}腕'); return 0
    if args.command == 'check':
        ok, bad = check(args.expected, args.measured)
        for aid in bad: print(f'DIFF {aid}: 値/誤り/件数')
        print(f'一致 {len(ok)}腕 / 不一致 {len(bad)}腕')
        return int(bool(bad))
    if args.official and args.rom_dir: p.error('公式は環境変数のみ')
    rom = os.environ.get('PC88_REF_ROM_DIR') if args.official else args.rom_dir
    if not rom: p.error('公式PC88_REF_ROM_DIR／自作--rom-dirが必要')
    records = d.measure(rom, args.official, list(adopted().values()), args.work_dir)
    passed = d.emit(args.out, records)
    print('記録 143腕×2走: '+('pass' if passed else 'gate_failed'))
    return int(not passed)


if __name__ == '__main__':
    try: raise SystemExit(main())
    except Exception as e:
        print(f'NG 結果器具 ({type(e).__name__}、画面本文非出力)')
        raise SystemExit(1)
