#!/usr/bin/env python3
"""l4-s5i: LIST数値定数の測定器具と候補N_A・追補1候補N_B。

測定の打鍵・行抽出はlistkwと共有する。各腕2走。画面全体は出力しない。
期待値は親が測定後に作る tests/conformance/expected_l4_listnum.tsv。

追補1: predict-add1 は作業TSVを生成、measure-add1 は159腕を2走する。
probe-entry --arm ID（または --body BODY）はnew後の単独入力を探り、
エラー表と完全一致した番号だけを出す。追補1の観測本文は出力しない。
selftest は合成検査に加え、一時ビルドした自作ROMで探りの対照を検査する。
"""
from __future__ import annotations

import argparse
import os
import subprocess
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


class EntryOverflow(Exception):
    """N_B が行の入力拒否を予測する。"""


def build_arms_s5i_add1() -> list[tuple[str, str, bool]]:
    """(id, 本文, 観察腕)。初回の順序と本文を維持する。"""
    arms = [(aid, body, False) for aid, body in build_arms_s5i()]
    groups = [
        ('round', ['1.4%', '2.5%', '.5%', '0.49%', '32767.4%', '3.5%']),
        ('entry', ['32767.5%', '40000%', '1e39', '1d39', '&h10000', '&o200000']),
        ('mark', ['1e5!', '1e5%', '1d5#', '1e2#', '1d2%', '1.5e1!']),
        ('space', ['&h1 0', '&o 7', '&o1 7', '&1 0', '&  10', '&h 0']),
        ('else', ['1e5else', '1elsex', '1els', '10else', '1.5else']),
    ]
    for group, values in groups:
        for i, value in enumerate(values, 1):
            body = 'if a then 10else 20' if value == '10else' else 'a=' + value
            arms.append((f'add1-{group}-{i:02d}', body, group == 'entry' and i >= 3))
    return arms


def _number(body: str, start: int, skip_spaces: bool, suffixes: bool, n_b=False) -> tuple[str, int]:
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
            if n_b:
                skip_spaces = False
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
    if k < n and body[k] in 'ed' and not (n_b and body.startswith('else', k)):
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
    if k < n and body[k] in '%!#' and not (n_b and exponent):
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
        if n_b and mark == '%':
            shifted = value + Fraction(1, 2)
            rounded = shifted.numerator // shifted.denominator
            if rounded > 32767:
                raise EntryOverflow
            return str(rounded), i
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


def _predict(body: str, *, skip_spaces=True, suffixes=True, n_b=False) -> str:
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
            text, i = _number(body, i, skip_spaces, suffixes, n_b)
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


def predict_body_n_b(body: str) -> str | None:
    try:
        return _predict(body, n_b=True)
    except EntryOverflow:
        return None


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


def entry_error_numbers(data: bytes) -> list[int]:
    """画面行を内部で完全一致比較し、番号だけ返す。"""
    if len(data) < kw.STRIDE * kw.ROWS:
        raise ValueError('画面写しが短い')
    messages = {}
    for line in (kw.REPO / 'src/l4_basic/errors.tsv').read_text(encoding='utf-8').splitlines():
        if line and not line.startswith('#'):
            number, message = line.split('\t')
            messages[message.encode('ascii')] = int(number)
    found = set()
    for r in range(kw.ROWS):
        row = data[r * kw.STRIDE:r * kw.STRIDE + kw.COLS].strip(b' ')
        if row in messages:
            found.add(messages[row])
    return sorted(found)


def probe_entry(rom_dir: str, official: bool, body: str, *, lineno=10) -> list[int]:
    # 行番号付きの1行を入力する。実行やclsはしない。
    if not body.isascii() or body != body.lower() or '\n' in body or '\r' in body:
        raise ValueError('本文は改行なしの小文字ASCIIで指定する')
    with tempfile.TemporaryDirectory() as td:
        dump = pathlib.Path(td) / 'entry.bin'
        txt = 'new\n' + kw.line_text(lineno, body) + '\n'
        start = 420 if official else 60
        frame = start + 8 * len(txt) + 600
        args = [str(kw.FRONT), '--core', str(kw.find_core()), '--rom-dir', rom_dir,
                '--frames', str(frame + 50)]
        if official:
            args += ['--type-at', '300', '--type', '\n']
        args += ['--type-at', str(start), '--type', txt,
                 '--vram-dump', str(dump), '--vram-dump-at', str(frame)]
        p = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                           env=dict(os.environ, M6FH_LONG_TYPING='1'))
        err = p.stderr.decode('utf-8', errors='replace').lower()
        if p.returncode or 'untypable' in err or '打てない' in err:
            raise SystemExit('入力時エラーの探りに失敗')
        return entry_error_numbers(dump.read_bytes())


def classify_add1(first, second, prediction, observation=False, gates=(True, True)):
    if not all(gates):
        return 'differ'
    if observation:
        return 'observed'
    if first != second:
        return 'unstable'
    return 'agree' if first == prediction else 'differ'


def measure_add1(rom_dir: str, official: bool) -> list[dict]:
    records = []
    with tempfile.TemporaryDirectory() as td:
        work = pathlib.Path(td)
        for k, chunk in kw.chunk_arms(build_arms_s5i_add1()):
            typed = [kw.line_text((j + 1) * 10, b) for j, (_, b, _) in enumerate(chunk)]
            predictions = [None if observed else predict_body_n_b(b) for _, b, observed in chunk]
            runs = []
            for repeat in range(2):
                listed, _, untypable = kw.run_chunk(rom_dir, official, typed, work, f'add1c{k:04d}r{repeat}')
                by_no = {}
                for row in listed:
                    digits = ''
                    for ch in row.lstrip(' '):
                        if not ch.isdigit():
                            break
                        digits += ch
                    no = int(digits)
                    by_no.setdefault(no, []).append(row)
                # 予測拒否・観察欠落を除外。予測入場の欠落は腕単位のdifferにする。
                required = {(j + 1) * 10 for j, (_, _, observed) in enumerate(chunk)
                            if predictions[j] is not None and not observed}
                optional = set(range(10, 10 * len(chunk) + 1, 10)) - required
                expected_count = len(required) + sum(no in by_no for no in optional)
                missing_required = sum(no not in by_no for no in required)
                gate = (not untypable and len(listed) == expected_count - missing_required
                        and set(by_no) <= required | optional
                        and all(len(rows) == 1 for rows in by_no.values()))
                errors = {no: probe_entry(rom_dir, official, body)
                          for j, (_, body, _) in enumerate(chunk)
                          if (no := (j + 1) * 10) not in by_no}
                runs.append((by_no, gate, errors))
            for j, (aid, _, observed) in enumerate(chunk):
                no = (j + 1) * 10
                obs = [run[0].get(no, [None])[0] for run in runs]
                pred = None if predictions[j] is None else f'{no} {predictions[j]}'
                gates = [run[1] for run in runs]
                errors = [run[2].get(no, []) for run in runs]
                status = classify_add1(*obs, pred, observed, gates)
                if not observed and all(gates) and obs == [None, None] and errors[0] != errors[1]:
                    status = 'unstable'
                records.append(dict(id=aid, observation=observed, obs=obs, pred=pred,
                                    gates=gates, errors=errors, status=status))
    return records


def cmd_measure_add1(a):
    records = measure_add1(a.rom_dir, a.official)
    with open(a.out, 'w', encoding='utf-8') as f:
        f.write('# id\tobservation\tobs_sig\tobs_run2_sig\tpred_NB_sig\tentry_errors\tentry_errors_run2\tgate_run1\tgate_run2\tstatus\n')
        for r in records:
            fields = [r['id'], str(int(r['observation'])),
                      *[kw.sig(v) if v is not None else 'absent' for v in r['obs']],
                      'observational' if r['observation'] else (kw.sig(r['pred']) if r['pred'] is not None else 'absent'),
                      *[','.join(map(str, nums)) for nums in r['errors']],
                      *[str(int(v)) for v in r['gates']], r['status']]
            f.write('\t'.join(fields) + '\n')
    counts = {s: sum(r['status'] == s for r in records) for s in ('agree', 'differ', 'unstable', 'observed')}
    holds = not counts['differ'] and not counts['unstable']
    print(f'arms={len(records)} ' + ' '.join(f'{s}={v}' for s, v in counts.items())
          + (' N_B_holds' if holds else ' N_B_partial'))
    return int(any(not all(r['gates']) or r['status'] == 'unstable' for r in records))


def cmd_probe_entry(a):
    body = a.body
    if a.arm:
        arms = {aid: b for aid, b, _ in build_arms_s5i_add1()}
        if a.arm not in arms:
            raise SystemExit('未知の腕id')
        body = arms[a.arm]
    for number in probe_entry(a.rom_dir, a.official, body):
        print(number)
    return 0


def cmd_predict_add1(a):
    path = pathlib.Path(a.out)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8') as f:
        f.write('# id\tobservation\tprediction\n')
        for _, chunk in kw.chunk_arms(build_arms_s5i_add1()):
            for j, (aid, body, observed) in enumerate(chunk):
                pred = None if observed else predict_body_n_b(body)
                value = 'observational' if observed else ('None' if pred is None else f'{(j + 1) * 10} {pred}')
                f.write(f'{aid}\t{int(observed)}\t{value}\n')
    print(f'arms={len(build_arms_s5i_add1())} out={path}')
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

    round1 = {
        'a=1.5%': 'A=2', 'a=32768%': None,
        'a=1e5#': 'A=100000!#', 'a=1d5!': 'A=100000#!',
        'a=&h 10': 'A=&H0 10', 'a=1else': 'A=1ELSE',
    }
    for i, (body, want) in enumerate(round1.items(), 1):
        expect(f'追補1既知腕{i}: N_B再現・N_A不一致',
               predict_body_n_b(body) == want and predict_body_n_a(body) != want)
    boundaries = {
        'a=1.4%': 'A=1', 'a=2.5%': 'A=3', 'a=.5%': 'A=1',
        'a=0.49%': 'A=0', 'a=32767.4%': 'A=32767', 'a=3.5%': 'A=4',
        'a=32767.5%': None, 'a=40000%': None,
        'a=1e5%': 'A=100000!%', 'a=1d2%': 'A=100#%',
        'a=&h1 0': 'A=&H1 0', 'a=&o 7': 'A=&O0 7',
        'a=&o1 7': 'A=&O1 7', 'a=&1 0': 'A=&O10', 'a=&  10': 'A=&O10',
        'a=1e5else': 'A=100000!ELSE', 'a=1elsex': 'A=1ELSEX',
        'a=1els': 'A=1!LS', 'a=1.5else': 'A=1.5ELSE',
        'if a then 10else 20': 'IF A THEN 10ELSE 20',
    }
    expect('追補1境界の予測', all(predict_body_n_b(b) == w for b, w in boundaries.items()))
    addarms = build_arms_s5i_add1()
    expect('追補1の腕: 初回維持・159腕・観察4腕・小文字',
           [(aid, b) for aid, b, _ in addarms[:130]] == arms
           and len(addarms) == len({aid for aid, _, _ in addarms}) == 159
           and sum(o for _, _, o in addarms) == 4
           and all(b == b.lower() and b.isascii() and len(b) < 70 for _, b, _ in addarms))
    expect('エラー照合: 完全一致・番号のみ',
           entry_error_numbers(mk({0: 'Overflow', 1: 'Syntax error', 2: 'Syntax error suffix'})) == [2, 6]
           and entry_error_numbers(mk({0: '10 a=1', 1: 'Ok'})) == [])

    def fake_add1(rom_dir, official, lines, work, tag):
        rows = []
        for line in lines:
            no, body = line.split(' ', 1)
            # 観察腕は欠落と入場を混在させる。
            if body in ('a=1e39', 'a=&h10000'):
                continue
            pred = 'A=1' if body in ('a=1d39', 'a=&o200000') else predict_body_n_b(body)
            if pred is not None:
                rows.append(f'{no} {pred}')
        return rows, 2, False

    with patch.object(kw, 'run_chunk', side_effect=fake_add1), patch(__name__ + '.probe_entry', return_value=[6]) as prober:
        records = measure_add1('synthetic-unused', False)
        expect('追補1合成2走: 拒否・観察欠落が関門へ波及しない',
               all(all(r['gates']) for r in records)
               and sum(r['status'] == 'agree' for r in records) == 155
               and sum(r['status'] == 'observed' for r in records) == 4
               and prober.call_count == 10
               and all(r['errors'] == [[6], [6]] for r in records if r['obs'] == [None, None]))

    def missing_add1(*args):
        rows, other, untypable = fake_add1(*args)
        if args[-1].startswith('add1c0000'):
            rows.pop(0)
        return rows, other, untypable

    with patch.object(kw, 'run_chunk', side_effect=missing_add1), patch(__name__ + '.probe_entry', return_value=[]):
        records = measure_add1('synthetic-unused', False)
        expect('追補1合成陰性: 予測入場の欠落は当該腕だけdiffer',
               records[0]['status'] == 'differ' and all(records[0]['gates'])
               and all(r['status'] == 'agree' for r in records[1:15]))

    def unstable_add1(*args):
        rows, other, untypable = fake_add1(*args)
        if args[-1] == 'add1c0000r1':
            rows.pop(0)
        return rows, other, untypable

    with patch.object(kw, 'run_chunk', side_effect=unstable_add1), patch(__name__ + '.probe_entry', return_value=[]):
        records = measure_add1('synthetic-unused', False)
        expect('追補1合成陰性: 片走だけの欠落はunstable',
               records[0]['status'] == 'unstable' and all(records[0]['gates'])
               and all(r['status'] == 'agree' for r in records[1:15]))

    for fault in ('duplicate', 'unexpected', 'untypable'):
        def broken_add1(*args):
            rows, other, untypable = fake_add1(*args)
            if args[-1].startswith('add1c0000'):
                if fault == 'duplicate':
                    rows.append(rows[0])
                elif fault == 'unexpected':
                    rows.append('999 A=1')
                else:
                    untypable = True
            return rows, other, untypable

        with patch.object(kw, 'run_chunk', side_effect=broken_add1), patch(__name__ + '.probe_entry', return_value=[]):
            records = measure_add1('synthetic-unused', False)
            expect('追補1関門陰性: ' + fault,
                   all(r['gates'] == [False, False] and r['status'] == 'differ' for r in records[:15])
                   and all(all(r['gates']) for r in records[15:]))

    probe_counts = {}

    def alternating_errors(rom_dir, official, body):
        probe_counts[body] = probe_counts.get(body, 0) + 1
        return [6] if probe_counts[body] % 2 else []

    with patch.object(kw, 'run_chunk', side_effect=fake_add1), patch(__name__ + '.probe_entry', side_effect=alternating_errors):
        records = measure_add1('synthetic-unused', False)
        expect('追補1合成陰性: 拒否行のエラー番号の2走差',
               sum(r['status'] == 'unstable' for r in records) == 3
               and sum(r['status'] == 'observed' for r in records) == 4)
    expect('追補1判定: 不安定・観察・予測拒否・予測外入場',
           classify_add1(None, '10 A=1', None) == 'unstable'
           and classify_add1(None, None, None, True) == 'observed'
           and classify_add1(None, '10 A=1', None, True) == 'observed'
           and classify_add1(None, None, None) == 'agree'
           and classify_add1('10 A=1', '10 A=1', None) == 'differ')

    # 自作ROMだけを一時ビルドする。陽性対照は上限外の行番号で構文エラー。
    with tempfile.TemporaryDirectory() as td:
        rom = pathlib.Path(td) / 'rom'
        built = subprocess.run([sys.executable, str(kw.REPO / 'src/build_main_rom.py'), str(rom)],
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        expect('探り対照: 自作ROMビルド', built.returncode == 0)
        if built.returncode == 0:
            expect('探り陰性対照: a=1で番号なし', probe_entry(str(rom), False, 'a=1') == [])
            expect('探り陽性対照: 上限外行番号で番号2',
                   probe_entry(str(rom), False, 'a=1', lineno=65530) == [2])
    print(f'arms={len(arms)} add1_arms={len(addarms)} ng={len(fails)}')
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
    m = sub.add_parser('measure-add1')
    m.add_argument('--rom-dir', required=True)
    m.add_argument('--out', required=True)
    m.add_argument('--official', action='store_true')
    p = sub.add_parser('probe-entry')
    p.add_argument('--rom-dir', required=True)
    p.add_argument('--official', action='store_true')
    selection = p.add_mutually_exclusive_group(required=True)
    selection.add_argument('--arm')
    selection.add_argument('--body')
    p = sub.add_parser('predict-add1')
    p.add_argument('--out', default=str(kw.REPO.parent / 'tmp/l4s5i-work/predict_add1.tsv'))
    a = ap.parse_args()
    return {'measure': cmd_measure, 'check': cmd_check, 'predict': cmd_predict, 'selftest': cmd_selftest,
            'measure-add1': cmd_measure_add1, 'probe-entry': cmd_probe_entry,
            'predict-add1': cmd_predict_add1}[a.cmd](a)


if __name__ == '__main__':
    sys.exit(main())
