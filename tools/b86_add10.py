#!/usr/bin/env python3
"""追補10: 生値は外部の一時ファイルにのみ保持する。"""
import collections, json, pathlib, re, sys
import b86_add3 as base
import b86_add8b as kb
import b86_add9 as old
from b86_add7 import Code
from b86_add1 import word

TARGETS=('6f96','42f6','43e1','43e9','4353','7071','11df','3e0d')
KEYS=kb.KEYS

def arms():
    for t in TARGETS:
        for mode in ('call','jp0','jp1','jp2'):
            for irq in ('di','ei'):
                for n in range(4): yield f'{t}-{mode}-{irq}-{n}',dict(t=t,mode=mode,irq=irq,n=n)
    for irq in ('di','ei'):
        for n in range(4): yield f'6f6b-call-{irq}-{n}',dict(t='6f6b',mode='call',irq=irq,n=n)
    for key in KEYS:
        for n in range(4): yield f'3080-{key}-{n}',dict(t='3080',mode='call',irq='di',n=n,key=key)

def inputs(a):
    r=old.inputs(dict(n=a['n'],case=0,target=a['t']))
    r['IFF']=int(a['irq']=='ei')
    if a['t']=='6f6b': r['BC']=(0xcc40,0xcd40,0xce40,0xcb40)[a['n']]
    return r

def generate(a):
    r=inputs(a); c=Code(); c.emit('f3 31 00 d0'); c.label('bootmem'); c.emit('32 f2 cf'); c.label('boot'); c.emit('d3 7e')
    c.emit('21 00 c4 36 c2 11 01 c4 01 00 01 ed b0 3e c4 ed 47 ed 5e')
    for i,v in enumerate((0xd3,0x7a,0xfb,0xed,0x4d)):
        c.emit('3e %02x 32'%v); c.b+=word(0xc2c2+i)
    if a['t']=='3080':
        # 既知の前回値を自作で配置し、実行後の書込みと比較する。
        v=(0,0x55,0xaa,0xff)[a['n']]
        c.emit('21 d0 e6 06 18 3e %02x 77 23 10 fc'%v)
        c.emit('32 cf e6 32 f9 ef 01 ff ff 0b 78 b1 20 fb')
    if a['t']=='6f6b':
        # HL を異なる自作受け口に向け、到達時は印を出して RET。
        for addr in (r['HL'], r['DE'], r['BC']):
            for i,v in enumerate((0xd3,0x7b,0xc9)):
                c.emit('3e %02x 32'%v); c.b+=word(addr+i)
    c.emit('31 00 d0')
    if a['mode'].startswith('jp'):
        for _ in range(1+int(a['mode'][-1])): c.addr(0x21,'end'); c.emit('e5')
    c.emit('21'); c.b+=word((r['A']<<8)|r['F']); c.emit('e5 f1')
    for op,k in ((0x01,'BC'),(0x11,'DE'),(0x21,'HL')): c.b.append(op); c.b+=word(r[k])
    for pre,k in ((0xdd,'IX'),(0xfd,'IY')): c.b.extend((pre,0x21)); c.b+=word(r[k])
    c.emit('fb' if r['IFF'] else 'f3'); c.label('startmem'); c.emit('32 f0 cf'); c.label('start'); c.emit('d3 7f')
    c.emit('cd' if a['mode']=='call' else 'c3'); c.b+=word(int(a['t'],16))
    c.label('end'); c.emit('d3 7d'); c.label('endmem'); c.emit('32 f1 cf f5 c5 d5 e5 dd e5 fd e5 ed 57 f5 f3')
    c.emit('e1 7d'); c.label('snap0'); c.emit('d3 7c')
    for i in range(6):
        c.emit('e1 7d'); c.label(f'snap{2*i+1}'); c.emit('d3 7c 7c'); c.label(f'snap{2*i+2}'); c.emit('d3 7c')
    c.emit('21 00 00 39 7d'); c.label('snap13'); c.emit('d3 7c 7c'); c.label('snap14'); c.emit('d3 7c')
    c.label('captured'); c.emit('d3 7f f3 76 18 fd')
    return c.finish(),c.labels

def extract(path,a):
    m=generate(a)[1]; ev=base.events(path/'io'); mem=kb.parsemem(path/'mem',m)
    if ev is None or mem is None: return {'判定':'欠測（ログ不足または取りこぼし）'},None
    def mark(e,p,pc): return e[0]=='OUT' and e[1]==p and e[3]==pc
    boots=[i for i,e in enumerate(ev) if mark(e,0x7e,m['boot'])]
    if not boots: return {'判定':'欠測（開始印なし）'},None
    stop=boots[1] if len(boots)>1 else len(ev)
    start=next((i for i in range(boots[0]+1,stop) if mark(ev[i],0x7f,m['start'])),None)
    if start is None: return {'判定':'欠測（入口未到達）'},None
    end=next((i for i in range(start+1,stop) if mark(ev[i],0x7d,m['end'])),None)
    captured=next((i for i in range(end+1,stop) if mark(ev[i],0x7f,m['captured'])),None) if end is not None else None
    snaps=[] if end is None else [e for e in ev[end+1:captured if captured is not None else stop] if e[0]=='OUT' and e[1]==0x7c and e[3] in {m[f'snap{i}'] for i in range(15)}]
    returned=captured is not None and [e[3] for e in snaps]==[m[f'snap{i}'] for i in range(15)]
    seg=ev[start+1:end if end is not None else stop]
    reached={k:any(mark(e,0x7b,inputs(a)[k]) for e in seg) for k in ('HL','DE','BC')} if a['t']=='6f6b' else None
    seg=[e for e in seg if not (mark(e,0x7a,0xc2c2) or (a['t']=='6f6b' and any(mark(e,0x7b,inputs(a)[k]) for k in ('HL','DE','BC'))))]
    counts=collections.Counter((d,p) for d,p,v,pc in seg); writes=collections.Counter(addr for pc,addr,v in mem)
    # 区間前に記録された値だけを基準にする。未知の初期値は推測しない。
    previous={}
    for line in (path/'mem').read_text().splitlines():
        match=re.fullmatch(r'\s*\d+\s+\d+\s+([0-9A-F]{4})\s+([0-9A-F]{4})\s+([0-9A-F]{2})\s*',line)
        if not match: continue
        pc,addr,value=(int(x,16) for x in match.groups())
        if pc==m['startmem'] and addr==0xcff0: break
        previous[addr]=value
    changes=collections.Counter(); unknown=collections.Counter()
    for pc,addr,value in mem:
        if addr not in previous: unknown[addr]+=1
        elif previous[addr]!=value: changes[addr]+=1
        previous[addr]=value
    row={'判定':'取得','戻り':'確認' if returned else '戻らない','再起動':len(boots)>1,'自作HL受け口到達':reached,'I/O':[{'方向':d,'ポート':f'{p:02X}','件数':n} for (d,p),n in sorted(counts.items())], 'RAM書込':[{'番地':f'{addr:04X}','件数':n} for addr,n in sorted(writes.items())], 'RAM変化（前値既知）':[{'番地':f'{addr:04X}','件数':n} for addr,n in sorted(changes.items())], 'RAM前値不明の書込':[{'番地':f'{addr:04X}','件数':n} for addr,n in sorted(unknown.items())]}
    vals={'out':{},'mem':{},'keyin':{}}
    for d,p,v,pc in seg:
        if d=='OUT': vals['out'].setdefault(str(p),[]).append(v)
        if d=='IN' and p<12: vals['keyin'].setdefault(str(p),[]).append(v)
    for pc,addr,v in mem: vals['mem'][str(addr)]=v
    if returned:
        s=[e[2] for e in snaps]; iy,ix,hl,de,bc,af=[s[i]+256*s[i+1] for i in range(1,13,2)]
        vals['regs']={'A':af>>8,'F':af&255,'BC':bc,'DE':de,'HL':hl,'IX':ix,'IY':iy,'SP':s[13]+256*s[14],'IFF':int(bool(s[0]&4))}
    return row,vals

def report(root):
    aa=dict(arms()); rows={}; vals={}
    for name in aa:
        p=root/'raw'/name
        if (p/'row.json').exists(): rows[name]=json.loads((p/'row.json').read_text()); vals[name]=json.loads((p/'values.tmp').read_text())
        else: rows[name]={'判定':'欠測（実行失敗または未実行）'}
    groups={}
    for t in (*TARGETS,'6f6b'):
        for mode in (('call',) if t=='6f6b' else ('call','jp0','jp1','jp2')):
            for irq in ('di','ei'):
                names=[f'{t}-{mode}-{irq}-{n}' for n in range(4)]; valid=[(inputs(aa[x]),vals[x]) for x in names if vals.get(x) and 'regs' in vals[x]]
                rel={o:{i:old.relations([(r[i],v['regs'][o]) for r,v in valid],8 if o in ('A','F') else 1 if o=='IFF' else 16) for i in old.REGS} for o in old.REGS}
                ports=sorted({p for r,v in valid for p in v['out']})
                outs={f'{int(p):02X}:{j}':{i:old.relations([(r[i],v['out'][p][j]) for r,v in valid if len(v['out'].get(p,[]))>j],8) for i in ('A','BC','DE','HL')} for p in ports for j in range(max(len(v['out'].get(p,[])) for r,v in valid))}
                groups[f'{t}-{mode}-{irq}']={'有効数':len(valid),'レジスタ関係':rel,'OUT関係':outs}
    keys={}
    for name,a in aa.items():
        if a['t']!='3080': continue
        v=vals.get(name); prev=(0,0x55,0xaa,0xff)[a['n']]; key=KEYS[a['key']]
        if not v or 'regs' not in v or key is None: continue
        row,bit=key; inv=v['keyin'].get(str(row),[]); observed=inv[-1] if inv else None
        def rel(addr):
            x=v['mem'].get(str(addr),prev)
            ref=vals.get(f'3080-none-{a["n"]}'); baseline=None if not ref else ref['mem'].get(str(addr),prev)
            return {'前回と一致':x==prev,'入力行と一致':None if observed is None else x==observed,'入力行の反転と一致':None if observed is None else x==(observed^255),'押下ビットが立つ':bool(x&(1<<bit)),'押下ビットだけと一致':x==(1<<bit),'押下ビットだけの反転と一致':x==(255^(1<<bit)),'無押下と異なる':None if baseline is None else x!=baseline,'行番号と一致':x==row,'ビット番号と一致':x==bit,'行とビットの通し番号と一致':x==row*8+bit}
        keys[name]={'行':row,'ビット':bit,'E6D0+r':rel(0xe6d0+row),'E6DC+r':rel(0xe6dc+row),'EFF9':rel(0xeff9),'E6CF':rel(0xe6cf)}
    (root/'summary.json').write_text(json.dumps({'腕':rows,'組':groups,'キー関係':keys},ensure_ascii=False,indent=2)+'\n')

def main():
    cmd=sys.argv[1]; aa=dict(arms())
    if cmd=='list': print('\n'.join(aa)); return
    root=pathlib.Path(sys.argv[2])
    if cmd=='report': report(root); return
    name=sys.argv[3]; a=aa[name]
    if cmd=='generate':
        data,_=generate(a); (root/'probe.bin').write_bytes(data); (root/'probe.d88').write_bytes(base.disk(data))
    elif cmd=='extract':
        row,v=extract(root,a); (root/'row.json').write_text(json.dumps(row,ensure_ascii=False)); (root/'values.tmp').write_text(json.dumps(v))
if __name__=='__main__': main()
