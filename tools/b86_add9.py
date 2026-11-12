#!/usr/bin/env python3
"""B86 追補9。実測値は一時領域内のみ、出力は関係と真偽。"""
import json, pathlib, sys
import b86_add3 as base
from b86_add7 import Code
from b86_add1 import word

REGS=('A','BC','DE','HL','IX','IY','F','SP','IFF')
FLAGS={'Z':0x40,'C':1,'S':0x80,'P/V':4}

def arms():
    for target in ('37c9','37d2','3847','3391','369a'):
        cases=range(4) if target!='369a' else range(12)
        for case in cases:
            for n in range(4):
                yield f'{target}-{case:02d}-{n}',dict(target=target,case=case,n=n,media=0)
                if target=='369a': yield f'{target}-{case:02d}-{n}-m1',dict(target=target,case=case,n=n,media=1)

def inputs(a):
    n=a['n']; case=a['case']; t=a['target']
    r={'A':[0x19,0x53,0xa6,0xec][n], 'BC':[0x1245,0x2367,0x459a,0x67bc][n],
       'DE':[0xc820,0xc920,0xca20,0xcb20][n], 'HL':[0xc800,0xc900,0xca00,0xcb00][n],
       'IX':[0x1753,0x2864,0x3975,0x4a86][n], 'IY':[0x5b97,0x6ca8,0x7db9,0x8eca][n],
       'F':[0x00,0x45,0x81,0xc4][n], 'SP':0xd000,'IFF':n%2}
    if t=='369a':
        b=(0,1,3,0x80)[case//3]; sector=(0,1,5)[case%3]
        r['BC']=(b<<8)|sector
        r['F']=(r['F']&~1)|(n%2)
    return r

def generate(a):
    r=inputs(a); t=a['target']; c=Code()
    c.emit('f3 31 00 d0'); c.label('boot'); c.emit('d3 7e')
    c.emit('21 00 c4 36 c2 11 01 c4 01 00 01 ed b0 3e c4 ed 47 ed 5e')
    for i,v in enumerate((0xd3,0x7a,0xed,0x4d)):
        c.emit('3e %02x 32'%v); c.b+=word(0xc2c2+i)
    # 3847 は自作パターンをサブ RAM に書いてから 09 で読み出す。
    if t=='3847':
        def call(addr): c.emit('cd'); c.b.extend(word(addr))
        c.emit('3e 0c'); call(0x37c9)
        for v in (0x60,0,1,0): c.emit('3e %02x'%v); call(0x37d2)
        c.emit('af 32 04 c1'); c.label('loop')
        c.emit('3e %02x'%([0,1,0x80,0xff][a['case']])); call(0x37d2)
        c.emit('3a 04 c1 3c 32 04 c1'); c.addr(0xc2,'loop')
        c.emit('3e 09'); call(0x37c9)
        for v in (0x60,0,0x61,0): c.emit('3e %02x'%v); call(0x37d2)
    if t=='37d2':
        c.emit('3e 0c cd c9 37')
    if t=='3391':
        # HL に置いた自作コードが捕捉処理へ直行する。
        payload=[0xd3,0x7b,0xc3,0,0]
        c.addr(0x21,'capture'); c.emit('22'); c.b+=word(r['HL']+3)
        for i,v in enumerate(payload[:3]): c.emit('3e %02x 32'%v); c.b+=word(r['HL']+i)
    c.emit('31 00 d0')
    c.emit('21'); c.b+=word((r['A']<<8)|r['F']); c.emit('e5 f1')
    for op,key in ((0x01,'BC'),(0x11,'DE'),(0x21,'HL')): c.b.append(op); c.b+=word(r[key])
    for prefix,key in ((0xdd,'IX'),(0xfd,'IY')): c.b.extend((prefix,0x21)); c.b+=word(r[key])
    c.emit('fb' if r['IFF'] else 'f3'); c.label('start'); c.emit('d3 7f cd'); c.b+=word(int(t,16))
    c.label('capture'); c.emit('f5 c5 d5 e5 dd e5 fd e5 ed 57 f5 f3')
    c.emit('e1 7d'); c.label('snap0'); c.emit('d3 7c')
    for i in range(6):
        c.emit('e1 7d'); c.label(f'snap{2*i+1}'); c.emit('d3 7c 7c'); c.label(f'snap{2*i+2}'); c.emit('d3 7c')
    # 保存した6語を取り出した後の SP が戻り直後の SP。
    c.emit('21 00 00 39 7d'); c.label('snap13'); c.emit('d3 7c 7c'); c.label('snap14'); c.emit('d3 7c')
    c.label('end'); c.emit('d3 7f f3 76 18 fd')
    return c.finish(),c.labels

def extract(path,a):
    m=generate(a)[1]; ev=base.events(path/'io')
    if ev is None: return {'判定':'欠測（ログ不足）'},None
    def ismark(e,p,pc): return e[0]=='OUT' and e[1]==p and e[3]==pc
    boots=[i for i,e in enumerate(ev) if ismark(e,0x7e,m['boot'])]
    if not boots: return {'判定':'欠測（開始印なし）'},None
    limit=boots[1] if len(boots)>1 else len(ev)
    start=next((i for i in range(boots[0]+1,limit) if ismark(ev[i],0x7f,m['start'])),None)
    if start is None: return {'判定':'欠測（前置き未完了）'},None
    end=next((i for i in range(start+1,limit) if ismark(ev[i],0x7f,m['end'])),None)
    snaps=[e for e in ev[start+1:end if end is not None else limit] if e[0]=='OUT' and e[1]==0x7c and e[3] in {m[f'snap{i}'] for i in range(15)}]
    reached=any(ismark(e,0x7b,inputs(a)['HL']) for e in ev[start+1:end if end is not None else limit]) if a['target']=='3391' else None
    if (a['target']=='3391' and not reached) or end is None or [e[3] for e in snaps]!=[m[f'snap{i}'] for i in range(15)]:
        return {'判定':'取得','戻り':'戻らない','再起動':limit<len(ev),'自作コード到達':reached},None
    s=[e[2] for e in snaps]; words=[s[i]+256*s[i+1] for i in range(1,13,2)]
    iy,ix,hl,de,bc,af=words
    result={'A':af>>8,'F':af&255,'BC':bc,'DE':de,'HL':hl,'IX':ix,'IY':iy,'SP':s[13]+256*s[14],'IFF':int(bool(s[0]&4))}
    return {'判定':'取得','戻り':'確認','再起動':limit<len(ev),'自作コード到達':reached},result

def relations(pairs,bits=16):
    if len(pairs)<2: return {'不変':None,'入力加算一定':None,'定数':None}
    mod=1<<bits
    return {'不変':all(x==y for x,y in pairs), '入力加算一定':len({(y-x)%mod for x,y in pairs})==1,
            '定数':len({y for x,y in pairs})==1,'入力変化あり':len({x for x,y in pairs})>1}

def report(root):
    aa=dict(arms()); rows={}; values={}
    for name,a in aa.items():
        p=root/'raw'/name
        if (p/'row.json').exists():
            rows[name]=json.loads((p/'row.json').read_text()); values[name]=json.loads((p/'values.tmp').read_text())
        else: rows[name]={'判定':'欠測（実行失敗または未実行）'}
    groups={}
    for target in ('37c9','37d2','3847','3391','369a'):
        for case in (range(12) if target=='369a' else range(4)):
            names=[f'{target}-{case:02d}-{n}' for n in range(4)]
            valid=[(inputs(aa[n]),values[n]) for n in names if values.get(n) is not None]
            rel={key:relations([(i[key],o[key]) for i,o in valid],8 if key in ('A','F') else 1 if key=='IFF' else 16) for key in REGS}
            rel['他入力との対応']={out:{src:relations([(i[src],o[out]) for i,o in valid],8 if out in ('A','F') else 1 if out=='IFF' else 16) for src in REGS} for out in REGS}
            rel['Fビット']={k:relations([(int(bool(i['F']&mask)),int(bool(o['F']&mask))) for i,o in valid],1) for k,mask in FLAGS.items()}
            if target=='3847':
                pat=[0,1,0x80,0xff][case]
                rel['受信模様との関係']={'Aが模様と一致':None if not valid else all(o['A']==pat for i,o in valid),'Zが受信Aゼロと一致':None if not valid else all(bool(o['F']&0x40)==(o['A']==0) for i,o in valid)}
            groups[f'{target}-{case:02d}']={'有効数':len(valid),'関係':rel}
    pattern={}
    for n in range(4):
        names=[f'3847-{case:02d}-{n}' for case in range(4)]
        outs=[values.get(name) for name in names]
        pattern[str(n)]={key: None if any(o is None for o in outs) else len({o[key] for o in outs})>1 for key in REGS}
        pattern[str(n)]['Fビット']={k:None if any(o is None for o in outs) else len({bool(o['F']&mask) for o in outs})>1 for k,mask in FLAGS.items()}
    media={}
    for case in range(12):
        for n in range(4):
            name=f'369a-{case:02d}-{n}'; x=values.get(name); y=values.get(name+'-m1')
            media[name]={key:None if x is None or y is None else x[key]!=y[key] for key in REGS}
            media[name]['Fビット']={k:None if x is None or y is None else bool(x['F']&mask)!=bool(y['F']&mask) for k,mask in FLAGS.items()}
    (root/'summary.json').write_text(json.dumps({'腕':rows,'組':groups,'受信模様による変化':pattern,'媒体変更による変化':media},ensure_ascii=False,indent=2)+'\n')

def main():
    cmd=sys.argv[1]; aa=dict(arms())
    if cmd=='list': print('\n'.join(aa)); return
    root=pathlib.Path(sys.argv[2])
    if cmd=='report': report(root); return
    name=sys.argv[3]; a=aa[name]
    if cmd=='generate':
        data,_=generate(a); (root/'probe.bin').write_bytes(data)
        disk=bytearray(base.disk(data))
        if a['media']:
            for track in range(80):
                pos=int.from_bytes(disk[0x20+4*track:0x24+4*track],'little')
                if not pos: continue
                for sector in range(16):
                    size=int.from_bytes(disk[pos+14:pos+16],'little')
                    if track or sector: disk[pos+16:pos+16+size]=bytes(x^255 for x in disk[pos+16:pos+16+size])
                    pos+=16+size
        (root/'probe.d88').write_bytes(disk)
    elif cmd=='extract':
        row,vals=extract(root,a); (root/'row.json').write_text(json.dumps(row,ensure_ascii=False)); (root/'values.tmp').write_text(json.dumps(vals))
if __name__=='__main__': main()
