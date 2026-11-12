#!/usr/bin/env python3
"""追補11: 自作送信器と値を出さない集計。"""
import json, pathlib, re, sys
import b86_add3 as base
from b86_add7 import Code
from b86_add1 import word

# 0D で起動後、09 と4引数を自作受信してから遅延し1バイト送る。
def payload(delay, pattern):
    # RECV x5: 対称 PIO、受信値は捨てる。DJNZ は受信ルーチン外。
    p=bytearray.fromhex('06 05 cd 2b 60 10 fb 01')+word(delay)
    p+=bytes.fromhex('0b 78 b1 20 fb db fe e6 02 28 fa 3e')+bytes([pattern])
    p+=bytes.fromhex('d3 fd 3e 09 d3 ff db fe e6 04 28 fa 3e 08 d3 ff c3 c1 00')
    assert len(p)<=0x2b
    p+=bytes(0x2b-len(p))
    p+=bytes.fromhex('3e 0b d3 ff db fe e6 01 28 fa 3e 0a d3 ff db fc 3e 0d d3 ff db fe e6 01 20 fa 3e 0c d3 ff c9')
    return bytes(p)

def arms():
    for irq in ('di','ei'):
        for delay in ('short','long'):
            for pattern in ('a','b'):
                yield f'{irq}-{delay}-{pattern}',dict(irq=irq,delay=delay,pattern=pattern)

def generate(a):
    sub=payload(0x0800 if a['delay']=='short' else 0xffff, 0x35 if a['pattern']=='a' else 0xca)
    c=Code(); c.emit('f3 31 00 d0'); c.label('boot'); c.emit('d3 7e')
    c.emit('21 00 c4 36 c2 11 01 c4 01 00 01 ed b0 3e c4 ed 47 ed 5e')
    # AF と HL を保存し、割り込みが積んだ戻り PC の上位だけを ROM 域かに縮約。
    handler=bytes.fromhex('f5 e5 21 04 00 39 23 7e fe 80 3e 00 30 01 3c d3 7a 3e 02 d3 e4 e1 f1 fb ed 4d')
    c.addr(0x21,'handler'); c.emit('11 c2 c2 01'); c.b+=word(len(handler)); c.emit('ed b0')
    def send(addr,v): c.emit('3e %02x cd'%v); c.b.extend(word(addr))
    send(0x37c9,0x0c)
    for v in (0x60,0,len(sub)>>8,len(sub)&255): send(0x37d2,v)
    c.addr(0x21,'sub'); c.emit('06 %02x'%len(sub)); c.label('load'); c.emit('7e e5 c5 cd d2 37 c1 e1 23 10 f4')
    send(0x37c9,0x0d)
    for v in (0x60,0): send(0x37d2,v)
    send(0x37c9,0x09)
    for v in (0x60,0,0x60,1): send(0x37d2,v)
    c.emit('3e 02 d3 e6 d3 e4')
    c.emit('fb' if a['irq']=='ei' else 'f3'); c.label('start'); c.emit('d3 7f cd 47 38')
    c.label('returned'); c.emit('f5 ed 57 f5 f3 e1 7d'); c.label('iff'); c.emit('d3 7c f1'); c.label('value'); c.emit('d3 7d f3 76 18 fd')
    c.label('handler'); c.b+=handler
    c.label('sub'); c.b+=sub
    return c.finish(),c.labels

def extract(path,a):
    m=generate(a)[1]; ev=base.events(path/'io')
    if ev is None: return {'判定':'欠測（ログ不足）'}
    def mark(e,p,pc): return e[0]=='OUT' and e[1]==p and e[3]==pc
    boots=[i for i,e in enumerate(ev) if mark(e,0x7e,m['boot'])]
    if not boots: return {'判定':'欠測（開始印なし）'}
    limit=boots[1] if len(boots)>1 else len(ev)
    start=next((i for i in range(boots[0]+1,limit) if mark(ev[i],0x7f,m['start'])),None)
    if start is None: return {'判定':'欠測（前置き未完了）'}
    stop=next((i for i in range(start+1,limit) if mark(ev[i],0x7d,m['value'])),None)
    seg=ev[start+1:stop if stop is not None else limit]
    sent=[e[2] for e in ev[boots[0]+1:start] if e[:2]==('OUT',0xfd)]
    receive=next((i for i,e in enumerate(seg) if e[:2]==('IN',0xfc)),None)
    irq=[(i,e) for i,e in enumerate(seg) if mark(e,0x7a,0xc2c2+15)]
    iff=[e for e in seg if mark(e,0x7c,m['iff'])]
    return {'判定':'取得','戻り':stop is not None,'再起動':limit<len(ev),
            '受信前の受け口回数':sum(receive is None or i<receive for i,e in irq),
            '受信前のPCがROM内': [bool(e[2]) for i,e in irq if receive is None or i<receive],
            '戻り時IFF':bool(iff[0][2]&4) if stop is not None and len(iff)==1 else None,
            '模様と一致':ev[stop][2]==(0x35 if a['pattern']=='a' else 0xca) if stop is not None else None,
            '受信確認':receive is not None,
            '09前置き送信一致':sent[-5:]==[9,0x60,0,0x60,1],
            '受信前の状態読取回数':sum(e[:2]==('IN',0xfe) for e in seg[:receive] if receive is not None) if receive is not None else sum(e[:2]==('IN',0xfe) for e in seg)}

def main():
    cmd=sys.argv[1]; aa=dict(arms())
    if cmd=='list': print('\n'.join(aa)); return
    root=pathlib.Path(sys.argv[2])
    if cmd=='report':
        rows={n:json.loads((root/'raw'/n/'row.json').read_text()) if (root/'raw'/n/'row.json').exists() else {'判定':'欠測（実行失敗または未実行）'} for n in aa}
        (root/'summary.json').write_text(json.dumps({'腕':rows},ensure_ascii=False,indent=2)+'\n'); return
    a=aa[sys.argv[3]]
    if cmd=='generate':
        data,_=generate(a); (root/'probe.bin').write_bytes(data); (root/'probe.d88').write_bytes(base.disk(data))
    elif cmd=='extract': (root/'row.json').write_text(json.dumps(extract(root,a),ensure_ascii=False)+'\n')
    else: raise ValueError(cmd)
if __name__=='__main__': main()
