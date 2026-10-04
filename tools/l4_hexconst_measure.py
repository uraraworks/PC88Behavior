#!/usr/bin/env python3
"""l4-s9f: &H/&O定数の予測・数値PRINTとERRの採取（画面本文を出さない）。"""
import argparse
import csv
import json
import math
import os
from pathlib import Path
import re
import subprocess
import tempfile
from unittest.mock import patch
import l4_listkw_measure as kw

WORK = kw.REPO.parent / 'tmp/l4s9f-work'


def read_gw(text):
    """公開GWのOCTCNSの散文規則。返値は符号付き値、未消費部分、ERR。"""
    assert text.startswith('&')
    rest = text[1:].lstrip(' ')
    hexa = rest[:1].lower() == 'h'
    if hexa or rest[:1].lower() == 'o':
        rest = rest[1:]
    value = digits = 0
    while rest:
        if not hexa:
            rest = rest.lstrip(' ')
            if not rest:
                break
        ch = rest[0].lower()
        alphabet = '0123456789abcdef' if hexa else '01234567'
        if ch not in alphabet:
            if not hexa and ch in '89':
                return None, rest, 2
            break
        digit = alphabet.index(ch)
        digits += 1
        if (hexa and digits == 5) or (not hexa and value * 8 + digit > 65535):
            return None, rest, 6
        value = value * (16 if hexa else 8) + digit
        rest = rest[1:]
    return value if value < 32768 else value - 65536, rest, None


CASES = [
    ('h0', '&h0'), ('h10', '&h10'), ('hff', '&hff'), ('h7fff', '&h7fff'),
    ('h8000', '&h8000'), ('hffff', '&hffff'), ('h10000', '&h10000'),
    ('h1ffff', '&h1ffff'), ('o17', '&o17'), ('o177777', '&o177777'),
    ('o200000', '&o200000'), ('short17', '&17'),
    ('add1', '&hffff+1'), ('intvar', '&hffff'), ('divide', '&h10/3'),
    ('negative', '-&h1'), ('empty', '&h'), ('invalid', '&hg'),
    ('hexspace', '&h 10'), ('prefixspace', '& h10'),
    ('add0', '&h8000+0'), ('absolute', 'abs(&h8000)'),
    ('octspace', '&o1 7'), ('octinvalid', '&o8'),
    ('suffix-int', '&h10%'), ('suffix-single', '&h10!'), ('suffix-double', '&h10#'),
    ('sign-inside', '&h-1'), ('leading-zero', '&h00010'),
]


def outcome(a):
    expr = a['expr']
    if a.get('error'):
        return ('err', 5), False
    if expr == '&hffff+1':
        return 0, False
    if expr == '&h10/3':
        return 5.33333, False  # 単精度PRINTの有効6桁
    if expr == '-&h1':
        return -1, False
    if expr == '&h-1':
        return -1, False  # 桁なしの0で止まり、式の減算になる
    if expr == '&h8000+0':
        return -32768, False
    if expr == 'abs(&h8000)':
        return 32768, False
    if expr.startswith('&'):
        value, tail, err = read_gw(expr)
        return (('err', err), True) if err else (('err', 2), False) if tail.strip() else (value, False)
    return a['value'], False


def arms():
    return [dict(id=mode+'-'+aid, expr=expr, mode=mode, integer=(aid == 'intvar'))
            for aid, expr in CASES for mode in ('direct', 'program')]


def controls():
    base = [('zero', '0', 0), ('positive', '16', 16),
            ('negative', '-32768', -32768), ('fraction', '5.33333', 5.33333)]
    out = [dict(id='control-'+mode+'-'+aid, mode=mode, expr=expr, value=value)
           for aid, expr, value in base for mode in ('direct', 'program')]
    out += [dict(id='control-'+mode+'-error', mode=mode, expr='error 5', error=True)
            for mode in ('direct', 'program')]
    return out


def result_rows(value):
    first = ['s9ge', 1, value[1]] if isinstance(value, tuple) else ['s9g', 1, value]
    return [first, ['s9gd', 1, 1]]


def prediction(a):
    value, lexical = outcome(a)
    rejected = a['mode'] == 'program' and lexical
    return dict(entry_errors=[['s9ge', 1, value[1]]] if rejected else [],
                listed_lines=0 if rejected else 1 if a['mode'] == 'program' else None,
                result=[['s9gd', 1, 1]] if rejected else result_rows(value))


def prediction_untrapped(a):
    p = prediction(a)
    if p['listed_lines'] == 0:
        p['entry_errors'] = []
    return p


def program(a, trap=True):
    """各要素は打鍵行か採取段階。LISTは番号だけ数え、本文は記録しない。"""
    out = ['new']
    if trap:
        out += ['940 print "s9ge";1;err:f=1:resume 960', '960 end',
                '950 print "s9ge";1;err:f=1:resume next']
    action = a['expr'] if a.get('error') else ('a%=' if a.get('integer') else 'v=')+a['expr']
    variable = 'a%' if a.get('integer') else 'v'
    printing = f'if f=0 then print "s9g";1;{variable}'
    if a['mode'] == 'program':
        out += ['10 f=0']
        if trap:
            out += ['15 on error goto 950']
        out += ['40 print "s9gd";1;1', '50 end', 'f=0']
        if trap:
            out += ['on error goto 940']
        out += ['cls', '20 '+action+(':'+printing if not a.get('error') else ''),
                ('capture', 'entry'), 'cls', 'list', ('capture', 'list'), 'cls', 'run',
                ('capture', 'result')]
    else:
        out += ['f=0']
        if trap:
            out += ['on error goto 940']
        out += ['cls', action]
        if not a.get('error'):
            out += [printing]
        out += ['print "s9gd";1;1', ('capture', 'result')]
    assert all(not isinstance(x, str) or (len(x) < 80 and x == x.lower()
               and '@' not in x and (a['mode'] != 'direct' or not x[0].isdigit() or x.startswith(('940 ', '950 ', '960 ')))) for x in out)
    return out


NUMBER = r'(?: +(?:\d+(?:\.\d*)?|\.\d+)(?:[ED][+-]?\d+)?| *-(?:\d+(?:\.\d*)?|\.\d+)(?:[ED][+-]?\d+)?)'
MARK = re.compile(r'^(s9ge|s9gd|s9g)('+NUMBER+r')('+NUMBER+r') *$', re.I)


def screen_rows(data):
    if len(data) != 3000:
        raise ValueError('画面写しの長さが不正')
    return [data[r*120:r*120+80].rstrip(b' ') for r in range(25)]


def extract(data):
    rows, other = [], 0
    for raw in screen_rows(data):
        if not raw:
            continue
        text = raw.decode('ascii', errors='replace')
        m = MARK.fullmatch(text)
        if m:
            nums = [float(t.upper().replace('D', 'E')) for t in m.groups()[1:]]
            rows.append([m[1].lower(), *(int(n) if math.isfinite(n) and n.is_integer() else n for n in nums)])
        elif text.lower().startswith(('s9g', 's9ge', 's9gd')):
            rows.append(['invalid'])  # 印の一部破損を他の画面行へ逃がさない
        else:
            other += 1
    return rows, other


def list_count(data, trap=True):
    numbers, other = [], 0
    for raw in screen_rows(data):
        if not raw:
            continue
        m = re.match(rb'^ *(\d+) +', raw)
        if m and all(32 <= b <= 126 for b in raw):
            numbers.append(int(m[1]))
        elif re.match(rb'^ *\d', raw):
            return -1, other  # 予期しない番号・文字
        else:
            other += 1
    scaffold = {10, 40, 50} | ({15, 940, 950, 960} if trap else set())
    if (len(numbers) != len(set(numbers)) or set(numbers) - scaffold - {20}
            or not scaffold <= set(numbers)):
        return -1, other
    return numbers.count(20), other


def valid(obs, a):
    entry, result, count = obs['entry_errors'], obs['result'], obs['listed_lines']
    err = lambda r: len(r) == 3 and r[:2] == ['s9ge', 1] and isinstance(r[2], int) and 1 <= r[2] <= 255
    if a['mode'] == 'direct':
        if entry or count is not None:
            return False
    elif count not in (0, 1) or len(entry) > 1 or any(not err(r) for r in entry):
        return False
    if a['mode'] == 'program' and count == 0:
        return result == [['s9gd', 1, 1]]
    if entry or len(result) != 2 or result[1] != ['s9gd', 1, 1]:
        return False
    r = result[0]
    return err(r) or (len(r) == 3 and r[:2] == ['s9g', 1]
                      and isinstance(r[2], (int, float)) and math.isfinite(r[2]))


def dump_path(path, frame, multiple):
    return path.with_name(path.stem+f'.f{frame:06d}'+path.suffix) if multiple else path


def run_arm(rom, official, a, work, trap=True):
    args = [str(kw.FRONT), '--core', str(kw.find_core()), '--rom-dir', str(rom)]
    at = 700 if official else 100
    if official:
        args += ['--type-at', '300', '--type', '\n']
    captures = []
    for step in program(a, trap):
        if isinstance(step, str):
            args += ['--type-at', str(at), '--type', step+'\n']
            at += (len(step)+1)*8+240+(15000 if step == 'run' else 0)
        else:
            path = work/(step[1]+'.bin')
            frame = at+200
            args += ['--vram-dump', str(path), '--vram-dump-at', str(frame)]
            captures.append((step[1], path, frame))
            at = frame+100
    args += ['--frames', str(at+100)]
    paths = [(stage, dump_path(path, frame, len(captures) > 1)) for stage, path, frame in captures]
    try:
        proc = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              env=dict(os.environ, M6FH_LONG_TYPING='1'))
        if proc.returncode or b'untypable' in proc.stderr.lower() or '打てない'.encode() in proc.stderr:
            raise RuntimeError('測定器の実行または打鍵に失敗')
        obs = dict(entry_errors=[], listed_lines=None, result=[])
        others = {}
        for stage, path in paths:
            if stage == 'list':
                obs['listed_lines'], others[stage] = list_count(path.read_bytes(), trap)
            else:
                rows, others[stage] = extract(path.read_bytes())
                obs['entry_errors' if stage == 'entry' else 'result'] = rows
        return obs, others
    finally:
        for _, path in paths:
            path.unlink(missing_ok=True)
        for _, path, _ in captures:
            path.unlink(missing_ok=True)


def measure(rom, official, selected, work, trap=True):
    work.mkdir(parents=True, exist_ok=True)
    records = []
    with tempfile.TemporaryDirectory(prefix='measure-', dir=work) as temp:
        for a in selected:
            obs, others, failed = [], [], []
            for _ in range(2):
                try:
                    value, count = run_arm(rom, official, a, Path(temp), trap)
                    obs.append(value); others.append(count); failed.append(False)
                except Exception:
                    obs.append({}); others.append({}); failed.append(True)
            gate = not any(failed) and obs[0] == obs[1] and valid(obs[0], a)
            records.append(dict(arm=a, obs=obs, others=others, failed=failed, gate=gate))
    return records


def write(path, header, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8', newline='') as stream:
        writer = csv.writer(stream, delimiter='\t'); writer.writerow(header); writer.writerows(rows)


def emit(path, records, trap=True):
    cs = [r for r in records if r['arm']['id'].startswith('control-')]
    required = [a for a in controls() if trap or not a.get('error')]
    calibration = (len(cs) == len(required)
                   and {r['arm']['id'] for r in cs} == {a['id'] for a in required}
                   and all(r['gate'] and r['obs'][0] == prediction(r['arm']) for r in cs))
    write(path, ['arm', 'repeat', 'typed_lines', 'observation', 'other_line_counts',
                 'gate', 'H_GW', 'H_GW_U', 'typing_or_capture_failed'],
          [(r['arm']['id'], i+1, json.dumps(program(r['arm'], trap), ensure_ascii=False),
            json.dumps(r['obs'][i]), json.dumps(r['others'][i]),
            'pass' if calibration and r['gate'] else 'gate_failed',
            'gate_failed' if not calibration or not r['gate'] else
            'agree' if r['obs'][0] == prediction(r['arm']) else 'differ',
            'gate_failed' if not calibration or not r['gate'] else
            'agree' if r['obs'][0] == prediction_untrapped(r['arm']) else 'differ',
            int(r['failed'][i]))
           for r in records for i in range(2)])
    return calibration and all(r['gate'] for r in records)


def check(expected, measured):
    try:
        with expected.open(encoding='utf-8') as s:
            wanted = list(csv.DictReader(s, delimiter='\t'))
        with measured.open(encoding='utf-8') as s:
            actual = list(csv.DictReader(s, delimiter='\t'))
        known = {a['id']: a for a in controls()+arms()}
        targets = {}
        for r in wanted:
            value = json.loads(r.get('prediction') or r['observation'])
            if r['arm'] not in known or not valid(value, known[r['arm']]):
                return False
            if r['arm'] in targets and targets[r['arm']] != value:
                return False
            targets[r['arm']] = value
        grouped = {}
        for r in actual:
            grouped.setdefault(r['arm'], []).append(r)
        if not targets or set(targets) != set(grouped):
            return False
        cs = [aid for aid in targets if aid.startswith('control-')]
        control_sets = [{a['id'] for a in controls()},
                        {a['id'] for a in controls() if not a.get('error')}]
        if set(cs) not in control_sets or any(targets[aid] != prediction(known[aid]) for aid in cs):
            return False
        for aid, value in targets.items():
            runs = grouped[aid]
            if len(runs) != 2 or {r['repeat'] for r in runs} != {'1', '2'}:
                return False
            if any(r['gate'] != 'pass' or r['typing_or_capture_failed'] != '0'
                   or not valid(json.loads(r['observation']), known[aid])
                   or json.loads(r['observation']) != value for r in runs):
                return False
        return True
    except (ValueError, KeyError, TypeError, OSError):
        return False


def screen_of(rows):
    data = bytearray(b' '*3000)
    for i, row in enumerate(rows):
        text = (row[0]+''.join(' '+str(x)+' ' for x in row[1:])).encode('ascii')
        data[i*120:i*120+len(text)] = text
    return bytes(data)


def selftest(work):
    work.mkdir(parents=True, exist_ok=True)
    for text, value in [('&h0', 0), ('&h10', 16), ('&hff', 255), ('&h7fff', 32767),
                        ('&h8000', -32768), ('&hffff', -1), ('&o17', 15),
                        ('&o177777', -1), ('&17', 15), ('&HfF', 255), ('&O17', 15),
                        ('&h', 0), ('& h10', 16), ('&o1 7', 15)]:
        assert read_gw(text) == (value, '', None)
    for text in ['&h10000', '&h1ffff', '&h00010', '&o200000']:
        assert read_gw(text)[2] == 6
    assert read_gw('&o8')[2] == 2 and read_gw('&18')[2] == 2
    assert read_gw('&h 10') == (0, ' 10', None)
    assert read_gw('&hg') == (0, 'g', None) and read_gw('&h10%') == (16, '%', None)
    selected = controls()+arms()
    assert len({a['id'] for a in selected}) == len(selected)
    for a in selected:
        p = prediction(a)
        assert valid(p, a)
        assert extract(screen_of(p['result']))[0] == p['result']
        assert valid(prediction_untrapped(a), a)
        program(a)
    assert outcome(dict(expr='&hffff+1')) == (0, False)
    assert outcome(dict(expr='abs(&h8000)')) == (32768, False)
    assert outcome(dict(expr='&h10/3')) == (5.33333, False)
    assert outcome(dict(expr='&h-1')) == (-1, False)
    good = result_rows(-32768)
    assert extract(screen_of(good))[0] == good
    assert extract(screen_of(result_rows(5.33333)))[0] == result_rows(5.33333)
    for rows in [[['s9g', 1]], [['s9ge', 1, 0], ['s9gd', 1, 1]],
                 [['s9g', 2, 16], ['s9gd', 1, 1]], good+good]:
        assert not valid(dict(entry_errors=[], listed_lines=None, result=extract(screen_of(rows))[0]), controls()[0])
    assert extract(screen_of(good).replace(b's9g', b'z9g', 1))[0] != good
    data = bytearray(b' '*3000)
    for i, number in enumerate([10, 20, 40, 50, 15, 940, 950, 960]):
        text = f'{number} REM'.encode('ascii')
        data[i*120:i*120+len(text)] = text
    assert list_count(bytes(data))[0] == 1
    rejected = bytearray(data); rejected[120:200] = b' '*80
    assert list_count(bytes(rejected))[0] == 0
    assert list_count(b' '*3000)[0] == -1
    data[240:250] = b'20 PRINT 2'; assert list_count(bytes(data))[0] == -1
    assert dump_path(Path('screen.bin'), 123, True).name == 'screen.f000123.bin'
    assert dump_path(Path('screen.bin'), 123, False).name == 'screen.bin'
    try:
        extract(b' ')
        assert False
    except ValueError:
        pass
    with tempfile.TemporaryDirectory(prefix='replay-', dir=work) as temp:
        root = Path(temp)
        def replay(rom, official, a, directory, trap=True):
            return prediction(a), {}
        with patch(__name__+'.run_arm', replay):
            records = measure('', False, selected, root)
        expected, measured = root/'expected.tsv', root/'measured.tsv'
        write(expected, ['arm', 'prediction'], [(a['id'], json.dumps(prediction(a))) for a in selected])
        assert emit(measured, records) and check(expected, measured)
        assert not emit(root/'missing.tsv', records[1:])
        err_records = measure('', False, [], root)  # 空の対照は関門を通さない
        assert not emit(root/'empty.tsv', err_records)
        import copy
        bad_err = copy.deepcopy(records)
        error_record = next(r for r in bad_err if r['arm']['id'] == 'control-direct-error')
        for p in error_record['obs']:
            p['result'][0][2] = 6
        assert not emit(root/'error.tsv', bad_err)
        with (root/'error.tsv').open() as s:
            assert all(r['gate'] == 'gate_failed' for r in csv.DictReader(s, delimiter='\t'))
        calls = 0
        def changed(rom, official, a, directory, trap=True):
            nonlocal calls
            calls += 1
            p = prediction(a)
            if calls == 2:
                p['result'][0][2] = 123
            return p, {}
        with patch(__name__+'.run_arm', changed):
            broken = measure('', False, [selected[0]], root)
        assert not broken[0]['gate'] and not emit(measured, broken)
        records[0]['obs'] = [dict(entry_errors=[], listed_lines=None, result=result_rows(123))]*2
        assert not emit(measured, records) and not check(expected, measured)
        with measured.open() as s:
            assert all(r['gate'] == 'gate_failed' for r in csv.DictReader(s, delimiter='\t'))
        with patch(__name__+'.run_arm', side_effect=RuntimeError('合成打鍵失敗')):
            broken = measure('', False, [selected[0]], root)
        assert not broken[0]['gate'] and all(broken[0]['failed'])
        assert not emit(measured, [])
    print('OK GW固定値、数値・ERR・入力拒否の採取、2走・関門・照合の陰性対照')
    with tempfile.TemporaryDirectory(prefix='selftest-', dir=work) as temp:
        root = Path(temp); rom = root/'rom'
        proc = subprocess.run([os.sys.executable, str(kw.REPO/'src/build_main_rom.py'), str(rom),
                               '--work-dir', str(root/'asm')], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        assert proc.returncode == 0, '自作ROM一時ビルド失敗'
        constants = [a for a in controls() if not a.get('error')]
        records = measure(rom, False, constants, root, trap=False)
        assert all(r['gate'] and r['obs'][0] == prediction(r['arm']) for r in records), \
            '自作ROM定数対照失敗: '+json.dumps([(r['arm']['id'], r['gate'], r['obs']) for r in records])
        observed, expected = root/'measured.tsv', root/'expected.tsv'
        assert emit(observed, records, trap=False)
        write(expected, ['arm', 'prediction'], [(a['id'], json.dumps(prediction(a))) for a in constants])
        assert check(expected, observed)
        wrong = prediction(constants[0]); wrong['result'][0][2] = 7
        write(expected, ['arm', 'prediction'], [(a['id'], json.dumps(wrong if i == 0 else prediction(a))) for i, a in enumerate(constants)])
        assert not check(expected, observed)
        records[0]['obs'] = [wrong, wrong]
        assert not emit(observed, records, trap=False)
    print('OK 自作ROM一時ビルド、10進定数8腕×2走、期待値改変拒否')
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
        write(args.out, ['arm', 'candidate', 'prediction', 'prediction_untrapped', 'typed_lines'],
              [(a['id'], 'H_GW', json.dumps(prediction(a)), json.dumps(prediction_untrapped(a)),
                json.dumps(program(a), ensure_ascii=False)) for a in selected])
        return 0
    records = measure(args.rom_dir, args.official, selected, args.work_dir)
    passed = emit(args.out, records)
    print(f'記録完了: {len(records)}腕×2走、全体関門 '+('通過' if passed else '失敗'))
    return 0 if passed else 1


if __name__ == '__main__':
    raise SystemExit(main())
