#!/usr/bin/env python3
"""B86 追補7: 自作プローブと値を出さない集計。"""
import collections
import json
import pathlib
import sys
import b86_add3 as base
from b86_add1 import word

DUMMY = [0x1357, 0x2468, 0x5a3c, 0x6b4d, 0x7c5e, 0x1d6f]

def arms():
    for target in ('control', 'positive'):
        for mode in ('di', 'ei', 'irq'):
            for n in range(7):
                yield f'{target}-{mode}-{n}', dict(kind='stack', target=target, mode=mode, n=n)
    variants=[('base',1,0,0)]+[(f'{key}{v:02x}', *( (v,0,0) if key=='req' else (1,v,0) if key=='arg1' else (1,0,v))) for key in ('req','arg1','arg2') for v in (0,1,2,255) if not (key=='req' and v==1) and not (key!='req' and v==0)]
    for variant,req,arg1,arg2 in variants:
        for mode in ('same','changed','no369a'):
            for ending in ('ret','wait'):
                yield f'3391-{variant}-{mode}-{ending}', dict(kind='3391', req=req,arg1=arg1,arg2=arg2,mode=mode,ending=ending)
    for target in ('3080','39ce','3ded','11df'):
        for mode in ('di','ei','irq'):
            for n in range(7):
                yield f'{target}-{mode}-{n}', dict(kind='stack', target=target,mode=mode,n=n)

class Code:
    def __init__(self): self.b=bytearray(); self.labels={}; self.fix=[]
    def emit(self, h): self.b.extend(bytes.fromhex(h))
    def label(self,n): self.labels[n]=0xc000+len(self.b)
    def addr(self,op,n): self.b.append(op); self.fix.append((len(self.b),n)); self.b+=b'\0\0'
    def finish(self):
        for i,n in self.fix: self.b[i:i+2]=word(self.labels[n])
        if len(self.b)>256: raise ValueError(f'器具領域超過 {len(self.b)}')
        return bytes(self.b)+bytes(256-len(self.b))

def generate(a):
    c=Code(); c.emit('f3 31 00 f0'); c.label('boot'); c.emit('d3 7e')
    if a['kind']=='3391':
        if a['mode']!='no369a':
            for i,(target,v) in enumerate(((0x37c9,a['req']),(0x37d2,a['arg1']),(0x37d2,a['arg2']))):
                c.emit('3e %02x'%v); c.label('pre%d'%i); c.emit('d3 7f cd'); c.b+=word(target); c.label('post%d'%i); c.emit('d3 7f')
            c.emit('01 02 00 21 00 c8 b7'); c.label('pre3'); c.emit('d3 7f cd 9a 36'); c.label('post3'); c.emit('d3 7f')
        # 転送が自作コードを上書きし得るため、369A の後で配置する。
        for addr in (0xc800,0xc900):
            payload=bytes.fromhex('d3 7b c9' if a['ending']=='ret' else 'd3 7b 18 fe')
            for i,v in enumerate(payload): c.emit('3e %02x 32'%v); c.b+=word(addr+i)
        if a['mode']!='same':
            c.emit('21'); c.b+=word(0xc900 if a['mode']=='changed' else 0xc800)
        c.label('start'); c.emit('d3 7f cd 91 33'); c.label('end'); c.emit('d3 7f f3 76 18 fd')
    else:
        # IM2 の全ベクタを C2C2 に揃え、受け口を自作 RAM にコピー。
        c.emit('21 00 c4 36 c2 11 01 c4 01 00 01 ed b0 3e c4 ed 47 ed 5e')
        c.addr(0x21,'handler'); c.emit('11 c2 c2 01'); c.b+=word(0) # 長さは後で確定
        lengthpos=len(c.b)-2; c.emit('ed b0 3e 02 d3 e6 d3 e4')
        if a['mode']=='irq':
            c.label('start'); c.emit('d3 7f fb 76 18 fd')
        else:
            c.emit('fb 76' if a['mode']=='ei' else 'f3')
            c.label('start'); c.emit('d3 7f'); c.addr(0xc3,'launch')
        c.label('handler')
        if a['mode']=='irq':
            c.emit('d3 7a f3'); c.addr(0xc3,'launch')
        else:
            c.emit('f5 3e 02 d3 e4 d3 7a f1 fb ed 4d')
        c.b[lengthpos:lengthpos+2]=word(len(c.b)-(c.labels['handler']-0xc000))
        c.label('launch')
        # 割り込み内の CPU 戻り先より上に自作戻り先とダミーを積む。
        c.addr(0x21,'end'); c.emit('e5')
        for v in DUMMY[:a['n']]: c.emit('21'); c.b+=word(v); c.emit('e5')
        c.emit('01 11 11 11 22 22 21 33 33 dd 21 44 44 fd 21 55 55')
        target={'control': 'control', 'positive':'positive'}.get(a['target'])
        if target: c.addr(0xc3,target)
        else: c.emit('c3'); c.b+=word(int(a['target'],16))
        c.label('control'); c.emit('c9')
        # ダミーを6語消費して戻る陽性対照。
        c.label('positive'); c.emit('f1 c1 d1 e1 dd e1 fd e1 c9')
        c.label('end'); c.emit('f5 c5 d5 e5 dd e5 fd e5 ed 57 f5 f3')
        # 先頭は LD A,I の flags、その後 IY IX HL DE BC AF。
        c.emit('e1 7d'); c.label('snap0'); c.emit('d3 7c')
        for i in range(6):
            c.emit('e1 7d'); c.label(f'snap{2*i+1}'); c.emit('d3 7c 7c'); c.label(f'snap{2*i+2}'); c.emit('d3 7c')
        c.label('captured'); c.emit('d3 7f f3 76 18 fd')
    return c.finish(), c.labels

def summarize(path,a,m):
    ev=base.events(path/'io')
    if ev is None: return {'判定':'欠測（ログ取りこぼし）'}
    def matches(e,port,pc): return e[0]=='OUT' and e[1]==port and e[3]==pc
    starts=[i for i,e in enumerate(ev) if matches(e,0x7e,m['boot'])]
    if not starts: return {'判定':'欠測（開始印なし）'}
    limit=starts[1] if len(starts)>1 else len(ev)
    seg=ev[starts[0]+1:limit]; begins=[i for i,e in enumerate(seg) if matches(e,0x7f,m['start'])]
    result={'判定':'取得','再起動':limit<len(ev)}
    if not begins: result.update({'判定':'欠測（入口未到達）'}); return result
    seg=seg[begins[0]+1:]; result['I/O']=[{'方向':d,'ポート':f'{p:02X}','件数':n} for (d,p),n in sorted(collections.Counter((e[0],e[1]) for e in seg if e[1] not in (0x7a,0x7b,0x7c,0x7f)).items())]
    if a['kind']=='3391':
        seen=[f'{addr:04X}' for addr in (0xc800,0xc900) if any(matches(e,0x7b,addr) for e in seg)]
        result['自作コード到達']=seen
        result['戻り']='確認' if any(matches(e,0x7f,m['end']) for e in seg) else '戻らない（再起動）' if limit<len(ev) else '時間上限内未確認'
        result['前置き']=[{'開始':any(matches(e,0x7f,m[f'pre{i}']) for e in ev[starts[0]+1:limit]),'戻り':any(matches(e,0x7f,m[f'post{i}']) for e in ev[starts[0]+1:limit])} for i in range(4) if f'pre{i}' in m]
    else:
        # 受け口の実行番地は RAM にコピーされたアドレス。
        handlerpc=0xc2c2+(0 if a['mode']=='irq' else 5)
        result['受け口回数']=sum(matches(e,0x7a,handlerpc) for e in ev[starts[0]+1:limit])
        captures=[e for e in seg if e[0]=='OUT' and e[1]==0x7c and e[3] in {m[f'snap{i}'] for i in range(13)}]
        snap=[e[2] for e in captures]
        returned=([e[3] for e in captures]==[m[f'snap{i}'] for i in range(13)] and any(matches(e,0x7f,m['captured']) for e in seg))
        result['戻り']='確認' if returned else '戻らない（再起動）' if limit<len(ev) else '時間上限内未確認'
        result['EI状態']=(bool(snap[0]&4) if returned else None)
        if returned:
            values=[snap[i]+256*snap[i+1] for i in range(1,13,2)]
            result['ダミーとの一致']={reg:[v==x for x in DUMMY[:a['n']]] for reg,v in zip(('IY','IX','HL','DE','BC','AF'),values)}
        else: result['ダミーとの一致']=None
    return result

def main():
    cmd=sys.argv[1]
    if cmd=='list': print('\n'.join(dict(arms()))); return
    path=pathlib.Path(sys.argv[2]); a=dict(arms())[sys.argv[3]]; data,marks=generate(a)
    if cmd=='generate': (path/'probe.bin').write_bytes(data); (path/'probe.d88').write_bytes(base.disk(data))
    elif cmd=='summarize': pathlib.Path(sys.argv[4]).write_text(json.dumps(summarize(path,a,marks),ensure_ascii=False,indent=2)+'\n')
    else: raise ValueError(cmd)
if __name__=='__main__': main()
