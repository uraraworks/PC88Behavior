#!/usr/bin/env python3
"""l4-t7 測定器の開発途上版。画面本文を出力・保存しない。"""
import argparse
import concurrent.futures
import copy
import json
import os
import re
import subprocess
import sys
from pathlib import Path
sys.dont_write_bytecode = True
import l4_listkw_measure as kw
import l4_t5_delete_measure as common
import l4_key_measure as key_measure

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / 'tmp/t7-work'
REFS = {'none': 'rem', 'ERR2': 'error 2', 'ERR5': 'error 5', 'ERR8': 'error 8'}
RENUMBER = {
    'default': ('renum', list(range(10, 71, 10))),
    'start': ('renum 100', list(range(100, 161, 10))),
    'start-old': ('renum 100,12', [5, 7, 100, 110, 120, 130, 140]),
    'step': ('renum 100,12,5', [5, 7, 100, 105, 110, 115, 120]),
    'omitted': ('renum ,,20', list(range(10, 131, 20))),
    'undefined': ('renum', list(range(10, 71, 10))),
    'overflow': ('renum 65525,5,10', [65525, 65529, 65535]),
    'zero': ('renum 100,5,0', [100]),
    'between': ('renum 100,8,10', [5, 7, 100, 110, 120, 130, 140]),
    'empty': ('renum', []), 'program': ('goto 90', []),
}
AUTO = {'default': ('auto', [10, 20, 30]), 'start': ('auto 100', [100, 110, 120]),
        'step': ('auto 100,5', [100, 105, 110]),
        'omitted': ('auto ,20', [10, 30, 50]),
        'collision': ('auto', [10, 20, 30])}
OLD = [5, 7, 12, 30, 31, 40, 50]
NAMES = ['ref-'+x for x in REFS] + ['renum-'+x for x in RENUMBER] + ['auto-'+x for x in AUTO]


def program(undefined=False):
    # Z=1 の直接GOTOはその行の印だけを立てる。RUNはZを初期化する。
    tails = ['goto 999' if undefined else 'goto 7', 'gosub 40',
             'if 1 then 30', 'on 1 goto 31', 'restore 40:run 50',
             'return:data 1', 'end']
    return [f'{n} poke &he{0x010+i:03x},{i+1}:if z=1 then end else {tail}'
            for i, (n, tail) in enumerate(zip(OLD, tails))]


def plan(name):
    cmds = [('type', 'clear 200,&hdfff'), ('type', 'new')]
    arm = name.split('-', 1)[1]
    if name.startswith('renum-') and arm != 'empty':
        cmds += [('type', x) for x in program(arm == 'undefined')]
        if arm == 'program':
            cmds += [('type', '90 on error goto 95:renum:end'),
                     ('type', '95 poke &he018,err:end')]
    if name == 'auto-collision':
        cmds.append(('type', '10 poke &he017,8:end'))
    cmds += [('type', 'for i=&he000 to &he048:poke i,0:next'), ('type', 'poke &he000,151')]
    if name.startswith('renum-') and arm != 'empty':
        for i, n in enumerate(OLD):
            cmds += [('type', 'z=1'), ('type', f'goto {n}'), ('type', f'poke &he002,{40+i}')]
    if name.startswith('renum-'):
        cmds += [('type', 'poke &he002,1'), ('type', 'run'), ('type', 'poke &he002,2')]
        operation, new = RENUMBER[arm]
        candidates = sorted(set(OLD + new)) if arm != 'empty' else []
    elif name.startswith('auto-'):
        operation, candidates = AUTO[arm]
    else:
        operation = REFS[arm]; candidates = []
    cmds += [('type', 'cls:locate 0,5'), ('snap', 'before'), ('type', operation), ('snap2', 'operation')]
    if name.startswith('auto-'):
        cmds += [('type', f'poke &he{0x010+i:03x},{i+1}:end') for i in range(3)]
        cmds += [('key', 'RETROK_BREAK'),
                 ('type', 'poke &he006,csrlin:poke &he007,pos(0)'),
                 ('type', 'poke &he002,3')]
    if name.startswith('renum-'):
        cmds += [('type', 'poke &he002,3'), ('type', 'run'), ('type', 'poke &he002,4')]
    if candidates:
        cmds.append(('type', 'for i=&he010 to &he017:poke i,0:next'))
    for i, n in enumerate(candidates):
        cmds += [('type', 'z=1'), ('type', 'cls:locate 0,5'), ('type', f'goto {n}'),
                 ('snap2', f'p{i}'), ('type', f'poke &he002,{10+i}')]
    cmds += [('type', 'poke &he001,163')]
    return cmds, candidates


def parse_signatures(path):
    result = {}; current = None
    for line in path.read_text().splitlines():
        fields = line.split('\t')
        if fields[0] == 'snapshot_id':
            current = fields[1]; result[current] = {}
        elif current is not None and len(fields) == 3 and fields[0].isdigit():
            result[current][int(fields[0])] = (int(fields[1]), fields[2])
    return result


def parse_memory(path, first_type_frame):
    raw = path.read_text()
    if not re.search(r'^range\s+: E000-E048$', raw, re.M): raise ValueError('範囲')
    m = re.search(r'^# 取りこぼし: 0件 / 総イベント数: (\d+)件$', raw, re.M)
    if not m: raise ValueError('取りこぼし')
    writes = []; boot_writes = 0; count = 0
    for row in raw.splitlines():
        if re.match(r'^\s*\d+\s', row):
            x = re.fullmatch(r'\s*(\d+)\s+(\d+)\s+[0-9A-F]{4}\s+([0-9A-F]{4})\s+([0-9A-F]{2})', row)
            if not x or int(x[1]) != count+1: raise ValueError('形式')
            count += 1
            if int(x[2]) < first_type_frame: boot_writes += 1
            else: writes.append((int(x[3], 16), int(x[4], 16)))
    if count != int(m[1]): raise ValueError('件数')
    prefix = [(a, 0) for a in range(0xe000, 0xe049)] + [(0xe000, 151)]
    if writes[:len(prefix)] != prefix: raise ValueError('初期化')
    common.reject_unexpected(writes[len(prefix):], {0xe001, 0xe002, 0xe006, 0xe007} | set(range(0xe010, 0xe019)), len(prefix))
    if writes[-1:] != [(0xe001, 163)]: raise ValueError('完了')
    return {'writes': writes[len(prefix):-1], 'boot_writes': boot_writes}


def cursor_at(path, frames):
    # CRTCのカーソル座標のみを抽出する。BASIC内部のCSRLIN/POSとは区別する。
    pattern = re.compile(r'^\s*\d+\s+\d+\s+(\d+)\s+main\s+(OUT|IN)\s+([0-9A-F]{4})\s+([0-9A-F]{2})\s+[0-9A-F]{4}\s*$')
    result = []; index = 0; cursor = None; pending = None
    with path.open() as f:
        for line in f:
            m = pattern.match(line)
            if not m: continue
            frame = int(m[1])
            while index < len(frames) and frame >= frames[index]:
                result.append(cursor); index += 1
            if m[2] != 'OUT': continue
            port, value = int(m[3], 16) & 255, int(m[4], 16)
            if port == 0x51: pending = [] if value in (0x80, 0x81) else None
            elif port == 0x50 and pending is not None:
                pending.append(value)
                if len(pending) == 2: cursor = list(pending); pending = None
            else: pending = None
    while index < len(frames): result.append(cursor); index += 1
    return result


def capture(rom, name, work, official=False):
    cmds, candidates = plan(name)
    args = [str(kw.FRONT), '--core', str(kw.find_core()), '--rom-dir', str(rom),
            '--screen-signature-only', '--out', str(work/'signatures.tsv')]
    at = 700 if official else 100; snapshots = []; frames = {}
    first_type_frame = at
    for kind, value in cmds:
        if kind == 'type':
            args += ['--type-at', str(at), '--type', value+'\n']; at += (len(value)+1)*8+240
        elif kind == 'key':
            args += ['--key-at', str(at), '--key', value]; at += 300
        else:
            for delay in ((60, 160) if kind == 'snap2' else (60,)):
                sid = value + ('a' if delay == 60 else 'b')
                frames[sid] = at+delay
                args += ['--screen-signature-at', f'{sid}:{at+delay}']; snapshots.append(sid)
            at += 260
    log = work/'ram.log'; report = work/'signatures.tsv'
    io = work/'io.log'
    if name == 'auto-collision': args += ['--io-log', str(io)]
    args += ['--mem-write-log', str(log), '--mem-write-range', 'E000-E048',
             '--mem-write-from-frame', '0', '--frames', str(at+600)]
    try:
        p = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                           env=dict(os.environ, M6FH_LONG_TYPING='1'))
        if p.returncode: raise ValueError('実行/打鍵')
        sigs = parse_signatures(report)
        if set(sigs) != set(snapshots): raise ValueError('画面署名')
        for sid in snapshots:
            if sid.endswith('b') and sigs[sid] != sigs[sid[:-1]+'a']: raise ValueError('画面安定')
        if 5 not in sigs['beforea'] or any(i in sigs['beforea'] for i in range(5)):
            raise ValueError('開始位置')
        operation = next(value for kind, value in cmds[cmds.index(('snap', 'before'))+1:] if kind == 'type')
        expected = common.signature(6, operation)
        if sigs['operationa'].get(6) != (expected['char_count'], expected['sha256']):
            raise ValueError('打鍵反映')
        for i, n in enumerate(candidates):
            expected = common.signature(6, f'goto {n}')
            if sigs[f'p{i}a'].get(6) != (expected['char_count'], expected['sha256']):
                raise ValueError('GOTO打鍵反映')
        memory = parse_memory(log, first_type_frame)
        validate_events(name, candidates, memory['writes'])
        result = {'screen': {k: v for k, v in sigs.items() if not k.endswith('b')},
                  'writes': memory['writes'], 'boot_writes': memory['boot_writes'], 'candidates': candidates}
        if name == 'auto-collision':
            times = [frames['operationa'], frames['operationb']]
            geometry = key_measure.parse_geometry(io, times)
            cursors = cursor_at(io, times)
            if geometry[0] != geometry[1] or geometry[0]['columns'] != 80 or geometry[0]['rows'] is None:
                raise ValueError('表示設定')
            if cursors[0] != cursors[1]: raise ValueError('カーソル安定')
            result['collision_cursor_crtc'] = cursors[0]
            result['collision_geometry'] = geometry[0]
        return result
    finally:
        log.unlink(missing_ok=True); report.unlink(missing_ok=True); io.unlink(missing_ok=True)


def validate_events(name, candidates, writes):
    arm = name.split('-', 1)[1]
    if name.startswith('renum-') and arm != 'empty':
        for i in range(len(OLD)):
            if writes[:2] != [(0xe010+i, i+1), (0xe002, 40+i)]:
                raise ValueError('操作前の行確認')
            writes = writes[2:]
    expected = ([1, 2, 3, 4] if name.startswith('renum-') else
                [3] if name.startswith('auto-') else []) + list(range(10, 10+len(candidates)))
    stages = [value for addr, value in writes if addr == 0xe002]
    if stages != expected: raise ValueError('段階')


def response(rows, prompts=None):
    # 位置を固定した後、最後の非空行をプロンプトとして除く。
    lines = sorted((int(row), value) for row, value in rows.items() if 7 <= int(row) < 19)
    if not lines: raise ValueError('プロンプト')
    if prompts is not None and prompts.get(lines[-1][0]) != lines[-1][1]:
        raise ValueError('プロンプト')
    return lines[:-1]


def identify(target, references):
    matches = [name for name, value in references.items() if value == target]
    return matches[0] if len(matches) == 1 else ('候補外' if not matches else '参照衝突')


def summarize(record, refs, prompts, name):
    screen = record['screen']; writes = record['writes']; candidates = record['candidates']
    try: operation = identify(response(screen['operationa'], prompts), refs)
    except ValueError:
        if not name.startswith('auto-'): raise
        operation = '入力中またはプロンプト欠測'
    result = {'operation': operation, 'probes': {}}
    remaining = list(writes)
    if name.startswith('renum-') and name != 'renum-empty': remaining = remaining[14:]
    if name.startswith('renum-'):
        regions = {}
        for stage in (1, 2, 3, 4):
            segment = []
            while remaining and remaining[0] != (0xe002, stage): segment.append(remaining.pop(0))
            if not remaining: raise ValueError('段階')
            remaining.pop(0); regions[stage] = segment
        result['before_run'] = regions[2]
        result['after_run'] = regions[4]
        expected_path = [(0xe010+i, i+1) for i in (0, 1, 5, 2, 3, 4, 6)]
        result['before_path_complete'] = regions[2] == expected_path
        result['run_order_equal'] = (regions[2] == regions[4]) if result['before_path_complete'] else None
    elif name.startswith('auto-'):
        pre = []
        while remaining and remaining[0] != (0xe002, 3): pre.append(remaining.pop(0))
        if not remaining: raise ValueError('停止')
        remaining.pop(0)
        if len(pre) < 2 or [a for a, _ in pre[-2:]] != [0xe006, 0xe007]:
            raise ValueError('停止後カーソル診断')
        result['after_stop'] = pre
        result['after_stop_cursor'] = {'csrlin': pre[-2][1], 'pos': pre[-1][1]}
        result['auto_screen'] = screen['operationa']
        if name == 'auto-collision':
            result['collision_cursor_crtc'] = record['collision_cursor_crtc']
    if candidates:
        if remaining[:8] != [(a, 0) for a in range(0xe010, 0xe018)]:
            raise ValueError('行印初期化')
        del remaining[:8]
    for i, n in enumerate(candidates):
        segment = []
        while remaining and remaining[0] != (0xe002, 10+i): segment.append(remaining.pop(0))
        if not remaining: raise ValueError('GOTO段階')
        remaining.pop(0)
        result['probes'][str(n)] = {'marks': segment,
                                    'response': identify(response(screen[f'p{i}a'], prompts), refs)}
    if remaining: raise ValueError('余分な書込み')
    return result


def stable_pair(pair):
    return len(pair) == 2 and pair[0] is not None and pair[0] == pair[1]


def measure(rom, work, official=False):
    work.mkdir(parents=True, exist_ok=True)
    records = {name: {'runs': [None, None], 'gate': False} for name in NAMES}
    def run_one(name, index):
        directory = work/name/str(index); directory.mkdir(parents=True, exist_ok=True)
        return capture(rom, name, directory, official)
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        tasks = {pool.submit(run_one, name, i): (name, i) for name in NAMES for i in range(2)}
        for task in concurrent.futures.as_completed(tasks):
            name, i = tasks[task]
            try: records[name]['runs'][i] = task.result()
            except (ValueError, OSError) as exc:
                print(f'{name}: 関門失敗 ({exc})', flush=True)
            print(f'{name}: {i+1}走終了', flush=True)
    for name in NAMES:
        records[name]['gate'] = stable_pair(records[name]['runs'])
        print(f'{name}: '+('通過' if records[name]['gate'] else '失敗'), flush=True)
    if all(records['ref-'+x]['gate'] for x in REFS):
        refs = {x: response(records['ref-'+x]['runs'][0]['screen']['operationa']) for x in REFS}
        prompts = {}
        for x in REFS:
            rows = records['ref-'+x]['runs'][0]['screen']['operationa']
            lines = sorted((int(k), v) for k, v in rows.items() if 7 <= int(k) < 19)
            if not lines: raise ValueError('参照プロンプト')
            row, value = lines[-1]
            if row in prompts and prompts[row] != value: raise ValueError('参照プロンプト不一致')
            prompts[row] = value
        start = records['ref-none']['runs'][0]['screen']['beforea'].get(5)
        for name in NAMES:
            if not name.startswith('ref-') and records[name]['gate']:
                try:
                    if records[name]['runs'][0]['screen']['beforea'].get(5) != start:
                        raise ValueError('開始プロンプト')
                    records[name]['result'] = summarize(records[name]['runs'][0], refs, prompts, name)
                except ValueError:
                    records[name]['gate'] = False
                    print(f'{name}: 判定失敗', flush=True)
    return {'version': 1, 'records': records}


def valid(data):
    return (data.get('version') == 1 and set(data.get('records', {})) == set(NAMES)
            and all(r['gate'] and stable_pair(r['runs']) for r in data['records'].values()))


def check(actual, expected):
    return valid(actual) and valid(expected) and actual == expected


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2)+'\n')


def selftest():
    work = WORK/'selftest'; work.mkdir(parents=True, exist_ok=True)
    rom = work/'rom'
    p = subprocess.run([sys.executable, '-B', str(ROOT/'src/build_main_rom.py'), str(rom),
                        '--work-dir', str(work/'asm')], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if p.returncode: raise ValueError('自作ROMビルド')
    data = measure(rom, work)
    save(work/'actual.json', data)
    if not valid(data): print('全腕関門: 失敗'); return 1
    # JSON往復後に照合し、実際のCLIと同じ型にする。
    data = json.loads((work/'actual.json').read_text())
    save(work/'expected.json', data)
    assert check(data, data)
    broken = copy.deepcopy(data)
    for run in broken['records'][NAMES[0]]['runs']:
        run['screen']['operationa']['6'][0] ^= 1
    assert valid(broken) and not check(data, broken)
    a, b = [(7, [1, 'a'])], [(7, [1, 'b'])]
    assert identify(a, {'ERR8': a, 'ERR2': b}) == 'ERR8'
    assert identify(a, {'ERR8': b, 'ERR2': b}) == '候補外'
    mismatch = copy.deepcopy(data)
    mismatch['records'][NAMES[0]]['runs'][1]['screen']['operationa']['6'][0] ^= 1
    assert not valid(mismatch)
    common.unexpected_selftest(lambda p: parse_memory(p, 10), work/'synthetic.log', [(0xe001, 163)])
    print('合成対照: 起動時書込みを除外、打鍵後の前置き前と器具外の書込みを拒否')
    print('陰性対照: 壊した期待値・参照ずらし・2走不一致を拒否')
    print(f'全腕関門: {len(NAMES)}/{len(NAMES)}')
    return 0


def main():
    ap = argparse.ArgumentParser(); sub = ap.add_subparsers(dest='command', required=True)
    sub.add_parser('selftest')
    m = sub.add_parser('measure'); m.add_argument('--rom-dir', type=Path, required=True)
    m.add_argument('--work-dir', type=Path, required=True); m.add_argument('--out', type=Path, required=True)
    m.add_argument('--official', action='store_true')
    e = sub.add_parser('expected'); e.add_argument('--measured', type=Path, required=True); e.add_argument('--out', type=Path, required=True)
    c = sub.add_parser('check'); c.add_argument('--measured', type=Path, required=True); c.add_argument('--expected', type=Path, required=True)
    args = ap.parse_args()
    if args.command == 'selftest': return selftest()
    if args.command == 'measure':
        data = measure(args.rom_dir, args.work_dir, args.official); save(args.out, data); return int(not valid(data))
    data = json.loads(args.measured.read_text())
    if args.command == 'expected':
        if not valid(data): print('関門失敗'); return 1
        save(args.out, data); return 0
    ok = check(data, json.loads(args.expected.read_text()))
    print('照合: '+('一致' if ok else '不一致')); return int(not ok)


if __name__ == '__main__':
    try: raise SystemExit(main())
    except (ValueError, OSError, KeyError) as exc:
        print('NG 器具:', type(exc).__name__, '（本文非出力）'); raise SystemExit(1)
