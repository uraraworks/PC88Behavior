#!/usr/bin/env python3
"""l4-s9d: CLEAR受理境界とFREの採取。本文・ROMバイト列は出力しない。"""
import argparse
import csv
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
from unittest.mock import patch
import l4_peekpoke_measure as previous

common = previous.common
kw = previous.kw
WORK = kw.REPO.parent / 'tmp/l4s9d-work'
DONE = ['s9dd', 1, 1]
MARK = re.compile(r'^(s9d[aved])((?: +\d+| *-\d+)+) *$')


def controls():
    return [dict(id='control-value', kind='constant', expr='73', expected=73),
            dict(id='control-error', kind='error', expected=5)]


def arms():
    out = []
    for a in [*range(0x8000, 0x10000, 0x400), 0xffff]:
        arm = dict(id=f'limit-{a:04x}', kind='limit', limit=a)
        out += [dict(arm, id='default-'+arm['id'], kind='default'), arm]
    for size in (256, 1024):
        arm = dict(id=f'stack-{size}', kind='limit', limit=49151, stack=size)
        out += [dict(arm, id='default-'+arm['id'], kind='default'), arm]
    out.append(dict(id='default-empty', kind='default', limit=32768, expr='fre("")'))
    return out


def known_arms():
    """追補1の関門。1回目で測定済みの値（0xE400→23270、0xE800→ERR 5、第3引数256→14309）。"""
    return [dict(id='a1-known-e400', kind='known', limit=0xe400,
                 rows=[['s9da', 1, 1], ['s9dv', 2, 23270], DONE.copy()]),
            dict(id='a1-known-e800', kind='known', limit=0xe800,
                 rows=[['s9de', 1, 5], DONE.copy()]),
            dict(id='a1-known-stack-256', kind='known', limit=49151, stack=256,
                 rows=[['s9da', 1, 1], ['s9dv', 2, 14309], DONE.copy()])]


def addendum1_arms():
    """追補1: 上限の受理境界の二分詰め＋第3引数とGOSUB・FORの深さ。予測は立てない（観測）。"""
    out = []
    for a in (0xe500, 0xe580, 0xe5c0, 0xe5e0, 0xe5f0, 0xe5f8, 0xe5fc, 0xe5fd,
              0xe5fe, 0xe5ff, 0xe600, 0xe601, 0xe700):
        out.append(dict(id=f'a1-limit-{a:04x}', kind='limit', limit=a))
    out.append(dict(id='a1-default-limit-e5fd', kind='default', limit=0xe5fd))
    for sub in ('gosub', 'for'):
        for n in (64, 128, 256, 512, 1024, None):
            out.append(dict(id=f'a1-{sub}-'+('default' if n is None else str(n)),
                            kind='depth', sub=sub, stack=n))
    return out


def selection(addendum):
    return controls()+(known_arms()+addendum1_arms() if addendum == 1 else arms())


DEPTH_CAP = 3000


def for_levels(n):
    return 72 if n is None else n//8+8


def prediction(a):
    if a['kind'] == 'known': return [r.copy() for r in a['rows']]
    if a['kind'] == 'constant': return [['s9dv', 1, a['expected']], DONE.copy()]
    if a['kind'] == 'error': return [['s9de', 1, a['expected']], DONE.copy()]
    return None  # 番地・FRE値・境界ERR番号は予測しない。


def depth_program(a):
    n = a['stack']
    lines = ['new', '5 on error goto 950',
             '20 clear ,49152'+('' if n is None else f',{n}'),
             '30 on error goto 950', '40 print "s9da";1;1']
    if a['sub'] == 'gosub':
        # 深さdは毎段グローバル変数へ。溢れたらONERRORへ飛ぶ。
        lines += ['50 d=0:gosub 100', '60 print "s9dv";2;d', '70 goto 800',
                  f'100 d=d+1:if d<{DEPTH_CAP} then gosub 100', '110 return']
        var = 'd'
    else:
        k = for_levels(n)
        lines.append('50 l=0')
        segs = [f'for {chr(97+i//10)}{i%10}=0 to 0:l={i+1}' for i in range(k)]
        for j in range(0, k, 3):
            lines.append(f'{100+10*(j//3)} '+':'.join(segs[j:j+3]))
        lines.append('600 print "s9dv";2;l')
        var = 'l'
    lines += ['800 print "s9dd";1;1', '810 end',
              '950 if erl=20 then print "s9de";1;err:resume 800',
              f'960 print "s9de";2;err:print "s9dv";2;{var}:resume 800',
              'cls', 'run']
    assert all(len(s) < 80 and s == s.lower() and '@' not in s for s in lines)
    assert not any(re.search(r'\b(peek|poke|usr|call)\b', s) for s in lines)
    return lines


def program(a, trap=True):
    k = a['kind']
    if k == 'depth': return depth_program(a)
    lines = ['new']
    if trap: lines.append('5 on error goto 950')
    if k in ('limit', 'default', 'known'):
        # 既定腕も同じCLEAR行を保持し、分岐先だけを変える。
        lines += ['10 goto '+('30' if k == 'default' else '20'),
                  f'20 clear ,{a["limit"]}'+(f',{a["stack"]}' if 'stack' in a else '')]
        if trap: lines.append('30 on error goto 950')
        lines += ['40 print "s9da";1;1', '50 print "s9dv";2;'+a.get('expr', 'fre(0)')]
    else:
        if a.get('clear'): lines.append('10 clear ,49151')
        if trap: lines.append('15 on error goto 950')
        lines.append('50 '+('error 5' if k == 'error' else 'print "s9dv";1;'+a['expr']))
    lines += ['800 print "s9dd";1;1', '810 end']
    if trap:
        if k in ('limit', 'default', 'known'):
            lines += ['950 if erl=20 then print "s9de";1;err:resume 800',
                      '960 print "s9de";2;err:resume 800']
        else: lines += ['950 print "s9de";1;err:resume 800']
    lines += ['cls', 'run']
    assert all(len(s) < 80 and s == s.lower() and '@' not in s for s in lines)
    assert not any(re.search(r'\b(peek|poke|usr|call)\b', s) for s in lines)
    return lines


def extract(data):
    if len(data) != 3000: raise ValueError('画面写しの長さが不正')
    rows, other = [], 0
    for i in range(25):
        raw = data[i*120:i*120+80]
        if raw == b' '*80: continue
        m = MARK.fullmatch(raw.decode('ascii', errors='replace').rstrip(' '))
        if not m: other += 1; continue
        row = [m[1], *(int(x) for x in common.TOKEN.findall(m[2]))]
        # 自分のPRINTだけを採る。未知の印・本文は件数だけ。
        if len(row) != 3 or row[1] not in (1, 2): other += 1; continue
        if row[0] in ('s9da', 's9dd') and row != [row[0], 1, 1]:
            other += 1; continue
        if row[0] == 's9de' and not 1 <= row[2] <= 255: other += 1; continue
        if row[0] == 's9dv' and not 0 <= row[2] <= 65535: other += 1; continue
        rows.append(row)
    return rows, other


def valid(rows, a):
    if not rows or rows[-1] != DONE: return False
    if a['kind'] == 'known': return rows == prediction(a)
    if a['kind'] == 'depth':
        body = rows[:-1]
        if len(body) == 1 and body[0][:2] == ['s9de', 1]: return True  # CLEAR自体が誤り
        if not body or body[0] != ['s9da', 1, 1]: return False
        if len(body) == 2: return body[1][:2] == ['s9dv', 2]  # 上限到達で誤りなし
        return (len(body) == 3 and body[1][:2] == ['s9de', 2]
                and body[2][:2] == ['s9dv', 2])
    if prediction(a) is not None:
        return (len(rows) == 2 and rows[0][0] in ('s9dv', 's9de')
                and rows[0][1] == 1)
    if len(rows) == 2:
        return a['kind'] == 'limit' and rows[0][0:2] == ['s9de', 1]
    return (len(rows) == 3 and rows[0] == ['s9da', 1, 1]
            and rows[1][0] in ('s9dv', 's9de') and rows[1][1] == 2)


def depth_result(rows):
    """深さ測定腕の採取行から (深さ, 誤り番号, 上限到達か) を返す。CLEAR誤りは None。"""
    body = rows[:-1]
    if len(body) < 2 or body[0] != ['s9da', 1, 1]: return None
    if len(body) == 2: return body[1][2], None, True
    return body[2][2], body[1][2], False


def snapshots(screen):
    return [p for p in screen.parent.glob(screen.stem+'.f*'+screen.suffix)
            if re.fullmatch(re.escape(screen.stem)+r'\.f\d{6}'+re.escape(screen.suffix), p.name)]


def run_arm(rom, official, a, work, trap=True):
    args = [str(kw.FRONT), '--core', str(kw.find_core()), '--rom-dir', str(rom)]
    at = 700 if official else 100
    if official: args += ['--type-at', '300', '--type', '\n']
    for line in program(a, trap):
        args += ['--type-at', str(at), '--type', line+'\n']
        at += (len(line)+1)*8+240+(15000 if line == 'run' else 0)
    screen = work/'screen.bin'; frame = at+200
    args += ['--vram-dump', str(screen), '--vram-dump-at', str(frame), '--frames', str(at+300)]
    try:
        p = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                           env=dict(os.environ, M6FH_LONG_TYPING='1'))
        if p.returncode or b'untypable' in p.stderr.lower() or '打てない'.encode() in p.stderr:
            raise RuntimeError('打鍵または採取に失敗')
        files = ([screen] if screen.exists() else [])+snapshots(screen)
        target = screen if screen.exists() else work/f'screen.f{frame:06d}.bin'
        if target not in files: raise RuntimeError('指定フレームの採取がない')
        return extract(target.read_bytes())
    finally:
        for p in [screen, *snapshots(screen)]: p.unlink(missing_ok=True)


def measure(rom, official, selected, work, trap=True):
    work.mkdir(parents=True, exist_ok=True); records = []; calibration = True
    with tempfile.TemporaryDirectory(prefix='measure-', dir=work) as t:
        for a in selected:
            r = dict(arm=a, obs=[], others=[], failed=[], skipped=not calibration)
            for _ in range(2):
                if not calibration:
                    rows, count, failed = [], 0, False
                else:
                    try:
                        rows, count = run_arm(rom, official, a, Path(t), trap)
                        rows, _ = extract(common.screen_of(rows)); failed = False
                    except Exception: rows, count, failed = [], 0, True
                r['obs'].append(rows); r['others'].append(count); r['failed'].append(failed)
            r['gate'] = not r['skipped'] and not any(r['failed']) and r['obs'][0] == r['obs'][1] and valid(r['obs'][0], a)
            if prediction(a) is not None:
                calibration &= r['gate'] and r['obs'][0] == prediction(a)
            records.append(r)
    return records


def emit(path, records, trap=True):
    known = [r for r in records if prediction(r['arm']) is not None]
    required = {a['id'] for a in controls()}
    own = bool(records) and all(r['arm'].get('own') for r in records)
    calibration = bool(known) and (own or required <= {r['arm']['id'] for r in known}) and all(
        r['gate'] and not r['skipped'] and not any(r['failed'])
        and all(rows == prediction(r['arm']) for rows in r['obs']) for r in known)
    out = []
    for r in records:
        for i in range(2):
            rows, _ = extract(common.screen_of(r['obs'][i]))
            gate = (calibration and r['gate'] and not r['skipped'] and not any(r['failed'])
                    and r['obs'][0] == r['obs'][1] and valid(rows, r['arm']))
            pred = prediction(r['arm'])
            state = 'gate_failed' if not gate else 'observe' if pred is None else 'agree' if rows == pred else 'differ'
            out.append([r['arm']['id'], i+1, json.dumps(program(r['arm'], trap)), json.dumps(rows),
                        r['others'][i], 'pass' if gate else 'gate_failed', state,
                        int(r['failed'][i]), int(r['skipped'])])
    common.write(path, ['arm', 'repeat', 'typed_lines', 'print_values', 'other_line_counts',
                       'gate', 'P_MANUAL', 'typing_or_capture_failed', 'skipped'], out)
    return calibration and all(r['gate'] and not r['skipped'] and not any(r['failed'])
                                   and r['obs'][0] == r['obs'][1] for r in records)


def check(expected, measured):
    with expected.open() as f: wanted = list(csv.DictReader(f, delimiter='\t'))
    with measured.open() as f: actual = list(csv.DictReader(f, delimiter='\t'))
    if not wanted or len({r['arm'] for r in wanted}) != len(wanted): return False
    targets = {r['arm']: json.loads(r['prediction']) for r in wanted}
    if any(v is None for v in targets.values()): return False  # 予測なしを合格にしない。
    if set(targets) != {r['arm'] for r in actual}: return False
    for aid, value in targets.items():
        runs = [r for r in actual if r['arm'] == aid]
        if len(runs) != 2 or {r['repeat'] for r in runs} != {'1', '2'}: return False
        if any(r['gate'] != 'pass' or r['skipped'] != '0' or r['typing_or_capture_failed'] != '0'
               or json.loads(r['print_values']) != value for r in runs): return False
    return True


def addendum_selftest(work):
    sel = selection(1); obs = addendum1_arms()
    assert len(obs) == 26 and len({a['id'] for a in sel}) == len(sel)
    assert not any(a['id'] in {b['id'] for b in arms()} for a in obs)  # 既存の腕と混ざらない
    def sample(a):
        if prediction(a) is not None: return prediction(a)
        if a['kind'] != 'depth': return [['s9da', 1, 1], ['s9dv', 2, 23270], DONE.copy()]
        return [['s9da', 1, 1], ['s9de', 2, 7], ['s9dv', 2, 40], DONE.copy()]
    for a in sel:
        program(a)
        rows = sample(a)
        assert extract(common.screen_of(rows))[0] == rows and valid(rows, a), a['id']
        assert not valid(rows[:-1], a), a['id']
        if a['kind'] == 'depth':
            assert depth_result(rows) == (40, 7, False)
            assert valid([['s9da', 1, 1], ['s9dv', 2, DEPTH_CAP], DONE.copy()], a)  # 上限到達
            assert depth_result([['s9da', 1, 1], ['s9dv', 2, DEPTH_CAP], DONE]) == (DEPTH_CAP, None, True)
            assert valid([['s9de', 1, 5], DONE.copy()], a) and depth_result([['s9de', 1, 5], DONE]) is None
            # 陰性: 添字違い・順序違い・印欠落
            assert not valid([['s9da', 1, 1], ['s9de', 1, 7], ['s9dv', 2, 40], DONE], a)
            assert not valid([['s9da', 1, 1], ['s9dv', 2, 40], ['s9de', 2, 7], DONE], a)
            assert not valid([['s9de', 2, 7], ['s9dv', 2, 40], DONE], a)
            assert not valid([['s9da', 1, 1], ['s9de', 2, 7], DONE], a)
    # 深さ腕の打鍵: 第3引数の有無、FORの段数、直接モードの語、80字未満
    g = {a['id']: program(a) for a in obs if a['kind'] == 'depth'}
    assert '20 clear ,49152' in g['a1-gosub-default'] and '20 clear ,49152,128' in g['a1-gosub-128']
    assert sum(l.count('for ') for l in g['a1-for-1024']) == for_levels(1024)
    assert sum(l.count('for ') for l in g['a1-for-default']) == 72
    assert not any(re.fullmatch(r'\d.*', l) is None and l not in ('new', 'cls', 'run') for l in g['a1-for-256'])
    # 既知腕の打鍵行は、1回目の対応する腕と完全一致（CLEARを実行する形）。
    first = {a['id']: a for a in arms()}
    for kid, rid in (('a1-known-e400', 'limit-e400'), ('a1-known-e800', 'limit-e800'),
                     ('a1-known-stack-256', 'stack-256')):
        k = [a for a in known_arms() if a['id'] == kid][0]
        assert program(k) == program(first[rid]) and '10 goto 20' in program(k), kid
    ref = WORK/'official_round1.tsv'
    if ref.exists():  # 期待値は1回目の公式観測そのもの（あれば照合）
        got = {(r['arm']): json.loads(r['print_values']) for r in csv.DictReader(ref.open(), delimiter='\t')}
        for kid, rid in (('a1-known-e400', 'limit-e400'), ('a1-known-e800', 'limit-e800'),
                         ('a1-known-stack-256', 'stack-256')):
            assert prediction([a for a in known_arms() if a['id'] == kid][0]) == got[rid], kid
    # 関門: 既知腕（0xE400）の値違いで全体gate_failed、後続は停止
    calls = []
    def drift(rom, official, a, work, trap=True):
        calls.append(a['id'])
        if a['id'] == 'a1-known-e400': return [['s9da', 1, 1], ['s9dv', 2, 23271], DONE.copy()], 0
        return sample(a), 0
    with tempfile.TemporaryDirectory(prefix='addendum-', dir=work) as t:
        root = Path(t)
        with patch(__name__+'.run_arm', lambda rom, official, a, work, trap=True: (sample(a), 0)):
            records = measure('', False, sel, root)
        assert emit(root/'good.tsv', records)
        with patch(__name__+'.run_arm', drift): records = measure('', False, sel, root)
        assert not emit(root/'drift.tsv', records)
        assert 'a1-limit-e500' not in calls and len(calls) == 6  # 対照2腕×2走＋既知e400の2走で停止
        rows = list(csv.DictReader((root/'drift.tsv').open(), delimiter='\t'))
        assert all(r['gate'] == 'gate_failed' for r in rows) and len(rows) == 2*len(sel)
    print('OK 追補1: 腕26＋関門5の合成陽性・陰性、深さ腕の添字・順序・上限到達、既知値ずれで停止')


def selftest(work):
    work.mkdir(parents=True, exist_ok=True)
    selected = controls()+arms()
    for a in selected: program(a)
    def sample(a):
        return prediction(a) or [['s9da', 1, 1], ['s9dv', 2, 12345], DONE.copy()]
    for a in selected:
        rows = sample(a)
        assert extract(common.screen_of(rows))[0] == rows and valid(rows, a)
        assert not valid(extract(common.screen_of(rows).replace(b's9dd', b'z9dd'))[0], a)
    assert not valid(extract(common.screen_of([['s9da', 1, 1], ['s9dv', 1, 73], DONE]))[0], arms()[0])
    with tempfile.TemporaryDirectory(prefix='synthetic-', dir=work) as t:
        root = Path(t)
        with patch(__name__+'.run_arm', lambda rom, official, a, work, trap=True: (sample(a), 0)):
            records = measure('', False, selected, root)
        assert emit(root/'good.tsv', records)
        calls = 0
        def bad(*args):
            nonlocal calls
            calls += 1
            return [['s9dv', 1, 74], DONE], 0
        with patch(__name__+'.run_arm', bad): records = measure('', False, selected, root)
        assert calls == 2 and not emit(root/'bad.tsv', records)
        assert all(r['gate'] == 'gate_failed' for r in csv.DictReader((root/'bad.tsv').open(), delimiter='\t'))
        # CLEAR失敗とCLEAR成功後FRE失敗を区別する。
        assert valid([['s9de', 1, 5], DONE], arms()[1])
        assert valid([['s9da', 1, 1], ['s9de', 2, 13], DONE], arms()[0])
        for name in ('screen.bin', 'screen.f000123.bin', 'screen.f000124.bin'):
            (root/name).write_bytes(b' ' * 3000)
        assert len(snapshots(root/'screen.bin')) == 2
    print('OK 合成取り出しの陽性・陰性、CLEAR/FRE誤りの区別、関門停止')
    addendum_selftest(work)
    with tempfile.TemporaryDirectory(prefix='own-rom-', dir=work) as t:
        root = Path(t); rom = root/'rom'
        p = subprocess.run([os.sys.executable, str(kw.REPO/'src/build_main_rom.py'), str(rom),
                            '--work-dir', str(root/'asm')], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        assert p.returncode == 0, '自作ROMの一時ビルド失敗'
        own = [dict(id='own-value', kind='constant', expr='73', expected=73, own=True),
               dict(id='own-clear', kind='constant', expr='73', expected=73, clear=True, own=True),
               dict(id='own-len', kind='constant', expr='len("ab")', expected=2, own=True)]
        records = measure(rom, False, own, root, trap=False)
        assert emit(root/'own.tsv', records, trap=False), '自作ROMの定数対照不一致'
        common.write(root/'expected.tsv', ['arm', 'prediction'], [(a['id'], json.dumps(prediction(a))) for a in own])
        assert check(root/'expected.tsv', root/'own.tsv')
        records[0]['obs'][1] = [['s9dv', 1, 74], DONE]
        emit(root/'wrong.tsv', records, trap=False)
        assert not check(root/'expected.tsv', root/'wrong.tsv')
        records[0]['skipped'] = True
        assert not emit(root/'skip.tsv', records, trap=False)
        assert not check(root/'expected.tsv', root/'skip.tsv')
    print('OK 自作ROM定数3腕×2走（CLEAR受理を含む）、不一致・SKIP拒否')
    return 0


def main():
    p = argparse.ArgumentParser(description=__doc__); sub = p.add_subparsers(dest='command', required=True)
    s = sub.add_parser('selftest'); s.add_argument('--work-dir', type=Path, default=WORK)
    c = sub.add_parser('check'); c.add_argument('--expected', type=Path, required=True); c.add_argument('--measured', type=Path, required=True)
    q = sub.add_parser('predict'); q.add_argument('--out', type=Path, required=True); q.add_argument('--addendum', type=int, choices=[1])
    m = sub.add_parser('measure'); m.add_argument('--rom-dir', required=True); m.add_argument('--official', action='store_true'); m.add_argument('--work-dir', type=Path, default=WORK); m.add_argument('--out', type=Path, required=True); m.add_argument('--addendum', type=int, choices=[1])
    args = p.parse_args()
    if args.command == 'selftest': return selftest(args.work_dir)
    if args.command == 'check':
        ok = check(args.expected, args.measured); print('照合一致' if ok else '照合不一致'); return 0 if ok else 1
    selected = selection(args.addendum)
    if args.command == 'predict':
        common.write(args.out, ['arm', 'candidate', 'prediction', 'typed_lines'],
                     [(a['id'], 'P_MANUAL', json.dumps(prediction(a)), json.dumps(program(a))) for a in selected]); return 0
    if args.official:
        ref = os.environ.get('PC88_REF_ROM_DIR')
        if not ref or Path(ref).resolve() != Path(args.rom_dir).resolve(): p.error('公式ROMはPC88_REF_ROM_DIR経由で指定してください')
    records = measure(args.rom_dir, args.official, selected, args.work_dir)
    ok = emit(args.out, records)
    print(f'記録完了: {len(records)}腕×2走、採取関門'+('通過' if ok else '失敗'))
    return 0 if ok else 1

if __name__ == '__main__': raise SystemExit(main())
