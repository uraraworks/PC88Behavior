#!/usr/bin/env python3
"""l4-t4 BSAVE/BLOAD。自作媒体の当該ファイルだけを候補照合する。"""
import sys
sys.dont_write_bytecode=True
import hashlib, struct
from pathlib import Path
import l4_mlcall_measure as m
import build_blank_data_disk as blank
NAME=b't4own'
PATTERN=bytes(range(64))
ml_arms=m.arms

def arms():
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
            if directory[j:j+9]==NAME.ljust(9,b' '): entry=directory[j:j+11]; break
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

def media_prepare(work,a):
    for name in ('a.d88','b.d88'): (work/name).write_bytes(blank.build())
    def cleanup():
        for name in ('a.d88','b.d88'): (work/name).unlink(missing_ok=True)
    return ['--disk',str(work/'a.d88'),'--disk2',str(work/'b.d88'),'--save-to-disk-image'],cleanup

def media_observe(work,a):
    if a['id'].startswith('cal-'): return None
    try:
        # 指定どおり1:を固定。論理番号と物理ドライブを仮定せず、自作名だけ照合する。
        found=[inspect((work/name).read_bytes(),a,drive) for name,drive in (('a.d88','disk1'),('b.d88','disk2'))]
        hits=[o for o in found if o.get('found')]
        return hits[0] if len(hits)==1 else dict(found=False) if not hits else dict(unknown=True)
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

def safety(work):
    base_safety(work)
    image=blank.build(); a=arms()[2]; assert inspect(image,a)=={'found':False}
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

m.MEASURE_NAME='bsave'
m.PROGRAM_SHA='747065f60471dcc4e1114afcca6bff97c5613ee35fe01120953b3665cb14feb5'
m.PLAN_SHA='80b9be788f2d0f605222dc773a3da02da6bb728fa29427a657dc804e1bcbc9ca'
m.arms=arms
m.media_prepare=media_prepare
m.media_observe=media_observe
m.valid=media_valid
m.synth=synth
m.safety_selftest=safety
if __name__=='__main__':
    try: raise SystemExit(m.main())
    except Exception as exc:
        tb=m.traceback.extract_tb(exc.__traceback__);print(f'NG 媒体器具: {type(exc).__name__}、行{tb[-1].lineno}（本文非出力）');raise SystemExit(1)
