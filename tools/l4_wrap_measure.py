#!/usr/bin/env python3
"""l4-s9i: 既知文字だけの PRINT 行端予測・位置採取。生画面本文は返さない。"""
import argparse
import copy
import csv
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from unittest.mock import patch

REPO = Path(__file__).resolve().parent.parent
WORK = REPO.parent / 'tmp/l4s9i-work'
CANDIDATES = ('W_FULL', 'W_ITEM', 'W_GW', 'W_75')
BEGIN, END, DONE = b's9ib|', b'z', b's9id'
HEADER = ['arm', 'candidate', 'prediction', 'typed_lines']


def arm(aid, k=0, lengths=(0,), kind='string', tail=';'):
    return dict(id=aid, k=k, lengths=list(lengths), kind=kind, tail=tail)


def controls():
    return [arm('control-empty'), arm('control-string', lengths=(3,)),
            arm('control-two', lengths=(2, 3), kind='two'),
            arm('control-number', kind='number'), arm('control-comma', k=1, kind='comma'),
            arm('control-80', lengths=(80,)), arm('control-81', lengths=(81,)),
            arm('control-95', lengths=(95,)),
            arm('control-old-chunks', k=5, lengths=(35, 35, 8), kind='two')]


def arms():
    result = []
    pairs = {0: (69, 70, 71, 74, 75, 76, 79, 80, 81, 95, 161),
             1: (78, 79, 80), 5: (69, 70, 71, 74, 75, 76, 80, 81, 95),
             69: (10, 11, 12), 70: (9, 10, 11), 74: (5, 6, 7),
             75: (4, 5, 6), 79: (1, 2)}
    for k, values in pairs.items():
        for n in values:
            result.append(arm(f'string-{k:02d}-{n:03d}', k, (n,)))
    for k, a, values in [(0, 70, (9, 10, 11)), (5, 35, (35, 36, 40)),
                         (5, 70, (1, 5, 6)), (70, 5, (4, 5, 6))]:
        for b in values:
            result.append(arm(f'two-{k:02d}-{a:02d}-{b:02d}', k, (a, b), 'two'))
    for k in (0, 68, 69, 70, 71, 72, 73, 74, 75, 76, 77, 78, 79):
        result.append(arm(f'number-{k:02d}', k, kind='number'))
    for k in (55, 56, 57, 69, 70, 71, 79):
        result.append(arm(f'comma-{k:02d}', k, kind='comma'))
    for k in (55, 56, 69, 70, 79):
        result.append(arm(f'comma-tail-{k:02d}', k, kind='comma-tail', tail=','))
    for k, a, b in [(0, 70, 11), (5, 35, 36), (70, 5, 6), (79, 1, 1)]:
        result.append(arm(f'concat-{k:02d}-{a:02d}-{b:02d}', k, (a, b), 'concat'))
    for k, values in [(0, (79, 80, 81)), (5, (70, 75, 76)), (70, (9, 10, 11))]:
        for n in values:
            # セミコロンありの同じ腕は string 群に固定済み。
            result.append(arm(f'newline-{k:02d}-{n:03d}', k, (n,), tail=''))
    return result


def selected():
    return controls() + arms()


def items(a):
    values = [bytes([97+i])*n for i, n in enumerate(a['lengths'])]
    if a['kind'] == 'number':
        return [b' 12345 ']
    if a['kind'] == 'comma':
        return [b'c']
    if a['kind'] == 'comma-tail':
        return []
    return [b''.join(values)] if a['kind'] == 'concat' else values


def known(a):
    return b'p'*a['k'] + b''.join(items(a)).replace(b' ', b'')


def program(a):
    lines = ['new', f'10 p$=string$({a["k"]},"p")']
    for i, n in enumerate(a['lengths']):
        name = chr(97+i)
        lines.append(f'{20+i} {name}$=string$({n},"{name}")')
    lines += ['40 cls', '50 print "s9ib|"']
    kind = a['kind']
    if kind == 'number':
        lines.append('70 print p$;12345'+a['tail'])
    elif kind in ('comma', 'comma-tail'):
        lines.append('70 print p$,'+('"c";' if kind == 'comma' else ''))
    else:
        names = [chr(97+i)+'$' for i in range(len(a['lengths']))]
        expr = ('+' if kind == 'concat' else ';').join(names)
        # prefix と対象項目は別文。対象を打鍵長で分割しない。
        lines += ['60 print p$;', '70 print '+expr+a['tail']]
    lines += ['80 print "z";', '90 locate 0,12:print "s9id"', '100 end', 'cls', 'run']
    if not all(len(s) < 80 and s == s.lower() and '@' not in s and '_' not in s for s in lines):
        raise ValueError('打鍵行の制約違反')
    return lines


def observation(codes):
    tails = []
    for row in range(len(codes)//80):
        part = bytes(codes[row*80:(row+1)*80])
        tails.append(80-len(part.rstrip(b' ')))
    return dict(codes=list(codes), end=[len(codes)//80, len(codes)%80], blank_tails=tails)


def prediction(a, candidate='W_FULL'):
    if candidate not in CANDIDATES:
        raise ValueError('候補が不正')
    limit = 75 if candidate == 'W_75' else 80
    row, col = 0, 0
    cells = {}

    def newline():
        nonlocal row, col
        row += 1
        col = 0

    def output(value):
        nonlocal col
        for code in value:
            cells[row*80+col] = code
            col += 1
            if col == limit:
                newline()

    def item(value):
        if candidate in ('W_ITEM', 'W_GW') and col and col+len(value) > 80:
            newline()
        output(value)

    def comma():
        nonlocal col
        target = (col//14+1)*14
        if (candidate == 'W_GW' and col >= 56) or target >= limit:
            newline()
        else:
            col = target

    item(b'p'*a['k'])
    if a['kind'] in ('comma', 'comma-tail'):
        comma()
    for value in items(a):
        item(value)
    if a['tail'] == '':
        newline()
    # 終了印は一文字。項目検査が次行へ送る追加効果を持たない。
    end = row*80+col
    return observation([cells.get(i, 32) for i in range(end)])


def valid(obs, a):
    if not isinstance(obs, dict) or set(obs) != {'codes', 'end', 'blank_tails'}:
        return False
    codes = obs['codes']
    if (not isinstance(codes, list) or len(codes) >= 7*80 or
            any(type(c) is not int or c not in (32, 49, 50, 51, 52, 53, 97, 98, 99, 112) for c in codes)):
        return False
    if bytes(codes).replace(b' ', b'') != known(a):
        return False
    if (not isinstance(obs['end'], list) or any(type(x) is not int for x in obs['end']) or
            not isinstance(obs['blank_tails'], list) or any(type(x) is not int for x in obs['blank_tails'])):
        return False
    return obs == observation(codes)


def extract(data, a):
    """既知の順序と個数を検査する前に、印間の値を外へ返してはならない。"""
    if len(data) != 3000:
        raise ValueError('画面写しの長さが不正')
    rows = [data[i*120:i*120+80] for i in range(25)]
    area = b''.join(rows[:13])
    if rows[0] != BEGIN.ljust(80, b' ') or rows[12] != DONE.ljust(80, b' '):
        raise ValueError('前印・完了印の位置が不正')
    if area.count(BEGIN) != 1 or area.count(DONE) != 1:
        raise ValueError('印が重複')
    payload = b''.join(rows[1:12])
    if payload.count(END) != 1:
        raise ValueError('終了印が欠落または重複')
    end = payload.index(END)
    if end >= 7*80 or payload[end+1:].strip(b' '):
        raise ValueError('終了印の位置・後続が不正')
    obs = observation(payload[:end])
    if not valid(obs, a):
        raise ValueError('既知の文字の順序・個数・形式が不一致')
    return obs


def screen_of(obs):
    flat = bytearray(b' '*2000)
    flat[:len(BEGIN)] = BEGIN
    payload = bytes(obs['codes'])+END
    flat[80:80+len(payload)] = payload
    flat[12*80:12*80+len(DONE)] = DONE
    data = bytearray(b' '*3000)
    for row in range(25):
        data[row*120:row*120+80] = flat[row*80:row*80+80]
    return bytes(data)


def find_core():
    paths = sorted((REPO.parent/'vendor/quasi88-libretro').glob('quasi88_libretro.*'))
    if not paths:
        raise RuntimeError('測定用コアが無い')
    return paths[0]


def run_arm(rom, official, a, work):
    args = [str(REPO/'tools/harness/frontend/q88measure'), '--core', str(find_core()), '--rom-dir', str(rom)]
    at = 700 if official else 100
    if official:
        args += ['--type-at', '300', '--type', '\n']
    for line in program(a):
        args += ['--type-at', str(at), '--type', line+'\n']
        at += (len(line)+1)*8+240+(15000 if line == 'run' else 0)
    base = work/'screen.bin'
    frames = (at+200, at+300)
    for frame in frames:
        args += ['--vram-dump', str(base), '--vram-dump-at', str(frame)]
    args += ['--frames', str(at+400)]
    try:
        proc = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              env=dict(os.environ, M6FH_LONG_TYPING='1'))
        if proc.returncode or b'untypable' in proc.stderr.lower() or '打てない'.encode() in proc.stderr:
            raise RuntimeError('測定器の実行または打鍵に失敗')
        shots = [base.with_name(f'screen.f{frame:06d}.bin').read_bytes() for frame in frames]
        if shots[0] != shots[1]:
            raise RuntimeError('完了後の2写しが不一致')
        return extract(shots[0], a)
    finally:
        for path in work.glob('screen*.bin'):
            path.unlink()


def measure(rom, official, chosen, work):
    work.mkdir(parents=True, exist_ok=True)
    records = []
    with tempfile.TemporaryDirectory(prefix='measure-', dir=work) as temp:
        for a in chosen:
            obs, failed = [], []
            for _ in range(2):
                try:
                    obs.append(run_arm(rom, official, a, Path(temp)))
                    failed.append(False)
                except Exception:
                    # 例外の中身・stdout/stderr・不正なセル値は記録しない。
                    obs.append(None)
                    failed.append(True)
            records.append(dict(arm=a, obs=obs, failed=failed))
    return records


def write(path, header, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8', newline='') as stream:
        writer = csv.writer(stream, delimiter='\t')
        writer.writerow(header)
        writer.writerows(rows)


def prediction_rows(chosen, candidates=CANDIDATES):
    return [(a['id'], c, json.dumps(prediction(a, c)), json.dumps(program(a)))
            for a in chosen for c in candidates]


def stable(r):
    return (len(r['obs']) == 2 and r['failed'] == [False, False] and
            r['obs'][0] == r['obs'][1] and valid(r['obs'][0], r['arm']))


def emit(path, records, chosen):
    by_id = {r['arm']['id']: r for r in records}
    complete = len(records) == len(by_id) and set(by_id) == {a['id'] for a in chosen}
    calibration = complete and all(a['id'] in by_id and stable(by_id[a['id']]) and
                                  by_id[a['id']]['obs'][0] == prediction(a) for a in controls()[:5])
    passed, rows = calibration, []
    for r in records:
        a = r['arm']
        preds = [prediction(a, c) for c in CANDIDATES]
        gate = calibration and stable(r)
        match = gate and r['obs'][0] in preds
        passed = passed and match
        for i in range(2):
            # 呼出し側が不正観測を渡してもセル列を漏らさない。
            safe = r['obs'][i] if valid(r['obs'][i], a) else None
            rows.append((a['id'], i+1, json.dumps(safe), json.dumps(program(a)),
                         'pass' if match else 'differ' if gate else 'gate_failed',
                         int(r['failed'][i]),
                         *('agree' if gate and safe == p else 'differ' if gate else 'gate_failed' for p in preds)))
    write(path, ['arm', 'repeat', 'observation', 'typed_lines', 'status', 'typing_or_capture_failed', *CANDIDATES], rows)
    return bool(passed)


def read_rows(path):
    with path.open(encoding='utf-8') as stream:
        return list(csv.DictReader(stream, delimiter='\t'))


def check(expected, measured):
    catalog = {a['id']: a for a in selected()}
    targets, actual = {}, {}
    for r in read_rows(expected):
        aid, candidate = r['arm'], r['candidate']
        if aid not in catalog or candidate not in CANDIDATES or (aid, candidate) in targets:
            return False
        value = json.loads(r['prediction'])
        if value != prediction(catalog[aid], candidate) or not valid(value, catalog[aid]):
            return False
        targets[aid, candidate] = value
    ids = {aid for aid, _ in targets}
    if not ids or not {a['id'] for a in controls()[:5]} <= ids:
        return False
    for r in read_rows(measured):
        actual.setdefault(r['arm'], []).append(r)
    if set(actual) != ids:
        return False
    for aid, runs in actual.items():
        if len(runs) != 2 or {r['repeat'] for r in runs} != {'1', '2'}:
            return False
        obs = [json.loads(r['observation']) for r in runs]
        if (not valid(obs[0], catalog[aid]) or obs[0] != obs[1] or
                any(r['status'] != 'pass' or r['typing_or_capture_failed'] != '0' or
                    json.loads(r['typed_lines']) != program(catalog[aid]) for r in runs)):
            return False
        if obs[0] not in [v for (key, _), v in targets.items() if key == aid]:
            return False
        if aid in {a['id'] for a in controls()[:5]} and obs[0] != prediction(catalog[aid]):
            return False
    return True


def synthetic_selftest(work):
    all_arms = selected()
    assert len({a['id'] for a in all_arms}) == len(all_arms)
    fixed = [
        (arm('x', 5, (76,)), 'W_FULL', [1, 1], [0], (0, 5, 97)),
        (arm('x', 5, (76,)), 'W_ITEM', [1, 76], [75], (1, 0, 97)),
        (arm('x', 5, (76,)), 'W_GW', [1, 76], [75], (1, 0, 97)),
        (arm('x', 5, (76,)), 'W_75', [1, 6], [5], (0, 5, 97)),
        (arm('x', 0, (81,)), 'W_FULL', [1, 1], [0], (0, 0, 97)),
        (arm('x', 0, (161,)), 'W_ITEM', [2, 1], [0, 0], (0, 0, 97)),
        (arm('x', 74, kind='number'), 'W_FULL', [1, 1], [0], (0, 75, 49)),
        (arm('x', 74, kind='number'), 'W_ITEM', [1, 7], [6], (1, 1, 49)),
        (arm('x', 74, kind='number'), 'W_75', [1, 6], [6], (1, 0, 49)),
        (arm('x', 56, kind='comma'), 'W_GW', [1, 1], [24], (1, 0, 99)),
        (arm('x', 56, kind='comma'), 'W_FULL', [0, 71], [], (0, 70, 99)),
        (arm('x', 70, (5, 6), 'two'), 'W_ITEM', [1, 6], [5], (0, 70, 97)),
        (arm('x', 70, (5, 6), 'concat'), 'W_ITEM', [1, 11], [10], (1, 0, 97)),
        (arm('x', 0, (80,), tail=''), 'W_FULL', [2, 0], [0, 80], (0, 0, 97)),
    ]
    for a, candidate, end, tails, (r, c, code) in fixed:
        obs = prediction(a, candidate)
        assert obs['end'] == end and obs['blank_tails'] == tails and obs['codes'][r*80+c] == code, '固定値不一致'
    assert prediction(arm('x', 5, (75,)), 'W_ITEM')['end'] == [1, 0], 'ちょうど収まる境界'
    assert prediction(arm('x', 70, (5,)), 'W_75')['end'] == [1, 0], '75桁境界'
    for a in all_arms:
        program(a)
        for candidate in CANDIDATES:
            obs = prediction(a, candidate)
            assert valid(obs, a) and extract(screen_of(obs), a) == obs
    a = controls()[1]
    good = screen_of(prediction(a))
    bad_shots = [good[:-1], good.replace(BEGIN, b'x9ib|', 1), good.replace(DONE, b'x9id', 1),
                 good.replace(b'aaaz', b'aabz', 1), good.replace(b'aaaz', b'aa\xffz', 1),
                 good.replace(b'aaaz', b'aa\x01z', 1), good.replace(b'aaaz', b'aaazx', 1),
                 good.replace(b'aaaz', b'aazz', 1)]
    duplicate = bytearray(good)
    duplicate[5*120:5*120+len(BEGIN)] = BEGIN
    bad_shots.append(bytes(duplicate))
    reverse = bytearray(good)
    reverse[:len(BEGIN)] = b'z    '
    reverse[120:125] = BEGIN
    bad_shots.append(bytes(reverse))
    shifted = bytearray(good)
    shifted[:120] = good[120:240]
    bad_shots.append(bytes(shifted))
    for shot in bad_shots:
        try:
            extract(shot, a)
        except ValueError as error:
            assert '\xff' not in str(error) and 'aaaz' not in str(error)
        else:
            raise AssertionError('採取陰性を拒否しなかった')
    def replay(rom, official, a, directory):
        return extract(screen_of(prediction(a)), a)
    with patch(__name__+'.run_arm', replay):
        records = measure('', False, all_arms, work)
    expected, measured = work/'expected.tsv', work/'measured.tsv'
    write(expected, HEADER, prediction_rows(all_arms))
    assert emit(measured, records, all_arms) and check(expected, measured)
    for mutation in ('mismatch', 'unknown', 'failure', 'control', 'missing', 'duplicate'):
        broken = copy.deepcopy(records)
        if mutation == 'mismatch':
            broken[-1]['obs'][1] = prediction(broken[-1]['arm'], 'W_ITEM')
            # この腕で候補が同じでも、未知の位置に空白を追加して不一致を作る。
            broken[-1]['obs'][1] = observation([32]+broken[-1]['obs'][1]['codes'])
        elif mutation == 'unknown':
            broken[-1]['obs'] = [observation([255])]*2
        elif mutation == 'failure':
            broken[-1]['failed'][1] = True
        elif mutation == 'control':
            broken[1]['obs'] = [observation([32, 97, 97, 97])]*2
        elif mutation == 'missing':
            broken = broken[1:]
        else:
            broken.append(broken[-1])
        assert not emit(measured, broken, all_arms) and not check(expected, measured), '判定陰性が成功した'
    def failed(*args):
        raise RuntimeError('合成の採取失敗')
    with patch(__name__+'.run_arm', failed):
        assert not emit(measured, measure('', False, controls(), work), controls())
    # 壊れた期待値・SKIP・走番号重複も成功にしない。
    assert emit(measured, records, all_arms)
    rows = read_rows(measured)
    rows[0]['status'] = 'SKIP'
    write(measured, rows[0].keys(), [r.values() for r in rows])
    assert not check(expected, measured)
    assert emit(measured, records, all_arms)
    rows = read_rows(measured)
    rows[1]['repeat'] = '1'
    write(measured, rows[0].keys(), [r.values() for r in rows])
    assert not check(expected, measured)
    print('OK 固定予測、合成採取の陽性・陰性、未知文字遮断、2走・定数関門・欠落・SKIP拒否')


def selftest(work):
    try:
        work.mkdir(parents=True, exist_ok=True)
        context = tempfile.TemporaryDirectory(prefix='selftest-', dir=work)
    except PermissionError:
        print('作業置き場に書けないため、許可された一時領域で全検査を実行')
        context = tempfile.TemporaryDirectory(prefix='l4s9i-selftest-')
    with context as temp:
        root = Path(temp)
        synthetic_selftest(root)
        rom = root/'rom'
        proc = subprocess.run([sys.executable, str(REPO/'src/build_main_rom.py'), str(rom),
                               '--work-dir', str(root/'asm')], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if proc.returncode:
            raise RuntimeError('自作ROMの一時ビルド失敗')
        chosen = controls()
        records = measure(rom, False, chosen, root)
        if not all(stable(r) and r['obs'][0] == prediction(r['arm'], 'W_FULL') for r in records):
            failed_ids = [r['arm']['id'] for r in records if not stable(r) or r['obs'][0] != prediction(r['arm'])]
            raise RuntimeError('自作W_FULL定数対照不一致: '+','.join(failed_ids))
        expected, measured = root/'constant-expected.tsv', root/'constant-measured.tsv'
        write(expected, HEADER, prediction_rows(chosen, ('W_FULL',)))
        assert emit(measured, records, chosen) and check(expected, measured)
        records[-1]['obs'] = [prediction(chosen[-1], 'W_ITEM')]*2
        emit(measured, records, chosen)
        assert not check(expected, measured), 'W_FULL限定対照が別候補を許した'
    print('OK 自作ROMの定数9腕×2走、W_FULL既知値一致、別候補の陰性')
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('predict')
    p.add_argument('--out', type=Path, required=True)
    m = sub.add_parser('measure')
    m.add_argument('--rom-dir')
    m.add_argument('--official', action='store_true')
    m.add_argument('--out', type=Path, required=True)
    m.add_argument('--work-dir', type=Path, default=WORK)
    c = sub.add_parser('check')
    c.add_argument('--expected', type=Path, required=True)
    c.add_argument('--measured', type=Path, required=True)
    s = sub.add_parser('selftest')
    s.add_argument('--work-dir', type=Path, default=WORK)
    args = parser.parse_args()
    try:
        if args.command == 'selftest':
            return selftest(args.work_dir)
        if args.command == 'predict':
            write(args.out, HEADER, prediction_rows(selected()))
            return 0
        if args.command == 'check':
            passed = check(args.expected, args.measured)
            print('照合一致' if passed else '照合不一致')
            return 0 if passed else 1
        rom = os.environ.get('PC88_REF_ROM_DIR') if args.official else args.rom_dir
        if not rom or (args.official and args.rom_dir):
            parser.error('公式ROMの場所はPC88_REF_ROM_DIRのみ、自作は--rom-dirを指定')
        chosen = selected()
        records = measure(rom, args.official, chosen, args.work_dir)
        passed = emit(args.out, records, chosen)
        print(f'記録完了: {len(chosen)}腕×2走、既知候補一致 '+('通過' if passed else '失敗'))
        return 0 if passed else 1
    except (OSError, ValueError, KeyError, TypeError, RuntimeError, AssertionError) as error:
        # 例外に画面由来値が入っても、この境界を越えて表示しない。
        print('失敗: 入出力・形式・既知値の検査が不成立', file=sys.stderr)
        if args.command == 'selftest' and isinstance(error, (AssertionError, RuntimeError)):
            # 自己検査の例外は合成画面・自作ROMの固定メッセージのみ。
            print(str(error), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
