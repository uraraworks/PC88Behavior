#!/usr/bin/env python3
"""l4-s9g: 行編集後の保存状態を予測・採取・照合する。画面本文は出さない。"""
import argparse
import contextlib
import copy
import csv
import json
import io
import os
from pathlib import Path
import re
import subprocess
import tempfile
import traceback
from unittest.mock import patch

import l4_listkw_measure as kw
import l4_listnum_measure as num

WORK = kw.REPO.parent / 'tmp/l4s9g-work'
OPERATIONS = {
    'none': None,
    'insert-before': '15 rem inserted',
    'insert-after': '155 rem inserted',
    'delete-before': '10',
    'delete-after': '150',
    'replace-stop': '100 print "s9hp";1;1:stop:rem changed',
    'replace-before': '10 rem changed before and longer',
    'replace-after': '150 rem changed after and longer',
    'replace-identical': '150 rem after',
    'missing': '777',
    'new': 'new',
    'clear': 'clear',
    'assign': 'a=29',
    'list': 'list',
}
PROBES = ('vars', 'cont', 'gosub', 'for', 'data', 'onerror',
          'return-goto', 'next-goto', 'resume', 'resume-goto')
RESET = set(OPERATIONS) - {'none', 'missing', 'assign', 'list'}
ARITY = {'s9h': 4, 's9hb': 4, 's9hf': 3,
         **{x: 2 for x in ('s9hp', 's9ha', 's9hc', 's9hr', 's9hd',
                           's9he', 's9hn', 's9hu', 's9ho', 's9hz')}}
NUMBER = r'(?: +\d+| *-\d+)'
MARK = re.compile(r'^(s9h[a-z]?)((?:'+NUMBER+r')+) *$', re.I)


def arms():
    return [dict(id=f'{op}-{probe}', operation=op, probe=probe)
            for op in OPERATIONS for probe in PROBES]


def controls():
    values = [('values', [['s9h', 1, 17, 23, 3]]),
              ('flow', [['s9hf', 1, 3, 4]]),
              ('read', [['s9hd', 1, 22]]),
              ('trap', [['s9he', 1, 5], ['s9hn', 1, 1]])]
    out = [dict(id='control-'+name, rows=rows) for name, rows in values]
    for mode, numbers in [('direct', (5, 8, 17)), ('program', (1, 3, 5))]:
        out += [dict(id=f'control-{mode}-{n}', mode=mode, error=n) for n in numbers]
    return out


def stage(rows=(), error=None, exact=False):
    # errors は正の包含だけを保存。省略した番号の2値は false,false。
    return dict(rows=copy.deepcopy(list(rows)),
                errors=[] if error is None else [[error, True, exact]])


def prepare_rows(a):
    if a['id'].startswith('control-'):
        return [['s9hp', 1, 1]]
    rows = [['s9hb', 1, 17, 23, 3]]
    if a['probe'] == 'data':
        rows += [['s9ha', 1, 11]]
    return rows + [['s9hp', 1, 1]]


def prediction(a):
    """E_GW。未分離の missing×エラートラップは予測なし（null）。"""
    before = stage(prepare_rows(a))
    operation = stage([['s9ho', 1, 1]])
    error, exact = None, False
    if a['id'].startswith('control-'):
        rows = a.get('rows', [])
        error = a.get('error')
        exact = a.get('mode') == 'direct'
    else:
        op, probe = a['operation'], a['probe']
        if op == 'missing' and probe in ('onerror', 'resume', 'resume-goto'):
            return None
        if op == 'missing':
            operation = stage([['s9ho', 1, 1]], 8, True)
        reset = op in RESET
        rows = []
        if probe == 'vars':
            rows = [['s9h', 1, 0, 0, 0] if reset else
                    ['s9h', 1, 29 if op == 'assign' else 17, 23, 3]]
        elif probe in ('cont', 'gosub', 'for', 'resume'):
            if reset:
                error, exact = 17, True
            else:
                rows = {'cont': [['s9hc', 1, 1]], 'gosub': [['s9hr', 1, 71]],
                        'for': [['s9hf', 1, 3, 4]], 'resume': [['s9hu', 1, 83]]}[probe]
        elif op == 'new':
            error, exact = 8, True  # 本文も消え、GOTO 110 の対象が無い。
        elif probe == 'data':
            rows = [['s9hd', 1, 11 if reset else 22]]
        elif probe == 'onerror':
            if reset:
                error = 5
            else:
                rows = [['s9he', 1, 5], ['s9hn', 1, 1]]
        elif probe in ('return-goto', 'next-goto', 'resume-goto'):
            if reset:
                error = {'return-goto': 3, 'next-goto': 1, 'resume-goto': 20}[probe]
            else:
                rows = {'return-goto': [['s9hr', 1, 71]],
                        'next-goto': [['s9hf', 1, 3, 4]],
                        'resume-goto': [['s9hu', 1, 83]]}[probe]
    return dict(prepare=before, operation=operation,
                result=stage(rows + [['s9hz', 1, 1]], error, exact))


def print_row(row):
    return 'print "'+row[0]+'";'+ ';'.join(str(x) for x in row[1:])


def program(a):
    out = ['new']
    if a['id'].startswith('control-'):
        if a.get('mode') == 'program':
            body = {1: 'next i', 3: 'return', 5: 'error 5'}[a['error']]
            out += ['110 '+body, '120 end']
        out += ['cls', 'print "s9hp";1;1', ('capture', 'prepare'),
                'cls', 'print "s9ho";1;1', ('capture', 'operation'), 'cls']
        if 'rows' in a:
            out += [print_row(row) for row in a['rows']]
        elif a['mode'] == 'program':
            out += ['goto 110']
        else:
            out += [{5: 'error 5', 8: 'goto 777', 17: 'cont'}[a['error']]]
    else:
        probe = a['probe']
        base = {10: 'rem before', 20: 'dim b(3):a=17:b(2)=23:c$="abc"',
                25: 'print "s9hb";1;a;b(2);len(c$)', 30: 'goto 100',
                100: 'print "s9hp";1;1:stop', 110: 'print "s9hc";1;1',
                120: 'end', 150: 'rem after'}
        if probe in ('gosub', 'return-goto'):
            base.update({30: 'gosub 100', 40: 'print "s9hr";1;71',
                         50: 'end', 110: 'return'})
        elif probe in ('for', 'next-goto'):
            base.update({30: 'k=0:for i=1 to 3', 40: 'k=k+1',
                         50: 'if k=1 then 100', 60: 'goto 110',
                         110: 'next i', 120: 'print "s9hf";1;k;i:end'})
        elif probe == 'data':
            base.update({30: 'read d', 35: 'print "s9ha";1;d:goto 100',
                         110: 'read d', 115: 'print "s9hd";1;d',
                         900: 'data 11,22,33'})
        elif probe == 'onerror':
            base.update({30: 'on error goto 800:goto 100', 110: 'error 5',
                         120: 'print "s9hn";1;1:end',
                         800: 'print "s9he";1;err:resume 120'})
        elif probe in ('resume', 'resume-goto'):
            base.update({30: 'on error goto 800', 40: 'error 5',
                         50: 'print "s9hu";1;83:end', 110: 'resume next',
                         800: 'goto 100'})
        out += [f'{n} {body}' for n, body in sorted(base.items())]
        out += ['cls', 'run', ('capture', 'prepare'), 'cls']
        if OPERATIONS[a['operation']] is not None:
            out += [OPERATIONS[a['operation']]]
        out += ['print "s9ho";1;1', ('capture', 'operation'), 'cls']
        out += ['print "s9h";1;a;b(2);len(c$)' if probe == 'vars' else
                'cont' if probe in ('cont', 'gosub', 'for', 'resume') else 'goto 110']
    out += ['print "s9hz";1;1', ('capture', 'result')]
    assert all(not isinstance(x, str) or
               (x.isascii() and x == x.lower() and len(x) < 80 and '@' not in x
                and '\n' not in x and '\r' not in x) for x in out)
    return out


def error_numbers():
    return [int(line.split('\t')[0]) for line in
            (kw.REPO/'src/l4_basic/errors.tsv').read_text(encoding='utf-8').splitlines()
            if line and not line.startswith('#')]


def extract(data):
    if len(data) != 3000:
        raise ValueError('画面写しの長さが不正')
    rows, other = [], 0
    for r in range(25):
        raw = data[r*120:r*120+80].rstrip(b' ')
        if not raw:
            continue
        text = raw.decode('ascii', errors='replace')
        match = MARK.fullmatch(text)
        if match and match[1].lower() in ARITY:
            values = [int(n) for n in match[2].split()]
            row = [match[1].lower(), *values]
            rows.append(row if len(values) == ARITY[row[0]] else ['invalid'])
        elif text.lower().startswith('s9h'):
            rows.append(['invalid'])
        else:
            other += 1
    errors = []
    for n in error_numbers():
        contains, exact = num.entry_message_status(data, n)
        if contains:
            errors.append([n, contains, exact])
    return dict(rows=rows, errors=errors), other


def valid_stage(value):
    if not isinstance(value, dict) or set(value) != {'rows', 'errors'}:
        return False
    rows, errors = value['rows'], value['errors']
    if not isinstance(rows, list) or not isinstance(errors, list):
        return False
    for row in rows:
        if (not isinstance(row, list) or not row or row[0] not in ARITY
                or len(row) != ARITY[row[0]]+1 or row[1] != 1
                or any(type(n) is not int for n in row[1:])):
            return False
    numbers = []
    for e in errors:
        if (not isinstance(e, list) or len(e) != 3 or type(e[0]) is not int
                or e[0] not in error_numbers() or e[1] is not True
                or type(e[2]) is not bool):
            return False
        numbers.append(e[0])
    return numbers == sorted(set(numbers))


def valid(value, a):
    if not isinstance(value, dict) or set(value) != {'prepare', 'operation', 'result'}:
        return False
    if not all(valid_stage(v) for v in value.values()):
        return False
    if value['prepare'] != stage(prepare_rows(a)):
        return False
    # 欠落・重複・不完全な採取を、誤りや別の表示に逃がさない。
    if value['operation']['rows'].count(['s9ho', 1, 1]) != 1:
        return False
    result = value['result']
    if not result['rows'] or result['rows'][-1] != ['s9hz', 1, 1]:
        return False
    if result['rows'].count(['s9hz', 1, 1]) != 1:
        return False
    rows = result['rows'][:-1]
    if not rows:
        return bool(result['errors'])
    probe = a.get('probe')
    allowed = {'vars': ('s9h',), 'cont': ('s9hc',), 'gosub': ('s9hr',),
               'return-goto': ('s9hr',), 'for': ('s9hf',), 'next-goto': ('s9hf',),
               'data': ('s9hd',), 'onerror': ('s9he', 's9hn'),
               'resume': ('s9hu', 's9hp'), 'resume-goto': ('s9hu', 's9hp')}
    if probe:
        if any(r[0] not in allowed[probe] for r in rows):
            return False
        if len(rows) > (2 if probe == 'onerror' else 1):
            return False
    elif rows != a.get('rows', []):
        return False
    return True


def dump_path(path, frame, multiple):
    return path.with_name(path.stem+f'.f{frame:06d}'+path.suffix) if multiple else path


def run_arm(rom, official, a, work):
    args = [str(kw.FRONT), '--core', str(kw.find_core()), '--rom-dir', str(rom)]
    at = 700 if official else 100
    if official:
        args += ['--type-at', '300', '--type', '\n']
    captures = []
    for step in program(a):
        if isinstance(step, str):
            args += ['--type-at', str(at), '--type', step+'\n']
            at += (len(step)+1)*8+240+(15000 if step == 'run' else 0)
        else:
            path, frame = work/(step[1]+'.bin'), at+200
            args += ['--vram-dump', str(path), '--vram-dump-at', str(frame)]
            captures.append((step[1], path, frame))
            at = frame+100
    args += ['--frames', str(at+100)]
    paths = [(name, dump_path(path, frame, len(captures) > 1))
             for name, path, frame in captures]
    try:
        proc = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              env=dict(os.environ, M6FH_LONG_TYPING='1'))
        if (proc.returncode or b'untypable' in proc.stderr.lower()
                or '打てない'.encode() in proc.stderr):
            raise RuntimeError('測定器の実行または打鍵に失敗')
        obs, others = {}, {}
        for name, path in paths:
            obs[name], others[name] = extract(path.read_bytes())
        return obs, others
    finally:
        for _, path in paths:
            path.unlink(missing_ok=True)
        for _, path, _ in captures:
            path.unlink(missing_ok=True)


def measure(rom, official, selected, work):
    work.mkdir(parents=True, exist_ok=True)
    records = []
    with tempfile.TemporaryDirectory(prefix='measure-', dir=work) as temp:
        for a in selected:
            obs, others, failed = [], [], []
            for _ in range(2):
                try:
                    value, count = run_arm(rom, official, a, Path(temp))
                    obs.append(value); others.append(count); failed.append(False)
                except Exception:
                    obs.append({}); others.append({}); failed.append(True)
            gate = not any(failed) and obs[0] == obs[1] and valid(obs[0], a)
            records.append(dict(arm=a, obs=obs, others=others, failed=failed, gate=gate))
    return records


def write(path, header, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8', newline='') as stream:
        writer = csv.writer(stream, delimiter='\t')
        writer.writerow(header); writer.writerows(rows)


def comparable(value):
    """予測・期待値との比較だけからexactを除く。保存観測は変更しない。"""
    if value is None:
        return None
    return {name: dict(rows=v['rows'], errors=[e[:2] for e in v['errors']])
            for name, v in value.items()}


def emit(path, records):
    # 保存された gate を信用せず、2走と既知の採取形を再評価する。
    known = {a['id']: a for a in controls()+arms()}
    for r in records:
        r['gate'] = (r['gate'] and r['arm'] == known.get(r['arm']['id'])
                     and len(r['obs']) == 2 and len(r['failed']) == 2
                     and not any(r['failed']) and r['obs'][0] == r['obs'][1]
                     and valid(r['obs'][0], r['arm']))
    cs = [r for r in records if r['arm']['id'].startswith('control-')]
    calibrated = (len(cs) == len(controls())
                  and {r['arm']['id'] for r in cs} == {a['id'] for a in controls()}
                  and all(r['gate'] and comparable(r['obs'][0]) ==
                          comparable(prediction(r['arm'])) for r in cs))
    write(path, ['arm', 'repeat', 'typed_lines', 'observation', 'other_line_counts',
                 'gate', 'E_GW', 'typing_or_capture_failed'],
          [(r['arm']['id'], i+1, json.dumps(program(r['arm']), ensure_ascii=False),
            json.dumps(r['obs'][i]), json.dumps(r['others'][i]),
            'pass' if calibrated and r['gate'] else 'gate_failed',
            'gate_failed' if not calibrated or not r['gate'] else
            'unpredicted' if prediction(r['arm']) is None else
            'agree' if comparable(r['obs'][0]) == comparable(prediction(r['arm'])) else 'differ',
            int(r['failed'][i])) for r in records for i in range(2)])
    return calibrated and bool(records) and all(r['gate'] for r in records)


def rejudge(measured, out):
    """保存TSVの観測からmeasureと同じemitを使う。旧判定列は参照しない。"""
    if measured.resolve() == out.resolve():
        raise ValueError('再判定の入力と出力は別ファイルにする')
    known = {a['id']: a for a in controls()+arms()}
    grouped = {}
    with measured.open(encoding='utf-8', newline='') as stream:
        for row in csv.DictReader(stream, delimiter='\t'):
            aid, repeat = row['arm'], row['repeat']
            if aid not in known or repeat not in ('1', '2'):
                raise ValueError('腕または走番号が不正')
            runs = grouped.setdefault(aid, {})
            if repeat in runs or json.loads(row['typed_lines']) != json.loads(
                    json.dumps(program(known[aid]))):
                raise ValueError('走の重複または打鍵計画の不一致')
            if row['typing_or_capture_failed'] not in ('0', '1'):
                raise ValueError('採取失敗フラグが不正')
            runs[repeat] = row
    records = []
    for aid, runs in grouped.items():
        if set(runs) != {'1', '2'}:
            raise ValueError('2走の記録が不足')
        rows = [runs[str(i)] for i in (1, 2)]
        records.append(dict(arm=known[aid], gate=True,
                            obs=[json.loads(r['observation']) for r in rows],
                            others=[json.loads(r['other_line_counts']) for r in rows],
                            failed=[r['typing_or_capture_failed'] == '1' for r in rows]))
    return emit(out, records)


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
            aid = r['arm']
            if aid not in known or not valid(value, known[aid]):
                return False
            if aid in targets and comparable(targets[aid]) != comparable(value):
                return False
            targets[aid] = value
        grouped = {}
        for r in actual:
            grouped.setdefault(r['arm'], []).append(r)
        if not targets or set(targets) != set(grouped):
            return False
        cs = {aid for aid in targets if aid.startswith('control-')}
        if cs != {a['id'] for a in controls()}:
            return False
        if any(comparable(targets[aid]) != comparable(prediction(known[aid])) for aid in cs):
            return False
        for aid, value in targets.items():
            runs = grouped[aid]
            if len(runs) != 2 or {r['repeat'] for r in runs} != {'1', '2'}:
                return False
            if json.loads(runs[0]['observation']) != json.loads(runs[1]['observation']):
                return False
            if any(r['gate'] != 'pass' or r['typing_or_capture_failed'] != '0'
                   or not valid(json.loads(r['observation']), known[aid])
                   or comparable(json.loads(r['observation'])) != comparable(value) for r in runs):
                return False
        return True
    except (ValueError, KeyError, TypeError, OSError):
        return False


def screen_of(rows, error=None, exact=True):
    data = bytearray(b' '*3000)
    texts = [row[0]+''.join((' ' if n >= 0 else '')+str(n)+' ' for n in row[1:])
             for row in rows]
    if error is not None:
        messages = dict(line.split('\t') for line in
                        (kw.REPO/'src/l4_basic/errors.tsv').read_text().splitlines()
                        if line and not line.startswith('#'))
        texts += [messages[str(error)]+('' if exact else ' in 110')]
    for i, text in enumerate(texts):
        raw = text.encode('ascii')
        assert i < 25 and len(raw) < 80
        data[i*120:i*120+len(raw)] = raw
    return bytes(data)


def selftest(work=None):
    # selftest の既定はOS一時ディレクトリ。測定の既定WORKに書込権限を要求しない。
    if work is not None:
        work.mkdir(parents=True, exist_ok=True)
    known = controls()+arms()
    assert len(arms()) == 140 and len({a['id'] for a in known}) == len(known)
    by_id = {a['id']: a for a in known}
    for a in known:
        program(a)
        p = prediction(a)
        if p is not None:
            assert valid(p, a), a['id']
            for v in p.values():
                error = v['errors'][0] if v['errors'] else None
                data = screen_of(v['rows'], error[0] if error else None,
                                 error[2] if error else True)
                assert extract(data)[0] == v
    fixed = {'none-vars': [['s9h', 1, 17, 23, 3]],
             'assign-vars': [['s9h', 1, 29, 23, 3]],
             'clear-vars': [['s9h', 1, 0, 0, 0]],
             'none-data': [['s9hd', 1, 22]], 'insert-before-data': [['s9hd', 1, 11]],
             'none-gosub': [['s9hr', 1, 71]], 'none-for': [['s9hf', 1, 3, 4]],
             'none-resume': [['s9hu', 1, 83]],
             'none-onerror': [['s9he', 1, 5], ['s9hn', 1, 1]]}
    for aid, rows in fixed.items():
        assert prediction(by_id[aid])['result']['rows'] == rows+[['s9hz', 1, 1]]
    for aid, n, exact in [('new-cont', 17, True), ('new-data', 8, True),
                          ('clear-return-goto', 3, False), ('clear-next-goto', 1, False),
                          ('clear-onerror', 5, False), ('clear-resume-goto', 20, False),
                          ('replace-identical-cont', 17, True)]:
        assert prediction(by_id[aid])['result']['errors'] == [[n, True, exact]]
    assert prediction(by_id['missing-vars'])['operation']['errors'] == [[8, True, True]]
    for probe in ('onerror', 'resume', 'resume-goto'):
        assert prediction(by_id['missing-'+probe]) is None
    row = [['s9h', 1, 17, 23, 3]]
    assert extract(screen_of(row))[0] == stage(row)
    assert extract(screen_of([['s9h', 1, -1, 0, 3]]))[0]['rows'][0][2] == -1
    assert extract(b' '*3000)[0] == stage()
    assert extract(screen_of(row).replace(b's9h', b'z9h', 1))[0]['rows'] == []
    for exact in (True, False):
        assert extract(screen_of([], 17, exact))[0]['errors'] == [[17, True, exact]]
    assert extract(screen_of(row).replace(b' 17', b' xx', 1))[0]['rows'] == [['invalid']]
    try:
        extract(b' ')
        raise AssertionError('短い写しを受理')
    except ValueError:
        pass
    assert dump_path(Path('x.bin'), 123, True).name == 'x.f000123.bin'
    assert dump_path(Path('x.bin'), 123, False).name == 'x.bin'
    selected = [a for a in known if prediction(a) is not None]
    with tempfile.TemporaryDirectory(prefix='l4s9g-selftest-', dir=work) as temp:
        root = Path(temp)
        # 偽フロントエンドで多枚採取の名前・打鍵順・写しの片付けを通す。
        # stdout/stderr の未知の本文は、例外経由でも外へ出さない。
        probe = by_id['none-vars']
        planned = prediction(probe)
        def frontend(argv, **kwargs):
            frames, typed, dumps = [], [], []
            for i, arg in enumerate(argv):
                if arg == '--type-at':
                    frames.append(int(argv[i+1]))
                elif arg == '--type':
                    typed.append(argv[i+1])
                elif arg == '--vram-dump':
                    assert argv[i+2] == '--vram-dump-at'
                    dumps.append((Path(argv[i+1]), int(argv[i+3])))
            assert frames == sorted(set(frames))
            assert typed[0] == '\n' and all(t == t.lower() for t in typed)
            assert typed[1:] == [x+'\n' for x in program(probe) if isinstance(x, str)]
            assert int(argv[-1]) > dumps[-1][1] and len(dumps) == 3
            for name, (path, frame) in zip(('prepare', 'operation', 'result'), dumps):
                v = planned[name]
                dump_path(path, frame, True).write_bytes(screen_of(v['rows']))
            return subprocess.CompletedProcess(argv, 0, b'unknown-screen-body', b'unknown-screen-body')
        captured = io.StringIO()
        with patch.object(kw, 'find_core', return_value=Path('synthetic-core')), \
             patch.object(subprocess, 'run', side_effect=frontend), \
             contextlib.redirect_stdout(captured), contextlib.redirect_stderr(captured):
            got, _ = run_arm('synthetic-rom', True, probe, root)
        assert got == planned and captured.getvalue() == '' and not list(root.glob('*.bin'))
        with patch.object(kw, 'find_core', return_value=Path('synthetic-core')), \
             patch.object(subprocess, 'run', return_value=subprocess.CompletedProcess(
                 [], 1, b'unknown-screen-body', b'unknown-screen-body')):
            try:
                run_arm('synthetic-rom', False, probe, root)
                raise AssertionError('実行失敗を受理')
            except RuntimeError as error:
                assert 'unknown-screen-body' not in str(error)
        with patch(__name__+'.run_arm', side_effect=lambda rom, official, a, wd: (prediction(a), {})):
            records = measure('', False, selected, root)
        expected, measured = root/'expected.tsv', root/'measured.tsv'
        def freeze(chosen):
            write(expected, ['arm', 'prediction'],
                  [(a['id'], json.dumps(prediction(a))) for a in chosen])
        freeze(selected)
        assert emit(measured, records) and check(expected, measured)
        # exactだけの差は全腕の期待値比較から除外し、観測には残す。
        changed = copy.deepcopy(records)
        for r in changed:
            for o in r['obs']:
                for v in o.values():
                    for e in v['errors']:
                        e[2] = not e[2]
        assert emit(measured, changed) and check(expected, measured)
        with measured.open() as stream:
            saved = list(csv.DictReader(stream, delimiter='\t'))
        assert all(r['E_GW'] == 'agree' for r in saved)
        assert json.loads(next(r for r in saved if r['arm'] ==
                               'control-direct-17')['observation'])['result']['errors'] == [[17, True, False]]
        # 旧全体gate_failedから、保存観測だけを使って回復する。
        for r in saved:
            r['gate'] = r['E_GW'] = 'gate_failed'
        write(measured, list(saved[0]), [list(r.values()) for r in saved])
        rejudged = root/'rejudged.tsv'
        assert rejudge(measured, rejudged) and check(expected, rejudged)
        # 本体の番号違いは校正通過でもdiffer。exactの2走差は関門失敗。
        different = copy.deepcopy(changed)
        target = next(r for r in different if r['arm']['id'] == 'new-cont')
        for o in target['obs']:
            o['result']['errors'][0][0] = 8
        assert emit(measured, different) and not check(expected, measured)
        assert rejudge(measured, rejudged)
        with rejudged.open() as stream:
            assert all(r['E_GW'] == 'differ' for r in csv.DictReader(stream, delimiter='\t')
                       if r['arm'] == 'new-cont')
        target['obs'][1]['result']['errors'][0][2] = True
        assert not emit(measured, different) and not check(expected, measured)
        assert not rejudge(measured, rejudged)
        # 欠落・重複した走、未知腕、失敗フラグ・打鍵計画の破損を拒否。
        for mutation in ('missing', 'duplicate', 'unknown', 'flag', 'typing'):
            bad_rows = copy.deepcopy(saved)
            if mutation == 'missing':
                bad_rows.pop()
            elif mutation == 'duplicate':
                bad_rows.append(copy.deepcopy(bad_rows[0]))
            elif mutation == 'unknown':
                bad_rows[0]['arm'] = 'unknown'
            elif mutation == 'flag':
                bad_rows[0]['typing_or_capture_failed'] = '2'
            else:
                bad_rows[0]['typed_lines'] = '[]'
            write(measured, list(saved[0]), [list(r.values()) for r in bad_rows])
            try:
                rejudge(measured, rejudged)
                raise AssertionError('保存TSVの破損を受理')
            except ValueError:
                pass
        print('OK exactだけの差はagree、番号違いはdiffer、保存TSV再構成と2走・形式の拒否', flush=True)
        assert not emit(root/'empty.tsv', []) and not check(expected, root/'empty.tsv')
        assert not emit(root/'missing.tsv', records[1:])
        for mutation in ('value', 'repeat', 'capture', 'error', 'skip'):
            bad = copy.deepcopy(records)
            if mutation == 'value':
                for o in bad[0]['obs']:
                    o['result']['rows'][0][2] = 999
            elif mutation == 'repeat':
                bad[0]['obs'][1]['result']['rows'][0][2] = 999
            elif mutation == 'capture':
                bad[0]['obs'][1] = {}; bad[0]['failed'][1] = True
            elif mutation == 'error':
                r = next(r for r in bad if r['arm']['id'] == 'control-direct-17')
                for o in r['obs']:
                    o['result']['errors'][0][0] = 8
            else:
                bad[0]['gate'] = False
            assert not emit(measured, bad) and not check(expected, measured)
        with patch(__name__+'.run_arm', side_effect=RuntimeError('合成失敗')):
            failed = measure('', False, [known[0]], root)
        assert not failed[0]['gate'] and failed[0]['failed'] == [True, True]
        # 採取段階の異常・数値破損・重複の陰性対照。
        p = prediction(by_id['none-vars'])
        for name in ('prepare', 'operation', 'result'):
            bad = copy.deepcopy(p); bad[name]['rows'] = []
            assert not valid(bad, by_id['none-vars'])
        bad = copy.deepcopy(p); bad['result']['rows'] *= 2
        assert not valid(bad, by_id['none-vars'])
        print('OK 固定予測、PRINT・誤り2値の陽性陰性、2走・採取欠落・対照破損・本文漏出の拒否', flush=True)
        rom = root/'rom'
        built = subprocess.run([os.sys.executable, str(kw.REPO/'src/build_main_rom.py'),
                                str(rom), '--work-dir', str(root/'asm')],
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        assert built.returncode == 0, '自作ROM一時ビルド失敗'
        own = controls()+[by_id['none-'+probe] for probe in
                          ('vars', 'cont', 'gosub', 'for', 'data', 'return-goto', 'next-goto')]
        observed = measure(rom, False, own, root)
        bad_ids = [r['arm']['id'] for r in observed
                   if not r['gate'] or comparable(r['obs'][0]) != comparable(prediction(r['arm']))]
        if bad_ids:
            print('NG 自作ROMの既知値対照: '+','.join(bad_ids))
            for r in observed:
                if r['arm']['id'] in bad_ids:
                    print(json.dumps(dict(arm=r['arm']['id'], observation=r['obs'],
                                          failed=r['failed']), ensure_ascii=False))
        assert not bad_ids, '自作ROMの既知値対照失敗: '+','.join(bad_ids)
        freeze(own)
        assert emit(measured, observed) and check(expected, measured)
        wrong = prediction(own[0]); wrong['result']['rows'][0][2] = 999
        write(expected, ['arm', 'prediction'], [(a['id'], json.dumps(wrong if i == 0 else prediction(a)))
                                              for i, a in enumerate(own)])
        assert not check(expected, measured)
        print(f'OK 自作ROM一時ビルド、定数・既存機能{len(own)}腕×2走、期待値改変拒否')
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('predict'); p.add_argument('--out', type=Path, required=True)
    m = sub.add_parser('measure'); m.add_argument('--rom-dir')
    m.add_argument('--official', action='store_true'); m.add_argument('--out', type=Path, required=True)
    m.add_argument('--work-dir', type=Path, default=WORK)
    c = sub.add_parser('check'); c.add_argument('--expected', type=Path, required=True)
    c.add_argument('--measured', type=Path, required=True)
    r = sub.add_parser('rejudge'); r.add_argument('--measured', type=Path, required=True)
    r.add_argument('--out', type=Path, required=True)
    s = sub.add_parser('selftest'); s.add_argument('--work-dir', type=Path)
    args = parser.parse_args()
    if args.command == 'selftest':
        return selftest(args.work_dir)
    if args.command == 'check':
        ok = check(args.expected, args.measured)
        print('照合一致' if ok else '照合不一致'); return 0 if ok else 1
    if args.command == 'rejudge':
        ok = rejudge(args.measured, args.out)
        print('再判定完了: 関門'+('通過' if ok else '失敗'))
        return 0 if ok else 1
    selected = controls()+arms()
    if args.command == 'predict':
        write(args.out, ['arm', 'candidate', 'prediction', 'typed_lines'],
              [(a['id'], 'E_GW', json.dumps(prediction(a)), json.dumps(program(a), ensure_ascii=False))
               for a in selected])
        print(f'予測記録: {len(selected)}腕（予測なし3腕）'); return 0
    rom = os.environ.get('PC88_REF_ROM_DIR') if args.official else args.rom_dir
    if not rom or (args.official and args.rom_dir):
        parser.error('公式ROMはPC88_REF_ROM_DIRだけ、自作ROMは--rom-dirで指定する')
    records = measure(rom, args.official, selected, args.work_dir)
    ok = emit(args.out, records)
    print(f'記録完了: {len(records)}腕×2走、関門'+('通過' if ok else '失敗'))
    return 0 if ok else 1


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as error:
        # 例外のreprやフロントエンドの出力を本文漏えいの経路にしない。
        frames = traceback.extract_tb(error.__traceback__)
        print(f'NG 器具の検査または実行に失敗 ({type(error).__name__}, '
              f'行{frames[-1].lineno}、画面本文は非出力)')
        raise SystemExit(1)
