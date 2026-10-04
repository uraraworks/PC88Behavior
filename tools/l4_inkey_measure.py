#!/usr/bin/env python3
"""l4-s9c: INKEY$の整数採取。画面本文・測定器診断は出力しない。"""
import argparse
import csv
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
from unittest.mock import patch
import l4_listkw_measure as kw
import l4_strfunc_measure as sf

WORK = kw.REPO.parent / 'tmp/l4s9c-work'
CANDIDATES = ('K_BUF', 'K_LAST', 'K_NONE')
ENCODER = ['900 l=len(a$):print "ik";n;l;',
           '905 if l=0 then goto 920',
           '910 for k=1 to l:print asc(mid$(a$,k,1));:next',
           '920 print:return']


def controls():
    return [dict(id='control-ab', kind='constant', expr='"ab"', value=[97,98]),
            dict(id='control-empty', kind='constant', expr='""', value=[]),
            dict(id='control-mid', kind='constant', expr='mid$("hello",2,3)', value=[101,108,108])]


def arms():
    result = [dict(id='idle-once',kind='once'), dict(id='idle-100',kind='idle'),
              dict(id='run-return',kind='buffer',text='',offset=0)]
    for name, text in [('a','a'),('z','z'),('0','0'),('9','9'),('space',' '),
                       ('bang','!'),('question','?'),('plus','+'),('bracket','['),('return','\n')]:
        result.append(dict(id='key-'+name,kind='key',text=text,offset=600))
    for text in ['ab','abcde','aab']:
        result.append(dict(id='buffer-'+text,kind='buffer',text=text,offset=100))
    result += [dict(id='early-ab',kind='buffer',text='ab',offset=24),
               dict(id='echo-idle',kind='echo',text='',offset=600),
               dict(id='echo-a',kind='echo',text='a',offset=600),
               dict(id='hold-a',kind='echo',text='a',offset=600,hold=160)]
    return result


def addendum_arms():
    return [dict(id=name,kind='buffer',text=text,offset=100,
                 wait=30000,reads=30,packed=True)
            for name,text in [('buffer-abcde-long','abcde'),
                              ('buffer-10','abcdefghij'),
                              ('buffer-20','abcdefghijklmnopqrst')]]


def selected_arms(addendum=None):
    # 定数3腕は追補でも全体関門に必要。既存のINKEY$腕は再測定しない。
    return controls()+(addendum_arms() if addendum==1 else arms())


def program(arm):
    kind=arm['kind']
    lines=['new',*ENCODER]
    if arm.get('packed'):
        lines[-1:] = ['920 if n=1 or n mod 2=1 then print:return',
                      '925 print ":";:return']
    if kind=='constant':
        lines += ['10 n=1:a$='+arm['expr'], '20 gosub 900']
    elif kind=='timing':
        lines += ['10 input a$', '20 n=1:gosub 900']
    elif kind=='once':
        lines += ['10 n=1:a$=inkey$:gosub 900']
    elif kind=='idle':
        lines += ['10 c=0:m=0', '20 for n=1 to 100:a$=inkey$',
                  '30 if len(a$)>0 then c=c+1', '40 if len(a$)>m then m=len(a$)',
                  '50 next', '60 print "iks";100;c;m']
    elif kind=='key':
        # RUNのRETURN混入を隠さず、最初の1回を別印に残す。
        lines += ['10 n=1:a$=inkey$:gosub 900',
                  '20 a$=inkey$:if a$="" then 20', '30 n=2:gosub 900']
    elif kind=='buffer':
        lines += ['10 n=1:a$=inkey$:gosub 900',
                  f"20 for j=1 to {arm.get('wait',3000)}:next",
                  f"30 for n=2 to {arm.get('reads',8)+1}:a$=inkey$:gosub 900:next"]
    elif kind=='echo':
        # 画面出力は全ポーリング終了後。10000回の窓で非空回数と最大長を採る。
        lines += ['10 n=1:a$=inkey$:gosub 900', '20 c=0:m=0:x$=""',
                  '30 for j=1 to 10000:a$=inkey$',
                  '40 if len(a$)=0 then goto 80', '50 c=c+1',
                  '60 if len(a$)>m then m=len(a$)',
                  '70 if len(x$)<8 then x$=x$+a$', '80 next',
                  '90 print "iks";10000;c;m', '100 n=2:a$=x$:gosub 900']
    else:
        raise ValueError('未知の腕')
    lines += ['800 print "ikd";1', '810 end', 'cls', 'run']
    assert all(len(s)<80 and s==s.lower() for s in lines)
    return lines


def schedule(arm, official=False):
    """RUN改行の押下フレームを原点とし、押下4・解放8を固定する。"""
    events=[];at=700 if official else 100
    if official:
        events.append(dict(at=300,text='\n',hold=4,gap=8))
    for line in program(arm):
        events.append(dict(at=at,text=line+'\n',hold=4,gap=8))
        if line=='run':
            run_return=at+len(line)*12
        at+=(len(line)+1)*12+240
    if arm.get('text'):
        events.append(dict(at=arm.get('event_at',run_return+arm['offset']),text=arm['text'],
                           hold=arm.get('hold',4),gap=8))
    capture=run_return+18000
    return events,capture,run_return


MARK=re.compile(r'^(ikd|iks|ik)((?: +\d+| *-\d+)+) *$',re.I)
TOKEN=re.compile(r' +\d+| *-\d+')


def extract(data):
    if len(data)!=3000:
        raise ValueError('画面写し長さ不正')
    rows=[];other=0
    for i in range(25):
        raw=data[i*120:i*120+80]
        if raw==b' '*80:
            continue
        parts=raw.decode('ascii',errors='replace').rstrip(' ').split(':')
        matches=[MARK.fullmatch(part) for part in parts]
        if all(matches) and (len(parts)==1 or
                             len(parts)==2 and all(m[1].lower()=='ik' for m in matches)):
            rows.extend([m[1].lower(),*(int(t) for t in TOKEN.findall(m[2]))] for m in matches)
        else:
            other+=1
    return rows,other


def valid(arm,rows):
    if not rows or rows[-1]!=['ikd',1]:
        return False
    kind=arm['kind']
    indices={'constant':[1],'once':[1],'idle':[],'key':[1,2],
             'buffer':list(range(1,arm.get('reads',8)+2)),'echo':[1,2]}[kind]
    reads=[r for r in rows[:-1] if r[0]=='ik']
    stats=[r for r in rows[:-1] if r[0]=='iks']
    if [r[1] for r in reads if len(r)>=3]!=indices:
        return False
    if any(len(r)<3 or not 0<=r[2]<=8 or len(r)!=3+r[2]
           or any(not 0<=v<=255 for v in r[3:]) for r in reads):
        return False
    if kind in ('idle','echo'):
        samples=100 if kind=='idle' else 10000
        if len(stats)!=1 or len(stats[0])!=4 or stats[0][1]!=samples:
            return False
        _,_,count,maximum=stats[0]
        if not 0<=count<=samples or not 0<=maximum<=255 or (count==0)!=(maximum==0):
            return False
    elif stats:
        return False
    return len(rows)==len(reads)+len(stats)+1 and rows==(
        reads[:1]+stats+reads[1:]+[['ikd',1]] if kind=='echo' else reads+stats+[['ikd',1]])


def prediction(arm,candidate):
    kind=arm['kind']
    end=[['ikd',1]]
    if kind=='constant':
        return [['ik',1,len(arm['value']),*arm['value']]]+end
    if kind=='once':
        return [['ik',1,0]]+end
    if kind=='idle':
        return [['iks',100,0,0]]+end
    if kind=='key' and arm['text']!='\n':
        return [['ik',1,0],['ik',2,1,ord(arm['text'])]]+end
    if kind=='buffer':
        text=arm['text'] if candidate=='K_BUF' else arm['text'][-1:] if candidate=='K_LAST' else ''
        values=[[ord(ch)] for ch in text]+[[]]*(arm.get('reads',8)-len(text))
        return [['ik',1,0]]+[['ik',i+2,len(v),*v] for i,v in enumerate(values)]+end
    # RETURNのコード、ポーリング窓の回数・リピート数は予測しない。
    return None


def buffer_probe_frames(arm,official=False):
    if arm['kind']!='buffer' or not arm.get('text') or arm['offset']<100:
        return []
    _,_,origin=schedule(arm,official)
    start=origin+arm['offset']
    return [start-1,start+len(arm['text'])*12+16]


def buffer_waiting(rows):
    return len(rows)==1 and len(rows[0])>=3 and rows[0][:2]==['ik',1]


def run_arm(rom,official,arm,work):
    events,capture,_=schedule(arm,official)
    args=[str(kw.FRONT),'--core',str(kw.find_core()),'--rom-dir',str(rom)]
    for e in events:
        args+=['--key-hold',str(e['hold']),'--key-gap',str(e['gap']),
               '--type-at',str(e['at']),'--type',e['text']]
    screen=work/'screen.bin'
    probes=[work/f'probe-{i}.bin' for i,_ in enumerate(buffer_probe_frames(arm,official))]
    for path,frame in zip(probes,buffer_probe_frames(arm,official)):
        args+=['--vram-dump',str(path),'--vram-dump-at',str(frame)]
    args+=['--vram-dump',str(screen),'--vram-dump-at',str(capture),'--frames',str(capture+100)]
    try:
        p=subprocess.run(args,capture_output=True,env=dict(os.environ,M6FH_LONG_TYPING='1'))
        if p.returncode or b'untypable' in p.stderr.lower() or '打てない'.encode() in p.stderr:
            raise RuntimeError('打鍵・採取失敗')
        # 写しを複数指定するとフロントエンドは名前に .f<6桁フレーム> を付け足す
        # (1つだけなら元の名前のまま)。器具が元の名前で読み、先行入力の腕が
        # 全部「採取失敗」になっていた(l4-s9c 1回目)。
        frames=buffer_probe_frames(arm,official)
        if probes:
            probes=[dumped(path,frame) for path,frame in zip(probes,frames)]
            screen=dumped(screen,capture)
        if any(not buffer_waiting(extract(path.read_bytes())[0]) for path in probes):
            raise RuntimeError('先行入力がFOR待ち中である関門の失敗')
        return extract(screen.read_bytes())
    finally:
        for path in [screen,*probes]:
            path.unlink(missing_ok=True)
        for path in work.glob('*.f[0-9]*.bin*'):
            path.unlink(missing_ok=True)


def dumped(path,frame):
    return path.with_name(f'{path.stem}.f{frame:06d}{path.suffix}')


def measure(rom,official,selected,work):
    work.mkdir(parents=True,exist_ok=True)
    records=[]
    with tempfile.TemporaryDirectory(prefix='measure-',dir=work) as tmp:
        for arm in selected:
            obs=[];others=[];failed=[]
            for _ in range(2):
                try:
                    rows,count=run_arm(rom,official,arm,Path(tmp))
                    obs.append(rows);others.append(count);failed.append(False)
                except Exception:
                    obs.append([]);others.append(0);failed.append(True)
            records.append(dict(arm=arm,obs=obs,others=others,failed=failed,
                                gate=not any(failed) and obs[0]==obs[1] and others[0]==others[1]
                                and valid(arm,obs[0])))
    return records


def emit(path,records):
    indexed={r['arm']['id']:r for r in records}
    calibration=all(a['id'] in indexed and indexed[a['id']]['gate']
                    and indexed[a['id']]['obs'][0]==prediction(a,'K_BUF') for a in controls())
    baseline=indexed.get('echo-idle')
    rows=[]
    for r in records:
        arm=r['arm'];passed=calibration and r['gate']
        predictions=[prediction(arm,c) for c in CANDIDATES]
        for i in range(2):
            rows.append([arm['id'],i+1,json.dumps(program(arm)),json.dumps(schedule(arm)[0]),json.dumps(schedule(arm,True)[0]),
                         json.dumps(r['obs'][i]),r['others'][i],
                         'pass' if passed else 'gate_failed',int(r['failed'][i]),
                         json.dumps(buffer_probe_frames(arm)),json.dumps(buffer_probe_frames(arm,True)),
                         int(arm['kind'] not in ('constant','idle','once') and bool(r['obs'][i])
                             and r['obs'][i][0][:3]!=['ik',1,0]),
                         *['gate_failed' if not passed else 'unpredicted' if p is None else
                           'agree' if p==r['obs'][i] else 'differ' for p in predictions],
                         '' if not passed or not baseline or not baseline['gate'] or arm['kind']!='echo'
                         else int(r['others'][i]>baseline['others'][i])])
    sf.write(path,['arm','repeat','typed_lines','events_self','events_official', 'print_values',
                   'other_line_counts','gate','typing_or_capture_failed','buffer_probe_frames_self',
                   'buffer_probe_frames_official','preparation_contaminated',*CANDIDATES,
                   'other_rows_increased_vs_idle'],rows)
    return calibration and all(r['gate'] for r in records)


def check(expected,measured,candidate='K_BUF'):
    try:
        with expected.open() as f:
            wanted=list(csv.DictReader(f,delimiter='\t'))
        with measured.open() as f:
            actual=list(csv.DictReader(f,delimiter='\t'))
        selected={a['id']:a for a in controls()+arms()+addendum_arms()}
        targets={}
        for r in wanted:
            if r.get('candidate',candidate)!=candidate:
                continue
            if r['arm'] in targets:
                return False
            targets[r['arm']]=json.loads(r.get('prediction') or r['print_values'])
        grouped={}
        for r in actual:
            grouped.setdefault(r['arm'],[]).append(r)
        if not targets or set(targets)!=set(grouped):
            return False
        for aid,value in targets.items():
            runs=grouped[aid]
            # 予測なしは照合の合格にしない。
            if value is None or aid not in selected or len(runs)!=2 or {r['repeat'] for r in runs}!={'1','2'}:
                return False
            if any(r['gate']!='pass' or r['typing_or_capture_failed']!='0'
                   or not valid(selected[aid],json.loads(r['print_values']))
                   or json.loads(r['print_values'])!=value for r in runs):
                return False
        return True
    except (ValueError,KeyError,TypeError,OSError):
        return False


def synthetic_screen(arm,rows):
    if not arm.get('packed'):
        return sf.screen_of(rows)
    def encoded(row):
        return row[0]+''.join(' '+str(x)+' ' for x in row[1:])
    lines=[encoded(rows[0])]
    for i in range(1,len(rows)-1,2):
        lines.append(':'.join(encoded(r) for r in rows[i:min(i+2,len(rows)-1)]))
    lines.append(encoded(rows[-1]))
    assert len(lines)<=25 and all(len(line)<80 for line in lines)
    data=bytearray(b' '*3000)
    for i,line in enumerate(lines):
        data[i*120:i*120+len(line)]=line.encode('ascii')
    return bytes(data)


def selftest(work):
    work.mkdir(parents=True,exist_ok=True)
    selected=controls()+arms()+addendum_arms()
    assert len({a['id'] for a in selected})==len(selected)
    for a in selected:
        program(a);events,cap,origin=schedule(a)
        assert all(e['gap']>=8 for e in events)
        if a.get('text'):
            assert events[-1]['at']==origin+a['offset']
        for c in CANDIDATES:
            value=prediction(a,c)
            if value is not None:
                assert valid(a,value) and extract(synthetic_screen(a,value))==(value,0)
    good=prediction(controls()[0],'K_BUF')
    assert not valid(controls()[0],extract(sf.screen_of(good).replace(b'ik ',b'zz ',1))[0])
    assert not valid(controls()[0],[['ik',1,3,97,98],['ikd',1]])
    assert buffer_waiting([['ik',1,0]])
    assert not buffer_waiting([['ik',1,0],['ik',2,0]])
    assert not buffer_waiting([])
    wrong=[['ik',1,2,97,99],['ikd',1]]
    assert valid(controls()[0],wrong) and wrong!=good
    try:
        extract(b' ')
        raise AssertionError('短い画面を拒否しない')
    except ValueError:
        pass
    with tempfile.TemporaryDirectory(prefix='selftest-',dir=work) as tmp:
        root=Path(tmp)
        def replay(rom,official,a,directory):
            p=prediction(a,'K_BUF')
            if p is None:
                p=([['ik',1,0],['ik',2,1,13],['ikd',1]] if a['kind']=='key' else
                   [['ik',1,0],['iks',10000,0,0],['ik',2,0],['ikd',1]])
            return p,2
        with patch(__name__+'.run_arm',replay):
            records=measure('',False,selected,root)
        assert emit(root/'good.tsv',records)
        sf.write(root/'expected.tsv',['arm','prediction'],[(a['id'],json.dumps(prediction(a,'K_BUF'))) for a in selected])
        assert not check(root/'expected.tsv',root/'good.tsv')  # 予測なしは合格しない
        calls=0
        def changed(rom,official,a,directory):
            nonlocal calls
            calls+=1
            return (wrong if calls==2 else prediction(a,'K_BUF')),2
        with patch(__name__+'.run_arm',changed):
            mismatch=measure('',False,controls()[:1],root)
        assert not mismatch[0]['gate']
        records[0]['obs']=[wrong,wrong]
        assert not emit(root/'bad.tsv',records)
        with (root/'bad.tsv').open() as f:
            assert all(r['gate']=='gate_failed' for r in csv.DictReader(f,delimiter='\t'))
        with patch(__name__+'.run_arm',side_effect=RuntimeError('合成失敗')):
            broken=measure('',False,controls(),root)
        assert not emit(root/'failed.tsv',broken)
        # 追補だけ＋必須定数の選択と、既知候補列への完全一致／1標本改変の拒否。
        extra=selected_arms(1)
        assert [a['id'] for a in extra]==[a['id'] for a in controls()+addendum_arms()]
        with patch(__name__+'.run_arm',replay):
            extra_records=measure('',False,extra,root)
        assert emit(root/'addendum.tsv',extra_records)
        sf.write(root/'addendum-expected.tsv',['arm','prediction'],
                 [(a['id'],json.dumps(prediction(a,'K_BUF'))) for a in extra])
        assert check(root/'addendum-expected.tsv',root/'addendum.tsv')
        extra_records[-1]['obs'][1][1][3]=ord('z')
        assert emit(root/'addendum-changed.tsv',extra_records)
        assert not check(root/'addendum-expected.tsv',root/'addendum-changed.tsv')
        # 合成写しを実際の run_arm 経路に渡し、最終打鍵後の待ち関門も検査。
        for a in addendum_arms():
            frames=buffer_probe_frames(a)
            _,cap,origin=schedule(a)
            assert frames==[origin+99,origin+100+len(a['text'])*12+16]
            assert len(frames)+1<=16 and frames[-1]<origin+1000<cap
            def capture(args,**kwargs):
                for i,arg in enumerate(args):
                    if arg=='--vram-dump':
                        path=Path(args[i+1]);frame=int(args[i+3])
                        rows=prediction(a,'K_BUF') if frame==cap else [['ik',1,0]]
                        dumped(path,frame).write_bytes(
                            synthetic_screen(a,rows) if frame==cap else sf.screen_of(rows))
                return subprocess.CompletedProcess(args,0,b'',b'')
            with patch.object(subprocess,'run',capture):
                observed,count=run_arm('',False,a,root)
            assert count==0 and observed==prediction(a,'K_BUF') and valid(a,observed)
            for damage in ('late','marker','missing','length'):
                def damaged_capture(args,**kwargs):
                    result=capture(args,**kwargs)
                    for i,arg in enumerate(args):
                        if arg!='--vram-dump':
                            continue
                        frame=int(args[i+3]);path=dumped(Path(args[i+1]),frame)
                        if damage=='late' and frame==frames[-1]:
                            path.write_bytes(sf.screen_of([['ik',1,0],['ik',2,0]]))
                        elif frame==cap and damage!='late':
                            data=path.read_bytes()
                            if damage=='marker':
                                data=data.replace(b'ik ',b'zz ',1)
                            elif damage=='missing':
                                data=data.replace(b'ikd',b'zzz',1)
                            else:
                                data=data.replace(b'ik 2  1 ',b'ik 2  2 ',1)
                            path.write_bytes(data)
                    return result
                with patch.object(subprocess,'run',damaged_capture):
                    damaged=measure('',False,[a],root)
                assert not damaged[0]['gate'],damage
            assert not list(root.glob('*.f[0-9]*.bin*'))
        # 時刻対照: 待ち窓が600～800の合成INPUT受信器。
        # 同じ生成済みイベントを渡し、--type-atを無視する故障も拒否する。
        a=dict(id='timing',kind='constant',expr='""',value=[],text='a',offset=24)
        b=dict(a,offset=600)
        def receiver(events,origin,ignore_time=False):
            return sum(600<=((0 if ignore_time else e['at'])-origin)<800
                       for e in events if e['text']=='a')
        ea,_,ra=schedule(a);eb,_,rb=schedule(b)
        assert receiver(ea,ra)==0 and receiver(eb,rb)==1
        assert receiver(eb,rb,True)==0
        rom=root/'rom'
        p=subprocess.run([os.sys.executable,str(kw.REPO/'src/build_main_rom.py'),str(rom),
                          '--work-dir',str(root/'asm')],capture_output=True)
        assert p.returncode==0,'自作ROM一時ビルド失敗'
        # 実フロントエンド: 写しを2枚指定したときの名前の付け方を dumped() が
        # 当てること(合成の再生では run_arm を差し替えるので通らない経路)。
        pair=[root/'pair-a.bin',root/'pair-b.bin']
        q=subprocess.run([str(kw.FRONT),'--core',str(kw.find_core()),'--rom-dir',str(rom),
                          '--vram-dump',str(pair[0]),'--vram-dump-at','200',
                          '--vram-dump',str(pair[1]),'--vram-dump-at','300','--frames','350'],
                         capture_output=True)
        assert q.returncode==0,'2枚の写しの採取失敗'
        assert all(dumped(x,f).exists() for x,f in zip(pair,(200,300))),'写しの名前の付け方が dumped() と違う'
        for x in root.glob('pair-*'):
            x.unlink()
        # 実フロントエンド: 起動直後(入力待ち前)とINPUT待ち後で同じ文字列を打つ。
        timing=dict(id='timing-input',kind='timing',text='a\n',offset=600)
        late,_=run_arm(rom,False,timing,root)
        early,_=run_arm(rom,False,dict(timing,event_at=0),root)
        assert late==[['ik',1,1,97],['ikd',1]],'INPUT待ち後の時刻対照不一致'
        assert early!=late and ['ikd',1] not in early,'打鍵開始時刻が効かない'
        records=measure(rom,False,controls(),root)
        assert all(r['gate'] and r['obs'][0]==prediction(r['arm'],'K_BUF') for r in records), '自作ROM定数対照失敗'
        assert emit(root/'measured.tsv',records)
        sf.write(root/'expected.tsv',['arm','prediction'],[(a['id'],json.dumps(prediction(a,'K_BUF'))) for a in controls()])
        assert check(root/'expected.tsv',root/'measured.tsv')
        sf.write(root/'wrong.tsv',['arm','prediction'],[(a['id'],json.dumps(wrong if i==0 else prediction(a,'K_BUF'))) for i,a in enumerate(controls())])
        assert not check(root/'wrong.tsv',root/'measured.tsv')
    print('OK 採取陽性・陰性、追補3腕の待ち関門・詰め印行・完全一致、全腕2走合成、関門伝播、合成・実フロントエンド打鍵時刻対照、自作ROM定数3腕×2走、check陰性')
    return 0


def main():
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='command',required=True)
    pred=sub.add_parser('predict');pred.add_argument('--out',type=Path,required=True)
    m=sub.add_parser('measure');m.add_argument('--rom-dir',required=True);m.add_argument('--official',action='store_true');m.add_argument('--out',type=Path,required=True);m.add_argument('--work-dir',type=Path,default=WORK)
    c=sub.add_parser('check');c.add_argument('--expected',type=Path,required=True);c.add_argument('--measured',type=Path,required=True);c.add_argument('--candidate',choices=CANDIDATES,default='K_BUF')
    s=sub.add_parser('selftest');s.add_argument('--work-dir',type=Path,default=WORK)
    for parser in (pred,m):
        parser.add_argument('--addendum',type=int,choices=[1])
    args=p.parse_args()
    if args.command=='selftest':
        return selftest(args.work_dir)
    if args.command=='check':
        ok=check(args.expected,args.measured,args.candidate);print('照合一致' if ok else '照合不一致');return 0 if ok else 1
    selected=selected_arms(args.addendum)
    if args.command=='predict':
        sf.write(args.out,['arm','candidate','prediction','typed_lines','events_self','events_official'],
                 [(a['id'],c,json.dumps(prediction(a,c)),json.dumps(program(a)),
                   json.dumps(schedule(a)[0]),json.dumps(schedule(a,True)[0])) for a in selected for c in CANDIDATES]);return 0
    records=measure(args.rom_dir,args.official,selected,args.work_dir)
    ok=emit(args.out,records);print(f'記録完了: {len(records)}腕×2走、関門'+('通過' if ok else '失敗'));return 0 if ok else 1

if __name__=='__main__':
    raise SystemExit(main())
