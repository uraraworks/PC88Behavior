#!/usr/bin/env python3
"""追補13: 自作介入と、値を伏せた入出力関係の集計。"""
import collections
import json
import pathlib
import sys
import b86_add10 as prev
import b86_add8b as memory
from b86_add7 import Code
from b86_add1 import word, ranges

VALUES = (0, 1, 2, 4, 8, 16, 32, 64, 128, 255)
PORTS = (0x31, 0x30, 0x40, 0x51, 0x50, 0x64, 0x65, 0x68)
REGS = ('A', 'F', 'BC', 'DE', 'HL', 'IX', 'IY', 'SP', 'IFF')
# 需要観測の読み番地。範囲の重複は集合で除く。
def addresses():
    spans = ((0xe60e,0xe616),(0xe62b,0xe646),(0xe6b0,0xe6b4),
             (0xe6b6,0xe6b6),(0xe6b8,0xe6b9),(0xe6c0,0xe6c2),
             (0xe6c4,0xe6c5),(0xeabd,0xeabd),(0xeacc,0xeacd),
             (0xeb10,0xeb11),(0xec41,0xec42),(0xec46,0xec46),
             (0xef86,0xef89),(0xf136,0xf137),(0xff08,0xfff7))
    return sorted({x for lo,hi in spans for x in range(lo,hi+1)})

def arms():
    for target in ('7071','3e0d'):
        yield f'{target}-base', dict(target=target, addr=None, value=None)
        for addr in addresses()+[0xe700]:
            for value in VALUES:
                yield f'{target}-{addr:04x}-{value:02x}', dict(target=target,addr=addr,value=value)

def generate(a):
    c=Code(); c.emit('f3 31 00 d0'); c.label('bootmem'); c.emit('32 f2 cf'); c.label('boot'); c.emit('d3 7e')
    if a['addr'] is not None:
        c.emit('3e %02x 32'%a['value']); c.b+=word(a['addr'])
    c.emit('31 00 d0'); c.addr(0x21,'end'); c.emit('e5')
    c.emit('21 00 35 e5 f1 01 34 12 11 00 c9 21 00 c8 dd 21 57 13 fd 21 68 24')
    c.label('startmem'); c.emit('32 f0 cf'); c.label('start'); c.emit('d3 7f')
    # 7071 の直前の OUT 31。A は全腕で自作の 00 に固定。
    if a['target']=='7071': c.emit('3e 00 d3 31')
    c.emit('c3'); c.b+=word(int(a['target'],16))
    c.label('end'); c.emit('d3 7d'); c.label('endmem'); c.emit('32 f1 cf f5 c5 d5 e5 dd e5 fd e5 ed 57 f5 f3')
    c.emit('e1 7d'); c.label('snap0'); c.emit('d3 7c')
    for i in range(6):
        c.emit('e1 7d'); c.label(f'snap{2*i+1}'); c.emit('d3 7c 7c'); c.label(f'snap{2*i+2}'); c.emit('d3 7c')
    c.emit('21 00 00 39 7d'); c.label('snap13'); c.emit('d3 7c 7c'); c.label('snap14'); c.emit('d3 7c')
    c.label('captured'); c.emit('d3 7f f3 76 18 fd')
    return c.finish(),c.labels

def extract(path,a):
    m=generate(a)[1]; original=prev.generate; prev.generate=lambda _: generate(a)
    try: row,vals=prev.extract(path,dict(t=a['target'],irq='di',mode='jp0'))
    finally: prev.generate=original
    if vals is None: return row,vals
    ev=prev.base.events(path/'io')
    start=next(i for i,e in enumerate(ev) if e[0]=='OUT' and e[1]==0x7f and e[3]==m['start'])
    stop=next((i for i,e in enumerate(ev[start+1:],start+1) if e[0]=='OUT' and ((e[1]==0x7d and e[3]==m['end']) or (e[1]==0x7e and e[3]==m['boot']))),len(ev))
    seg=ev[start+1:stop]
    # 自作 OUT 31 は区間の先頭で、ROM の出力には数えない。
    if a['target']=='7071' and seg and seg[0][0:2]==('OUT',0x31): seg=seg[1:]
    out={}
    for d,p,v,pc in seg:
        if d=='OUT' and p in PORTS: out.setdefault(str(p),[]).append(v)
    mem=memory.parsemem(path/'mem',m)
    counts=collections.Counter(addr for pc,addr,v in mem if 0xf3c8<=addr<=0xfff7)
    row={'判定':row['判定'],'戻り':row['戻り'],'再起動':row['再起動'],
         '画面書込':{'件数':sum(counts.values()),'異なる番地数':len(counts),'範囲':ranges(sorted(counts))},
         'OUT件数':{f'{p:02X}':len(out.get(str(p),[])) for p in PORTS}}
    return row,{'out':out,'regs':vals.get('regs')}

def relation(pairs, bits=8):
    if len(pairs)<2 or len({x for x,y in pairs})<2: return {'判定':'未判定'}
    ys=[y for x,y in pairs]
    if len(set(ys))==1: return {'判定':'定数（値はリポジトリ外）'}
    result={'判定':'変化','入力と一致':all(x==y for x,y in pairs)}
    if bits==8:
        result['ビット対応候補']={str(j):[f'{i}{suffix}' for i in range(8) for suffix,inv in (('',0),('反転',1)) if all(((y>>j)&1)==(((x>>i)&1)^inv) for x,y in pairs)] for j in range(8)}
    return result

def report(root):
    aa=dict(arms()); rows={}; vals={}
    for name in aa:
        p=root/'raw'/name
        if (p/'row.json').exists() and (p/'values.tmp').exists():
            rows[name]=json.loads((p/'row.json').read_text()); vals[name]=json.loads((p/'values.tmp').read_text())
        else: rows[name]={'判定':'欠測（未実行または実行失敗）'}
    groups={}
    for target in ('7071','3e0d'):
        base=rows[f'{target}-base']; bv=vals.get(f'{target}-base')
        for addr in addresses()+[0xe700]:
            names=[f'{target}-{addr:04x}-{v:02x}' for v in VALUES]
            valid=[(aa[n]['value'],vals[n]) for n in names if vals.get(n)]
            o={}
            for p in PORTS:
                size=max((len(v['out'].get(str(p),[])) for x,v in valid),default=0)
                for j in range(size):
                    pairs=[(x,v['out'][str(p)][j]) for x,v in valid if len(v['out'].get(str(p),[]))>j]
                    o[f'{p:02X}:{j+1}']=relation(pairs)
                    baseout = bv['out'].get(str(p),[]) if bv else []
                    o[f'{p:02X}:{j+1}']['基準と異なる']={f'{x:02X}': (y!=baseout[j] if len(baseout)>j else None) for x,y in pairs}
            regs={r:relation([(x,v['regs'][r]) for x,v in valid if v.get('regs')],8 if r in ('A','F') else 16) for r in REGS}
            comparisons={n:{'画面書込が基準と異なる':None if '画面書込' not in rows[n] or '画面書込' not in base else rows[n]['画面書込']!=base['画面書込'],
                '戻りが基準と異なる':None if '戻り' not in rows[n] or '戻り' not in base else rows[n]['戻り']!=base['戻り'],
                '戻りレジスタが基準と異なる':{r:None if not vals.get(n) or not vals[n].get('regs') or not bv or not bv.get('regs') else vals[n]['regs'][r]!=bv['regs'][r] for r in REGS}} for n in names}
            groups[f'{target}-{addr:04x}']={'入力番地':f'{addr:04X}','陰性対照':addr==0xe700,'有効数':len(valid),'OUT関係':o,'戻りレジスタ関係':regs,'基準との差':comparisons}
    (root/'summary.json').write_text(json.dumps({'腕':rows,'組':groups},ensure_ascii=False,indent=2)+'\n')

def main():
    cmd=sys.argv[1]; aa=dict(arms())
    if cmd=='list': print('\n'.join(aa)); return
    root=pathlib.Path(sys.argv[2])
    if cmd=='report': report(root); return
    a=aa[sys.argv[3]]
    if cmd=='generate':
        data,_=generate(a); (root/'probe.bin').write_bytes(data); (root/'probe.d88').write_bytes(prev.base.disk(data))
    elif cmd=='extract':
        row,v=extract(root,a); (root/'row.json').write_text(json.dumps(row,ensure_ascii=False)); (root/'values.tmp').write_text(json.dumps(v))
if __name__=='__main__': main()
