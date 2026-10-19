#!/usr/bin/env python3
"""l4-t4 BSAVE/BLOAD。自作媒体の当該ファイルだけを候補照合する。"""
import sys
sys.dont_write_bytecode=True
import hashlib, struct, os, shutil, csv
from pathlib import Path
import l4_mlcall_measure as m
import build_blank_data_disk as blank
NAME=b't4own'
PATTERN=bytes(range(64))
ml_arms=m.first_arms

def first_arms():
    aa=ml_arms()[:2]
    def add(i,cmds,prediction='ERR番号、正常時は既知型との一致',post=None,pattern=PATTERN):
        aa.append(dict(id=i,commands=cmds,prediction=prediction,
            setup=[f'for j=0 to {len(pattern)-1}:poke {m.DATA}+j,j:next j'] if pattern==PATTERN else m.put(m.DATA,pattern),
            post=post or [],code=list(m.ENTRY+m.MARK+b'\xc9'),pattern=list(pattern)))
    save='bsave "1:t4own",&hc100,64'
    for tag,load,addr in [('default','bload "1:t4own"',m.DATA),('relocate','bload "1:t4own",&hc200',m.RELOC)]:
        add('bload-'+tag,[save,f'for j=0 to 63:poke {m.DATA}+j,0:next j',load],post=[f'z=1:for j=0 to 63:z=z and (peek({addr}+j)=j):next j',m.result(73,'z<>0')])
    code=bytes.fromhex('3e d5 32 1e c3 c9')
    add('bload-run',[f'bsave "1:t4own",{m.DATA},{len(code)}',f'for j=0 to {len(code)-1}:poke {m.DATA}+j,0:next j','bload "1:t4own",r'],'保存した自作コードが実行印213を付けRET',pattern=code)
    for tag,cmd in [('missing','bload "1:absent"'),('zero','bsave "1:t4own",&hc100,0'),('overflow','bsave "1:t4own",65530,10'),('save-missing','bsave "1:t4own",&hc100'),('load-missing','bload'),('drive','bload "9:t4own"'),('extra','bload "1:t4own",&hc200,1'),('address-string','bsave "1:t4own","a",64')]: add(tag,[cmd])
    return aa

def addendum_arms():
    aa=first_arms()
    for a in aa[2:]:
        a['id']='a1-'+a['id']
        a['commands']=[c.replace('1:t4own','2:t4own').replace('1:absent','2:absent') for c in a['commands']]
    cal=dict(id='a1-cal-disk',commands=['bsave "2:t4cal",&hc100,1'],
             prediction='公式ではERR0かつドライブ2にt4cal必須。自作は未実装既知',
             setup=['poke &hc100,0'],post=[],code=list(m.ENTRY+m.MARK+b'\xc9'),pattern=[0])
    return aa[:2]+[cal]+aa[2:]

def arms(): return first_arms() if m.ROUND=='first' else addendum_arms()

# D88の外形は必要なセクタ位置を見つけるためだけに走査。本文は要求先だけ取得。
def sector(image,c,h,r):
    pos=struct.unpack_from('<I',image,32+(c*2+h)*4)[0]
    if not pos: raise ValueError('媒体トラック')
    count=struct.unpack_from('<H',image,pos+4)[0]
    for _ in range(count):
        size=struct.unpack_from('<H',image,pos+14)[0]
        if tuple(image[pos:pos+3])==(c,h,r): return image[pos+16:pos+16+size]
        pos+=16+size
    raise ValueError('媒体セクタ')

def classify(data,candidates):
    matches=[dict(encoding=n,offset=i) for n,b in candidates.items() for i in range(len(data)-len(b)+1) if data[i:i+len(b)]==b]
    return dict(matches=matches,length=len(data),sha256=hashlib.sha256(data).hexdigest())

def inspect(image,a,drive='synthetic'):
    entry=None
    for r in range(1,13):
        directory=sector(image,18,1,r)
        for j in range(0,256,16):
            if directory[j]==255: break
            if directory[j:j+9]==(b't4cal' if a['id']=='a1-cal-disk' else NAME).ljust(9,b' '): entry=directory[j:j+11]; break
        if entry is not None or 255 in directory[::16]: break
    if entry is None: return dict(found=False)
    # FATは単位0..159だけ、当該鎖をたどる。単位外を読まない。
    fat=sector(image,18,1,14)[:160]; unit=entry[10]; seen=set(); data=bytearray()
    while True:
        if unit>=160 or unit in seen or unit in (74,75): raise ValueError('媒体鎖')
        seen.add(unit); t=fat[unit]
        n=8 if t<160 else t-0xc0
        if not 0<=n<=8: raise ValueError('媒体終端')
        for k in range(n):
            linear=unit*8+k; track,rr=divmod(linear,16); c,h=divmod(track,2)
            data+=sector(image,c,h,rr+1)
        if t>=160: break
        unit=t
    pattern=bytes(a.get('pattern',PATTERN)); start=m.DATA; end=start+len(pattern)-1
    # ヘッダ候補は本体先頭16バイトのみ。開始/終了 inclusive/exclusiveを区別。
    hdr=classify(bytes(data[:16]),{'start-le':struct.pack('<H',start),'end-inclusive-le':struct.pack('<H',end),'end-exclusive-le':struct.pack('<H',end+1)})
    return dict(found=True,drive=drive,name_match=True,type01=entry[9]==1,header=hdr,payload=classify(bytes(data),{'own-pattern':pattern}))

def reference_disk():
    root=os.environ.get('PC88_REF_DISK_DIR')
    if not root: raise ValueError('関門失敗: PC88_REF_DISK_DIR_missing')
    config=Path(os.environ.get('M6FF_FROZEN_CONFIG',m.REPO/'tools/m6ff_frozen.tsv'))
    with config.open() as f:
        rows=list(csv.reader(f,delimiter='\t'))
    names=[r[1] for r in rows if len(r)>=2 and r[0]=='reference_disk']
    if len(names)!=1 or Path(names[0]).name!=names[0]: raise ValueError('参照媒体設定')
    source=Path(root)/names[0]
    if not source.is_file(): raise ValueError('関門失敗: reference_disk_missing')
    return source

def media_prepare(work,a):
    source=reference_disk() # 両ROMとも同じ構成。像を解析・ハッシュ・表示しない。
    def cleanup():
        for name in ('a.d88','b.d88'): (work/name).unlink(missing_ok=True)
    try:
        shutil.copyfile(source,work/'a.d88')
        (work/'a.d88').chmod(0o600)
        (work/'b.d88').write_bytes(blank.build())
    except BaseException:
        cleanup(); raise
    return ['--disk',str(work/'a.d88'),'--disk2',str(work/'b.d88'),'--save-to-disk-image'],cleanup

def media_observe(work,a):
    if a['id'].startswith('cal-'): return None
    try: return inspect((work/'b.d88').read_bytes(),a,'disk2')
    except (OSError,ValueError,IndexError,struct.error): return dict(unknown=True)

base_safety=m.safety_selftest
base_synth=m.synth
def synth(a):
    o=base_synth(a)
    if not a["id"].startswith("cal-"): o["media"]={"found":False}
    return o
base_valid=m.valid

def media_valid(o,a):
    if type(o) is not dict or set(o) not in ({'values','writes'},{'values','writes','media'}): return False
    if not base_valid({k:v for k,v in o.items() if k!='media'},a): return False
    if 'media' not in o: return a['id'].startswith('cal-')
    d=o['media']
    if d in ({'found':False},{'unknown':True}): return True
    if type(d) is not dict or set(d)!={'found','drive','name_match','type01','header','payload'}: return False
    if d['drive'] not in ('disk1','disk2','synthetic'): return False
    for key in ('header','payload'):
        q=d[key]
        if type(q) is not dict or set(q)!={'matches','length','sha256'}: return False
        if type(q['length']) is not int or q['length']<0 or not m.re.fullmatch('[0-9a-f]{64}',q['sha256']): return False
        if any(set(x)!={'encoding','offset'} or x['encoding'] not in ('start-le','end-inclusive-le','end-exclusive-le','own-pattern') or type(x['offset']) is not int or not 0<=x['offset']<q['length'] for x in q['matches']): return False
    return all(type(d[k]) is bool for k in ('found','name_match','type01'))

def media_safety_selftest(work):
    work.mkdir(parents=True,exist_ok=True)
    with m.tempfile.TemporaryDirectory(dir=work,prefix='synthetic-source-') as td:
        source=Path(td)/'own.d88';source.write_bytes(blank.build())
        with m.patch(__name__+'.reference_disk',return_value=source): base_safety(work)
    image=blank.build(); a=first_arms()[2]; assert inspect(image,a)=={'found':False}
    # 公開規則で当該ファイルを合成。末尾の秘密値は照合結果に出ない。
    image=bytearray(image)
    def write(c,h,r,data):
        pos=struct.unpack_from('<I',image,32+(c*2+h)*4)[0]
        while tuple(image[pos:pos+3])!=(c,h,r): pos+=272
        image[pos+16:pos+16+len(data)]=data
    entry=NAME.ljust(9,b' ')+bytes([1,72])+bytes([255])*5
    write(18,1,1,entry); write(18,1,14,bytes([255])*72+b'\xc1')
    body=struct.pack('<HH',m.DATA,m.DATA+63)+PATTERN+b'secret-media'
    write(18,0,1,body)
    obs=inspect(image,a); assert obs['found'] and obs['type01']
    assert {'encoding':'start-le','offset':0} in obs['header']['matches']
    assert obs['payload']['matches']==[{'encoding':'own-pattern','offset':4}]
    o=m.synth(a);o['media']=obs;assert media_valid(o,a)
    bad=m.copy.deepcopy(o);bad['media']['payload']['raw']='secret-media';assert not media_valid(bad,a)
    write(18,1,14,bytes([255])*72+b'\x48')
    try: inspect(image,a)
    except ValueError: pass
    else: raise AssertionError('循環鎖を受理')
    assert 'secret-media' not in m.json.dumps(obs)
    print('OK 媒体合成: 種別・鎖・終端・位置照合・循環陰性・生値拒否',flush=True)

base_calibrated=m.calibrated

def disk_gates(rs,official):
    by={r['arm']['id']:r for r in rs}
    cal=by.get('a1-cal-disk')
    positive=bool(cal and cal['gate'] and all(o.get('values',{}).get('count')==0 and o.get('media',{}).get('found') and o['media'].get('name_match') and o['media'].get('drive') in ('disk2','synthetic') for o in cal['obs']))
    measured=[r for r in rs if not r['arm']['id'].startswith('cal-') and r['arm']['id']!='a1-cal-disk']
    errors=[o.get('values',{}).get('first_err') for r in measured for o in r['obs']]
    uniform=bool(errors) and None not in errors and len(set(errors))==1
    positive_known=bool(not official and not positive and cal and cal['gate'] and all(o.get('values',{}).get('first_err')==2 and o['values'].get('first_stage')==1 for o in cal['obs']))
    uniform_known=not official and uniform and set(errors)=={2}
    return dict(positive=positive,nonuniform=not uniform,
                positive_known=positive_known,uniform_known=uniform_known,
                passed=(positive or positive_known) and (not uniform or uniform_known))

def calibrated(rs):
    if not base_calibrated(rs): return False
    if m.ROUND=='first': return True
    return disk_gates(rs,m.OFFICIAL)['passed']

base_summary=m.summary
def summary(rs,work=None):
    base_summary(rs,work)
    with ((m.ROOT if work is None else work)/'selfrun-addendum1.md').open('a') as f:
        f.write('\nディスクBASIC関門: '+m.json.dumps(disk_gates(rs,False),ensure_ascii=False)+'\n')
        f.write('自作はBSAVE/BLOAD未実装のため陽性対照・一様ERRを既知扱い。公式では両条件を必須とする。\n')

base_measure=m.measure
def measure(rom,official,work):
    reference_disk() # 不足時は全腕の起動前に止める。
    return base_measure(rom,official,work)

def safety(work):
    media_safety_selftest(work)
    aa=addendum_arms()
    rs=[dict(arm=a,obs=[synth(a),synth(a)],gate=True) for a in aa]
    cal=rs[2]
    # 媒体の合成陽性は既存媒体検査も通る形で作る。
    image=bytearray(blank.build())
    def write(c,h,r,data):
        pos=struct.unpack_from('<I',image,32+(c*2+h)*4)[0]
        while tuple(image[pos:pos+3])!=(c,h,r): pos+=272
        image[pos+16:pos+16+len(data)]=data
    write(18,1,1,b't4cal'.ljust(9,b' ')+bytes([1,72])+bytes([255])*5)
    write(18,1,14,bytes([255])*72+b'\xc1')
    write(18,0,1,b'\x00')
    for o in cal['obs']: o['media']=inspect(image,cal['arm'],'synthetic')
    def seterr(r,e):
        for o in r['obs']:
            j=o['writes'].index([1,1])+1
            o['writes'][j:j]=m.error_block(e,1,0,set())
            o['values']={m.FIELDS[i]:v for i,v in o['writes']}
    seterr(rs[-1],2)
    assert all(media_valid(o,r['arm']) for r in rs for o in r['obs'])
    assert disk_gates(rs,True)['passed']
    bad=m.copy.deepcopy(rs)
    for o in bad[2]['obs']: o['media']={'found':False}
    assert all(media_valid(o,r['arm']) for r in bad for o in r['obs'])
    assert not disk_gates(bad,True)['positive'] and disk_gates(bad,True)['nonuniform']
    bad=m.copy.deepcopy(rs)
    # ERR0一様でも落とす。較正は正常なままなので一様判定まで届く。
    bad[-1]=m.copy.deepcopy(rs[-2]);bad[-1]['arm']=rs[-1]['arm']
    assert all(media_valid(o,r['arm']) for r in bad for o in r['obs'])
    assert disk_gates(bad,True)['positive'] and not disk_gates(bad,True)['nonuniform']
    assert not disk_gates(bad,True)['passed'] and not disk_gates(bad,False)['passed']
    uniform33=m.copy.deepcopy(rs)
    for r in uniform33[3:]:
        r['obs']=[synth(r['arm']),synth(r['arm'])];seterr(r,33)
    assert all(media_valid(o,r['arm']) for r in uniform33 for o in r['obs'])
    assert disk_gates(uniform33,True)['positive'] and not disk_gates(uniform33,True)['passed']
    assert not disk_gates(uniform33,False)['passed']
    uniform2=m.copy.deepcopy(uniform33)
    for r in uniform2[2:]:
        r['obs']=[synth(r['arm']),synth(r['arm'])];seterr(r,2)
    assert disk_gates(uniform2,False)['passed'] and not disk_gates(uniform2,True)['passed']
    with m.tempfile.TemporaryDirectory(dir=work,prefix='disk-gate-') as td:
        target=Path(td)/'invalid.tsv'
        with m.patch.object(m,'OFFICIAL',True),m.patch.object(m,'ROUND','addendum1'):
            assert not m.emit(target,uniform33)
        with target.open() as f: rows=list(csv.DictReader(f,delimiter='\t'))
        assert all(r['gate']=='gate_failed' for r in rows)
        assert m.json.loads(rows[-1]['observation'])['values']['first_err']==33
    missing=m.copy.deepcopy(rs);seterr(missing[2],33)
    assert not disk_gates(missing,True)['passed']
    with m.patch.dict(os.environ,{},clear=True):
        try: reference_disk()
        except ValueError: pass
        else: raise AssertionError('参照媒体なしで起動')
    print('OK 追補媒体関門: 陽性/陰性・一様/非一様・自作既知・環境欠落',flush=True)

m.MEASURE_NAME='bsave'
m.PROGRAM_SHA='747065f60471dcc4e1114afcca6bff97c5613ee35fe01120953b3665cb14feb5'
m.PLAN_SHA='80b9be788f2d0f605222dc773a3da02da6bb728fa29427a657dc804e1bcbc9ca'
m.ADDENDUM_PLAN_SHA='06c4588b90f4134d830808f5d11db93e2604404ddf3a1a447ebbf5202a2ee1b4'
m.ADDENDUM_PROGRAM_SHA='c97d3e716d02896cdf22643a9152ecdc540c23f669ab893f878ee845ff574c7e'
m.arms=arms
m.addendum_arms=addendum_arms
m.measure=measure
m.summary=summary
m.calibrated=calibrated
m.media_prepare=media_prepare
m.media_observe=media_observe
m.valid=media_valid
m.synth=synth
m.safety_selftest=safety
if __name__=='__main__':
    try: raise SystemExit(m.main())
    except Exception as exc:
        tb=m.traceback.extract_tb(exc.__traceback__);print(f'NG 媒体器具: {type(exc).__name__}、行{tb[-1].lineno}（本文非出力）');raise SystemExit(1)
