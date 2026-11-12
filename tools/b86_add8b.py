#!/usr/bin/env python3
"""B86 追補8。生値は非公開作業領域でのみ扱う。"""
import collections, json, pathlib, re, sys
import b86_add3 as base
from b86_add7 import Code
from b86_add1 import word

PORTS={'none':None,'p00':0,'p08':8,'p10':16,'p20':32,'p40':64,'p80':128}
KEYS={'none':None,'r00b0':(0,0),'r03b2':(3,2),'r07b4':(7,4),'r0bb7':(11,7)}
REGS={'IY':0x5555,'IX':0x4444,'HL':0x3333,'DE':0x2222,'BC':0x1111,'AF':0x1357}

def arms():
    for port in PORTS:
        for jump in (0xc800,0xc900):
            for key in KEYS:
                yield f'{port}-{jump:04x}-{key}', (port,jump,key)

def generate(a):
    port,jump,key=a; c=Code()
    c.emit('f3 31 00 d0'); c.label('bootmem'); c.emit('32 f2 cf'); c.label('boot'); c.emit('d3 7e')
    # IM2 の全ベクタを C2C2 に揃え、印と RETI だけの受け口を置く。
    c.emit('21 00 c4 36 c2 11 01 c4 01 00 01 ed b0 3e c4 ed 47 ed 5e')
    for i,v in enumerate((0xd3,0x7a,0xed,0x4d)):
        c.emit('3e %02x 32'%v); c.b+=word(0xc2c2+i)
    # 別フレームまで待ち、起動時から保持した打鍵が有効になる時間を確保。
    c.emit('01 ff ff 0b 78 b1 20 fb')
    if PORTS[port] is not None: c.emit('3e %02x d3 31'%PORTS[port])
    for i,v in enumerate((0xc3,0x80,0x30)):
        c.emit('3e %02x 32'%v); c.b+=word(jump+i)
    c.addr(0x21,'end'); c.emit('e5')
    c.emit('21 57 13 e5 f1 01 11 11 11 22 22 21 33 33 dd 21 44 44 fd 21 55 55')
    c.label('startmem'); c.emit('32 f0 cf'); c.label('start'); c.emit('d3 7f c3'); c.b+=word(jump)
    c.label('end'); c.emit('d3 7d'); c.label('endmem'); c.emit('32 f1 cf f5 c5 d5 e5 dd e5 fd e5 ed 57 f5 f3')
    c.emit('e1 7d'); c.label('snap0'); c.emit('d3 7c')
    for i in range(6):
        c.emit('e1 7d'); c.label(f'snap{2*i+1}'); c.emit('d3 7c 7c'); c.label(f'snap{2*i+2}'); c.emit('d3 7c')
    c.label('captured'); c.emit('d3 7f f3 76 18 fd')
    return c.finish(),c.labels

def parsemem(path, m):
    lines=path.read_text().splitlines()
    drops=[int(x) for line in lines for x in re.findall(r'取りこぼし: (\d+)件',line)]
    if drops != [0]: return None
    rows=[]
    for line in lines:
        q=re.fullmatch(r'\s*\d+\s+\d+\s+([0-9A-F]{4})\s+([0-9A-F]{4})\s+([0-9A-F]{2})\s*',line)
        if q: rows.append(tuple(int(x,16) for x in q.groups()))
    starts=[i for i,(pc,addr,v) in enumerate(rows) if pc==m['startmem'] and addr==0xcff0]
    if not starts: return None
    start=starts[0]; stop=next((i for i in range(start+1,len(rows)) if (rows[i][0]==m['bootmem'] and rows[i][1]==0xcff2) or (rows[i][0]==m['startmem'] and rows[i][1]==0xcff0)),len(rows))
    end=next((i for i in range(start+1,stop) if rows[i][0]==m['endmem'] and rows[i][1]==0xcff1),None)
    return rows[start+1:end if end is not None else stop]

def summarize(path,a,m):
    ev=base.events(path/'io'); mem=parsemem(path/'mem',m)
    if ev is None or mem is None: return {'判定':'欠測（ログ不足または取りこぼし）'},None
    def match(e,p,pc): return e[0]=='OUT' and e[1]==p and e[3]==pc
    boots=[i for i,e in enumerate(ev) if match(e,0x7e,m['boot'])]
    if not boots: return {'判定':'欠測（開始印なし）'},None
    stop=boots[1] if len(boots)>1 else len(ev)
    start=next((i for i in range(boots[0]+1,stop) if match(ev[i],0x7f,m['start'])),None)
    if start is None: return {'判定':'欠測（入口未到達）'},None
    end=next((i for i in range(start+1,stop) if match(ev[i],0x7f,m['captured'])),None)
    snaps=[e for e in ev[start+1:end if end is not None else stop] if e[0]=='OUT' and e[1]==0x7c and e[3] in {m[f'snap{i}'] for i in range(13)}]
    returned=end is not None and [e[3] for e in snaps]==[m[f'snap{i}'] for i in range(13)]
    # 戻り直後の記録開始より前の I/O に限る。スナップショット印は除外。
    segment=ev[start+1:end if end is not None else stop]
    segment=[e for e in segment if not (e[0]=='OUT' and e[1]==0x7c and e[3] in {m[f'snap{i}'] for i in range(13)})]
    irq=[i for i,e in enumerate(segment) if match(e,0x7a,0xc2c2)]
    ends=[i for i,e in enumerate(segment) if match(e,0x7d,m['end'])]
    locations=['戻り印前' if not ends or i<ends[0] else '戻り印後' for i in irq]
    segment=[e for e in segment if not (match(e,0x7a,0xc2c2) or match(e,0x7d,m['end']))]
    counts=collections.Counter((d,p) for d,p,v,pc in segment)
    expected=collections.Counter({**{('IN',i):1 for i in range(12)},('OUT',0xe4):2,('OUT',0x51):1,('OUT',0x50):2})
    writes=collections.Counter(addr for pc,addr,v in mem); values={addr:v for pc,addr,v in mem}
    out={'判定':'取得','戻り': '確認' if returned else '戻らない（再起動）' if len(boots)>1 else '時間上限内未確認', '再起動':len(boots)>1,
         'I/O':[{'方向':d,'ポート':f'{p:02X}','件数':n} for (d,p),n in sorted(counts.items())], 'ゲームの形と一致':counts==expected,
         '割り込み受け口':{'回数':len(irq),'位置':locations}, 'スタック付近書込':[{'番地':f'{addr:04X}','件数':n} for addr,n in sorted(writes.items()) if 0xcf80<=addr<=0xcfff], 'RAM書込':[{'番地':f'{addr:04X}','件数':n} for addr,n in sorted(writes.items())], 'EI状態':None,'入力との一致':None}
    if returned:
        s=[e[2] for e in snaps]; vals=[s[i]+256*s[i+1] for i in range(1,13,2)]
        out['EI状態']=bool(s[0]&4); out['入力との一致']={r:v==REGS[r] for r,v in zip(REGS,vals)}
    return out,values if returned else None

def main():
    cmd=sys.argv[1]; aa=dict(arms())
    if cmd=='list': print('\n'.join(aa)); return
    if cmd=='arm-report':
        root=pathlib.Path(sys.argv[2]); name=sys.argv[3]; p=root/'raw'/name
        row,vals=summarize(p,aa[name],generate(aa[name])[1])
        (p/'row.json').write_text(json.dumps(row,ensure_ascii=False))
        (p/'values.tmp').write_text(json.dumps(vals))
        return
    if cmd=='report':
        root=pathlib.Path(sys.argv[2]); rows={}; values={}
        for name,a in aa.items():
            p=root/'raw'/name
            if not (p/'row.json').exists() or not (p/'values.tmp').exists(): rows[name]={'判定':'欠測（実行失敗または未実行）'}; continue
            rows[name]=json.loads((p/'row.json').read_text()); v=json.loads((p/'values.tmp').read_text())
            values[name]=None if v is None else {int(k):x for k,x in v.items()}
        mapping={}
        for name,a in aa.items():
            port,jump,key=a
            if key=='none': continue
            ref=f'{port}-{jump:04x}-none'; x=values.get(ref); y=values.get(name)
            mapping[name]={'行':KEYS[key][0], 'ビット':KEYS[key][1], '変化番地':None if x is None or y is None else [f'{z:04X}' for z in sorted(x.keys() & y.keys()) if x[z]!=y[z]], '片方のみ書込':None if x is None or y is None else [f'{z:04X}' for z in sorted(x.keys() ^ y.keys())]}
        (root/'summary.json').write_text(json.dumps({'腕':rows,'キー対応':mapping},ensure_ascii=False,indent=2)+'\n'); return
    p=pathlib.Path(sys.argv[2]); a=aa[sys.argv[3]]; data,_=generate(a)
    (p/'probe.bin').write_bytes(data); (p/'probe.d88').write_bytes(base.disk(data))
if __name__=='__main__': main()
