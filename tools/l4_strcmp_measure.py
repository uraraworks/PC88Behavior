#!/usr/bin/env python3
"""l4-s9e の文字列比較の予測・整数PRINT採取。画面の他の本文は残さない。"""
import argparse
import csv
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
from unittest.mock import patch
import l4_listkw_measure as kw

WORK = kw.REPO.parent / 'tmp/l4s9e-work'
OPS = [('eq', '='), ('ne', '<>'), ('lt', '<'), ('gt', '>'), ('le', '<='), ('ge', '>=')]


def cmp_gw(op, a, b):
    """GWのSTRCMP: 符号なしバイトで先頭から比べ、先に終わった側が小さい。真は-1。"""
    order = (a > b) - (a < b)  # Pythonのbytes比較は符号なし辞書順で接頭辞は短い方が小さい
    return -1 if {'=': order == 0, '<>': order != 0, '<': order < 0,
                  '>': order > 0, '<=': order <= 0, '>=': order >= 0}[op] else 0


# 名前 -> (BASICの式, バイト列)。大文字・0・128以上は打鍵できないのでchr$で作る。
OPERAND = {
    'ab': ('"ab"', b'ab'), 'abc': ('"abc"', b'abc'), 'e': ('""', b''),
    'a': ('"a"', b'a'), 'ac': ('"ac"', b'ac'), 'ba': ('"ba"', b'ba'),
    'A': ('chr$(65)', b'A'), 'c200': ('chr$(200)', bytes([200])),
    'c127': ('chr$(127)', bytes([127])), 'c128': ('chr$(128)', bytes([128])),
    'c0': ('chr$(0)', b'\0'), 'c1': ('chr$(1)', b'\1'),
    'a0': ('"a"+chr$(0)', b'a\0'), 'a0b': ('"a"+chr$(0)+"b"', b'a\0b'),
    'a0c': ('"a"+chr$(0)+"c"', b'a\0c'),
}
PAIRS = [('eq', 'ab', 'ab'), ('prel', 'ab', 'abc'), ('prer', 'abc', 'ab'),
         ('ee', 'e', 'e'), ('ene', 'e', 'a'), ('nee', 'a', 'e'),
         ('lastlt', 'ab', 'ac'), ('lastgt', 'ac', 'ab'),
         ('firstlt', 'ab', 'ba'), ('firstgt', 'ba', 'ab'),
         ('case', 'a', 'A'), ('caser', 'A', 'a'),
         ('hil', 'c200', 'a'), ('hir', 'a', 'c200'),
         ('h127', 'c127', 'c128'), ('h128', 'c128', 'c127'),
         ('z-pre', 'a0', 'a'), ('z-prer', 'a', 'a0'), ('z-e', 'c0', 'e'),
         ('z-z', 'c0', 'c0'), ('z-1', 'c0', 'c1'), ('z-mid', 'a0b', 'a0c')]
VARPAIRS = [('ab', 'abc'), ('c200', 'a'), ('e', 'e')]

FUNCS = [  # (式, 予測値)
    ('left$("abc",2)="ab"', -1), ('left$("abc",2)<"abc"', -1),
    ('left$("abc",2)>"abc"', 0), ('mid$("hello",2,3)="ell"', -1),
    ('mid$("hello",2,3)<>"ell"', 0), ('right$("abc",2)>"ab"', -1),
    ('right$("abc",2)="bc"', -1), ('chr$(65)+"b"=chr$(65)+chr$(98)', -1),
    ('"a"+"b"="ab"', -1), ('"a"+"b"<"ab"', 0), ('"a"+"b"<="ab"', -1),
    ('str$(5)=" 5"', -1), ('str$(5)="5"', 0), ('left$("abc",0)=""', -1),
    ('chr$(65)<chr$(97)', -1), ('asc("a")=97', -1), ('val("1")=1', -1),
]
LOGIC = [
    ('("a"="a") and (1=1)', -1), ('("a"="b") and (1=1)', 0),
    ('("a"="b") or (1=1)', -1), ('("a"="b") or (2=1)', 0),
    ('("a"<"b") and ("b"<"c")', -1), ('not ("a"="b")', -1),
    ('not ("a"="a")', 0), ('("a"="a")+1', 0), ('("a"="b")+1', 1),
    ('-("a"="a")', 1), ('"a"="a" and 1=1', -1), ('"a"="b" or 1=1', -1),
    ('1=1 and "a"="b"', 0), ('("a"="a")=(1=1)', -1),
    ('("a"="b")=(1=2)', -1), ('("a"="a")=1', 0),
]
IFS = [  # (setup, 条件, 予測値)
    ([], 'a$=""', 1), ([], 'a$<>""', 0),
    (['a$="x"'], 'a$=""', 0), (['a$="x"'], 'a$<>""', 1),
    (['a$=chr$(0)'], 'a$=""', 0), (['a$=chr$(0)'], 'a$<>""', 1),
    ([], '"ab"="ab"', 1), ([], '"ab"<"abc"', 1), ([], '"b"<"a"', 0),
    (['a$="x"', 'b$="y"'], 'a$<>"" and b$<>""', 1),
    (['a$="x"', 'b$="y"'], 'a$<>"" and b$=""', 0),
    (['a$="x"', 'b$="y"'], 'a$="" or b$<>""', 1),
    (['a$="x"'], 'not (a$="")', 1), ([], 'a$=b$', 1),
    ([], 'left$("abc",2)="ab"', 1), (['a$=chr$(200)'], 'a$>"a"', 1),
]
TYPES = [('"a"=1', []), ('1="a"', []), ('"a"<1', []), ('1<"a"', []),
         ('"a"<>1', []), ('1<>"a"', []), ('""=0', []), ('"1"=1', []),
         ('1="1"', []), ('a$=1', ['a$="1"'])]


def arms():
    out = []
    for pid, l, r in PAIRS:
        for oid, op in OPS:
            out.append(dict(id=f'lit-{pid}-{oid}', setup=[], mode='v',
                            expr=OPERAND[l][0]+op+OPERAND[r][0],
                            pred=cmp_gw(op, OPERAND[l][1], OPERAND[r][1])))
    for l, r in VARPAIRS:
        for oid, op in OPS:
            out.append(dict(id=f'var-{l}-{r}-{oid}',
                            setup=['a$='+OPERAND[l][0], 'b$='+OPERAND[r][0]],
                            mode='v', expr='a$'+op+'b$',
                            pred=cmp_gw(op, OPERAND[l][1], OPERAND[r][1])))
    for i, (e, p) in enumerate(FUNCS, 1):
        out.append(dict(id=f'func-{i:02d}', setup=[], mode='v', expr=e, pred=p))
    for i, (e, p) in enumerate(LOGIC, 1):
        out.append(dict(id=f'logic-{i:02d}', setup=[], mode='v', expr=e, pred=p))
    for i, (s, c, p) in enumerate(IFS, 1):
        out.append(dict(id=f'if-{i:02d}', setup=s, mode='if', expr=c, pred=p))
    for i, (e, s) in enumerate(TYPES, 1):
        out.append(dict(id=f'type-{i:02d}', setup=s, mode='v', expr=e, pred=('err', 13)))
    return out


def controls():
    return [dict(id='control-true', setup=[], mode='v', expr='(1=1)', pred=-1),
            dict(id='control-false', setup=[], mode='v', expr='(1=2)', pred=0),
            dict(id='control-str', setup=[], mode='v', expr='asc(mid$("hello",2,3))', pred=101),
            dict(id='control-error', setup=[], mode='err', expr='error 5', pred=('err', 5))]


def prediction(arm):
    p = arm['pred']
    first = ['s9e', 1, p[1]] if isinstance(p, tuple) else ['s9f', 1, p]
    return [first, ['s9d', 1, 1]]


def program(arm, trap=True):
    lines = ['new', '950 print "s9e";n;err:f=1:resume next', '10 n=1:f=0']
    if trap:
        lines.append('15 on error goto 950')
    for i, s in enumerate(arm['setup']):
        lines.append(f'{16+i} {s}')
    out = lines
    if arm['mode'] == 'if':
        out.append(f'20 if {arm["expr"]} then print "s9f";n;1 else print "s9f";n;0')
    elif arm['mode'] == 'err':
        out.append('20 '+arm['expr'])
    else:
        out += ['20 v='+arm['expr'], '30 if f=0 then print "s9f";n;v']
    out += ['40 print "s9d";n;1', '50 end', 'cls', 'run']
    assert all(len(x) < 80 and x == x.lower() for x in out), arm['id']
    return out


MARK = re.compile(r'^(s9f|s9e|s9d)((?: +\d+| *-\d+)+) *$', re.I)
TOKEN = re.compile(r' +\d+| *-\d+')


def extract(data):
    if len(data) != 3000:
        raise ValueError('画面写しの長さが不正')
    rows, other = [], 0
    for r in range(25):
        raw = data[r*120:r*120+80]
        if raw == b' '*80:
            continue
        m = MARK.fullmatch(raw.decode('ascii', errors='replace').rstrip(' '))
        if m:
            rows.append([m[1].lower(), *(int(t) for t in TOKEN.findall(m[2]))])
        else:
            other += 1
    return rows, other


def valid(rows):
    if len(rows) != 2 or rows[1] != ['s9d', 1, 1]:
        return False
    row = rows[0]
    if len(row) != 3 or row[1] != 1:
        return False
    if row[0] == 's9f':
        return -1 <= row[2] <= 255
    return row[0] == 's9e' and 1 <= row[2] <= 255


def run_arm(rom, official, arm, work, trap=True):
    args = [str(kw.FRONT), '--core', str(kw.find_core()), '--rom-dir', str(rom)]
    at = 700 if official else 100
    if official:
        args += ['--type-at', '300', '--type', '\n']
    for line in program(arm, trap):
        args += ['--type-at', str(at), '--type', line+'\n']
        at += (len(line)+1)*8+240+(15000 if line == 'run' else 0)
    screen = work/'screen.bin'
    args += ['--vram-dump', str(screen), '--vram-dump-at', str(at+200), '--frames', str(at+300)]
    try:
        proc = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              env=dict(os.environ, M6FH_LONG_TYPING='1'))
        if proc.returncode or b'untypable' in proc.stderr.lower() or '打てない'.encode() in proc.stderr:
            raise RuntimeError('測定器の実行または打鍵に失敗')
        return extract(screen.read_bytes())
    finally:
        screen.unlink(missing_ok=True)


def measure(rom, official, selected, work, trap=True):
    work.mkdir(parents=True, exist_ok=True)
    records = []
    with tempfile.TemporaryDirectory(prefix='measure-', dir=work) as temp:
        for arm in selected:
            obs, others, failed = [], [], []
            for _ in range(2):
                try:
                    rows, count = run_arm(rom, official, arm, Path(temp), trap)
                    obs.append(rows); others.append(count); failed.append(False)
                except Exception:
                    obs.append([]); others.append(0); failed.append(True)
            gate = not any(failed) and obs[0] == obs[1] and valid(obs[0])
            records.append(dict(arm=arm, obs=obs, others=others, gate=gate, failed=failed))
    return records


def write(path, header, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8', newline='') as stream:
        w = csv.writer(stream, delimiter='\t'); w.writerow(header); w.writerows(rows)


def emit(path, records, trap=True):
    calibration = all(r['gate'] and r['obs'][0] == prediction(r['arm'])
                      for r in records if r['arm']['id'].startswith('control-'))
    write(path, ['arm', 'repeat', 'typed_lines', 'print_values', 'other_line_counts',
                 'gate', 'C_GW', 'typing_or_capture_failed'],
          [(r['arm']['id'], i+1, json.dumps(program(r['arm'], trap), ensure_ascii=False),
            json.dumps(r['obs'][i]), r['others'][i],
            'pass' if calibration and r['gate'] else 'gate_failed',
            'gate_failed' if not calibration or not r['gate'] else
            'agree' if r['obs'][0] == prediction(r['arm']) else 'differ',
            int(r['failed'][i])) for r in records for i in range(2)])
    return calibration and all(r['gate'] for r in records)


def check(expected, measured):
    with expected.open(encoding='utf-8') as stream:
        wanted = list(csv.DictReader(stream, delimiter='\t'))
    with measured.open(encoding='utf-8') as stream:
        actual = list(csv.DictReader(stream, delimiter='\t'))
    targets = {}
    for r in wanted:
        values = json.loads(r.get('prediction') or r['print_values'])
        if r['arm'] in targets and targets[r['arm']] != values:
            return False
        targets[r['arm']] = values
    grouped = {}
    for r in actual:
        grouped.setdefault(r['arm'], []).append(r)
    if not targets or set(targets) != set(grouped):
        return False
    for aid, value in targets.items():
        runs = grouped[aid]
        if len(runs) != 2 or {r['repeat'] for r in runs} != {'1', '2'}:
            return False
        if any(r['gate'] != 'pass' or not valid(json.loads(r['print_values']))
               or json.loads(r['print_values']) != value for r in runs):
            return False
    return True


def screen_of(rows):
    data = bytearray(b' '*3000)
    for i, row in enumerate(rows):
        text = (row[0]+''.join(' '+str(x)+' ' for x in row[1:])).encode('ascii')
        data[i*120:i*120+len(text)] = text
    return bytes(data)


def selftest(work):
    work.mkdir(parents=True, exist_ok=True)
    # 手計算の固定値（符号なし・接頭辞は短い方が小さい・大小文字は別）
    assert cmp_gw('<', b'ab', b'abc') == -1 and cmp_gw('>', b'ab', b'abc') == 0
    assert cmp_gw('=', b'', b'') == -1 and cmp_gw('<', b'', b'a') == -1
    assert cmp_gw('>', bytes([200]), b'a') == -1 and cmp_gw('<', bytes([200]), b'a') == 0
    assert cmp_gw('>', b'a', b'A') == -1 and cmp_gw('<>', b'ac', b'ab') == -1
    assert cmp_gw('<', b'a', b'a\0') == -1 and cmp_gw('=', b'\0', b'') == 0
    assert cmp_gw('<=', b'ba', b'ab') == 0 and cmp_gw('>=', b'ba', b'ab') == -1
    selected = controls()+arms()
    ids = [a['id'] for a in selected]
    assert len(ids) == len(set(ids)), '腕IDの重複'
    byid = {a['id']: a for a in selected}
    assert byid['lit-prel-lt']['pred'] == -1 and byid['lit-hil-gt']['pred'] == -1
    assert byid['lit-case-eq']['pred'] == 0 and byid['lit-ee-eq']['pred'] == -1
    assert byid['lit-z-pre-gt']['pred'] == -1 and byid['lit-z-prer-lt']['pred'] == -1
    assert byid['if-01']['pred'] == 1 and byid['if-02']['pred'] == 0
    assert prediction(byid['type-01']) == [['s9e', 1, 13], ['s9d', 1, 1]]
    for arm in selected:
        good = prediction(arm)
        assert valid(good) and extract(screen_of(good))[0] == good
        program(arm)
    good = prediction(controls()[1]); data = screen_of(good)
    assert not valid(extract(data.replace(b's9f', b'z9f', 1))[0])
    bad = [['s9f', 1], ['s9d', 1, 1]]
    assert not valid(extract(screen_of(bad))[0])
    bad = [['s9f', 1, 5], ['s9d', 1, 1]]
    assert valid(bad) and extract(screen_of(bad))[0] != good
    neg = prediction(controls()[0])
    assert extract(screen_of(neg))[0] == neg and neg[0][2] == -1
    err = prediction(controls()[-1]); bad = [['s9e', 1, 6], ['s9d', 1, 1]]
    assert valid(bad) and extract(screen_of(bad))[0] != err
    with tempfile.TemporaryDirectory(prefix='replay-', dir=work) as temp:
        root = Path(temp)
        def replay(rom, official, arm, directory, trap=True):
            return prediction(arm), 2
        with patch(__name__+'.run_arm', replay):
            records = measure('', False, selected, root)
        assert emit(root/'good.tsv', records) and all(r['gate'] for r in records)
        calls = 0
        wrong = [['s9f', 1, 0], ['s9d', 1, 1]]
        def changed(rom, official, arm, directory, trap=True):
            nonlocal calls
            calls += 1
            return (wrong if calls == 2 else prediction(arm)), 2
        target = byid['lit-eq-eq']
        with patch(__name__+'.run_arm', changed):
            broken = measure('', False, [target], root)
        assert not broken[0]['gate']
        def error_changed(rom, official, arm, directory, trap=True):
            rows = prediction(arm)
            if arm['id'] == 'control-error':
                rows[0][2] = 6
            return rows, 0
        with patch(__name__+'.run_arm', error_changed):
            broken = measure('', False, selected, root)
        assert not emit(root/'broken.tsv', broken)
        with (root/'broken.tsv').open() as stream:
            assert all(r['gate'] == 'gate_failed' for r in csv.DictReader(stream, delimiter='\t'))
        def failed(rom, official, arm, directory, trap=True):
            raise RuntimeError('合成の打鍵失敗')
        with patch(__name__+'.run_arm', failed):
            broken = measure('', False, [selected[0]], root)
        assert not broken[0]['gate'] and all(broken[0]['failed'])
    print('OK 合成採取の陽性・陰性対照、GW規則の固定値')
    with tempfile.TemporaryDirectory(prefix='selftest-', dir=work) as temp:
        root = Path(temp); rom = root/'rom'
        proc = subprocess.run([os.sys.executable, str(kw.REPO/'src/build_main_rom.py'), str(rom),
                               '--work-dir', str(root/'asm')],
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        assert proc.returncode == 0, '自作ROMの一時ビルド失敗'
        # 自作ROMのERROR/ON ERRORは使わない。数値比較など既存機能の定数だけ。
        constants = controls()[:3]
        records = measure(rom, False, constants, root, trap=False)
        assert all(r['gate'] and r['obs'][0] == prediction(r['arm']) for r in records), \
            '自作ROMの定数採取関門失敗: '+json.dumps([(r['arm']['id'], r['gate'], r['obs'], r['others']) for r in records])
        observed = root/'measured.tsv'; expected = root/'expected.tsv'
        assert emit(observed, records, trap=False)
        write(expected, ['arm', 'prediction'], [(a['id'], json.dumps(prediction(a))) for a in constants])
        assert check(expected, observed)
        wrong = prediction(constants[0]); wrong[0][-1] = 0
        write(expected, ['arm', 'prediction'],
              [(a['id'], json.dumps(wrong if i == 0 else prediction(a))) for i, a in enumerate(constants)])
        assert not check(expected, observed)
        records[0]['obs'] = [wrong, wrong]
        assert not emit(observed, records, trap=False)
        with observed.open() as stream:
            assert all(r['gate'] == 'gate_failed' for r in csv.DictReader(stream, delimiter='\t'))
    print('OK 自作ROM一時ビルド、定数3腕×2走、期待値改変の陰性対照')
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('predict'); p.add_argument('--out', type=Path, required=True)
    m = sub.add_parser('measure'); m.add_argument('--rom-dir', required=True)
    m.add_argument('--out', type=Path, required=True); m.add_argument('--official', action='store_true')
    m.add_argument('--work-dir', type=Path, default=WORK)
    c = sub.add_parser('check'); c.add_argument('--expected', type=Path, required=True)
    c.add_argument('--measured', type=Path, required=True)
    s = sub.add_parser('selftest'); s.add_argument('--work-dir', type=Path, default=WORK)
    args = parser.parse_args()
    if args.command == 'selftest':
        return selftest(args.work_dir)
    if args.command == 'check':
        ok = check(args.expected, args.measured); print('照合一致' if ok else '照合不一致'); return 0 if ok else 1
    selected = controls()+arms()
    if args.command == 'predict':
        write(args.out, ['arm', 'candidate', 'prediction', 'typed_lines'],
              [(a['id'], 'C_GW', json.dumps(prediction(a)), json.dumps(program(a), ensure_ascii=False)) for a in selected])
        return 0
    records = measure(args.rom_dir, args.official, selected, args.work_dir)
    passed = emit(args.out, records)
    print(f'記録完了: {len(records)}腕×2走、全体関門 '+('通過' if passed else '失敗'))
    return 0 if passed else 1


if __name__ == '__main__':
    raise SystemExit(main())
