#!/usr/bin/env python3
"""l4-s9h: PRINT USING の予測と印間の画面セルのコード列採取。本文は出力しない。"""
import argparse
import csv
from decimal import Decimal, ROUND_HALF_UP, localcontext
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
from unittest.mock import patch
import l4_listkw_measure as kw

WORK = kw.REPO.parent / 'tmp/l4s9h-work'
BEGIN, END = b's9hb|', b'|s9hz'
STATUS = re.compile(rb's9he +([0-9]+) *')
DONE = b's9hd'


class BasicError(Exception):
    def __init__(self, number):
        self.number = number


def tokens(fmt, candidate='U_GW'):
    """読んだ字句規則の散文モデル。N88 の差だけを小候補へ分岐する。"""
    n88 = candidate == 'U_N88'
    currency = '\\' if n88 else '$'
    fixed = '&' if n88 else '\\'
    variable = '@' if n88 else '&'
    out, i = [], 0
    while i < len(fmt):
        ch = fmt[i]
        if ch == '_' and i+1 < len(fmt):
            out.append(('literal', fmt[i+1])); i += 2; continue
        if ch == '!':
            out.append(('string', 1)); i += 1; continue
        if ch == variable:
            out.append(('string', 0)); i += 1; continue
        if ch == fixed:
            j = i+1
            while j < len(fmt) and fmt[j] == ' ':
                j += 1
            if j < len(fmt) and fmt[j] == fixed:
                out.append(('string', j-i+1)); i = j+1; continue
        lead = ch == '+'
        j = i+int(lead)
        prefix = ''
        for p in ('**'+currency, '**', currency*2):
            if fmt.startswith(p, j):
                prefix = p; j += len(p); break
        k = j
        if prefix or fmt[j:j+1] == '#':
            while j < len(fmt) and fmt[j] in '#,':
                j += 1
        left = len(prefix)+j-k
        comma = ',' in fmt[k:j]
        dot, decimals = False, 0
        if j < len(fmt) and fmt[j] == '.' and (left or fmt[j:j+2] == '.#'):
            dot = True; j += 1
            while j < len(fmt) and fmt[j] == '#':
                decimals += 1; j += 1
        if not left and not decimals:
            out.append(('literal', ch)); i += 1; continue
        sci = fmt.startswith('^^^^', j)
        if sci:
            j += 4
        trail = ''
        if not lead and j < len(fmt) and fmt[j] in '+-':
            trail = fmt[j]; j += 1
        out.append(('number', dict(left=left+int(lead), decimals=decimals,
                    dot=dot, lead=lead, trail=trail, sci=sci,
                    star=prefix.startswith('**'), currency=currency if currency in prefix else '',
                    comma=comma)))
        i = j
    return out


def numeric(field, value):
    left, places = field['left'], field['decimals']
    if left+places+int(field['dot']) >= 25:
        raise BasicError(5)
    if value['type'] == 'string':
        raise BasicError(13)
    x = Decimal(value['value'])
    negative = x < 0
    sign = '-' if negative else '+' if field['lead'] or field['trail'] == '+' else ''
    exponent = 0
    magnitude = abs(x)
    with localcontext() as ctx:
        ctx.prec = 80
        if field['sci']:
            # 左欄の1セルは先行符号用。後置符号では左欄を全部数字に使う。
            digits = left - int(left > 0 and not field['trail'])
            exponent = magnitude.adjusted()-digits+1 if magnitude else 0
            magnitude = magnitude.scaleb(-exponent)
        rounded = magnitude.quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP)
        if field['sci'] and magnitude and rounded >= Decimal(10)**digits:
            rounded /= 10; exponent += 1
        body = format(rounded, f'.{places}f')
    if field['dot'] and not places:
        body += '.'
    if field['comma'] and not field['sci']:
        a, sep, b = body.partition('.')
        body = format(int(a), ',')+sep+b
    if field['sci']:
        body += ('D' if value.get('double') else 'E')+f'{exponent:+03d}'
    body = field['currency']+body
    # 後置符号のセルは数値欄の外。正の末尾 '-' は空白。
    prefix = '' if field['trail'] else sign
    width = left+int(field['dot'])+places+4*int(field['sci'])
    content = prefix+body
    if len(content) > width and rounded < 1 and '.' in body:
        content = prefix+body.replace('0.', '.', 1)
    content = ('%'+content) if len(content) > width else content.rjust(width, '*' if field['star'] else ' ')
    if field['trail']:
        content += sign or ' '
    return content


def format_using(fmt, values, candidate='U_GW'):
    """部分出力も返す。書式欄なしの一巡は ERR 5。"""
    if not isinstance(fmt, str):
        return '', 13
    if not fmt:
        return '', 5
    parts = tokens(fmt, candidate)
    output, at = '', 0
    while True:
        used = 0
        for kind, field in parts:
            if kind == 'literal':
                output += field; continue
            if at == len(values):
                return output, 0
            value = values[at]
            try:
                if kind == 'string':
                    if value['type'] != 'string':
                        raise BasicError(13)
                    s = value['value']
                    output += s[:field].ljust(field) if field else s
                else:
                    output += numeric(field, value)
            except BasicError as error:
                return output, error.number
            at += 1; used += 1
        if at == len(values):
            return output, 0
        if not used:
            return output, 5


def num(value, double=False):
    return dict(type='number', value=str(value), double=double)


def string(value):
    return dict(type='string', value=value)


def arms():
    result = []
    def add(aid, fmt, values, sep=';', tail=';'):
        result.append(dict(id=aid, fmt=fmt, values=values, sep=sep, tail=tail))
    groups = [('hash', '###'), ('decimal', '##.##'), ('leadplus', '+###.#'),
              ('trailplus', '###.#+'), ('trailminus', '###.#-'),
              ('star', '**###.#'), ('dollar', '$$###.#'), ('stardollar', '**$###.#'),
              ('comma', '##,###.#'), ('scientific', '##.##^^^^')]
    for name, fmt in groups:
        for i, v in enumerate([0, 12, -12, '1.125', '1.25', '-1.25', '999.5', 123456]):
            add(f'{name}-{i+1:02d}', fmt, [num(v)])
    for i, v in enumerate(['2.5', '-2.5', '1.0625', '1.1875']):
        add(f'round-{i+1:02d}', '##.#' if i > 1 else '###', [num(v)])
    add('scientific-double', '##.##^^^^', [num('12.5', True)])
    for fmt, name in [('!', 'bang'), ('&', 'amp'), ('\\\\', 'slash2'),
                      ('\\  \\', 'slash4'), ('&  &', 'amp4'), ('@', 'at')]:
        for i, s in enumerate(['', 'a', 'abcde']):
            add(f'{name}-{i+1:02d}', fmt, [string(s)])
    for name, fmt in [('yen', '\\\\###.#'), ('staryen', '**\\###.#')]:
        for i, v in enumerate([0, 12, -12]):
            add(f'{name}-{i+1:02d}', fmt, [num(v)])
    for sep in (';', ','):
        add('repeat-'+('semi' if sep == ';' else 'comma'), '[##]', [num(1), num(2), num(-3)], sep)
        add('mixed-'+('semi' if sep == ';' else 'comma'), '!/##;', [string('ab'), num(2), string('cd'), num(3)], sep)
    for tail, name in [('', 'newline'), (';', 'semi'), (',', 'comma')]:
        add('tail-'+name, '##x ', [num(1)], tail=tail)
    for i, fmt in enumerate(['abc##xyz', '_#_!_&_##', '##__', '-##', '++##',
                             '##.##,', '##^^^', '##_', '##.']):
        add(f'literal-{i+1:02d}', fmt, [num('1.25')])
    add('format-24', '#'*24, [num(1)])
    add('format-25', '#'*25, [num(1)])
    add('format-empty', '', [num(1)])
    add('format-nofield', 'abc', [num(1)])
    add('format-type', 1, [num(1)])
    add('number-type', '##', [string('a')])
    add('string-type', '!', [num(1)])
    add('partial-type', '##/!', [num(1), num(2)])
    return result


def controls():
    return [dict(id='control-'+name, constant=value, tail=tail) for name, value, tail in [
        ('empty', '', ';'), ('spaces', '  a   ', ';'),
        ('symbols', '!&\\_#$*+-,.^%', ';'), ('wrap', 'a'*72+'  b   ', ';'),
        ('long', 'b'*95+'  ', ';'), ('newline', 'a  ', ''), ('comma', 'a ', ',')]]


def literal(value):
    # @ は打てず、_ は定数対照で欠落を検出した。どちらも文字コードで作る。
    return '+'.join('chr$(64)' if p == '@' else 'u$' if p == '_' else '"'+p+'"'
                    for p in re.split(r'([@_])', value))


def program(arm, trap=True):
    lines = ['new', '10 e=0:u$=chr$(95)']
    if trap:
        lines += ['15 on error goto 900', '900 e=err:resume 40']
    lines += ['20 print "s9hb|";']
    if 'constant' in arm:
        chunks = [arm['constant'][i:i+35] for i in range(0, len(arm['constant']), 35)] or ['']
        for i, chunk in enumerate(chunks):
            lines += [str(30+i)+' print '+literal(chunk)+(arm['tail'] if i == len(chunks)-1 else ';')]
    else:
        fmt = literal(arm['fmt']) if isinstance(arm['fmt'], str) else str(arm['fmt'])
        values = [literal(v['value']) if v['type'] == 'string' else v['value']+('#' if v.get('double') else '') for v in arm['values']]
        lines += ['30 print using '+fmt+';'+arm['sep'].join(values)+arm['tail']]
    lines += ['40 print "|s9hz"', '50 print "s9he";e', '60 print "s9hd"', '70 end', 'cls', 'run']
    if not all(len(line) < 80 and line == line.lower() and '@' not in line and '_' not in line for line in lines):
        raise ValueError('打鍵行の制約違反')
    return lines


def projection(output, tail, error=0, ordinary=False):
    """80列画面の印間セル。改行の残りセルも32として記録する。"""
    data = BEGIN+output.encode('ascii')
    if not error:
        if tail == '':
            data += b' '*(80-len(data)%80)
        elif tail == ',' and ordinary:
            col = len(data)%80
            next_col = (col//14+1)*14
            data += b' '*(next_col-col if next_col < 80 else 80-col)
    return dict(codes=list(data[len(BEGIN):]), end=[len(data)//80, len(data)%80], err=error)


def prediction(arm, candidate='U_GW'):
    if 'constant' in arm:
        return projection(arm['constant'], arm['tail'], ordinary=True)
    output, error = format_using(arm['fmt'], arm['values'], candidate)
    return projection(output, arm['tail'], error)


def extract(data):
    if len(data) != 3000:
        raise ValueError('画面写しの長さが不正')
    rows = [data[i*120:i*120+80] for i in range(25)]
    flat = b''.join(rows)
    if flat.count(BEGIN) != 1 or flat.count(END) != 1:
        raise ValueError('前後印が欠落または重複')
    start, end = flat.index(BEGIN), flat.index(END)
    if start % 80 or not start+len(BEGIN) <= end or end-start > 800:
        raise ValueError('印の順序・位置・範囲が不正')
    erow = (end+len(END)-1)//80
    if flat[end+len(END):(erow+1)*80].strip(b' '):
        raise ValueError('後印の後に余分な内容')
    if erow+2 >= 25 or rows[erow+2].rstrip(b' ') != DONE:
        raise ValueError('完了印が欠落')
    status = STATUS.fullmatch(rows[erow+1].rstrip(b' '))
    if not status or not 0 <= int(status[1]) <= 255:
        raise ValueError('ERR印が不正')
    codes = list(flat[start+len(BEGIN):end])
    if not all(32 <= c <= 126 for c in codes):
        raise ValueError('制御文字を含む画面は対象外')
    obs = dict(codes=codes, end=[end//80-start//80, end%80], err=int(status[1]))
    other = sum(bool(row.strip(b' ')) for i, row in enumerate(rows) if not start//80 <= i <= erow+2)
    return obs, other


def valid(obs):
    if not isinstance(obs, dict) or set(obs) != {'codes', 'end', 'err'}:
        return False
    codes, end, err = obs['codes'], obs['end'], obs['err']
    return (isinstance(codes, list) and len(codes) <= 800 and
            all(type(c) is int and 32 <= c <= 126 for c in codes) and
            isinstance(end, list) and len(end) == 2 and all(type(x) is int for x in end) and
            end == [(len(BEGIN)+len(codes))//80, (len(BEGIN)+len(codes))%80] and
            type(err) is int and 0 <= err <= 255)


def run_arm(rom, official, arm, work, trap=True):
    args = [str(kw.FRONT), '--core', str(kw.find_core()), '--rom-dir', str(rom)]
    at = 700 if official else 100
    if official:
        args += ['--type-at', '300', '--type', '\n']
    for line in program(arm, trap):
        args += ['--type-at', str(at), '--type', line+'\n']
        at += (len(line)+1)*8+240+(15000 if line == 'run' else 0)
    # 複数枚は .fNNNNNN.bin になる。2写しの内容一致も関門とする。
    base = work/'screen.bin'
    frames = [at+200, at+300]
    for frame in frames:
        args += ['--vram-dump', str(base), '--vram-dump-at', str(frame)]
    args += ['--frames', str(at+400)]
    try:
        proc = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              env=dict(os.environ, M6FH_LONG_TYPING='1'))
        if proc.returncode or b'untypable' in proc.stderr.lower() or '打てない'.encode() in proc.stderr:
            raise RuntimeError('測定器の実行または打鍵に失敗')
        captures = [extract(base.with_name(f'screen.f{frame:06d}.bin').read_bytes()) for frame in frames]
        if captures[0] != captures[1]:
            raise RuntimeError('完了後の2写しが不一致')
        return captures[0]
    finally:
        for path in work.glob('screen*.bin'):
            path.unlink()


def measure(rom, official, selected, work, trap=True):
    work.mkdir(parents=True, exist_ok=True)
    records = []
    with tempfile.TemporaryDirectory(prefix='measure-', dir=work) as temp:
        for arm in selected:
            obs, others, failed = [], [], []
            for _ in range(2):
                try:
                    value, other = run_arm(rom, official, arm, Path(temp), trap)
                    obs.append(value); others.append(other); failed.append(False)
                except Exception:
                    obs.append(None); others.append(0); failed.append(True)
            records.append(dict(arm=arm, obs=obs, others=others, failed=failed,
                                gate=not any(failed) and obs[0] == obs[1] and valid(obs[0])))
    return records


def write(path, header, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8', newline='') as stream:
        writer = csv.writer(stream, delimiter='\t')
        writer.writerow(header); writer.writerows(rows)


def emit(path, records, trap=True):
    by_id = {r['arm']['id']: r for r in records}
    def stable(r):
        return r['gate'] and not any(r['failed']) and r['obs'][0] == r['obs'][1] and valid(r['obs'][0])
    calibration = all(a['id'] in by_id and stable(by_id[a['id']]) and
                      by_id[a['id']]['obs'][0] == prediction(a) for a in controls())
    rows, passed = [], calibration
    for r in records:
        predictions = {c: prediction(r['arm'], c) for c in ('U_GW', 'U_N88')}
        known = r['obs'][0] in predictions.values()
        gate = calibration and stable(r)
        passed = passed and gate and known
        for i in range(2):
            rows.append((r['arm']['id'], i+1, json.dumps(program(r['arm'], trap)),
                         json.dumps(r['obs'][i]), r['others'][i],
                         'pass' if gate and known else 'differ' if gate else 'gate_failed',
                         *(('agree' if r['obs'][i] == p else 'differ') if gate else 'gate_failed' for p in predictions.values()),
                         int(r['failed'][i])))
    write(path, ['arm', 'repeat', 'typed_lines', 'observation', 'other_line_counts', 'gate',
                 'U_GW', 'U_N88', 'typing_or_capture_failed'], rows)
    return passed


def check(expected, measured):
    with expected.open(encoding='utf-8') as stream:
        wanted = list(csv.DictReader(stream, delimiter='\t'))
    with measured.open(encoding='utf-8') as stream:
        actual = list(csv.DictReader(stream, delimiter='\t'))
    targets, grouped = {}, {}
    for r in wanted:
        value = json.loads(r['prediction'])
        if not valid(value):
            return False
        targets.setdefault(r['arm'], []).append(value)
    for r in actual:
        grouped.setdefault(r['arm'], []).append(r)
    if not targets or set(targets) != set(grouped):
        return False
    for aid, values in targets.items():
        runs = grouped[aid]
        if len(runs) != 2 or {r['repeat'] for r in runs} != {'1', '2'}:
            return False
        obs = [json.loads(r['observation']) for r in runs]
        if obs[0] != obs[1] or any(r['gate'] != 'pass' or r['typing_or_capture_failed'] != '0' for r in runs):
            return False
        if not valid(obs[0]) or obs[0] not in values:
            return False
    return True


WRAP_CONTROLS = ('control-wrap', 'control-long')


def wrap_dependent(arm, obs):
    """行端の折り返し規則に依存する腕。観測か予測が80セルを超える、または改行抑止なのに2行目へ出た。"""
    cells = [len(BEGIN)+len(obs['codes'])] + [len(BEGIN)+len(prediction(arm, c)['codes']) for c in ('U_GW', 'U_N88')]
    return max(cells) > 80 or (obs['end'][0] >= 1 and arm['tail'] != '')


def rejudge(measured, out):
    """l4-s9h 追補1: 保存済み観測から再判定。折り返し対照2腕は関門から外し観測のみ残す。"""
    with measured.open(encoding='utf-8') as stream:
        rows = list(csv.DictReader(stream, delimiter='\t'))
    by_arm = {a['id']: a for a in controls()+arms()}
    grouped = {}
    for r in rows:
        grouped.setdefault(r['arm'], []).append(r)
    if set(grouped) != set(by_arm):
        return False
    def load(r):
        try:
            return json.loads(r['observation'])
        except ValueError:
            return None
    def stable(aid):
        runs = grouped[aid]
        if len(runs) != 2 or {r['repeat'] for r in runs} != {'1', '2'}:
            return False
        obs = [load(r) for r in runs]
        return (obs[0] == obs[1] and valid(obs[0]) and
                all(r['typing_or_capture_failed'] == '0' for r in runs))
    gated = [a for a in controls() if a['id'] not in WRAP_CONTROLS]
    calibration = len(gated) == 5 and all(
        stable(a['id']) and load(grouped[a['id']][0]) == prediction(a) for a in gated)
    out_rows, passed = [], calibration
    for aid, arm in by_arm.items():
        ok = stable(aid)
        for r in sorted(grouped[aid], key=lambda r: r['repeat']):
            obs = load(r)
            if aid in WRAP_CONTROLS:
                status, wrap = 'observed_only', ''
                agree = ('', '')
            elif not (calibration and ok):
                status, wrap, agree = 'gate_failed', '', ('gate_failed',)*2
                passed = False
            else:
                wrap = wrap_dependent(arm, obs)
                preds = [prediction(arm, c) for c in ('U_GW', 'U_N88')]
                known = obs in preds and not wrap
                status = 'pass' if known else 'unpredicted' if wrap else 'differ'
                agree = tuple('agree' if obs == p and not wrap else 'differ' for p in preds)
                passed = passed and known
            out_rows.append((aid, r['repeat'], r['observation'], r['other_line_counts'], status,
                             int(wrap) if wrap != '' else '', *agree, r['typing_or_capture_failed']))
    write(out, ['arm', 'repeat', 'observation', 'other_line_counts', 'status', 'wrap_dependent',
                'U_GW', 'U_N88', 'typing_or_capture_failed'], out_rows)
    return passed


def screen_of(obs):
    flat = bytearray(b' '*2000)
    payload = BEGIN+bytes(obs['codes'])+END
    flat[:len(payload)] = payload
    row = (len(payload)-1)//80+1
    status = b's9he '+str(obs['err']).encode()+b' '
    flat[row*80:row*80+len(status)] = status
    flat[(row+1)*80:(row+1)*80+len(DONE)] = DONE
    data = bytearray(b' '*3000)
    for i in range(25):
        data[i*120:i*120+80] = flat[i*80:i*80+80]
    return bytes(data)


def selftest(work):
    work.mkdir(parents=True, exist_ok=True)
    fixed = [('###', [num(12)], ' 12', 0), ('###', [num(-12)], '-12', 0),
             ('##', [num(123)], '%123', 0), ('##.##', [num('1.125')], ' 1.13', 0),
             ('###', [num('-2.5')], ' -3', 0), ('**###.#', [num(12)], '***12.0', 0),
             ('$$###.#', [num(-12)], ' -$12.0', 0), ('**$###.#', [num(12)], '***$12.0', 0),
             ('##,###.#', [num(1234)], ' 1,234.0', 0), ('##.##^^^^', [num(12)], ' 1.20E+01', 0),
             ('###.#+', [num(12)], ' 12.0+', 0), ('###.#-', [num(12)], ' 12.0 ', 0),
             ('##.##,', [num('1.25')], ' 1.25,', 0),
             ('\\  \\', [string('a')], 'a   ', 0), ('&', [string('abc')], 'abc', 0),
             ('_#__##', [num(2)], '#_ 2', 0), ('[##]', [num(1), num(2)], '[ 1][ 2]', 0),
             ('##/!', [num(1), num(2)], ' 1/', 13), ('abc', [num(1)], 'abc', 5),
             ('#'*25, [num(1)], '', 5)]
    for fmt, values, output, error in fixed:
        assert format_using(fmt, values) == (output, error), '予測器の固定値不一致'
    assert format_using('&  &', [string('a')], 'U_N88') == ('a   ', 0)
    assert format_using('@', [string('abc')], 'U_N88') == ('abc', 0)
    assert format_using('\\\\###.#', [num(12)], 'U_N88') == ('  \\12.0', 0)
    assert format_using('+###.#', [num(0)]) == ('  +0.0', 0)
    assert format_using('##.##^^^^', [num('12.5', True)]) == (' 1.25D+01', 0)
    assert format_using('', [num(1)]) == ('', 5)
    assert format_using(1, [num(1)]) == ('', 13)
    assert format_using('!', [num(1)]) == ('', 13)
    selected = controls()+arms()
    for arm in selected:
        program(arm)
        for c in ('U_GW', 'U_N88'):
            obs = prediction(arm, c)
            assert valid(obs) and extract(screen_of(obs))[0] == obs
    write(work/'predictions.tsv', ['arm', 'candidate', 'prediction', 'typed_lines'],
          [(a['id'], c, json.dumps(prediction(a, c)), json.dumps(program(a)))
           for a in selected for c in ('U_GW', 'U_N88')])
    good = prediction(controls()[1]); data = screen_of(good)
    for bad in [data.replace(BEGIN, b'z9hb|', 1), data.replace(END, b'|z9hz', 1),
                data.replace(DONE, b'z9hd', 1), data[:-1],
                data.replace(b's9he 0', b's9he x', 1)]:
        try:
            extract(bad)
        except ValueError:
            continue
        raise AssertionError('合成陰性対照を拒否しなかった')
    duplicate = bytearray(data); duplicate[12*120:12*120+len(BEGIN)] = BEGIN
    try:
        extract(bytes(duplicate))
        raise AssertionError('重複印を拒否しなかった')
    except ValueError:
        pass
    # 同じ長さの印を入れ替えた逆順と、印間の制御文字を拒否する。
    reverse = bytearray(data)
    reverse[:len(BEGIN)] = END
    pos = len(BEGIN)+len(good['codes'])
    reverse[pos:pos+len(END)] = BEGIN
    control = bytearray(data); control[len(BEGIN)] = 1
    for bad in (bytes(reverse), bytes(control)):
        try:
            extract(bad)
        except ValueError:
            continue
        raise AssertionError('印逆転・制御文字を拒否しなかった')
    changed = dict(good, codes=[*good['codes']]); changed['codes'][-1] = 33
    assert extract(screen_of(changed))[0] != good
    assert extract(data.replace(b's9he 0', b's9he 5'))[0] != good
    with tempfile.TemporaryDirectory(prefix='replay-', dir=work) as temp:
        root = Path(temp)
        def replay(rom, official, arm, directory, trap=True):
            return extract(screen_of(prediction(arm)))
        with patch(__name__+'.run_arm', replay):
            records = measure('', False, selected, root)
        assert emit(root/'good.tsv', records)
        write(root/'expected.tsv', ['arm', 'candidate', 'prediction'],
              [(a['id'], 'U_GW', json.dumps(prediction(a))) for a in selected])
        assert check(root/'expected.tsv', root/'good.tsv')
        write(root/'wrong.tsv', ['arm', 'prediction'],
              [(a['id'], json.dumps(changed if a['id'] == 'control-spaces' else prediction(a))) for a in selected])
        assert not check(root/'wrong.tsv', root/'good.tsv')
        records[-1]['obs'] = [dict(prediction(records[-1]['arm']), err=5)]*2
        assert not emit(root/'different.tsv', records)
        assert not check(root/'expected.tsv', root/'different.tsv')
        records[-1]['obs'] = [prediction(records[-1]['arm'])]*2
        records[0]['obs'][1] = changed
        assert not emit(root/'bad.tsv', records) and not check(root/'expected.tsv', root/'bad.tsv')
        calls = 0
        def alternating(rom, official, arm, directory, trap=True):
            nonlocal calls
            calls += 1
            return (changed if calls == 2 else prediction(arm)), 0
        with patch(__name__+'.run_arm', alternating):
            assert not measure('', False, [controls()[1]], root)[0]['gate']
        def failed(*args):
            raise RuntimeError('合成の打鍵失敗')
        with patch(__name__+'.run_arm', failed):
            broken = measure('', False, controls(), root)
        assert not emit(root/'failed.tsv', broken)
        assert not emit(root/'missing.tsv', records[1:])
    print('OK 合成採取の陽性・陰性、固定予測、2走・対照欠落・失敗伝播')
    # 追補1の再判定: 折り返し対照は関門外、残り5対照と2走一致・形式は関門のまま。
    with tempfile.TemporaryDirectory(prefix='rejudge-', dir=work) as temp:
        root = Path(temp)
        def synth(mutate=None):
            out = []
            for a in controls()+arms():
                o = prediction(a)
                if a['id'] in WRAP_CONTROLS:
                    o = dict(codes=[97]*70+[32]*5+[98], end=[1, 8], err=0)  # 80桁で折り返さない合成観測
                for i in (1, 2):
                    obs = o
                    if mutate:
                        obs = mutate(a['id'], i, o)
                    out.append((a['id'], i, json.dumps(obs), 0, 'x', 'x', 'x', 0 if obs is not None else 1))
            return out
        header = ['arm', 'repeat', 'observation', 'other_line_counts', 'gate', 'U_GW', 'U_N88', 'typing_or_capture_failed']
        # 陽性: 折り返し対照が予測外でも、他が全部一致なら通る。
        write(root/'m.tsv', header, synth())
        assert rejudge(root/'m.tsv', root/'r.tsv')
        with (root/'r.tsv').open(encoding='utf-8') as stream:
            got = {r['arm']: r for r in csv.DictReader(stream, delimiter='\t')}
        assert got['control-wrap']['status'] == 'observed_only' and got['hash-01']['status'] == 'pass'
        # 陰性1: 残り5対照の1つが違う値なら失敗。
        write(root/'m.tsv', header, synth(lambda a, i, o: changed if a == 'control-spaces' else o))
        assert not rejudge(root/'m.tsv', root/'r.tsv')
        # 陰性2: 2走不一致、陰性3: 打鍵失敗(null)
        write(root/'m.tsv', header, synth(lambda a, i, o: changed if (a, i) == ('hash-01', 2) else o))
        assert not rejudge(root/'m.tsv', root/'r.tsv')
        write(root/'m.tsv', header, synth(lambda a, i, o: None if a == 'format-empty' else o))
        assert not rejudge(root/'m.tsv', root/'r.tsv')
        # 陰性4: 予測外の値は differ、折り返し依存の腕は予測一致でも unpredicted。
        write(root/'m.tsv', header, synth(lambda a, i, o: dict(o, err=7) if a == 'hash-01' else o))
        assert not rejudge(root/'m.tsv', root/'r.tsv')
        def wrapped(a, i, o):
            if a != 'hash-01':
                return o
            return dict(codes=[97]*80, end=[1, 5], err=0)
        write(root/'m.tsv', header, synth(wrapped))
        assert not rejudge(root/'m.tsv', root/'r.tsv')
        with (root/'r.tsv').open(encoding='utf-8') as stream:
            got = {r['arm']: r for r in csv.DictReader(stream, delimiter='\t')}
        assert got['hash-01']['status'] == 'unpredicted' and got['hash-01']['wrap_dependent'] == '1'
        # 陰性5: 腕の欠落
        write(root/'m.tsv', header, synth()[2:])
        assert not rejudge(root/'m.tsv', root/'r.tsv')
    print('OK 再判定の陽性・陰性（折り返し対照の除外、5対照・2走・形式・欠落・折り返し依存）')
    with tempfile.TemporaryDirectory(prefix='selftest-', dir=work) as temp:
        root = Path(temp); rom = root/'rom'
        proc = subprocess.run([os.sys.executable, str(kw.REPO/'src/build_main_rom.py'), str(rom),
                               '--work-dir', str(root/'asm')], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        assert proc.returncode == 0, '自作ROMの一時ビルド失敗'
        records = measure(rom, False, controls(), root, trap=False)
        assert all(r['gate'] and r['obs'][0] == prediction(r['arm']) for r in records), \
            '自作定数関門失敗: '+json.dumps([(r['arm']['id'], r['obs'], r['failed']) for r in records])
        measured, expected = root/'measured.tsv', root/'expected.tsv'
        assert emit(measured, records, trap=False)
        write(expected, ['arm', 'prediction'], [(a['id'], json.dumps(prediction(a))) for a in controls()])
        assert check(expected, measured)
        records[1]['obs'] = [changed, changed]
        assert not emit(measured, records, trap=False) and not check(expected, measured)
    print('OK 自作ROM一時ビルド、普通PRINTの定数7腕×2走、既知値改変の陰性')
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('predict'); p.add_argument('--out', type=Path, required=True)
    m = sub.add_parser('measure'); m.add_argument('--rom-dir'); m.add_argument('--out', type=Path, required=True)
    m.add_argument('--official', action='store_true'); m.add_argument('--work-dir', type=Path, default=WORK)
    c = sub.add_parser('check'); c.add_argument('--expected', type=Path, required=True); c.add_argument('--measured', type=Path, required=True)
    j = sub.add_parser('rejudge'); j.add_argument('--measured', type=Path, required=True); j.add_argument('--out', type=Path, required=True)
    s = sub.add_parser('selftest'); s.add_argument('--work-dir', type=Path, default=WORK)
    args = parser.parse_args()
    if args.command == 'selftest':
        return selftest(args.work_dir)
    if args.command == 'rejudge':
        try:
            passed = rejudge(args.measured, args.out)
        except (OSError, ValueError, KeyError, TypeError):
            passed = False
        print('再判定: 全腕一致' if passed else '再判定: 不一致または関門失敗'); return 0 if passed else 1
    if args.command == 'check':
        try:
            passed = check(args.expected, args.measured)
        except (OSError, ValueError, KeyError, TypeError):
            passed = False
        print('照合一致' if passed else '照合不一致'); return 0 if passed else 1
    selected = controls()+arms()
    if args.command == 'predict':
        write(args.out, ['arm', 'candidate', 'prediction', 'typed_lines'],
              [(a['id'], c, json.dumps(prediction(a, c)), json.dumps(program(a)))
               for a in selected for c in ('U_GW', 'U_N88')])
        return 0
    rom = os.environ.get('PC88_REF_ROM_DIR') if args.official else args.rom_dir
    if not rom or (args.official and args.rom_dir):
        parser.error('公式ROMの場所は PC88_REF_ROM_DIR のみ、自作は --rom-dir で指定')
    records = measure(rom, args.official, selected, args.work_dir)
    passed = emit(args.out, records)
    print(f'記録完了: {len(records)}腕×2走、既知候補との一致 '+('通過' if passed else '失敗'))
    return 0 if passed else 1


if __name__ == '__main__':
    raise SystemExit(main())
