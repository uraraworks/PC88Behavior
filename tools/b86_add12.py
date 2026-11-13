#!/usr/bin/env python3
"""B86 追補12: 生値は一時領域に閉じ、関係のみ集計する。"""
import collections, json, pathlib, sys
import b86_add10 as prev
import b86_add9 as old
from b86_add7 import Code
from b86_add1 import word

VALUES=(0,1,2,0x7f,0xff)
def arms():
    for t in ('7071','11df','3e0d'):
        for field in (('port31',) if t=='7071' else ('A','B','C','HL')):
            for n in range(len(VALUES)):
                yield f'{t}-{field.lower()}-{n}',dict(t=t,field=field,n=n)
def inputs(a):
    r=dict(A=0x35,B=0x12,C=0x34,HL=0xc800,port31=0)
    r[a['field']]= (0xc800+VALUES[a['n']]) if a['field']=='HL' else VALUES[a['n']]
    r.update(F=0,BC=(r['B']<<8)|r['C'],DE=0xc900,IX=0x1357,IY=0x2468,SP=0xd000,IFF=0)
    return r

def generate(a):
    r=inputs(a); c=Code(); c.emit('f3 31 00 d0'); c.label('bootmem'); c.emit('32 f2 cf'); c.label('boot'); c.emit('d3 7e')
    # 自作RAM受け口。到達したら印を出し、戻り先を消費して復帰する。
    for i,v in enumerate((0xd3,0x7b,0xc9)):
        c.emit('3e %02x 32'%v); c.b+=word(0xc800+i)
    c.emit('31 00 d0'); c.addr(0x21,'end'); c.emit('e5')
    if a['t']=='7071': c.emit('3e %02x d3 31'%r['port31'])
    c.emit('21'); c.b+=word((r['A']<<8)|r['F']); c.emit('e5 f1')
    for op,k in ((1,'BC'),(0x11,'DE'),(0x21,'HL')): c.b.append(op); c.b+=word(r[k])
    for pre,k in ((0xdd,'IX'),(0xfd,'IY')): c.b.extend((pre,0x21)); c.b+=word(r[k])
    c.label('startmem'); c.emit('32 f0 cf'); c.label('start'); c.emit('d3 7f c3'); c.b+=word(int(a['t'],16))
    c.label('end'); c.emit('d3 7d'); c.label('endmem'); c.emit('32 f1 cf f5 c5 d5 e5 dd e5 fd e5 ed 57 f5 f3')
    c.emit('e1 7d'); c.label('snap0'); c.emit('d3 7c')
    for i in range(6):
        c.emit('e1 7d'); c.label(f'snap{2*i+1}'); c.emit('d3 7c 7c'); c.label(f'snap{2*i+2}'); c.emit('d3 7c')
    c.emit('21 00 00 39 7d'); c.label('snap13'); c.emit('d3 7c 7c'); c.label('snap14'); c.emit('d3 7c')
    c.label('captured'); c.emit('d3 7f f3 76 18 fd')
    return c.finish(),c.labels

def extract(path,a):
    # 追補10の区間・再起動・欠測・RAM判定を共用する。
    original=prev.generate; prev.generate=generate
    try: row,v=prev.extract(path,dict(a,irq='di',mode='jp0'))
    finally: prev.generate=original
    if v is None: return row,v
    ev=prev.base.events(path/'io'); m=generate(a)[1]
    start=next(i for i,e in enumerate(ev) if e[0]=='OUT' and e[1]==0x7f and e[3]==m['start'])
    stop=next((i for i,e in enumerate(ev[start+1:],start+1) if e[0]=='OUT' and ((e[1]==0x7d and e[3]==m['end']) or (e[1]==0x7e and e[3]==m['boot']))),len(ev))
    segment=ev[start+1:stop]
    row['自作RAM印到達']=any(d=='OUT' and p==0x7b and pc==0xc800 for d,p,x,pc in segment)
    if row['自作RAM印到達']:
        count=sum(d=='OUT' and p==0x7b and pc==0xc800 for d,p,x,pc in segment)
        for item in row['I/O']:
            if item['方向']=='OUT' and item['ポート']=='7B': item['件数']-=count
        row['I/O']=[item for item in row['I/O'] if item['件数']]
        marker_values=[x for d,p,x,pc in segment if d=='OUT' and p==0x7b and pc==0xc800]
        for x in marker_values: v['out'].get(str(0x7b),[]).remove(x)
        if not v['out'].get(str(0x7b)): v['out'].pop(str(0x7b),None)
    row.pop('自作HL受け口到達',None)
    row['11DF進入回数']='未計測（内部移動を数える機能なし）'
    row['制御移動先']='自作RAM印' if row['自作RAM印到達'] else '未確定'
    v['in71']=[x for d,p,x,pc in segment if d=='IN' and p==0x71]
    return row,v

def report(root):
    aa=dict(arms()); rows={}; values={}
    for name in aa:
        p=root/'raw'/name
        if (p/'row.json').exists() and (p/'values.tmp').exists():
            rows[name]=json.loads((p/'row.json').read_text()); values[name]=json.loads((p/'values.tmp').read_text())
        else: rows[name]={'判定':'欠測（未実行または実行失敗）'}
    groups={}
    for t in ('7071','11df','3e0d'):
        for field in (('port31',) if t=='7071' else ('A','B','C','HL')):
            names=[f'{t}-{field.lower()}-{n}' for n in range(len(VALUES))]
            valid=[(inputs(aa[x]),values[x]) for x in names if values.get(x)]
            result={'有効数':len(valid),'OUT関係':{},'戻りレジスタ関係':{}}
            ports=sorted({p for r,v in valid for p in v['out']},key=int)
            for p in ports:
                for j in range(max(len(v['out'].get(p,[])) for r,v in valid)):
                    pairs=[(r,v,v['out'][p][j]) for r,v in valid if len(v['out'].get(p,[]))>j]
                    def rel(xs):
                        if len(xs)<2: return {'判定':'未判定'}
                        if len({y for x,y in xs})==1: return {'判定':'定数（値はリポジトリ外）'}
                        return {'判定':'比較','入力と一致':all(x==y for x,y in xs),'入力と反転一致':all((x^255)==y for x,y in xs),'入力変化あり':len({x for x,y in xs})>1}
                    refs={k:rel([(r[k],y) for r,v,y in pairs]) for k in ('A','B','C','HL','port31')}
                    refs['IN71直前候補']=rel([(v['in71'][-1],y) for r,v,y in pairs if v['in71']])
                    result['OUT関係'][f'{int(p):02X}:{j+1}']=refs
            for reg in old.REGS:
                pairs=[(r[reg],v['regs'][reg]) for r,v in valid if 'regs' in v]
                result['戻りレジスタ関係'][reg]=old.relations(pairs,8 if reg in ('A','F') else 1 if reg=='IFF' else 16)
            groups[f'{t}-{field.lower()}']=result
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
