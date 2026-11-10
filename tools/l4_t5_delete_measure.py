#!/usr/bin/env python3
"""l4-t5 の画面署名・行生存測定。画面本文は出力・保存しない。"""
import argparse
import copy
import dataclasses
import json
import os
import re
import subprocess
import sys
from pathlib import Path

sys.dont_write_bytecode = True
import l4_listkw_measure as kw
import l4_key_measure as key_measure
import check_l3_screen_output as screen

REPO = Path(__file__).resolve().parents[1]
WORK = Path(os.environ.get('PC88_T5_WORK', REPO / 'tmp/t5-work'))
DELETE = {
    'single': 'delete 20', 'range': 'delete 20-40',
    'open-left': 'delete -30', 'open-right': 'delete 30-',
    'comma': 'delete 20,40', 'missing-ends': 'delete 15-45',
    'missing-single': 'delete 25', 'reverse': 'delete 40-20',
    'empty': 'delete', 'program': 'goto 95',
}
REFS = {'none': 'rem', 'ERR2': 'error 2', 'ERR5': 'error 5', 'ERR8': 'error 8'}
TRACES = {}
for count in (3, 5):
    for mode in ('off', 'on', 'toggle'):
        TRACES[f'trace-{count}-{mode}'] = (count, mode)
TRACES.update({'trace-program': (3, 'program'), 'trace-direct': (3, 'direct'),
               'trace-new': (3, 'new'), 'trace-invalid': (3, 'invalid')})
NAMES = ['ref-' + k for k in REFS] + list(DELETE) + list(TRACES)


def signature(row, body):
    return dataclasses.asdict(screen.signature([(row, body)]))


def bodies(raw):
    if len(raw) != 3000:
        raise ValueError('画面長')
    # q88measure の write_screen と同一の ASCII 変換と末尾空白除去。
    return [''.join(chr(b) if 32 <= b < 127 else ' ' for b in raw[r*120:r*120+80]).rstrip(' ')
            for r in range(25)]


def metrics(rows, raw, height):
    return [dict(row=i, nonblank=sum(c not in (0, 32) for c in raw[i*120:i*120+80]), **signature(i, body))
            for i, body in enumerate(rows[:height])]


def identify(target, references):
    matches = [name for name, value in references.items() if target == value]
    return matches[0] if len(matches) == 1 else ('候補外' if not matches else '参照衝突')


def stable_pair(pair):
    return len(pair) == 2 and all(item is not None for item in pair) and pair[0] == pair[1]


def trace_program(count, mode):
    # 20行は2回通過する。5行腕は番号の異なる2行を追加する。
    terminal = 'poke &he03a,csrlin:poke &he03b,pos(0):end'
    if mode == 'program':
        return ['10 tron', '20 a=a+1', '30 if a<2 then 20', '40 troff', '50 '+terminal]
    if count == 5:
        return ['10 a=0', '20 a=a+1', '30 if a<2 then 20', '40 a=a+1', '50 '+terminal]
    return ['10 a=0', '20 a=a+1:if a<2 then 20', '30 '+terminal]


def plan(name):
    delete = name in DELETE or name.startswith('ref-')
    cmds = ['clear 200,&hdfff', 'new']
    if delete:
        cmds += [f'{n} poke &he{0x010+i:03x},1:end' for i, n in enumerate(range(10, 100, 10))]
        if name == 'program':
            cmds += ['95 delete 30:end']
    else:
        count, mode = TRACES[name]
        cmds += trace_program(count, mode)
    cmds += ['for i=&he000 to &he048:poke i,0:next', 'poke &he000,151']
    if delete:
        for i,n in enumerate(range(10,100,10)):
            cmds += [f'goto {n}', f'poke &he{0x030+i:03x},1']
    else:
        mode = TRACES[name][1]
        if mode == 'off': cmds += ['troff']
        if mode in ('on','direct','new'): cmds += ['tron']
        if mode == 'toggle': cmds += ['tron', 'run', 'troff']
        if mode == 'new': cmds += ['new', *trace_program(3, 'on')]
    cmds += ['cls:locate 0,5', '@before']
    if name.startswith('ref-'): operation = REFS[name[4:]]
    elif name in DELETE: operation = DELETE[name]
    elif TRACES[name][1] == 'direct': operation = 'rem'
    elif TRACES[name][1] == 'invalid': operation = 'tron 1'
    else: operation = 'run'
    cmds += [operation, '@after', 'poke &he006,csrlin:poke &he007,pos(0)', 'poke &he005,err']
    if name in DELETE:
        cmds += ['for i=&he010 to &he018:poke i,0:next']
        for i,n in enumerate(range(10,100,10)):
            cmds += ['error 250', f'goto {n}', f'poke &he{0x020+i:03x},err']
    cmds += ['poke &he001,163']
    return cmds, operation


def reject_unexpected(writes, allowed, offset=0):
    bad = [(i, a) for i, (a, _) in enumerate(writes, offset+1) if a not in allowed]
    if bad:
        raise ValueError('器具外書込み: %d件 %s' %
                         (len(bad), ','.join('%d:%04X' % item for item in bad)))


def synthetic_log(path, extra, boot=False, before_prefix=False):
    writes = [(a, 0) for a in range(0xe000, 0xe049)] + [(0xe000, 151)]
    writes += extra
    timed = ([(9, 0xe048, 42)] if boot else []) + ([(10, 0xe048, 42)] if before_prefix else []) + [(10, a, v) for a, v in writes]
    path.write_text('range : E000-E048\n# 取りこぼし: 0件 / 総イベント数: %d件\n' % len(timed) +
                    ''.join('%d %d 0000 %04X %02X\n' % (i, frame, a, v)
                            for i, (frame, a, v) in enumerate(timed, 1)))


def unexpected_selftest(parser, path, tail):
    synthetic_log(path, tail, boot=True)
    assert parser(path)['boot_writes'] == 1
    synthetic_log(path, tail, before_prefix=True)
    try:
        parser(path)
    except ValueError:
        pass
    else:
        raise AssertionError('前置き前の書込みを検出できない')
    synthetic_log(path, tail[:-1] + [(0xe048, 42)] + tail[-1:])
    try:
        parser(path)
    except ValueError as exc:
        assert '器具外書込み: 1件' in str(exc) and ':E048' in str(exc)
    else:
        raise AssertionError('器具外書込みを検出できない')
    finally:
        path.unlink(missing_ok=True)


def parse_memory(path, name, first_type_frame):
    raw = path.read_text()
    if not re.search(r'^range\s+: E000-E048$', raw, re.M): raise ValueError('範囲')
    total = re.search(r'^# 取りこぼし: 0件 / 総イベント数: (\d+)件$', raw, re.M)
    if not total: raise ValueError('取りこぼし')
    writes = []; boot_writes = 0; count = 0
    for row in raw.splitlines():
        if re.match(r'^\s*\d+\s', row):
            m = re.fullmatch(r'\s*(\d+)\s+(\d+)\s+[0-9A-F]{4}\s+([0-9A-F]{4})\s+([0-9A-F]{2})', row)
            if not m or int(m[1]) != count+1: raise ValueError('記録形式')
            count += 1
            if int(m[2]) < first_type_frame: boot_writes += 1
            else: writes.append((int(m[3],16), int(m[4],16)))
    if count != int(total[1]): raise ValueError('件数')
    allowed = {0xe000, 0xe001, 0xe005, 0xe006, 0xe007, 0xe03a, 0xe03b} | set(range(0xe010, 0xe019)) | set(range(0xe020, 0xe029)) | set(range(0xe030, 0xe039))
    reject_unexpected(writes[74:], allowed, 74)
    prefix = [(a,0) for a in range(0xe000,0xe049)] + [(0xe000,151)]
    if writes[:len(prefix)] != prefix:
        bad = [(i+1, writes[i][0]) for i in range(min(len(prefix),len(writes))) if writes[i] != prefix[i]]
        raise ValueError('初期化: 不一致%d件 %s' % (len(bad), ','.join('%d:%04X' % item for item in bad)))
    if writes[-1:] != [(0xe001,163)]: raise ValueError('完了')
    tail = writes[len(prefix):-1]
    if name in DELETE or name.startswith('ref-'):
        for i in range(9):
            if tail[:2] != [(0xe010+i,1), (0xe030+i,1)]: raise ValueError('操作前の行確認')
            del tail[:2]
    trace_cursor=[]
    if name in TRACES:
        while tail and tail[0][0] == 0xe03a:
            if len(tail)<2 or tail[1][0] != 0xe03b: raise ValueError('実行中カーソル')
            trace_cursor.append(dict(csrlin=tail[0][1],pos=tail[1][1])); del tail[:2]
    if len(tail)<3 or [x[0] for x in tail[:3]] != [0xe006,0xe007,0xe005]: raise ValueError('カーソル/ERR')
    result = dict(csrlin=tail[0][1], pos=tail[1][1], err=tail[2][1], boot_writes=boot_writes); del tail[:3]
    if name in TRACES: result['trace_cursor']=trace_cursor
    if name in DELETE:
        if tail[:9] != [(a,0) for a in range(0xe010,0xe019)]: raise ValueError('行印初期化')
        del tail[:9]
        result['survival'], result['goto_err'] = [], []
        for i in range(9):
            alive = bool(tail and tail[0] == (0xe010+i,1))
            if alive: tail.pop(0)
            if not tail or tail[0][0] != 0xe020+i: raise ValueError('GOTO診断')
            result['survival'].append(int(alive)); result['goto_err'].append(tail.pop(0)[1])
    if tail: raise ValueError('余分な書込み')
    return result


def capture(rom, name, work, official=False):
    cmds, operation = plan(name)
    args = [str(kw.FRONT), '--core', str(kw.find_core()), '--rom-dir', str(rom)]
    at = 700 if official else 100
    first_type_frame = at
    dumps, frames = [], []
    for cmd in cmds:
        if cmd.startswith('@'):
            for extra in ((60,) if cmd == '@before' else (60,160)):
                frame=at+extra
                args += ['--vram-dump', str(work/'screen.bin'), '--vram-dump-at', str(frame)]
                dumps.append(work/f'screen.f{frame:06d}.bin')
                frames.append(frame)
            at += 260
        else:
            args += ['--type-at',str(at),'--type',cmd+'\n']
            at += (len(cmd)+1)*8+240
    log=work/'ram.log'; io_log=work/'io.log'
    args += ['--io-log',str(io_log),'--mem-write-log',str(log),'--mem-write-range','E000-E048',
             '--mem-write-from-frame','0','--frames',str(at+600)]
    try:
        p=subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                         env=dict(os.environ,M6FH_LONG_TYPING='1'))
        if p.returncode or b'untypable' in p.stderr.lower() or '打てない'.encode() in p.stderr:
            raise ValueError('実行/打鍵')
        raw=[x.read_bytes() for x in dumps]
        if raw[1] != raw[2]: raise ValueError('画面安定')
        geometry=key_measure.parse_geometry(io_log,frames[1:])
        if geometry[0] != geometry[1] or geometry[0]['columns'] != 80 or geometry[0]['rows'] is None:
            raise ValueError('表示設定')
        height=geometry[0]['rows']
        before, after = bodies(raw[0]), bodies(raw[1])
        # 対照行を署名化し、同じ内容のプロンプトだけを探す。
        if not before[5] or any(before[i] for i in range(0,5)) or before[6]: raise ValueError('開始位置')
        if after[6].strip().lower() != operation: raise ValueError('打鍵反映')
        prompt_sig=signature(0,before[5])
        prompts=[i for i in range(7,min(height,19)) if signature(0,after[i]) == prompt_sig]
        if len(prompts)!=1: raise ValueError('プロンプト')
        end=prompts[0]
        memory=parse_memory(log,name,first_type_frame)
        # CSRLIN は診断文の RETURN 後なので、対照走の位置から2行進む。
        if memory['csrlin'] != end+2: raise ValueError('カーソル位置')
        return dict(start=6, prompt=end, response=[signature(i,after[i]) for i in range(7,end)],
                    geometry=geometry[0], rows=metrics(after,raw[1],height), memory=memory)
    finally:
        log.unlink(missing_ok=True)
        io_log.unlink(missing_ok=True)
        for x in dumps:
            x.unlink(missing_ok=True); Path(str(x)+'.info.txt').unlink(missing_ok=True)


def measure(rom, work, official=False):
    work.mkdir(parents=True,exist_ok=True)
    records={}
    for name in NAMES:
        runs=[]
        for _ in range(2):
            try: runs.append(capture(rom,name,work,official))
            except (ValueError,OSError) as e:
                print(f'{name}: 関門失敗 ({e})',flush=True); runs.append(None)
        records[name]={'runs':runs,'gate':stable_pair(runs)}
        print(f'{name}: '+('通過' if records[name]['gate'] else '失敗'),flush=True)
    refs={k:records['ref-'+k]['runs'][0]['response'] for k in REFS if records['ref-'+k]['gate']}
    if len(refs)==len(REFS):
        for name in (*DELETE, *TRACES):
            rec=records[name]
            rec['identification']=identify(rec['runs'][0]['response'],refs) if rec['gate'] else '欠測'
    return dict(version=1,records=records)


def valid_measurement(data):
    return (data.get('version')==1 and set(data.get('records',{}))==set(NAMES) and
            all(r.get('gate') is True and stable_pair(r.get('runs',[])) for r in data['records'].values()))


def check(actual, expected):
    return valid_measurement(actual) and valid_measurement(expected) and actual==expected


def save(path, data):
    Path(path).write_text(json.dumps(data,ensure_ascii=False,sort_keys=True,indent=2)+'\n')


def selftest():
    work=WORK/'selftest'; work.mkdir(parents=True,exist_ok=True)
    unexpected_selftest(lambda p: parse_memory(p, 'trace-3-off', 10), work/'synthetic.log',
                        [(0xe006, 1), (0xe007, 2), (0xe005, 0), (0xe001, 163)])
    print('合成対照: 起動時書込みを除外、打鍵後の前置き前と器具外の書込みを拒否')
    rom=work/'rom'
    p=subprocess.run([sys.executable,str(REPO/'src/build_main_rom.py'),str(rom),'--work-dir',str(work/'asm')],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    if p.returncode: raise ValueError('自作ROMビルド')
    data=measure(rom,work)
    save(work/'actual.json',data)
    if not valid_measurement(data):
        print('全腕関門: 失敗'); return 1
    save(work/'expected.json',data)
    expected=json.loads((work/'expected.json').read_text())
    assert check(data,expected)
    broken=copy.deepcopy(expected)
    for run in broken['records'][NAMES[0]]['runs']:
        run['memory']['err'] ^= 1
    assert valid_measurement(broken) and not check(data,broken)
    a=[signature(7,'a')]; b=[signature(7,'b')]
    assert identify(a,{'ERR2':a,'ERR5':b})=='ERR2'
    assert identify(a,{'ERR2':b,'ERR5':b})=='候補外'
    mismatch=copy.deepcopy(data)
    mismatch['records'][NAMES[0]]['runs'][1]['memory']['err'] ^= 1
    assert not valid_measurement(mismatch)
    print('陰性対照: 壊した期待値・参照ずらし・2走不一致 すべて通過')
    print('自作同定: '+', '.join(f'{n}={data["records"][n]["identification"]}' for n in DELETE))
    print(f'全腕関門: {len(NAMES)}/{len(NAMES)}')
    return 0


def main():
    ap=argparse.ArgumentParser(); sub=ap.add_subparsers(dest='cmd',required=True)
    m=sub.add_parser('measure'); m.add_argument('--rom-dir',type=Path,required=True); m.add_argument('--work-dir',type=Path,default=WORK/'measure'); m.add_argument('--out',type=Path,required=True); m.add_argument('--official',action='store_true')
    e=sub.add_parser('expected'); e.add_argument('--measured',type=Path,required=True); e.add_argument('--out',type=Path,required=True)
    c=sub.add_parser('check'); c.add_argument('--measured',type=Path,required=True); c.add_argument('--expected',type=Path,required=True)
    sub.add_parser('selftest'); a=ap.parse_args()
    if a.cmd=='selftest': return selftest()
    if a.cmd=='measure':
        data=measure(a.rom_dir,a.work_dir,a.official); save(a.out,data); return int(not valid_measurement(data))
    actual=json.loads(a.measured.read_text())
    if a.cmd=='expected':
        if not valid_measurement(actual): print('関門失敗'); return 1
        save(a.out,actual); return 0
    ok=check(actual,json.loads(a.expected.read_text())); print('照合: '+('一致' if ok else '不一致')); return int(not ok)

if __name__=='__main__':
    try: raise SystemExit(main())
    except (OSError,ValueError,KeyError,AssertionError) as exc:
        print('NG 器具:',type(exc).__name__,'（本文非出力）'); raise SystemExit(1)
