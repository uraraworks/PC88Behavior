#!/usr/bin/env python3
"""l4-s5j: GO SUBと行番号の空白の測定器具。画面本文は出力しない。"""
import argparse
from contextlib import redirect_stdout
import csv
from dataclasses import dataclass, replace
import pathlib
import io
import re
import subprocess
import sys
import tempfile
from unittest.mock import patch

import l4_listkw_measure as kw
import l4_listnum_measure as num

WORK = kw.REPO.parent / 'tmp/l4s5j-work'
EXPECTED = kw.REPO / 'tests/conformance/expected_l4_s5j.tsv'
BASE_CANDIDATES = ('G_A', 'G_B', 'G_0', 'L_A', 'L_B', 'L_0')
NEW_CANDIDATES = ('G_C', 'G_D', 'L_C', 'L_D')
ADD2_CANDIDATES = ('G_E', 'G_F', 'G_G')


@dataclass(frozen=True)
class Arm:
    id: str
    group: str
    typed: str
    seed: tuple[str, ...] = ()
    probe: bool = False
    add1: bool = False
    add2: bool = False
    add3: bool = False

    @property
    def candidates(self):
        base = ('G_A', 'G_B', 'G_0') if self.group == 'A' else ('L_A', 'L_B', 'L_0')
        if self.add3:
            return ('G_A', 'G_B', 'G_0', 'G_C', 'G_D', *ADD2_CANDIDATES, 'G_H')
        if self.add2:
            return ('G_A', 'G_B', 'G_0', 'G_C', 'G_D', *ADD2_CANDIDATES)
        return base + (('G_C', 'G_D') if self.group == 'A' else ('L_C', 'L_D')) if self.add1 else base

    @property
    def band(self):
        # 両候補の番号の間を含める。位置・予測番号による対応づけはしない。
        first = int(re.match(r'[0-9]+', self.typed)[0])
        spaced = int(re.match(r'[0-9 ]+', self.typed)[0].replace(' ', ''))
        numbers = [first, spaced, *(int(s.split(' ')[0]) for s in self.seed)]
        if self.add1:
            for typed in (*self.seed, self.typed):
                for candidate in ('L_C', 'L_D'):
                    numbers.append(parse_line(typed, candidate)[0])
        return min(numbers), max(numbers)


def build_arms():
    bodies = ['go sub10', 'go sub1', 'go sub123', 'go sub9', 'go sub0',
              'go sub12345', 'go sub1 0', 'go sub.5', 'go sub&h10',
              'go sub:end', 'go sub,', 'go sub"x"', 'go sub(1)', 'go sub+1',
              'go sub=1', 'go sub', 'go sub10:end', 'a=1:go sub10',
              'go sub10 x', 'go suba', 'go sub 10', 'go  sub10',
              'go to10', 'go to1:end', 'gosub10', 'rem go sub10',
              'print "go sub10"', 'data go sub10:go sub10']
    arms = [Arm(f'a{i:02d}', 'A', f'{100 + i * 10} {body}')
            for i, body in enumerate(bodies, 1)]
    inputs = ['1 0 print 1', '10 20 print 1', '1 2 3 4 print 1',
              '10  20 print 1', '10 2 0 print 1', '10  print 1',
              '10   print 1', '10 20', '10 20 ', '6552 9 print 1',
              '6553 0 print 1', '10 .5', '10 1e5', '10 &h1',
              '10 0 print 1', '0 1 print 1', '00010 print 1',
              '130 1+rem x end', '20 3 print 1', '30 4  print 1',
              '40 5   print 1', '50 6+print 1', '60 7:print 1',
              '70 8rem x end', '80 9', '90 0 ']
    for i, typed in enumerate(inputs, 1):
        digits = re.match(r'[0-9 ]+', typed)[0].replace(' ', '')
        seed = (f'{int(digits)} print 7',) if typed.strip().replace(' ', '').isdigit() else ()
        arms.append(Arm(f'b{i:02d}', 'B', typed, seed, i == 11))
    return arms


def build_add1_arms():
    arms = [replace(a, add1=True) for a in build_arms()]
    bodies = ['go suba b', 'go subab', 'go sub1  x', 'go sub  10',
              'go sub   10', 'go sub1 :end', 'go subx:end', 'go sub$',
              'go sub1 +1', 'go suba  b', 'go sub1 "a"', 'go subrem x',
              'go sub data x', 'go sub 1 0']
    arms.extend(Arm(f'a{i:02d}', 'A', f'{100 + i * 10} {body}', add1=True)
                for i, body in enumerate(bodies, 29))
    inputs = ['65530 print 1', '6553 5 print 1', '6553 6 print 1',
              '65535 print 1', '65536 print 1', '99999 print 1',
              '6553  0 print 1', '655290 print 1',
              '1 2 3 4 5 6 print 1', '65529 print 1']
    arms.extend(Arm(f'b{i:02d}', 'B', typed, probe=True, add1=True)
                for i, typed in enumerate(inputs, 27))
    return arms


def build_add2_arms():
    arms = [replace(a, add2=True) for a in build_add1_arms() if a.group == 'A']
    bodies = ['go subx(1)', 'go subx+1', 'go subx"a"', 'go subx,1',
              'go subx.5', 'go subx&h1', "go subx'c", 'go subx?1',
              'go subx=1', 'go subx$', 'go subx;1', 'go subx-1',
              'go subx*2', 'go subx#', 'go subx%', 'go subx 1',
              'go subx1', 'go subxx']
    arms.extend(Arm(f'a{i:02d}', 'A', f'{1000 + (i - 43) * 10} {body}',
                    add1=True, add2=True) for i, body in enumerate(bodies, 43))
    return arms


def build_add3_arms():
    arms = [replace(a, add3=True) for a in build_add2_arms()]
    bodies = ['go subx&o7', 'go subx&7', 'go subx&', 'go suba&h10', 'go sub1&h1', 'go subx<1', 'go subx>1', 'go subx/2', 'go subx^2', 'go subx\\2', 'go subx@', 'go subx!', 'go subx 1.5', 'go subx.', 'go subx..5', 'go subxa.b', 'a=1:go subx&h1:end', 'go sub&&h1']
    arms.extend(Arm(f'a{i:02d}', 'A', f'{2000 + (i - 61) * 10} {body}',
                    add1=True, add2=True, add3=True) for i, body in enumerate(bodies, 61))
    return arms


def predict_g(body, candidate):
    # N_Dの字句範囲を共有し、文字列・REM・DATA・名前の内部を改変しない。
    out, i = [], 0
    while i < len(body):
        c = body[i]
        if c == "'":
            out.append(body[i:])
            break
        if c == '"':
            end = body.find('"', i + 1)
            end = len(body) if end < 0 else end + 1
        elif c.isdigit() or c == '&' or (c == '.' and body[i + 1:i + 2].isdigit()):
            _, end = num._number(body, i, True, True, True, True, [False, None], True)
        elif c.isalpha():
            end = i + len(re.match(r'[a-z0-9.]+', body[i:])[0])
            word = body[i:end]
            if word == 'rem':
                out.append(body[i:])
                break
            if word == 'data':
                # 引用符内のコロンを文の区切りにしない。
                quoted = False
                while end < len(body):
                    if body[end] == '"':
                        quoted = not quoted
                    if body[end] == ':' and not quoted:
                        break
                    end += 1
            if word == 'go' and body[end:end + 4] == ' sub' and candidate != 'G_0':
                after = end + 4
                nxt = body[after:after + 1]

                if candidate in (*ADD2_CANDIDATES, 'G_H'):
                    i = after + bool(nxt)
                    first = body[i:i + 1]
                    spaced = bool(first) and (
                        first.isascii() and first.isalnum()
                        or candidate == 'G_F' and first == '.'
                        or candidate == 'G_H' and first in ('.', '&')
                        or candidate == 'G_G' and first not in (' ', ':'))
                    out.append('gosub' + (' ' if spaced else ''))
                    continue
                if candidate in ('G_C', 'G_D'):
                    if not nxt:
                        out.append('gosub')
                        i = after
                        continue
                    i = after + 1
                    rest = body[i:].lstrip(' ')
                    numeric = bool(rest) and (rest[0].isdigit() or rest[0] == '&'
                              or (rest[0] == '.' and rest[1:2].isdigit()))
                    if candidate == 'G_C' or (body[i:i + 1] == ' ' and numeric):
                        i = len(body) - len(rest)
                    out.append('gosub ')
                    continue
                consume = bool(nxt) and (not ('a' <= nxt <= 'z') if candidate == 'G_A' else nxt.isdigit())
                if consume:
                    out.append('gosub ')
                    i = after + 1
                    continue
                if nxt and nxt != ' ':
                    # 既存予測器の詰めを抑制するための内部の印（出力時に除く）。
                    out.append('go\x01')
                    i = end
                    continue
        else:
            end = i + 1
        out.append(body[i:end])
        i = end
    return num.predict_body_n_d(''.join(out)).replace('\x01', '')


def parse_line(typed, candidate):
    if candidate == 'L_0':
        m = re.match(r'[0-9]+', typed)
        return int(m[0]), typed[m.end():].lstrip(' ')
    if candidate in ('L_C', 'L_D'):
        limit = 65529 if candidate == 'L_C' else 65535
        no, i, last = 0, 0, 0
        while i < len(typed) and (typed[i].isdigit() or typed[i] == ' '):
            if typed[i].isdigit():
                next_no = no * 10 + int(typed[i])
                if next_no > limit:
                    break
                no = next_no
                last = i + 1
            i += 1
        body = typed[last:]
        return no, body[1:] if body.startswith(' ') else body
    m = re.match(r'[0-9 ]+', typed)
    prefix = m[0]
    no = int(prefix.replace(' ', ''))
    last = len(prefix.rstrip(' '))
    body = typed[last:]
    body = body.lstrip(' ') if candidate == 'L_A' else (body[1:] if body.startswith(' ') else body)
    return no, body


def predict(arm, candidate):
    stored = {}
    for typed in (*arm.seed, arm.typed):
        if arm.group == 'A':
            no, body = parse_line(typed, 'L_0')
            rendered = predict_g(body, candidate)
        else:
            no, body = parse_line(typed, candidate)
            rendered = num.predict_body_n_d(body)
        if not 0 <= no <= (65535 if candidate == 'L_D' else 65529):
            continue
        if not body.strip(' '):
            stored.pop(no, None)
        elif rendered is not None:
            stored[no] = f'{no} {rendered}'.rstrip(' ')
    return [stored[no] for no in sorted(stored)]


def extract_band(listed, band):
    return [row for row in listed if band[0] <= int(re.match(r' *([0-9]+)', row)[1]) <= band[1]]


def signature(rows):
    return kw.sig('\n'.join(rows)) if rows else 'no_line'


def classify(first, second, prediction):
    if 'gate_failed' in (first, second):
        return 'gate_failed'
    if first != second:
        return 'unstable'
    return 'agree' if first == prediction else 'differ'


def measure(rom_dir, official, arms=None, work=WORK):
    work.mkdir(parents=True, exist_ok=True)
    records = []
    # B群は番号帯が衝突するため各腕を単独chunkにする。毎回run_chunkがnewを打つ。
    with tempfile.TemporaryDirectory(prefix='measure-', dir=work) as td:
        for arm in build_arms() if arms is None else arms:
            observations, signatures, entries, others = [], [], [], []
            run_failed = False
            for repeat in range(2):
                try:
                    listed, other, untypable = kw.run_chunk(rom_dir, official,
                        [*arm.seed, arm.typed], pathlib.Path(td), f'{arm.id}-r{repeat}')
                except (SystemExit, Exception):
                    # 失敗を腕内に閉じ、次の腕の測定を続ける。
                    run_failed = True
                    observations.append([])
                    signatures.append('gate_failed')
                    others.append(0)
                    entries.append(None)
                    continue
                rows = extract_band(listed, arm.band)
                gate = not untypable and len(rows) == len(set(rows))
                if arm.group == 'A':
                    gate = gate and len(rows) == 1
                observations.append(rows)
                signatures.append(signature(rows) if gate else 'gate_failed')
                others.append(other + len(listed) - len(rows))
                entries.append(num.probe_entry_status(rom_dir, official, arm.typed,
                               lineno=None, number=2) if arm.probe else None)
            predictions = {c: signature(predict(arm, c)) for c in arm.candidates}
            statuses = {c: classify(*signatures, p) for c, p in predictions.items()}
            if run_failed:
                statuses = {c: 'gate_failed' for c in arm.candidates}
            stable = signatures[0] == signatures[1] and entries[0] == entries[1]
            if not run_failed and entries[0] != entries[1]:
                statuses = {c: 'unstable' for c in arm.candidates}
            records.append(dict(arm=arm, obs=observations, signatures=signatures,
                                entries=entries, others=others, stable=stable,
                                predictions=predictions, statuses=statuses,
                                gate_reason='q88measure_failed' if run_failed else None))
    return records


def write_predict(path, add1=False, add2=False, add3=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8', newline='') as f:
        writer = csv.writer(f, delimiter='\t')
        writer.writerow(['id', '群', '打った行', '先行入力', '番号帯', '候補', '予測行', '署名'])
        for arm in build_add3_arms() if add3 else (build_add2_arms() if add2 else (build_add1_arms() if add1 else build_arms())):
            for c in arm.candidates:
                rows = predict(arm, c)
                writer.writerow([arm.id, arm.group, arm.typed, '\\n'.join(arm.seed),
                                 f'{arm.band[0]}-{arm.band[1]}', c, '\\n'.join(rows), signature(rows)])


def write_measure(records, path, show_differs, add1=False, add2=False, add3=False):
    candidates = (('G_A', 'G_B', 'G_0', 'G_C', 'G_D', *ADD2_CANDIDATES) if add2
                  else (BASE_CANDIDATES + NEW_CANDIDATES if add1 else BASE_CANDIDATES))
    if add3:
        candidates = (*build_add3_arms()[0].candidates,)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8', newline='') as f:
        writer = csv.writer(f, delimiter='\t')
        writer.writerow(['id', '群', '打った行', '走1署名', '走2署名', '一致',
                         *candidates,
                         '走1番号2含む', '走1番号2完全一致', '走2番号2含む', '走2番号2完全一致',
                         '走1他行件数', '走2他行件数'])
        for r in records:
            arm = r['arm']
            entry = [int(v) for run in r['entries'] for v in run] if arm.probe else [''] * 4
            writer.writerow([arm.id, arm.group, arm.typed, *r['signatures'],
                             'stable' if r['stable'] else 'unstable',
                             *(r['statuses'].get(c, '') for c in candidates),
                             *entry, *r['others']])
            new = [r['statuses'][c] for c in (('G_H',) if add3 else (ADD2_CANDIDATES if add2 else NEW_CANDIDATES)) if c in r['statuses']]
            if show_differs and r['stable'] and (all(v == 'differ' for v in r['statuses'].values())
                    or ((add1 or add2 or add3) and new and all(v == 'differ' for v in new))):
                print(arm.id + '\t' + '\\n'.join(r['obs'][0]))
    for c in candidates:
        print(c + ' ' + ' '.join(f'{s}={sum(r["statuses"].get(c) == s for r in records)}'
              for s in ('agree', 'differ', 'unstable', 'gate_failed')))


def check_arms():
    return ([a for a in build_add1_arms() if a.group == 'B']
            + [a for a in build_add3_arms() if a.id != 'a71'])


def read_expected(path):
    expected = {}
    for line in path.read_text(encoding='utf-8').splitlines():
        if not line or line.startswith('#'):
            continue
        fields = line.split('\t')
        if (len(fields) != 2 or fields[0] in expected
                or not re.fullmatch(r'[0-9a-f]{16}|no_line', fields[1])):
            raise ValueError('期待値の列・重複・署名形式が不正')
        expected[fields[0]] = fields[1]
    if set(expected) != {a.id for a in check_arms()}:
        raise ValueError('期待値はB群36腕・A群77腕（a71除外）であること')
    return expected


def check(rom_dir, expected_path):
    try:
        expected = read_expected(expected_path)
    except (OSError, ValueError):
        print('期待値ファイルが不正', file=sys.stderr)
        return 1
    # 公式測定用の作業先を使わず、照合用の一時領域だけに書く。
    with tempfile.TemporaryDirectory(prefix='l4-s5j-check-') as td:
        records = measure(rom_dir, False, check_arms(), pathlib.Path(td))
    bad = [r['arm'].id for r in records
           if not r['stable'] or r['signatures'] != [expected[r['arm'].id]] * 2]
    for aid in bad:
        print(aid)
    return int(bool(bad))


def selftest(work):
    failed = []
    def expect(name, ok):
        print(('OK ' if ok else 'NG ') + name)
        if not ok:
            failed.append(name)
    arms = build_arms()
    expect('腕の一意性・小文字ASCII', len({a.id for a in arms}) == len(arms)
           and all(a.typed.isascii() and a.typed == a.typed.lower() for a in arms))
    for body, want in [('go sub10', 'GOSUB 0'), ('go sub 10', 'GOSUB 10')]:
        expect('G_A既知観測 ' + body, predict_g(body, 'G_A') == want)
    expect('G_0陰性対照', predict_g('go sub10', 'G_0') != 'GOSUB 0')
    known = Arm('known', 'B', '130 1+rem x end')
    expect('L_A既知観測', predict(known, 'L_A') == ['1301 +REM x end'])
    expect('L_0陰性対照', predict(known, 'L_0') != ['1301 +REM x end'])
    expect('G候補の識別', predict_g('go sub.5', 'G_A') == 'GOSUB 5'
           and predict_g('go sub.5', 'G_B') == 'GO SUB.5')
    expect('保護された文脈', predict_g('rem go sub10', 'G_A') == 'REM go sub10'
           and predict_g('print "go sub10"', 'G_A') == 'PRINT "go sub10"')
    expect('余分な空白の識別', predict(Arm('space', 'B', '10   print 1'), 'L_B') == ['10   PRINT 1'])
    deletion = next(a for a in arms if a.id == 'b08')
    expect('削除の識別', predict(deletion, 'L_A') == [] and len(predict(deletion, 'L_0')) == 2)
    data = bytearray(b' ' * (kw.STRIDE * kw.ROWS))
    for i, row in enumerate(['9 PRINT 1', '10 .5', '101 100000!', '102 PRINT 1']):
        data[i * kw.STRIDE:i * kw.STRIDE + kw.COLS] = row.encode().ljust(kw.COLS, b' ')
    listed, _ = kw.extract_list_lines(bytes(data))
    expect('番号帯の内外・数字本文', extract_band(listed, (10, 101)) == ['10 .5', '101 100000!'])
    expect('2走・欠落の判定', [classify(*v) for v in [('x', 'x', 'x'), ('x', 'x', 'y'),
           ('x', 'y', 'x'), ('no_line', 'no_line', 'no_line')]] == ['agree', 'differ', 'unstable', 'agree'])
    work.mkdir(parents=True, exist_ok=True)
    expected = read_expected(EXPECTED)
    with patch.object(kw, 'run_chunk', side_effect=lambda rom, official, lines, work, tag:
                      (predict(next(a for a in check_arms() if a.typed == lines[-1]),
                               'L_C' if tag.startswith('b') else 'G_H'), 0, False)) as run, \
         patch.object(num, 'probe_entry_status', return_value=(False, False)):
        output = io.StringIO()
        with redirect_stdout(output):
            rc = check('', EXPECTED)
    expect('check 113腕各2走・公式期待値一致・本文なし',
           rc == 0 and run.call_count == 226 and output.getvalue() == '')
    check_subset = check_arms()
    synthetic_check = [dict(arm=a, stable=True, signatures=[expected[a.id]] * 2)
                       for a in check_subset]
    for signatures, stable in [(['no_line', 'no_line'], True),
                               (['gate_failed'] * 2, True),
                               ([expected['a01'], 'no_line'], False)]:
        broken = [dict(r) for r in synthetic_check]
        index = next(i for i, r in enumerate(broken) if r['arm'].id == 'a01')
        broken[index].update(signatures=signatures, stable=stable)
        output = io.StringIO()
        with patch('l4_s5j_measure.measure' if __name__ != '__main__' else '__main__.measure',
                   return_value=broken), redirect_stdout(output):
            rc = check('', EXPECTED)
        expect('check 不一致・関門失敗・不安定をidだけで報告 ' + signatures[0],
               rc == 1 and output.getvalue() == 'a01\n')
    subset = [arms[i] for i in (0, 20, 28, 29, 33, 45)]
    def fake_run(rom, official, lines, work, tag):
        arm = next(a for a in arms if a.typed == lines[-1])
        rows = predict(arm, 'G_A' if arm.group == 'A' else 'L_A')
        return rows + ['99999 PRINT 9'], 2, False
    with patch.object(kw, 'run_chunk', side_effect=fake_run), patch.object(num, 'probe_entry_status', return_value=(True, True)):
        synthetic = measure('', False, arms, work)
    expect('全54腕の合成2走・帯外行の除外', all(r['statuses']['G_A' if r['arm'].group == 'A' else 'L_A'] == 'agree' and r['others'] == [3, 3] for r in synthetic))
    expect('no_lineの測定', next(r for r in synthetic if r['arm'].id == 'b08')['signatures'] == ['no_line', 'no_line'])
    with patch.object(kw, 'run_chunk', side_effect=[(['110 GOSUB 0'], 0, False), (['110 GOSUB 1'], 0, False)]):
        broken = measure('', False, [arms[0]], work)[0]
    expect('測定の不安定走を検出', all(s == 'unstable' for s in broken['statuses'].values()))
    with patch.object(kw, 'run_chunk', return_value=(['110 GOSUB 0'], 0, True)):
        broken = measure('', False, [arms[0]], work)[0]
    expect('打てない文字の関門', all(s == 'gate_failed' for s in broken['statuses'].values()))
    failed_arm, following_arm = build_add3_arms()[60:62]
    def fail_one_arm(rom, official, lines, work, tag):
        if lines[-1] == failed_arm.typed:
            raise SystemExit('q88measure failed')
        return predict(following_arm, 'G_H'), 0, False
    with patch.object(kw, 'run_chunk', side_effect=fail_one_arm) as run:
        isolated = measure('', False, [failed_arm, following_arm], work)
    expect('run_chunk失敗腕を関門化し後続腕を継続',
           isolated[0]['gate_reason'] == 'q88measure_failed'
           and all(v == 'gate_failed' for v in isolated[0]['statuses'].values())
           and isolated[1]['arm'] == following_arm and isolated[1]['statuses']['G_H'] == 'agree'
           and run.call_count == 4)
    add_arms = build_add1_arms()
    expect('追補78腕・初回54腕の入力不変・小文字ASCII', len(add_arms) == 78
           and [replace(a, add1=False) for a in add_arms[:54]] == arms
           and len({a.id for a in add_arms}) == 78
           and all(a.typed.isascii() and a.typed == a.typed.lower() for a in add_arms))
    expect('初回候補の予測不変', all(predict(a, c) == predict(b, c)
           for a, b in zip(arms, add_arms) for c in a.candidates))
    observations = {'a07': ['170 GOSUB 0'], 'a20': ['300 GOSUB'],
                    'b11': ['6553 0 PRINT 1']}
    selected = [a for a in add_arms if a.id in observations]
    with patch.object(kw, 'run_chunk', side_effect=lambda rom, official, lines, work, tag:
                      (observations[tag.split('-')[0]], 0, False)), \
         patch.object(num, 'probe_entry_status', return_value=(False, False)):
        round1 = measure('', False, selected, work)
    for r in round1:
        c = 'G_C' if r['arm'].group == 'A' else 'L_C'
        expect('初回外れ腕の合成再現 ' + r['arm'].id + ' ' + c,
               r['statuses'][c] == 'agree' and r['stable'])
    expect('G_D a20の行末空白除去', predict(selected[1], 'G_D') == ['300 GOSUB'])
    expect('G_C/G_Dの空白・数値再読の識別',
           predict_g('go sub1  x', 'G_C') == 'GOSUB X'
           and predict_g('go sub1  x', 'G_D') == 'GOSUB   X'
           and predict_g('go sub   10', 'G_D') == 'GOSUB 10'
           and predict_g('go sub1 .5', 'G_D') == 'GOSUB .5'
           and predict_g('go sub1 &h10', 'G_D') == 'GOSUB &H10')
    expect('追補G候補の保護文脈', all(
           predict_g(body, c) == predict_g(body, 'G_A')
           for c in ('G_C', 'G_D') for body in
           ('rem go suba', 'print "go suba"', 'data go suba', "'go suba", 'xgo suba')))
    expect('L_C/L_Dの上限・打切り空白',
           parse_line('6553  0 print 1', 'L_C') == (6553, ' 0 print 1')
           and parse_line('65535 print 1', 'L_C') == (6553, '5 print 1')
           and parse_line('65535 print 1', 'L_D') == (65535, 'print 1')
           and parse_line('65536 print 1', 'L_D') == (6553, '6 print 1')
           and predict(Arm('limit', 'B', '65535 print 1'), 'L_D') == ['65535 PRINT 1'])
    expect('追補番号帯・上限B探り', all(a.band[0] <= parse_line(a.typed, c)[0] <= a.band[1]
           for a in add_arms for c in ('L_C', 'L_D'))
           and all(a.probe for a in add_arms[68:])
           and next(a for a in add_arms if a.id == 'b30').band[1] == 65535)
    def fake_add1(rom, official, lines, work, tag):
        arm = next(a for a in add_arms if a.typed == lines[-1])
        return predict(arm, 'G_C' if arm.group == 'A' else 'L_C'), 0, False
    with patch.object(kw, 'run_chunk', side_effect=fake_add1), \
         patch.object(num, 'probe_entry_status', return_value=(False, False)) as probe:
        synthetic_add1 = measure('', False, add_arms, work)
    expect('追補78腕の合成2走・11探り腕各2走', probe.call_count == 22 and all(
           r['statuses']['G_C' if r['arm'].group == 'A' else 'L_C'] == 'agree'
           for r in synthetic_add1))
    with tempfile.TemporaryDirectory(prefix='add1-output-', dir=work) as td:
        path = pathlib.Path(td) / 'predict.tsv'
        write_predict(path, True)
        with path.open(encoding='utf-8') as f:
            predictions = list(csv.DictReader(f, delimiter='\t'))
        expect('predict-add1の全候補390予測', len(predictions) == 390
               and {r['候補'] for r in predictions} == set(BASE_CANDIDATES + NEW_CANDIDATES))
        # 旧候補がagreeでも、新候補だけ全differなら自作LIST行を出す。
        record = dict(round1[0], statuses={c: 'differ' for c in round1[0]['statuses']})
        record['statuses']['G_0'] = 'agree'
        output = io.StringIO()
        with redirect_stdout(output):
            write_measure([record, dict(record, stable=False)], pathlib.Path(td) / 'measure.tsv', True, True)
        expect('show-differsの新候補条件・不安定腕抑制',
               output.getvalue().splitlines().count('a07\t170 GOSUB 0') == 1)

    add2_arms = build_add2_arms()
    expect('追補2 A群60腕・新規18腕・既存42腕不変', len(add2_arms) == 60
           and [replace(a, add2=False) for a in add2_arms[:42]]
               == [a for a in add_arms if a.group == 'A']
           and len({a.id for a in add2_arms}) == 60
           and all(a.group == 'A' and not a.probe and a.typed.isascii()
                   and a.typed == a.typed.lower() for a in add2_arms)
           and all(a.band[0] >= 1000 and a.band[1] <= 1170 for a in add2_arms[42:]))
    expect('追補2でも既存G候補の予測不変', all(
           predict(a, c) == predict(b, c) for a, b in
           zip([a for a in add_arms if a.group == 'A'], add2_arms)
           for c in a.candidates))
    observations_add1 = {'a31': ['410 GOSUB  X'], 'a33': ['430 GOSUB  10'],
                         'a35': ['450 GOSUB:END'], 'a38': ['480 GOSUB  B']}
    with patch.object(kw, 'run_chunk', side_effect=lambda rom, official, lines, work, tag:
                      (observations_add1[tag.split('-')[0]], 0, False)):
        reproduced = measure('', False,
                             [a for a in add2_arms if a.id in observations_add1], work)
    expect('G_E 追補1外れ4腕の合成再現', all(
           r['statuses']['G_E'] == 'agree' and r['stable'] for r in reproduced))
    for body, want in [('go sub10', 'GOSUB 0'), ('go sub:end', 'GOSUB END'),
                       ('go suba', 'GOSUB')]:
        expect('G_E既知観測 ' + body, predict_g(body, 'G_E') == want)
    expect('追補2 G候補の保護文脈', all(
           predict_g(body, c) == predict_g(body, 'G_A')
           for c in ADD2_CANDIDATES for body in
           ('rem go suba', 'print "go suba"', 'data go suba', "'go suba", 'xgo suba')))
    # 親の追補1結果から、入力に対応するLIST署名だけを固定。ROM本文は含まない。
    observed_add1 = {'a01': '9e8824e3a24edaf0', 'a02': '6f0edcdb7b852769', 'a03': 'a703c99917a3e520', 'a04': 'eeeafb45eaca09b8', 'a05': '476df047a417b6e5', 'a06': '3838ed9615c8cb0e', 'a07': 'c1fc01a83f6e76f4', 'a08': '4ad09c86879353f0', 'a09': '8236644488de95df', 'a10': 'ed06d9f23571be47', 'a11': '5c0338941d7f13a0', 'a12': '0759bb1b14574a15', 'a13': '52c98e9aa30b8dc2', 'a14': '4d53c8c55a59aed1', 'a15': 'c1835b9e73cb1d6c', 'a16': '1eb3d32c4e0da7f0', 'a17': 'f2ea6e15e4219b40', 'a18': '697dd45167cbd4b2', 'a19': '139a405d236b5ed3', 'a20': '563092b5c0a445f7', 'a21': 'dd5f8a038a4f984c', 'a22': '5cdc8d6804f9acea', 'a23': 'd6b8ab3329ad767c', 'a24': '8b94f49f581acd53', 'a25': '0c60f1fb980738d0', 'a26': 'c6f368de391cf270', 'a27': '895b43fbf08f73c2', 'a28': '5b8f75ca783e46f0', 'a29': 'ee0a7e08e428b6f6', 'a30': 'c098ed0c7036e512', 'a31': 'a9b0558cb0b27df3', 'a32': '8a69df7bf5c47fbf', 'a33': 'c8d622a43871e196', 'a34': 'b89c0e27371cbab7', 'a35': '132eb433e238857b', 'a36': '3caab1073c57f6bb', 'a37': '3b9585121ad07726', 'a38': 'd4d189b2994ca084', 'a39': 'd4038b1fd6db0dfc', 'a40': '9b2b7b7cf787ac02', 'a41': '6224ef8f98463c27', 'a42': '3c890a4d09a4dfab'}
    with tempfile.TemporaryDirectory(prefix='add2-output-', dir=work) as td:
        path = pathlib.Path(td) / 'predict.tsv'
        write_predict(path, add2=True)
        with path.open(encoding='utf-8') as f:
            predictions = list(csv.DictReader(f, delimiter='\t'))
        expect('predict-add2 A群のみ480予測', len(predictions) == 480
               and all(r['群'] == 'A' for r in predictions)
               and {r['候補'] for r in predictions} == set(add2_arms[0].candidates))
        for c in ADD2_CANDIDATES:
            matching = [r for r in predictions if r['候補'] == c and r['id'] in observed_add1]
            differs = [r['id'] for r in matching if r['署名'] != observed_add1[r['id']]]
            expect(c + ' 既存42腕の署名再現（predict）' + (' 矛盾:' + ','.join(differs) if differs else ''),
                   len(matching) == 42 and not differs)
        record = dict(reproduced[0], statuses={c: 'differ' for c in add2_arms[0].candidates})
        record['statuses']['G_C'] = 'agree'
        output = io.StringIO()
        with redirect_stdout(output):
            write_measure([record, dict(record, stable=False),
                           dict(record, statuses={c: 'gate_failed' for c in record['statuses']})],
                          pathlib.Path(td) / 'measure.tsv', True, add2=True)
        expect('追補2 show-differsの3新候補条件・不安定/関門抑制',
               output.getvalue().splitlines().count('a31\t410 GOSUB  X') == 1)
    with patch.object(kw, 'run_chunk', side_effect=lambda rom, official, lines, work, tag:
                      (predict(next(a for a in add2_arms if a.typed == lines[-1]), 'G_E'), 0, False)) as run, \
         patch.object(num, 'probe_entry_status') as probe:
        synthetic_add2 = measure('', False, add2_arms, work)
    expect('追補2 A群60腕各2走・B探りなし', run.call_count == 120 and probe.call_count == 0
           and all(r['statuses']['G_E'] == 'agree' for r in synthetic_add2))

    add3_arms = build_add3_arms()
    expect('追補3 A群78腕・新規18腕・既存60腕不変', len(add3_arms) == 78
           and [replace(a, add3=False) for a in add3_arms[:60]] == add2_arms
           and len({a.id for a in add3_arms}) == 78
           and all(a.group == 'A' and not a.probe and a.typed == a.typed.lower()
                   and all(32 <= ord(c) <= 126 for c in a.typed) for a in add3_arms)
           and all(2000 <= a.band[0] == a.band[1] <= 2170 for a in add3_arms[60:]))
    expect('追補3でもG_A〜G_Gの予測不変', all(
           predict(a, c) == predict(b, c) for a, b in zip(add2_arms, add3_arms)
           for c in a.candidates))
    for body, want in [('go subx.5', 'GOSUB .5'), ('go subx&h1', 'GOSUB &H1'),
                       ('go sub10', 'GOSUB 0'), ('go subx:end', 'GOSUB:END'),
                       ('go sub1  x', 'GOSUB  X')]:
        expect('G_H既知観測 ' + body, predict_g(body, 'G_H') == want)
    # 親の追補2結果のLIST署名のみ。公式ROMのバイト列・画面本文は含まない。
    observed_add2 = {'a01': '9e8824e3a24edaf0', 'a02': '6f0edcdb7b852769', 'a03': 'a703c99917a3e520', 'a04': 'eeeafb45eaca09b8', 'a05': '476df047a417b6e5', 'a06': '3838ed9615c8cb0e', 'a07': 'c1fc01a83f6e76f4', 'a08': '4ad09c86879353f0', 'a09': '8236644488de95df', 'a10': 'ed06d9f23571be47', 'a11': '5c0338941d7f13a0', 'a12': '0759bb1b14574a15', 'a13': '52c98e9aa30b8dc2', 'a14': '4d53c8c55a59aed1', 'a15': 'c1835b9e73cb1d6c', 'a16': '1eb3d32c4e0da7f0', 'a17': 'f2ea6e15e4219b40', 'a18': '697dd45167cbd4b2', 'a19': '139a405d236b5ed3', 'a20': '563092b5c0a445f7', 'a21': 'dd5f8a038a4f984c', 'a22': '5cdc8d6804f9acea', 'a23': 'd6b8ab3329ad767c', 'a24': '8b94f49f581acd53', 'a25': '0c60f1fb980738d0', 'a26': 'c6f368de391cf270', 'a27': '895b43fbf08f73c2', 'a28': '5b8f75ca783e46f0', 'a29': 'ee0a7e08e428b6f6', 'a30': 'c098ed0c7036e512', 'a31': 'a9b0558cb0b27df3', 'a32': '8a69df7bf5c47fbf', 'a33': 'c8d622a43871e196', 'a34': 'b89c0e27371cbab7', 'a35': '132eb433e238857b', 'a36': '3caab1073c57f6bb', 'a37': '3b9585121ad07726', 'a38': 'd4d189b2994ca084', 'a39': 'd4038b1fd6db0dfc', 'a40': '9b2b7b7cf787ac02', 'a41': '6224ef8f98463c27', 'a42': '3c890a4d09a4dfab', 'a43': 'c20c812c0829e2ae', 'a44': '9accec6dbdae9c5e', 'a45': 'e632f351d2fcd589', 'a46': 'b52e00a30f48ab2d', 'a47': '32750682aae14788', 'a48': '36f9da01f1ae47e7', 'a49': '45ba357582793eb3', 'a50': 'd114f73fb0e90316', 'a51': 'a56629cc8927add7', 'a52': '45fc8a3716c050fc', 'a53': '8b3960a384a4edfd', 'a54': '116f09cbbd8596c9', 'a55': 'cf413737cc3bf6b7', 'a56': 'c4780d6822f22ca1', 'a57': '01f94f1825aae298', 'a58': 'edce4a7e6e1c5bed', 'a59': '0d69e82a0e2eb027', 'a60': '5c4fb4a4eb25d811'}
    with tempfile.TemporaryDirectory(prefix='add3-output-', dir=work) as td:
        path = pathlib.Path(td) / 'predict.tsv'
        write_predict(path, add3=True)
        with path.open(encoding='utf-8') as f:
            predictions = list(csv.DictReader(f, delimiter='\t'))
        expect('predict-add3 A群のみ702予測', len(predictions) == 702
               and all(r['群'] == 'A' for r in predictions)
               and {r['候補'] for r in predictions} == set(add3_arms[0].candidates))
        matching = [r for r in predictions if r['候補'] == 'G_H' and r['id'] in observed_add2]
        differs = [r['id'] for r in matching if r['署名'] != observed_add2[r['id']]]
        expect('G_H 既存60腕の署名再現（predict）' + (' 矛盾:' + ','.join(differs) if differs else ''),
               len(matching) == 60 and not differs)
        with patch.object(kw, 'run_chunk', side_effect=lambda rom, official, lines, work, tag:
                          (predict(next(a for a in add3_arms if a.typed == lines[-1]), 'G_H'), 0, False)) as run, \
             patch.object(num, 'probe_entry_status') as probe:
            synthetic_add3 = measure('', False, add3_arms, work)
        expect('追補3 A群78腕各2走・B探りなし', run.call_count == 156 and probe.call_count == 0
               and all(r['statuses']['G_H'] == 'agree' for r in synthetic_add3))
        record = dict(synthetic_add3[0], statuses={c: 'agree' for c in add3_arms[0].candidates})
        record['statuses']['G_H'] = 'differ'
        output = io.StringIO()
        with redirect_stdout(output):
            write_measure([record, dict(record, stable=False),
                           dict(record, statuses={c: 'gate_failed' for c in record['statuses']})],
                          pathlib.Path(td) / 'measure.tsv', True, add3=True)
        expect('追補3 show-differsのG_H条件・不安定/関門抑制',
               output.getvalue().splitlines().count('a01\t110 GOSUB 0') == 1)

    with tempfile.TemporaryDirectory(prefix='selftest-', dir=work) as td:
        root = pathlib.Path(td)
        rom, asm_work = root / 'rom', root / 'asm'
        built = subprocess.run([sys.executable, str(kw.REPO / 'src/build_main_rom.py'), str(rom),
                                '--work-dir', str(asm_work)],
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        expect('自作ROM一時ビルド', built.returncode == 0)
        if built.returncode == 0:
            records = measure(str(rom), False, subset, work)
            expect('自作ROM G_H/L_C（6腕各2走）', all(
                r['stable'] and r['signatures'] == [signature(predict(r['arm'],
                    'G_H' if r['arm'].group == 'A' else 'L_C'))] * 2 for r in records))

            # 期待値や実装ソースを変えず、詰め処理と途中空白だけをROMで無効化。
            # 命令長を保つため、他の呼び先・レイアウトは動かさない。
            sys.path.insert(0, str(kw.REPO / 'tools/asm'))
            import z80text
            main_asm = z80text.Assembler()
            main_asm.assemble(asm_work / 'n88_main_gen.asm')
            main_rom = bytearray((rom / 'N88.ROM').read_bytes())
            start = main_asm.labels['PARSE_LINENUM']
            end = main_asm.labels['_pln_finish']
            pattern = bytes.fromhex('dd7e00fe2028')  # LD A,(IX); CP ' '; JR Z
            assert main_rom[start:end].count(pattern) == 1
            branch = main_rom.index(pattern, start, end) + len(pattern) - 1
            offset = end - (branch + 2)
            assert -128 <= offset <= 127
            main_rom[branch + 1] = offset & 255
            (rom / 'N88.ROM').write_bytes(main_rom)

            bank_src = root / 'bank3.asm'
            sys.path.insert(0, str(kw.REPO / 'src/ext_bank'))
            from make_ext_rom_banks import BANK3_EXTRA_SOURCES, memmap
            bank_src.write_text(memmap.asm_prelude() + '\n'.join([(kw.REPO / 'src/ext_bank/bank3.asm').read_text(encoding='utf-8')]
                                           + [(kw.REPO / rel).read_text(encoding='utf-8') for rel in BANK3_EXTRA_SOURCES]),
                                encoding='utf-8')
            bank_asm = z80text.Assembler()
            bank_asm.assemble(bank_src)
            bank_rom = bytearray((rom / 'N88_3.ROM').read_bytes())
            entry = bank_asm.labels['LN_GOSUB'] - 0x6000
            assert bank_rom[entry:entry + 3] == bytes([0x3A]) + memmap.addresses()['MM_LN_CHECKONLY'].to_bytes(2, 'little')
            bank_rom[entry:entry + 3] = bytes.fromhex('f601c9')  # OR 1; RET (NZ)
            (rom / 'N88_3.ROM').write_bytes(bank_rom)
            negative_subset = [arms[0], arms[28]]
            records = measure(str(rom), False, negative_subset, work)
            expect('故障ROM陰性対照 G_0/L_0（2腕各2走）', all(
                r['statuses']['G_0' if r['arm'].group == 'A' else 'L_0'] == 'agree' for r in records))
            expect('故障ROMでG_H/L_Cとの差を検出', all(
                r['stable'] and r['signatures'] != [signature(predict(r['arm'],
                    'G_H' if r['arm'].group == 'A' else 'L_C'))] * 2 for r in records))
    return int(bool(failed))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest='cmd', required=True)
    for command in ('predict', 'predict-add1', 'predict-add2', 'predict-add3'):
        p = sub.add_parser(command)
        p.add_argument('--out', type=pathlib.Path, required=True)
    for command in ('measure', 'measure-add1', 'measure-add2', 'measure-add3'):
        m = sub.add_parser(command)
        m.add_argument('--rom-dir', required=True)
        m.add_argument('--out', type=pathlib.Path, required=True)
        m.add_argument('--official', action='store_true')
        m.add_argument('--show-differs', action='store_true')
        m.add_argument('--work-dir', type=pathlib.Path, default=WORK)
    st = sub.add_parser('selftest')
    st.add_argument('--work-dir', type=pathlib.Path, default=WORK)
    ck = sub.add_parser('check')
    ck.add_argument('--rom-dir', required=True)
    ck.add_argument('--expected', type=pathlib.Path, default=EXPECTED)
    args = ap.parse_args()
    if args.cmd == 'selftest':
        return selftest(args.work_dir)
    if args.cmd == 'check':
        return check(args.rom_dir, args.expected)
    add1 = args.cmd.endswith('-add1')
    add2 = args.cmd.endswith('-add2')
    add3 = args.cmd.endswith('-add3')
    if args.cmd in ('predict', 'predict-add1', 'predict-add2', 'predict-add3'):
        write_predict(args.out, add1, add2, add3)
    else:
        write_measure(measure(args.rom_dir, args.official,
                      arms=build_add3_arms() if add3 else (build_add2_arms() if add2 else (build_add1_arms() if add1 else None)), work=args.work_dir),
                      args.out, args.show_differs, add1, add2, add3)
    return 0


if __name__ == '__main__':
    sys.exit(main())
