#!/usr/bin/env python3
"""EDIT・MOTOR測定。画面本文とIOログの生データは保存しない。"""
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
import l4_t7_autorenum_measure as base

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / 'tmp/t10-work'
REFS = {'none': 'rem', 'ERR2': 'error 2', 'ERR5': 'error 5', 'ERR8': 'error 8'}
EDIT = {'line': 'edit 20', 'rewrite': 'edit 20', 'dot': 'edit .',
        'empty': 'edit', 'missing': 'edit 25', 'overflow': 'edit 70000', 'program': 'goto 90'}
MOTOR = {'bare': 'motor', 'one': 'motor 1', 'zero': 'motor 0',
         'two': 'motor 2', 'negative': 'motor -1', 'large': 'motor 256', 'program': 'goto 90'}
NAMES = ['ref-'+x for x in REFS] + ['edit-'+x for x in EDIT] + ['motor-'+x for x in MOTOR]
LINES = [f'{n} poke &he{0x010+i:03x},{i+1}:end' for i,n in enumerate((10,20,30))]


def plan(name):
    cmds = [('type', 'clear 200,&hdfff'), ('type', 'new')]
    if name.startswith('edit-'):
        cmds += [('type', x) for x in LINES]
        if name == 'edit-program':
            cmds += [('type','90 on error goto 95:edit 20:end'), ('type','95 poke &he018,err:end')]
        # 最後に入力した行を20とする。
        if name == 'edit-dot': cmds += [('type', LINES[1])]
    if name == 'motor-program':
        cmds += [('type','90 on error goto 95:motor 1:poke &he017,1:end'), ('type','95 poke &he018,err:end')]
    cmds += [('type','for i=&he000 to &he048:poke i,0:next'), ('type','poke &he000,151')]
    if name.startswith('edit-'):
        for i,n in enumerate((10,20,30)):
            cmds += [('type',f'goto {n}'),('type',f'poke &he002,{10+i}')]
    cmds += [('type','cls:locate 0,5'), ('snap','before')]
    op = REFS[name[4:]] if name.startswith('ref-') else (EDIT[name[5:]] if name.startswith('edit-') else MOTOR[name[6:]])
    cmds += [('type',op), ('snap2','operation')]
    if name == 'edit-rewrite':
        # EDIT開始位置から上書き入力。未受理ならその結果も区別する。
        cmds += [('type','20 poke &he011,9:end'), ('snap2','rewrite')]
    # 表示観察後、RETURNのみで入力状態から復帰する。
    if name.startswith('edit-') and name not in ('edit-program','edit-rewrite'):
        cmds += [('type','')]
    cmds += [('type','poke &he002,20')]
    if name.startswith('edit-'):
        cmds += [('type','poke &he011,0'), ('type','cls:locate 0,5'), ('type','goto 20'), ('snap2','probe'), ('type','poke &he002,21')]
    cmds += [('type','poke &he001,163')]
    return cmds, op


def io_outputs(path, start, end):
    pattern = re.compile(r'^\s*\d+\s+\d+\s+(\d+)\s+main\s+OUT\s+([0-9A-F]{4})\s+([0-9A-F]{2})\s+[0-9A-F]{4}\s*$')
    # ポートごとの値の変化だけを残す。繰返し回数やROM内部番地は保存しない。
    out = {}
    with path.open() as f:
        for line in f:
            m = pattern.match(line)
            if m and start <= int(m[1]) < end:
                port = str(int(m[2],16) & 255); value = int(m[3],16)
                seq = out.setdefault(port, [])
                if not seq or seq[-1] != value: seq.append(value)
    return out


def io_states(path, times):
    pattern = re.compile(r'^\s*\d+\s+\d+\s+(\d+)\s+main\s+OUT\s+([0-9A-F]{4})\s+([0-9A-F]{2})\s+[0-9A-F]{4}\s*$')
    states = {}; result = []; index = 0
    with path.open() as f:
        for line in f:
            m = pattern.match(line)
            if not m: continue
            while index < len(times) and int(m[1]) >= times[index]:
                result.append(states.copy()); index += 1
            states[str(int(m[2],16) & 255)] = int(m[3],16)
    while index < len(times): result.append(states.copy()); index += 1
    return result


def validate_io(path):
    main = False; count = 0; complete = False
    with path.open() as f:
        for line in f:
            if line.strip() == '# main': main = True; continue
            if not main: continue
            total = re.fullmatch(r'# 取りこぼし: (\d+)件 / 総イベント数: (\d+)件\s*', line)
            if total:
                complete = int(total[1]) == 0 and int(total[2]) == count
                break
            if re.match(r'^\s*\d+\s', line):
                m = re.fullmatch(r'\s*(\d+)\s+\d+\s+\d+\s+main\s+(?:OUT|IN)\s+[0-9A-F]{4}\s+[0-9A-F]{2}\s+[0-9A-F]{4}\s*', line)
                if not m or int(m[1]) != count + 1: raise ValueError('IO形式')
                count += 1
    if not complete: raise ValueError('IO取りこぼし')


def capture(rom, name, work, official=False):
    cmds, op = plan(name)
    args = [str(kw.FRONT),'--core',str(kw.find_core()),'--rom-dir',str(rom), '--screen-signature-only','--out',str(work/'signatures.tsv')]
    at = 700 if official else 100; first = at; snapshots=[]; frames={}; start=end=None
    for kind,value in cmds:
        if kind == 'type':
            if start is None and value == op and 'beforea' in frames: start=at
            args += ['--type-at',str(at),'--type',value+'\n']; at += (len(value)+1)*8+240
        elif kind == 'key': args += ['--key-at',str(at),'--key',value]; at += 300
        else:
            for delay in ((60,160) if kind == 'snap2' else (60,)):
                sid=value+('a' if delay==60 else 'b'); frames[sid]=at+delay
                args += ['--screen-signature-at',f'{sid}:{at+delay}']; snapshots.append(sid)
            at += 260
            if value == 'operation': end=at
    log=work/'ram.log'; report=work/'signatures.tsv'; io=work/'io.log'
    args += ['--io-log',str(io),'--mem-write-log',str(log),'--mem-write-range','E000-E048','--mem-write-from-frame','0','--frames',str(at+600)]
    try:
        p=subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=dict(os.environ,M6FH_LONG_TYPING='1'))
        if p.returncode: raise ValueError('実行/打鍵')
        sigs=base.parse_signatures(report)
        if set(sigs)!=set(snapshots): raise ValueError('画面署名')
        for sid in snapshots:
            if sid.endswith('b') and sigs[sid]!=sigs[sid[:-1]+'a']: raise ValueError('画面安定')
        if 5 not in sigs['beforea'] or any(i in sigs['beforea'] for i in range(5)): raise ValueError('開始位置')
        expected=common.signature(6,op)
        if sigs['operationa'].get(6)!=(expected['char_count'],expected['sha256']): raise ValueError('打鍵反映')
        memory=base.parse_memory(log,first)
        writes=memory['writes']
        stages=[v for a,v in writes if a==0xe002]
        if stages != ([10,11,12,20,21] if name.startswith('edit-') else [20]): raise ValueError('段階')
        if name.startswith('edit-') and writes[:6] != sum(([(0xe010+i,i+1),(0xe002,10+i)] for i in range(3)),[]): raise ValueError('元行')
        validate_io(io)
        cursor=base.cursor_at(io,[frames['operationa'],frames['operationb']])
        if cursor[0]!=cursor[1]: raise ValueError('カーソル安定')
        result={'screen':{k:v for k,v in sigs.items() if not k.endswith('b')},'writes':writes,'boot_writes':memory['boot_writes'],'cursor_crtc':cursor[0]}
        if name.startswith('motor-'):
            result['out_changes']={'before':io_outputs(io,frames['beforea'],start), 'operation':io_outputs(io,start,end)}
            result['out_last_before_after']=io_states(io,[start,end])
        return result
    finally:
        for path in (log,report,io): path.unlink(missing_ok=True)


def summarize(record, refs, prompts, name):
    rows=record['screen']['operationa']
    try: response=base.identify(base.response(rows,prompts),refs)
    except ValueError: response='入力中またはプロンプト欠測'
    candidates={}
    if name.startswith('edit-'):
        for i,line in enumerate(LINES):
            candidates[str((10,20,30)[i])]=[int(row) for row, val in rows.items() if val == tuple(common.signature(int(row),line)[k] for k in ('char_count','sha256'))]
    return {'response':response,'candidate_rows':candidates, 'probe_marks':[list(x) for x in record['writes'] if x[0] in (0xe011,0xe017,0xe018)]}


def measure(rom,work,official=False):
    work.mkdir(parents=True,exist_ok=True)
    records={n:{'runs':[None,None],'gate':False} for n in NAMES}
    def one(n,i):
        d=work/n/str(i); d.mkdir(parents=True,exist_ok=True); return capture(rom,n,d,official)
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        tasks={pool.submit(one,n,i):(n,i) for n in NAMES for i in range(2)}
        for task in concurrent.futures.as_completed(tasks):
            n,i=tasks[task]
            try: records[n]['runs'][i]=task.result()
            except (ValueError,OSError) as exc: print(f'{n}: 関門失敗 ({exc})',flush=True)
            print(f'{n}: {i+1}走終了',flush=True)
    for n in NAMES:
        records[n]['gate']=base.stable_pair(records[n]['runs'])
        print(f'{n}: '+('通過' if records[n]['gate'] else '失敗'),flush=True)
    if all(records['ref-'+x]['gate'] for x in REFS):
        refs={x:base.response(records['ref-'+x]['runs'][0]['screen']['operationa']) for x in REFS}
        prompts={}
        for x in REFS:
            rows=records['ref-'+x]['runs'][0]['screen']['operationa']; lines=sorted((int(k),v) for k,v in rows.items() if 7<=int(k)<19)
            if not lines: raise ValueError('参照プロンプト')
            row,value=lines[-1]
            if row in prompts and prompts[row]!=value: raise ValueError('参照プロンプト不一致')
            prompts[row]=value
        start=records['ref-none']['runs'][0]['screen']['beforea'].get(5)
        for n in NAMES:
            if not n.startswith('ref-') and records[n]['gate']:
                if records[n]['runs'][0]['screen']['beforea'].get(5)!=start: records[n]['gate']=False; continue
                records[n]['result']=summarize(records[n]['runs'][0],refs,prompts,n)
    else:
        for n in NAMES: records[n]['gate']=False
    return {'version':1,'records':records}


def valid(d):
    return d.get('version')==1 and set(d.get('records',{}))==set(NAMES) and all(r['gate'] and base.stable_pair(r['runs']) for r in d['records'].values())

def check(a,b): return valid(a) and valid(b) and a==b

def selftest():
    work=WORK/'selftest'; work.mkdir(parents=True,exist_ok=True); rom=work/'rom'
    p=subprocess.run([sys.executable,'-B',str(ROOT/'src/build_main_rom.py'),str(rom),'--work-dir',str(work/'asm')],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    if p.returncode: raise ValueError('自作ROMビルド')
    data=measure(rom,work); base.save(work/'actual.json',data)
    if not valid(data): return 1
    data=json.loads((work/'actual.json').read_text()); assert check(data,data)
    broken=copy.deepcopy(data)
    for r in broken['records']['ref-none']['runs']: r['screen']['operationa']['6'][0]^=1
    assert valid(broken) and not check(data,broken)
    a,b=[(7,[1,'a'])],[(7,[1,'b'])]
    assert base.identify(a,{'ERR8':a,'ERR2':b})=='ERR8' and base.identify(a,{'ERR8':b,'ERR2':b})=='候補外'
    mismatch=copy.deepcopy(data); mismatch['records']['ref-none']['runs'][1]['screen']['operationa']['6'][0]^=1
    assert not valid(mismatch)
    common.unexpected_selftest(lambda p:base.parse_memory(p,10),work/'synthetic.log',[(0xe001,163)])
    p=work/'sweep.log'; prefix=[(a,0) for a in range(0xe000,0xe049)]+[(0xe000,151),(0xe001,163)]
    for sweep in ([(a,0) for a in range(0xe000,0xe049)],[(a,(a*7)&255) for a in reversed(range(0xe000,0xe049))]):
        rows=[(9,a,v) for a,v in sweep]+[(10,a,v) for a,v in prefix]
        p.write_text('range : E000-E048\n# 取りこぼし: 0件 / 総イベント数: %d件\n'%len(rows)+''.join('%d %d 0000 %04X %02X\n'%(i,f,a,v) for i,(f,a,v) in enumerate(rows,1)))
        assert base.parse_memory(p,10)['boot_writes']==len(sweep)
        rows=[(10,a,v) for a,v in sweep]+[(10,a,v) for a,v in prefix]
        p.write_text('range : E000-E048\n# 取りこぼし: 0件 / 総イベント数: %d件\n'%len(rows)+''.join('%d %d 0000 %04X %02X\n'%(i,f,a,v) for i,(f,a,v) in enumerate(rows,1)))
        try: base.parse_memory(p,10)
        except ValueError: pass
        else: raise AssertionError('打鍵後掃引を検出できない')
    p.unlink()
    print('陰性対照: 期待値・参照ずらし・2走不一致・器具外書込み・打鍵後掃引を拒否、起動前掃引2種を除外')
    print(f'全腕関門: {len(NAMES)}/{len(NAMES)}'); return 0


def main():
    ap=argparse.ArgumentParser(); sub=ap.add_subparsers(dest='command',required=True)
    sub.add_parser('selftest')
    m=sub.add_parser('measure'); m.add_argument('--rom-dir',type=Path,required=True); m.add_argument('--work-dir',type=Path,required=True); m.add_argument('--out',type=Path,required=True); m.add_argument('--official',action='store_true')
    e=sub.add_parser('expected'); e.add_argument('--measured',type=Path,required=True); e.add_argument('--out',type=Path,required=True)
    c=sub.add_parser('check'); c.add_argument('--measured',type=Path,required=True); c.add_argument('--expected',type=Path,required=True)
    args=ap.parse_args()
    if args.command=='selftest': return selftest()
    if args.command=='measure':
        data=measure(args.rom_dir,args.work_dir,args.official); base.save(args.out,data); return int(not valid(data))
    data=json.loads(args.measured.read_text())
    if args.command=='expected':
        if not valid(data): return 1
        base.save(args.out,data); return 0
    ok=check(data,json.loads(args.expected.read_text())); print('照合: '+('一致' if ok else '不一致')); return int(not ok)

if __name__=='__main__':
    try: raise SystemExit(main())
    except (ValueError,OSError,KeyError) as exc:
        print('NG 器具:',type(exc).__name__,'（本文非出力）'); raise SystemExit(1)
