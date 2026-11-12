#!/usr/bin/env python3
"""B86 追補2: 自作器具と値なし集計。生ログは非公開出力先のみ。"""
import json
import pathlib
import re
import sys
import b86_add1 as base
from make_l3_testdisk import build_d88, coord_header_pattern

TARGET = base.TARGETS

def fixed_arms():
    yield 'coord-base', ['369a'], None, 0
    for reg in ('d','e','c','a','ix','iy'):
        yield 'coord-'+reg, ['369a'], reg, 0
    yield '3847-pair', ['37c9','37d2','3847'], None, 1
    yield '3847-read', ['369a','3847'], None, 1
    for a in (0,1,2,255):
        yield f'3847-send-{a:02x}', ['37c9','3847'], None, a
    for first in ('37c9','369a'):
        yield f'3391-{first}', [first,'3391'], None, 1
    for target in ('control','positive'):
        yield target, [target], None, 0

def arm_by_name(name):
    for arm in fixed_arms():
        if arm[0] == name: return arm
    m = re.fullmatch(r'ram-([0-9a-f]{4})-([01])', name)
    if m and 0xc100 <= int(m[1],16) <= 0xefff:
        return name, ['369a'], ('ram', int(m[1],16), int(m[2])), 0
    raise ValueError('不明な腕')

def generate(arm):
    name, targets, change, a = arm
    code = bytearray.fromhex('f3 31 00 f0 21 00 d0 01 00 08 af 77 23 3c 0b 57 78 b1 7a 20 f6')
    code += bytes.fromhex('21 00 c1 01 00 2f cd 80 c0')
    if isinstance(change, tuple):
        code += b'\x3e' + bytes([change[2]]) + b'\x32' + base.word(change[1])
    av = 2 if change == 'a' else a
    bc = 2 if change == 'c' else 1
    de = 0xd400
    if change == 'd': de = 0xd500
    if change == 'e': de = 0xd401
    code += b'\x21' + base.word(av << 8) + b'\xe5\xf1'
    code += b'\x01' + base.word(bc) + b'\x11' + base.word(de) + b'\x21\x00\xd0'
    code += b'\xdd\x21' + base.word(1 if change == 'ix' else 0)
    code += b'\xfd\x21' + base.word(1 if change == 'iy' else 0)
    markers=[]
    for i,target in enumerate(targets):
        markers.append(0xc000+len(code)); code += b'\xd3\x7f\xcd'+base.word(TARGET[target])
        markers.append(0xc000+len(code)); code += b'\xd3\x7f'
        if i == len(targets)-2:
            markers.append(0xc000+len(code)); code += b'\xd3\x7e'
    code += bytes.fromhex('21 00 c1 01 00 2f cd 80 c0 f3 76 18 fd')
    if len(code)>0x80: raise ValueError('器具領域重複')
    sector=code+bytes(256-len(code))
    sector[0x80:0x8a]=bytes.fromhex('7e d3 7d 23 0b 78 b1 20 f7 c9')
    sector[0xe0:0xe9]=bytes.fromhex('3e 5a 32 00 d0 d3 fd 37 c9')
    sector[0xf0]=0xc9
    return bytes(sector), markers

def disk(sector):
    data=bytearray(build_d88(sectors_per_track=16,n_cylinders=40,heads=2,content_rule='coord-header',disk_id=0xa1))
    offset=int.from_bytes(data[0x20:0x24],'little')
    data[offset+16:offset+16+256]=sector
    return data

def events(path):
    text=path.read_text(); drops=re.findall(r'取りこぼし: (\d+)件',text)
    if len(drops)!=2 or any(int(x) for x in drops): return None
    out=[]
    for line in text.splitlines():
        m=re.fullmatch(r'\s*\d+\s+\d+\s+\d+\s+main\s+(IN|OUT)\s+([0-9A-F]{4})\s+([0-9A-F]{2})\s+([0-9A-F]{4})',line)
        if m: out.append((m[1],int(m[2],16),int(m[3],16),int(m[4],16)))
    return out

def summarize(path, arm, markers):
    ev=events(path/'io')
    if ev is None: return {'判定':'欠測（ログ取りこぼし）'}
    def positions(port,pc): return [i for i,e in enumerate(ev) if e[0]=='OUT' and e[1]==port and e[3]==pc]
    n=len(arm[1]); pairs=[]; k=0
    for i in range(n):
        pairs.append((markers[k],markers[k+1])); k+=2
        if i==n-2: pre=markers[k]; k+=1
    prepos=positions(0x7e,pre) if n>1 else []
    rows=[]
    for i,(startpc,endpc) in enumerate(pairs):
        starts=positions(0x7f,startpc); ends=positions(0x7f,endpc)
        start=starts[0] if starts else None
        end=next((x for x in ends if start is not None and x>start),None)
        # 再起動の次の開始印が区間終端。重複を未帰還の証拠にしない。
        restart=starts[1] if len(starts)>1 else len(ev)
        stop=min(end if end is not None else len(ev),restart)
        if start is None:
            rows.append({'入口':arm[1][i],'開始':'欠測'}); continue
        segment=ev[start+1:stop]
        sent=[e[2] for e in segment if e[:2]==('OUT',0xfd)]
        recv=bytes(e[2] for e in segment if e[:2]==('IN',0xfc))
        coords=[[c,h,s] for c in range(40) for h in range(2) for s in range(1,17) if not (c==h==0 and s==1) and coord_header_pattern(0xa1,c,h,s) in recv]
        if (path/'probe.bin').read_bytes() in recv: coords.insert(0,[0,0,1])
        # 要求の区切りは IN FC、見出し値は非公開で保持し公開は自作入力との一致だけ。
        requests=[]; current=[]
        for e in segment:
            if e[:2]==('OUT',0xfd): current.append(e[2])
            elif e[:2]==('IN',0xfc) and current:
                requests.append(current); current=[]
        if current: requests.append(current)
        row={'入口':arm[1][i],'開始':'確認','終了印':'確認' if end is not None and end<restart else '未確認', '送信長':len(sent),'受信長':len(recv),'受信内の自作媒体座標':coords}
        if arm[1][i]=='3391':
            row={'入口':'3391','開始':'確認','観測終端':'終了印' if end is not None and end<restart else '再開始印' if restart<len(ev) else '時間上限', 'サブ要求見出し':[{'長さ':len(r),'先頭と自作A一致':r[0]==arm[3]} for r in requests]}
        if arm[1][i]=='3391':
            lines=(path/'io').read_text().splitlines()
            main_clocks=[]; sub=[]
            pattern=re.compile(r'\s*\d+\s+(\d+)\s+\d+\s+(main|sub)\s+(IN|OUT)\s+([0-9A-F]{4})\s+([0-9A-F]{2})\s+[0-9A-F]{4}')
            for line in lines:
                m=pattern.fullmatch(line)
                if m:
                    clock=int(m[1])
                    if m[2]=='main': main_clocks.append(clock)
                    elif m[4]=='00FB': sub.append((clock,m[3],int(m[5],16)))
            low=main_clocks[start]; high=main_clocks[stop] if stop<len(main_clocks) else None
            runs=[]
            for clock,kind,value in sub:
                if clock<=low or (high is not None and clock>=high): continue
                if not runs or runs[-1][0]!=kind: runs.append([kind,0,value])
                runs[-1][1]+=1
            row['FDC送信見出し']=[{'長さ':length,'先頭と自作A一致':value==arm[3]} for kind,length,value in runs if kind=='OUT']
        rows.append(row)
    first=positions(0x7f,pairs[0][0]); last=positions(0x7f,pairs[-1][1])
    before=[e[2] for e in ev[:first[0]] if e[:2]==('OUT',0x7d) and e[3]==0xc081] if first else []
    after=[e[2] for e in ev[last[0]+1:] if e[:2]==('OUT',0x7d) and e[3]==0xc081] if last else []
    ok=len(before)==len(after)==0x2f00
    changed=[0xc100+i for i,(x,y) in enumerate(zip(before,after)) if x!=y] if ok else []
    coords=[[c,h,s] for c in range(40) for h in range(2) for s in range(1,17) if not(c==h==0 and s==1) and coord_header_pattern(0xa1,c,h,s) in bytes(after)] if ok else []
    # 起動セクタ全体との一致も自作データとして座標に数える。
    if ok and (path/'probe.bin').read_bytes() in bytes(after): coords.insert(0,[0,0,1])
    return {'区間':rows,'前置き終了印':'確認' if prepos else '未確認' if n>1 else '対象外','RAM':{'判定':'取得' if ok else '欠測','変化番地範囲':base.ranges(changed) if ok else None,'自作媒体座標':coords if ok else None}}

def main():
    cmd=sys.argv[1]
    if cmd=='list': print('\n'.join(a[0] for a in fixed_arms())); return
    if cmd=='candidates':
        s=json.loads(pathlib.Path(sys.argv[2]).read_text())
        if s['RAM']['判定']!='取得': raise ValueError('候補を選べない: 基準腕が欠測')
        for lo,hi in s['RAM']['変化番地範囲']:
            for addr in range(int(lo,16),int(hi,16)+1):
                for val in (0,1): print(f'ram-{addr:04x}-{val}')
        return
    path=pathlib.Path(sys.argv[2]); arm=arm_by_name(sys.argv[3]); sector,markers=generate(arm)
    if cmd=='generate':
        (path/'probe.bin').write_bytes(sector); (path/'probe.d88').write_bytes(disk(sector))
    elif cmd=='summarize':
        pathlib.Path(sys.argv[4]).write_text(json.dumps(summarize(path,arm,markers),ensure_ascii=False,indent=2)+'\n')
    else: raise ValueError('不明な操作')
if __name__=='__main__': main()
