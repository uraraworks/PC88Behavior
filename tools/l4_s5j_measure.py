#!/usr/bin/env python3
"""l4-s5j: GO SUBと行番号の空白の測定器具。画面本文は出力しない。"""
import argparse
import csv
from dataclasses import dataclass
import pathlib
import re
import subprocess
import sys
import tempfile
from unittest.mock import patch

import l4_listkw_measure as kw
import l4_listnum_measure as num

WORK = kw.REPO.parent / 'tmp/l4s5j-work'


@dataclass(frozen=True)
class Arm:
    id: str
    group: str
    typed: str
    seed: tuple[str, ...] = ()
    probe: bool = False

    @property
    def candidates(self):
        return ('G_A', 'G_B', 'G_0') if self.group == 'A' else ('L_A', 'L_B', 'L_0')

    @property
    def band(self):
        # 両候補の番号の間を含める。位置・予測番号による対応づけはしない。
        first = int(re.match(r'[0-9]+', self.typed)[0])
        spaced = int(re.match(r'[0-9 ]+', self.typed)[0].replace(' ', ''))
        numbers = [first, spaced, *(int(s.split(' ')[0]) for s in self.seed)]
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
        if not 0 <= no <= 65529:
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
            for repeat in range(2):
                listed, other, untypable = kw.run_chunk(rom_dir, official,
                    [*arm.seed, arm.typed], pathlib.Path(td), f'{arm.id}-r{repeat}')
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
            stable = signatures[0] == signatures[1] and entries[0] == entries[1]
            if entries[0] != entries[1]:
                statuses = {c: 'unstable' for c in arm.candidates}
            records.append(dict(arm=arm, obs=observations, signatures=signatures,
                                entries=entries, others=others, stable=stable,
                                predictions=predictions, statuses=statuses))
    return records


def write_predict(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8', newline='') as f:
        writer = csv.writer(f, delimiter='\t')
        writer.writerow(['id', '群', '打った行', '先行入力', '番号帯', '候補', '予測行', '署名'])
        for arm in build_arms():
            for c in arm.candidates:
                rows = predict(arm, c)
                writer.writerow([arm.id, arm.group, arm.typed, '\\n'.join(arm.seed),
                                 f'{arm.band[0]}-{arm.band[1]}', c, '\\n'.join(rows), signature(rows)])


def write_measure(records, path, show_differs):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8', newline='') as f:
        writer = csv.writer(f, delimiter='\t')
        writer.writerow(['id', '群', '打った行', '走1署名', '走2署名', '一致',
                         'G_A', 'G_B', 'G_0', 'L_A', 'L_B', 'L_0',
                         '走1番号2含む', '走1番号2完全一致', '走2番号2含む', '走2番号2完全一致',
                         '走1他行件数', '走2他行件数'])
        for r in records:
            arm = r['arm']
            entry = [int(v) for run in r['entries'] for v in run] if arm.probe else [''] * 4
            writer.writerow([arm.id, arm.group, arm.typed, *r['signatures'],
                             'stable' if r['stable'] else 'unstable',
                             *(r['statuses'].get(c, '') for c in ('G_A', 'G_B', 'G_0', 'L_A', 'L_B', 'L_0')),
                             *entry, *r['others']])
            if show_differs and all(v == 'differ' for v in r['statuses'].values()):
                print(arm.id + '\t' + '\\n'.join(r['obs'][0]))
    for c in ('G_A', 'G_B', 'G_0', 'L_A', 'L_B', 'L_0'):
        print(c + ' ' + ' '.join(f'{s}={sum(r["statuses"].get(c) == s for r in records)}'
              for s in ('agree', 'differ', 'unstable', 'gate_failed')))


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
    with tempfile.TemporaryDirectory(prefix='selftest-', dir=work) as td:
        rom = pathlib.Path(td) / 'rom'
        built = subprocess.run([sys.executable, str(kw.REPO / 'src/build_main_rom.py'), str(rom)],
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        expect('自作ROM一時ビルド', built.returncode == 0)
        if built.returncode == 0:
            records = measure(str(rom), False, subset, work)
            expect('自作ROM陰性対照 G_0/L_0（6腕各2走）', all(
                r['statuses']['G_0' if r['arm'].group == 'A' else 'L_0'] == 'agree' for r in records))
            expect('自作ROMで新候補との差を検出', records[0]['statuses']['G_A'] == 'differ'
                   and records[2]['statuses']['L_A'] == 'differ')
    return int(bool(failed))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('predict')
    p.add_argument('--out', type=pathlib.Path, required=True)
    m = sub.add_parser('measure')
    m.add_argument('--rom-dir', required=True)
    m.add_argument('--out', type=pathlib.Path, required=True)
    m.add_argument('--official', action='store_true')
    m.add_argument('--show-differs', action='store_true')
    m.add_argument('--work-dir', type=pathlib.Path, default=WORK)
    st = sub.add_parser('selftest')
    st.add_argument('--work-dir', type=pathlib.Path, default=WORK)
    args = ap.parse_args()
    if args.cmd == 'selftest':
        return selftest(args.work_dir)
    if args.cmd == 'predict':
        write_predict(args.out)
    else:
        write_measure(measure(args.rom_dir, args.official, work=args.work_dir), args.out, args.show_differs)
    return 0


if __name__ == '__main__':
    sys.exit(main())
