#!/usr/bin/env python3
"""l4-t8: 画面本文を保存せず、独立起動で測る。"""
import argparse
import concurrent.futures
import copy
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
sys.dont_write_bytecode = True
import l4_t7_autorenum_measure as base
import l4_t5_delete_measure as common
import l4_listkw_measure as kw

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / 'tmp/t8-work'
REFS = base.REFS
ARMS = ['input', 'return', 'length15', 'length16', 'default', 'shift', 'inkey',
        'on', 'off', 'stop', 'omitted', 'invalid0', 'invalid11', 'unset', 'undefined']
NAMES = ['ref-'+x for x in REFS] + ARMS


def program(name):
    lines = ['10 on error goto 900']
    if name in ('input', 'return', 'length15', 'length16', 'default', 'shift'):
        setting = {'input':'key 1,"q7z"', 'return':'key 1,"q7"+chr$(13)',
                   'length15':'key 1,"abcdefghijklmno"', 'length16':'key 1,"abcdefghijklmnop"',
                   'shift':'key 6,"q7z"'}.get(name)
        if setting: lines.append('20 '+setting)
        lines += ['30 poke &he002,1:input a$', '40 poke &he010,len(a$)',
                  '50 for i=1 to len(a$):if i<=32 then poke &he010+i,asc(mid$(a$,i,1))',
                  '60 next i', '70 poke &he003,1:end']
    elif name == 'inkey':
        lines += ['20 key 1,"q7z"', '30 poke &he002,1',
                  '40 for i=1 to 20', '50 a$=inkey$:if a$<>"" then poke &he010+i,asc(a$)',
                  '60 for j=1 to 500:next j:next i', '70 poke &he003,1:end']
    else:
        target = '999,200' if name == 'undefined' else (',200' if name == 'omitted' else '100,200')
        index = 2 if name == 'omitted' else 1
        mode = 'off' if name == 'off' else ('stop' if name == 'stop' else 'on')
        lines += [f'20 on key gosub {target}', f'30 key({index}) {mode}',
                  '40 poke &he002,1', '50 for i=1 to 20000:next i',
                  '60 poke &he004,1']
        if name == 'stop': lines += ['65 key(1) on', '66 for i=1 to 20000:next i']
        lines += ['70 poke &he003,1:end', '100 poke &he005,1:return',
                  '200 poke &he006,1:return']
    lines += ['900 poke &he007,err:poke &he008,erl:resume 950', '950 poke &he003,2:end']
    return lines


def plan(name):
    cmds = [('type','clear 200,&hdfff'), ('type','new')]
    direct = name.startswith('ref-') or name in ('invalid0','invalid11','unset')
    if not direct: cmds += [('type', x) for x in program(name)]
    cmds += [('type','for i=&he000 to &he048:poke i,0:next'), ('type','poke &he000,151'),
             ('type','cls:locate 0,5'), ('snap','before')]
    operation = REFS[name[4:]] if name.startswith('ref-') else {'invalid0':'key(0) on','invalid11':'key(11) on','unset':'key(1) on'}.get(name, 'run')
    cmds += [('type',operation), ('snap2','operation')]
    if not direct:
        cmds += [('key','RETROK_F2' if name == 'omitted' else 'RETROK_F1')]
        if name == 'shift': cmds[-1] = ('shift','RETROK_F1')
        if name in ('input','length15','length16','default','shift'): cmds += [('type','')]
        cmds += [('wait','5000'), ('recover',''), ('key','RETROK_BREAK'), ('wait','600')]
    cmds += [('type','poke &he001,163')]
    return cmds, operation


def capture(rom, name, work, official=False):
    cmds, operation = plan(name)
    args = [str(kw.FRONT), '--core', str(kw.find_core()), '--rom-dir', str(rom),
            '--screen-signature-only', '--out', str(work/'sig.tsv')]
    at = 700 if official else 100; first = at; ids=[]; key_frame=None; recovery_frame=None
    for kind, value in cmds:
        if kind == 'type':
            args += ['--type-at',str(at),'--type',value+'\n']; at += (len(value)+1)*8+240
        elif kind == 'recover':
            recovery_frame=at
            args += ['--type-at',str(at),'--type','\n']; at += 248
        elif kind in ('key','shift'):
            if value in ('RETROK_F1','RETROK_F2'): key_frame=at
            if kind == 'shift': args += ['--key-at',str(at),'--key','RETROK_LSHIFT']
            args += ['--key-at',str(at),'--key',value]; at += 300
        elif kind == 'wait': at += int(value)
        else:
            for delay in ((60,160) if kind == 'snap2' else (60,)):
                sid = value+('a' if delay == 60 else 'b'); ids.append(sid)
                args += ['--screen-signature-at',f'{sid}:{at+delay}']
            at += 260
    log=work/'ram.log'; report=work/'sig.tsv'
    args += ['--mem-write-log',str(log),'--mem-write-range','E000-E048',
             '--mem-write-from-frame','0','--frames',str(at+600)]
    try:
        env=dict(os.environ); env.pop('M6FH_LONG_TYPING',None)
        p=subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=env)
        if p.returncode: raise ValueError('実行/打鍵')
        sig=base.parse_signatures(report)
        if set(sig)!=set(ids) or sig['operationa']!=sig['operationb']: raise ValueError('画面安定')
        if 5 not in sig['beforea'] or any(i in sig['beforea'] for i in range(5)): raise ValueError('開始位置')
        expected=common.signature(6,operation)
        if sig['operationa'].get(6)!=(expected['char_count'],expected['sha256']): raise ValueError('打鍵反映')
        mem=parse_memory(log,first,key_frame,recovery_frame)
        writes=mem['writes']
        result={'screen':{'beforea':sig['beforea'],'operationa':sig['operationa']},
                'writes':writes,'boot_writes':mem['boot_writes'], 'timing':mem['timing']}
        if name=='default':
            vals=[v for a,v in writes if 0xe011<=a<=0xe030]
            result['default_asc_sha256']=hashlib.sha256(bytes(vals)).hexdigest()
            result['writes']=[(a,v) for a,v in writes if not 0xe011<=a<=0xe030]
        return result
    finally:
        log.unlink(missing_ok=True); report.unlink(missing_ok=True)


def parse_memory(path, first, key_frame=None, recovery_frame=None):
    # t7の厳格なログ検査を再利用し、t8の印領域を許可する。
    import re
    raw=path.read_text()
    if not re.search(r'^range\s+: E000-E048$',raw,re.M): raise ValueError('範囲')
    m=re.search(r'^# 取りこぼし: 0件 / 総イベント数: (\d+)件$',raw,re.M)
    if not m: raise ValueError('取りこぼし')
    writes=[]; boot=0; count=0; timed=[]
    for row in raw.splitlines():
        if re.match(r'^\s*\d+\s',row):
            x=re.fullmatch(r'\s*(\d+)\s+(\d+)\s+[0-9A-F]{4}\s+([0-9A-F]{4})\s+([0-9A-F]{2})',row)
            if not x or int(x[1])!=count+1: raise ValueError('形式')
            count+=1
            if int(x[2])<first: boot+=1
            else:
                writes.append((int(x[3],16),int(x[4],16)))
                timed.append((int(x[2]),int(x[3],16),int(x[4],16)))
    if count!=int(m[1]): raise ValueError('件数')
    prefix=[(a,0) for a in range(0xe000,0xe049)]+[(0xe000,151)]
    if writes[:len(prefix)]!=prefix: raise ValueError('初期化')
    common.reject_unexpected(writes[len(prefix):],set(range(0xe001,0xe009))|set(range(0xe010,0xe031)),len(prefix))
    if writes[-1:]!=[(0xe001,163)]: raise ValueError('完了')
    timed=timed[len(prefix):]
    switch=next((f for f,a,v in timed if a==0xe004), None)
    return {'writes':writes[len(prefix):-1], 'boot_writes':boot,
            'timing': {'ready_before_key': any(a==0xe002 and v==1 and key_frame is not None and f<key_frame for f,a,v in timed),
                       'complete_before_key': any(a==0xe003 and key_frame is not None and f<key_frame for f,a,v in timed),
                       'complete_before_recovery': any(a==0xe003 and recovery_frame is not None and f<recovery_frame for f,a,v in timed),
                       'switch_before_key': any(a==0xe004 and key_frame is not None and f<key_frame for f,a,v in timed),
                       'handler_before_switch': any(a in (0xe005,0xe006) and switch is not None and f<switch for f,a,v in timed),
                       'handler_before_key': any(a in (0xe005,0xe006) and key_frame is not None and f<key_frame for f,a,v in timed),
                       'handler_before_recovery': any(a in (0xe005,0xe006) and recovery_frame is not None and f<recovery_frame for f,a,v in timed)}}


def measure(rom, work, official=False):
    records={n:{'runs':[None,None], 'gate':False} for n in NAMES}
    def run(n,i):
        d=work/n/str(i); d.mkdir(parents=True,exist_ok=True)
        return capture(rom,n,d,official)
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        tasks={pool.submit(run,n,i):(n,i) for n in NAMES for i in range(2)}
        for task in concurrent.futures.as_completed(tasks):
            n,i=tasks[task]
            try: records[n]['runs'][i]=task.result()
            except (ValueError,OSError) as exc: print(f'{n} {i+1}走: 関門失敗 ({exc})',flush=True)
    for n in NAMES:
        records[n]['gate']=base.stable_pair(records[n]['runs'])
        print(f"{n}: {'通過' if records[n]['gate'] else '失敗'}",flush=True)
    if all(records['ref-'+x]['gate'] for x in REFS):
        refs={x:base.response(records['ref-'+x]['runs'][0]['screen']['operationa']) for x in REFS}
        prompts={}
        for x in REFS:
            rows=records['ref-'+x]['runs'][0]['screen']['operationa']
            lines=sorted((int(k),v) for k,v in rows.items() if 7<=int(k)<19)
            if not lines: raise ValueError('参照プロンプト')
            row,value=lines[-1]
            if row in prompts and prompts[row]!=value: raise ValueError('参照プロンプト不一致')
            prompts[row]=value
        for n in NAMES:
            if records[n]['gate']:
                try: records[n]['response']=base.identify(base.response(records[n]['runs'][0]['screen']['operationa'],prompts),refs)
                except ValueError: records[n]['response']='入力中またはプロンプト欠測'
    return {'version':1,'records':records}


def valid(data):
    return (data.get('version')==1 and set(data.get('records',{}))==set(NAMES)
            and all(r['gate'] and base.stable_pair(r['runs']) and 'response' in r for r in data['records'].values()))


def check(a,b):
    if not valid(a) or not valid(b): return False
    a=copy.deepcopy(a); b=copy.deepcopy(b)
    for data in (a,b):
        for run in data['records']['default']['runs']:
            run.pop('default_asc_sha256',None)
    return a==b

def save(path,data): path.write_text(json.dumps(data,ensure_ascii=False,sort_keys=True,indent=2)+'\n')


def selftest():
    work=WORK/'selftest'; work.mkdir(parents=True,exist_ok=True); rom=work/'rom'
    p=subprocess.run([sys.executable,'-B',str(ROOT/'src/build_main_rom.py'),str(rom),'--work-dir',str(work/'asm')],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    if p.returncode: raise ValueError('自作ROMビルド')
    data=measure(rom,work); save(work/'actual.json',data)
    if not valid(data): return 1
    data=json.loads((work/'actual.json').read_text()); save(work/'expected.json',data)
    assert check(data,data)
    bad=copy.deepcopy(data)
    for run in bad['records'][NAMES[0]]['runs']: run['screen']['operationa']['6'][0]^=1
    assert valid(bad) and not check(data,bad)
    a,b=[(7,[1,'a'])],[(7,[1,'b'])]
    assert base.identify(a,{'ERR8':a,'ERR2':b})=='ERR8'
    assert base.identify(a,{'ERR8':b,'ERR2':b})=='候補外'
    bad=copy.deepcopy(data); bad['records'][NAMES[0]]['runs'][1]['screen']['operationa']['6'][0]^=1
    assert not valid(bad)
    common.unexpected_selftest(lambda p:parse_memory(p,10),work/'synthetic.log',[(0xe001,163)])
    sweep_path=work/'sweep.log'
    prefix=[(a,0) for a in range(0xe000,0xe049)]+[(0xe000,151),(0xe001,163)]
    for sweep in ([(a,0) for a in range(0xe000,0xe049)],
                  [(a,(a*7)&255) for a in reversed(range(0xe000,0xe049))]):
        rows=[(9,a,v) for a,v in sweep]+[(10,a,v) for a,v in prefix]
        sweep_path.write_text('range : E000-E048\n# 取りこぼし: 0件 / 総イベント数: %d件\n' % len(rows)+
                              ''.join('%d %d 0000 %04X %02X\n' % (i,f,a,v) for i,(f,a,v) in enumerate(rows,1)))
        result=parse_memory(sweep_path,10)
        assert result['boot_writes']==len(sweep) and not result['writes']
    sweep_path.unlink()
    print('起動時掃引2種: 除外を確認')
    print('陰性対照: 期待値・参照ずらし・2走不一致・器具外書込みを拒否、起動時掃引を除外し打鍵後掃引を拒否')
    print(f'全腕関門: {len(NAMES)}/{len(NAMES)}')
    return 0


def main():
    ap=argparse.ArgumentParser(); sub=ap.add_subparsers(dest='command',required=True)
    sub.add_parser('selftest')
    m=sub.add_parser('measure'); m.add_argument('--rom-dir',type=Path,required=True); m.add_argument('--work-dir',type=Path,required=True); m.add_argument('--out',type=Path,required=True); m.add_argument('--official',action='store_true')
    e=sub.add_parser('expected'); e.add_argument('--measured',type=Path,required=True); e.add_argument('--out',type=Path,required=True)
    c=sub.add_parser('check'); c.add_argument('--measured',type=Path,required=True); c.add_argument('--expected',type=Path,required=True)
    args=ap.parse_args()
    if args.command=='selftest': return selftest()
    if args.command=='measure':
        data=measure(args.rom_dir,args.work_dir,args.official); save(args.out,data); return int(not valid(data))
    data=json.loads(args.measured.read_text())
    if args.command=='expected':
        if not valid(data): return 1
        save(args.out,data); return 0
    ok=check(data,json.loads(args.expected.read_text())); print('照合: '+('一致' if ok else '不一致')); return int(not ok)


if __name__=='__main__':
    try: raise SystemExit(main())
    except (ValueError,OSError,KeyError) as exc:
        print('NG 器具:',type(exc).__name__,'（本文非出力）'); raise SystemExit(1)
