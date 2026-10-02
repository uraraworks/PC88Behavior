#!/usr/bin/env python3
"""l4-s5i: LIST数値定数の測定器具と事前登録候補N_A。

測定の打鍵・行抽出はlistkwと共有する。各腕2走。画面全体は出力しない。
期待値は親が測定後に作る tests/conformance/expected_l4_listnum.tsv。
"""
from __future__ import annotations

import argparse
from fractions import Fraction
import pathlib
import sys
import tempfile

import l4_listkw_measure as kw
import l4_mbf_oracle_v11_away as away

oracle = away.oracle
EXPECTED = kw.REPO / 'tests/conformance/expected_l4_listnum.tsv'


def build_arms_s5i() -> list[tuple[str, str]]:
    # 表の16/17/20桁・18桁小数も具体化。正本はこの順序で固定する。
    groups = [
        ('n1', '0 007 32767 32768 65535 100000 1234567 9999999 10000000 12345678 123456789 1234567890123456 12345678901234567 12345678901234567890 00000000 32766 32769 999999 99999999'.split()),
        ('n2', '.5 0.5 00.5 1. 1.0 1.50 3.141592 3.1415926 3.14159265 .0000001 123456.7 1234567.8 .123456789012345678 0.0 .0001 .00001 .000001 .00000001'.split()),
        ('n3', '1e5 1e6 1e7 1e-3 1.5e-3 1e-7 1e-8 1e16 1e17 1e38 1e+5 1e 1e+ 2.5e3 0e5 1e-'.split()),
        ('n4', '1d5 1d16 1d17 1d-3 1.5d-3 1d 1d+ 1d- 1d-16 1d-17'.split()),
        ('n5', '1% 1! 1# 1.5! 1.5# 1.5% 32768% 2! 100000# 1e5# 1d5! 12345678! 1234567# 0! 0# 0%'.split()),
        ('n6', '&h10 &hff &h0010 &hffff &h7fff &h8000 &h &10 &o17 &o &0 & &77777 &177777 &b101 &o0017 &h0'.split()),
        ('n7', ['1 2', '1 .5', '1 e5', '1. 5', '1 %', '12 34 56 78', '&h 10', '& 10', '1 d5', '1 e + 5', '1 #']),
        ('n8', ['1rem', '1data', '1end', '1e5rem', '1else', '1d5e', '1:rem x', '1 rem x end', '1remabc', '1 data x end']),
    ]
    arms = [(f'{group}-{i:02d}', 'a=' + value)
            for group, values in groups for i, value in enumerate(values, 1)]
    contexts = ['print 1e5', '?0.5', 'a=-1e5', 'a=b*007', 'data 1e5,0.5',
                'print "1e5"', 'rem 1e5', "' 1e5", 'goto 0010', 'gosub 007',
                'if a then 0020', 'on a goto 010,020', 'x=1rem x end']
    arms.extend((f'n9-{i:02d}', body) for i, body in enumerate(contexts, 1))
    return arms


def _number(body: str, start: int, skip_spaces: bool, suffixes: bool) -> tuple[str, int]:
    """空白は次の数値文字を受理する時だけ消費し、語前の空白は残す。"""
    n = len(body)
    i = start

    def next_at(k):
        if skip_spaces:
            while k < n and body[k] == ' ':
                k += 1
        return k

    if body[i] == '&':
        i += 1
        k = next_at(i)
        base = 8
        prefix = '&O'
        if k < n and body[k] in 'ho':
            base = 16 if body[k] == 'h' else 8
            prefix = '&H' if base == 16 else '&O'
            i = k + 1
        digits = ''
        valid = '0123456789abcdef' if base == 16 else '01234567'
        while (k := next_at(i)) < n and body[k] in valid:
            digits += body[k]
            i = k + 1
        value = int(digits or '0', base)
        return prefix + format(value, 'X' if base == 16 else 'o'), i

    mantissa = ''
    dot = False
    while (k := next_at(i)) < n:
        c = body[k]
        if c.isdigit() or (c == '.' and not dot):
            dot |= c == '.'
            mantissa += c
            i = k + 1
        else:
            break
    exponent = ''
    exp_digits = ''
    exp_sign = ''
    k = next_at(i)
    if k < n and body[k] in 'ed':
        exponent = body[k]
        i = k + 1
        k = next_at(i)
        if k < n and body[k] in '+-':
            exp_sign = body[k]
            i = k + 1
        while (k := next_at(i)) < n and body[k].isdigit():
            exp_digits += body[k]
            i = k + 1
    mark = ''
    k = next_at(i)
    if k < n and body[k] in '%!#':
        mark = body[k]
        i = k + 1
    value = Fraction(mantissa if mantissa != '.' else '0')
    power = int((exp_sign or '+') + (exp_digits or '0'))
    value *= Fraction(10) ** power
    if mark:
        kind = {'%': 'int', '!': 'single', '#': 'double'}[mark]
    elif exponent:
        kind = 'double' if exponent == 'd' else 'single'
    elif not dot and value <= 32767:
        kind = 'int'
    else:
        digits = mantissa.replace('.', '').lstrip('0')
        kind = 'double' if len(digits) >= 8 else 'single'
    if kind == 'int':
        # N_Aは整数の10進書き出しのみ。範囲・実行時のエラーは測定対象外。
        return str(int(value)), i
    number = (away.encode_single_away(value) if kind == 'single'
              else oracle.GwNum.from_fraction(value, 'double'))
    # l4_mbf_conform.expected_fout / expected_dfout と同じPRINT書式。
    # n88=True: single=6桁/LEN7、double=16桁/rstar、指数文字E/D。
    text, _ = oracle.fout_format(number, n88=True, fout_algo='gw')
    if suffixes:
        if kind == 'double' and 'D' not in text:
            text += '#'
        elif kind == 'single' and '.' not in text and 'E' not in text:
            text += '!'
    return text, i


def _predict(body: str, *, skip_spaces=True, suffixes=True) -> str:
    # 非数値の枝はpredict_body_cと同じ。14.1(5)の?直前の空白も扱う。
    body = body.lower()
    out = []
    i, n = 0, len(body)

    def namech(c):
        return c.isascii() and (c.isalnum() or c == '.')

    def run_at(k):
        j = k
        while j < n and namech(body[j]):
            j += 1
        return body[k:j]

    def quoted(k):
        j = body.find('"', k + 1)
        j = n if j < 0 else j + 1
        out.append(body[k:j])
        return j

    while i < n:
        c = body[i]
        if c == '"':
            i = quoted(i)
        elif c == "'":
            out.append(body[i:])
            break
        elif c == '?':
            if i and namech(body[i - 1]):
                out.append(' ')
            nxt = body[i + 1:i + 2]
            out.append('PRINT' + (' ' if nxt and (namech(nxt) or nxt == '&') else ''))
            i += 1
        elif c.isdigit() or c == '&' or (c == '.' and body[i + 1:i + 2].isdigit()):
            text, i = _number(body, i, skip_spaces, suffixes)
            out.append(text)
            if run_at(i) == 'rem':
                out.append(' ')
        elif namech(c):
            word = run_at(i)
            if word == 'rem':
                out.extend(['REM', body[i + 3:]])
                break
            if word == 'data':
                out.append('DATA')
                i += 4
                while i < n and body[i] != ':':
                    if body[i] == '"':
                        i = quoted(i)
                    else:
                        out.append(body[i])
                        i += 1
                continue
            if word == 'go' and body[i + 2:i + 3] == ' ':
                second = run_at(i + 3)
                if second in ('to', 'sub'):
                    out.append('GOTO' if second == 'to' else 'GOSUB')
                    i += 3 + len(second)
                    continue
            out.append(word.upper())
            i += len(word)
        else:
            out.append(c)
            i += 1
    return ''.join(out)


def predict_body_n_a(body: str) -> str:
    return _predict(body)


def predicted_list_text(lineno, body):
    return f'{lineno} {predict_body_n_a(body.lstrip(" "))}'


def classify(first, second, prediction):
    if first is None or second is None:
        return 'gate_failed'
    if first != second:
        return 'unstable'
    return 'agree' if first == prediction else 'differ'


def measure(rom_dir: str, official: bool) -> list[dict]:
    records = []
    with tempfile.TemporaryDirectory() as td:
        work = pathlib.Path(td)
        for k, chunk in kw.chunk_arms(build_arms_s5i()):
            typed = [kw.line_text((j + 1) * 10, b) for j, (_, b) in enumerate(chunk)]
            runs = []
            for repeat in range(2):
                listed, other, untypable = kw.run_chunk(rom_dir, official, typed, work, f'c{k:04d}r{repeat}')
                by_no = {}
                for row in listed:
                    digits = ''
                    for ch in row.lstrip(' '):
                        if not ch.isdigit():
                            break
                        digits += ch
                    no = int(digits)
                    by_no.setdefault(no, []).append(row)
                gate = not untypable and len(listed) == len(chunk)
                runs.append((by_no, gate, other))
            for j, (aid, body) in enumerate(chunk):
                no = (j + 1) * 10
                observations = []
                for by_no, gate, _ in runs:
                    rows = by_no.get(no, [])
                    observations.append(rows[0] if gate and len(rows) == 1 else None)
                pred = predicted_list_text(no, body)
                records.append(dict(id=aid, typed=typed[j], obs=observations,
                                    obs_sig=[kw.sig(v) if v is not None else 'gate_failed' for v in observations],
                                    pred=pred, pred_sig=kw.sig(pred),
                                    status=classify(*observations, pred)))
    return records


def cmd_measure(a):
    records = measure(a.rom_dir, a.official)
    with open(a.out, 'w', encoding='utf-8') as f:
        f.write('# id\tobs_sig\tobs_run2_sig\tpred_NA_sig\tstatus\n')
        for r in records:
            f.write('\t'.join([r['id'], *r['obs_sig'], r['pred_sig'], r['status']]) + '\n')
    counts = {s: sum(r['status'] == s for r in records)
              for s in ('agree', 'differ', 'unstable', 'gate_failed')}
    holds = counts['agree'] == len(records)
    print(f'arms={len(records)} ' + ' '.join(f'{s}={v}' for s, v in counts.items())
          + (' N_A_holds' if holds else ' N_A_partial'))
    print('differ_by_group=' + ','.join(f'{g}:{sum(r["status"] == "differ" and r["id"].startswith(g + "-") for r in records)}' for g in (f'n{i}' for i in range(1, 10))))
    if a.show_differs:
        for r in records:
            if r['status'] == 'differ':
                print(f'{r["id"]}\t{r["typed"]}\t=>\t{r["obs"][0]}\t(N_A: {r["pred"]})')
    return int(bool(counts['gate_failed'] or counts['unstable']))


def cmd_check(a):
    expected = {}
    excluded = set()
    for line in pathlib.Path(a.expected).read_text(encoding='utf-8').splitlines():
        if line.startswith('# excluded\t'):
            excluded.update(line.split('\t')[1].split(','))
        elif line and not line.startswith('#'):
            fields = line.split('\t')
            if fields[0] in expected:
                raise SystemExit('期待値のid重複')
            expected[fields[0]] = fields[1]
    records = measure(a.rom_dir, False)
    bad = 0
    for r in records:
        if r['id'] in excluded:
            continue
        if r['status'] in ('gate_failed', 'unstable') or any(s != expected.get(r['id']) for s in r['obs_sig']):
            bad += 1
            print(f'NG {r["id"]}: 署名不一致・欠落・関門失敗')
            if a.show_differs:
                print(f'{r["typed"]}\t=>\t{r["obs"]}')
    ids = {r['id'] for r in records}
    for aid in sorted(((set(expected) | excluded) - ids) | (set(expected) & excluded)):
        bad += 1
        print(f'NG {aid}: 期待値/除外のid不整合')
    print(f'arms={len(records)} checked={len(ids - excluded)} excluded={len(excluded)} ng={bad}')
    return int(bad != 0)


def cmd_predict(a):
    # 測定と同じ15行ずつの行番号割り振り。
    for _, chunk in kw.chunk_arms(build_arms_s5i()):
        for j, (aid, body) in enumerate(chunk):
            print(f'{aid}\t{predicted_list_text((j + 1) * 10, body)}')
    return 0


EXAMPLES = {
    '1e5': '100000!', '1d5': '100000#', '1.5e-3': '.0015', '0.5': '.5',
    '007': '7', '100000': '100000!', '1.': '1!', '1.0': '1!',
    '123456789': '123456789#', '12345678901234567890': '1.234567890123457D+19',
    '1%': '1', '&10': '&O10', '&b101': '&O0B101',
    '1.5': '1.5', '1.5#': '1.5#', '2!': '2!', '.5': '.5', '1!': '1!', '1#': '1#',
    '&h10': '&H10', '&o17': '&O17',
}
CASES = {'a=' + b: 'A=' + v for b, v in EXAMPLES.items()}
CASES.update({'x=1rem x end': 'X=1 REM x end', 'a=1 data x end': 'A=1#ATA X END'})


def cmd_selftest(a):
    fails = []

    def expect(name, cond):
        print(('OK  ' if cond else 'NG  ') + name)
        if not cond:
            fails.append(name)

    for body, want in CASES.items():
        expect(f'N_A例: {body}', predict_body_n_a(body) == want)
    for fault, options in [('空白読み飛ばしなし', dict(skip_spaces=False)),
                           ('型印付与なし', dict(suffixes=False))]:
        expect('故障検出: ' + fault, any(_predict(b, **options) != want for b, want in CASES.items()))
    contexts = {'data 1e5,"a:b":?0.5': 'DATA 1e5,"a:b":PRINT .5',
                'print "1e5"': 'PRINT "1e5"', 'rem 1e5': 'REM 1e5', "' 1e5": "' 1e5",
                'x1e5=007': 'X1E5=7', '?a?b': 'PRINT A PRINT B', 'go to 0010': 'GOTO 10',
                'go  to 0010': 'GO  TO 10', 'go to10': 'GO TO10', 'a=1 2': 'A=12'}
    for body, want in contexts.items():
        expect('文脈: ' + body, predict_body_n_a(body) == want)

    def mk(rows):
        data = bytearray(b' ' * (kw.STRIDE * kw.ROWS))
        for r, text in rows.items():
            data[r * kw.STRIDE:r * kw.STRIDE + kw.COLS] = text.encode('latin-1').ljust(kw.COLS, b' ')
        return bytes(data)

    listed, other = kw.extract_list_lines(mk({0: 'list', 1: '10 PRINT 1', 2: 'Ok'}))
    expect('取り出し陽性対照', listed == ['10 PRINT 1'])
    expect('非数値行陰性対照', other == 2)
    listed, other = kw.extract_list_lines(mk({1: '10 \xb1\xb2'}))
    expect('ASCII外陰性対照', listed == [] and other == 1)
    expect('2走判定', [classify(*v) for v in [('a', 'a', 'a'), ('b', 'b', 'a'), ('a', 'b', 'a'), (None, 'a', 'a')]] == ['agree', 'differ', 'unstable', 'gate_failed'])
    arms = build_arms_s5i()
    expect('腕のid一意・全群', len({aid for aid, _ in arms}) == len(arms) and {aid.split('-')[0] for aid, _ in arms} == {f'n{i}' for i in range(1, 10)})
    expect('腕は小文字・ASCII・80桁未満', all(b == b.lower() and b.isascii() and len(b) < 70 for _, b in arms))
    expect('全腕の予測が完了', all(predicted_list_text(150, b).isascii() for _, b in arms))
    # 自作の合成LIST行で実際の2走集計を通す。コア・ROMは起動しない。
    from unittest.mock import patch

    def fake_run(rom_dir, official, lines, work, tag):
        rows = []
        for line in lines:
            no, body = line.split(' ', 1)
            rows.append(predicted_list_text(int(no), body))
        return rows, 2, False

    with patch.object(kw, 'run_chunk', side_effect=fake_run) as runner:
        records = measure('synthetic-unused', False)
        expect('合成測定陽性: 全130腕2走一致', len(records) == len(arms)
               and all(r['status'] == 'agree' for r in records)
               and runner.call_count == 2 * len(list(kw.chunk_arms(arms))))

    def unstable_run(*args):
        rows, other, untypable = fake_run(*args)
        if args[-1] == 'c0000r1':
            rows[0] += '!'
        return rows, other, untypable

    with patch.object(kw, 'run_chunk', side_effect=unstable_run):
        records = measure('synthetic-unused', False)
        expect('合成測定陰性: 2走差を検出', records[0]['status'] == 'unstable'
               and sum(r['status'] == 'unstable' for r in records) == 1)

    def missing_run(*args):
        rows, other, untypable = fake_run(*args)
        if args[-1] == 'c0000r1':
            rows.pop()
        return rows, other, untypable

    with patch.object(kw, 'run_chunk', side_effect=missing_run):
        records = measure('synthetic-unused', False)
        expect('合成測定陰性: 行欠落を関門で検出',
               sum(r['status'] == 'gate_failed' for r in records) == kw.LINES_PER_RUN)
    print(f'arms={len(arms)} ng={len(fails)}')
    return int(bool(fails))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest='cmd', required=True)
    m = sub.add_parser('measure')
    m.add_argument('--rom-dir', required=True)
    m.add_argument('--out', required=True)
    m.add_argument('--official', action='store_true')
    m.add_argument('--show-differs', action='store_true')
    c = sub.add_parser('check')
    c.add_argument('--rom-dir', required=True)
    c.add_argument('--expected', default=str(EXPECTED))
    c.add_argument('--show-differs', action='store_true')
    sub.add_parser('predict')
    sub.add_parser('selftest')
    a = ap.parse_args()
    return {'measure': cmd_measure, 'check': cmd_check, 'predict': cmd_predict, 'selftest': cmd_selftest}[a.cmd](a)


if __name__ == '__main__':
    sys.exit(main())
