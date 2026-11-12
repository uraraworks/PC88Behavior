#!/usr/bin/env python3
"""B86 追補6: 3391 前置きのプローブと見出し集計。"""
import collections
import json
import pathlib
import sys
import b86_add3 as base
from b86_add1 import word


def arms3391():
    baseline = dict(req=1, arg1=0, arg2=0, b=0, c=2, hl=0xd000, carry=0)
    yield '3391-base', baseline.copy()
    for key, values in (('req',(0,2,255)), ('arg1',(1,2,255)), ('arg2',(1,2,255)),
                        ('b',(1,2)), ('c',(1,3)), ('hl',(0xd400,0xe000)), ('carry',(1,))):
        for v in values:
            a=baseline.copy(); a[key]=v
            yield f'3391-{key}-{v:04x}', a


def generate3391(a):
    code=bytearray.fromhex('f3 31 00 f0 01 01 00 11 00 00 21 00 00 dd 21 00 00 fd 21 00 00 d3 7e')
    # 転送先を自作の再現可能な模様に初期化する。
    code.extend(bytes.fromhex('21 00 d0 01 00 18 af 77 23 3c 0b 57 78 b1 7a 20 f6'))
    marks=[]
    def call(target):
        marks.append(0xc000+len(code)); code.extend(b'\xd3\x7f\xcd'+word(target))
        marks.append(0xc000+len(code)); code.extend(b'\xd3\x7f')
    code.extend(b'\x3e'+bytes([a['req']])); call(0x37c9)
    for v in (a['arg1'],a['arg2']):
        code.extend(b'\x3e'+bytes([v])); call(0x37d2)
    code.extend(b'\x01'+word(a['b']*256+a['c'])+b'\x21'+word(a['hl']))
    code.extend(b'\x37' if a['carry'] else b'\xb7'); call(0x369a)
    call(0x3391)
    code.extend(bytes.fromhex('f3 76 18 fd'))
    if len(code)>256: raise ValueError('器具領域超過')
    return bytes(code)+bytes(256-len(code)), marks


def summarize3391(path, a, marks):
    ev=base.events(path/'io')
    if ev is None: return {'判定':'欠測（ログ取りこぼし）'}
    starts=[i for i,e in enumerate(ev) if e[:2]==('OUT',0x7e) and e[3]==0xc015]
    if not starts: return {'判定':'欠測（開始印なし）'}
    limit=starts[1] if len(starts)>1 else len(ev)
    relevant=[(i,e) for i,e in enumerate(ev[starts[0]+1:limit],starts[0]+1)
              if e[:2]==('OUT',0x7f) and e[3] in marks]
    rows=[]; k=0
    for n,name in enumerate(('37c9','37d2','37d2','369a','3391')):
        if k==len(relevant): break
        i,e=relevant[k]
        if e[3]!=marks[2*n]: return {'判定':'欠測（印の順序異常）'}
        k+=1
        returned=k<len(relevant) and relevant[k][1][3]==marks[2*n+1]
        if k<len(relevant) and not returned: return {'判定':'欠測（印の順序異常）'}
        stop=relevant[k][0] if returned else limit
        segment=ev[i+1:stop]
        counts=collections.Counter((x[0],x[1]) for x in segment)
        row={'入口':name,'戻り':'確認' if returned else '戻らない（再起動）' if limit<len(ev) else '時間上限内未確認',
             'I/O':[{'方向':d,'ポート':f'{p:02X}','件数':v} for (d,p),v in sorted(counts.items())]}
        if name=='3391':
            req=[]; current=[]
            for x in segment:
                if x[:2]==('OUT',0xfd): current.append(x[2])
                elif x[:2]==('IN',0xfc) and current:
                    req.append({'先頭':f'{current[0]:02X}','長さ':len(current),'完結':True}); current=[]
            if current: req.append({'先頭':f'{current[0]:02X}','長さ':len(current),'完結':False})
            row['要求見出し']=req
            row['RAM移動']='欠測（観測器未実装）'
        rows.append(row)
        if not returned: break
        k+=1
    if k<len(relevant): return {'判定':'欠測（印の順序異常）'}
    return {'判定':'取得','再起動':limit<len(ev),'区間':rows}


def arms():
    yield from arms3391()
    for target in ('3080','11df','3ded','39ce','6f6b','control','positive'):
        modes = ('push','empty') if target not in ('6f6b','control','positive') else ('call',)
        for mode in modes:
            for interrupt in ('di','ei'):
                for reg in ('base','a','hl','de','bc'):
                    yield f'{target}-{mode}-{interrupt}-{reg}', dict(target=target, mode=mode, interrupt=interrupt, reg=reg)


def generate(a):
    if 'req' in a: return generate3391(a)
    target={'control':0xc0f0,'positive':0xc0e0}.get(a['target'])
    if target is None: target=int(a['target'],16)
    vals=dict(a=0x10,bc=0x1234,de=0x5678,hl=0xd100)
    if a['reg']!='base': vals[a['reg']] ^= 1
    c=bytearray.fromhex('f3 31 00 f0 01 01 00 11 00 00 21 00 00 dd 21 00 00 fd 21 00 00 d3 7e')
    # 前後比較領域 C100-EFFF。器具は C000-C0FF、スタックは F000。
    c+=bytes.fromhex('21 00 c1 01 00 2f cd a0 c0')
    if a['mode']!='call':
        dest=0xc0d0 if a['mode']=='push' else 0xc0d8
        c+=b'\x21'+word(dest)+bytes.fromhex('22 00 f0')
    c+=b'\x21'+word(vals['a']<<8)+bytes.fromhex('e5 f1')
    c+=b'\x01'+word(vals['bc'])+b'\x11'+word(vals['de'])+b'\x21'+word(vals['hl'])
    c+=b'\xfb' if a['interrupt']=='ei' else b'\xf3'
    start=0xc000+len(c); c+=b'\xd3\x7f'
    if a['mode']=='call':
        c+=b'\xcd'+word(target); end=0xc000+len(c); c+=b'\xd3\x7f\xc3\x80\xc0'
    else:
        c+=b'\xc3'+word(target); end=0xc0d0 if a['mode']=='push' else 0xc0d8
    if len(c)>0x80: raise ValueError('器具領域超過')
    sector=c+bytes(256-len(c))
    # 戻り直後の AF, BC, DE, HL と SP をポートへ保存。
    capture=bytes.fromhex('f5 c5 d5 e5 21 00 00 39 7d d3 7c 7c d3 7c e1 7d d3 7c 7c d3 7c e1 7d d3 7c 7c d3 7c e1 7d d3 7c 7c d3 7c e1 7d d3 7c 7c d3 7c 21 00 c1 01 00 2f cd a0 c0 f3 76 18 fd')
    # capture は C080 から、ダンプは C0B8 に配置。
    capture=capture.replace(bytes.fromhex('cd a0 c0'),bytes.fromhex('cd b8 c0'))
    sector[0x80:0x80+len(capture)]=capture
    sector[0xa0:0xa0+10]=bytes.fromhex('7e d3 7d 23 0b 78 b1 20 f7 c9') if 0xa0>=0x80+len(capture) else sector[0xa0:0xa0+10]
    # 共通ダンプを C0B8 とし、前置きも同じ場所を呼ぶ。
    sector[0x15:0x80]=sector[0x15:0x80].replace(bytes.fromhex('cd a0 c0'),bytes.fromhex('cd b8 c0'))
    sector[0xb8:0xc2]=bytes.fromhex('7e d3 7d 23 0b 78 b1 20 f7 c9')
    sector[0xd0:0xd5]=bytes.fromhex('d3 7f c3 80 c0')
    sector[0xd8:0xdd]=bytes.fromhex('d3 7f c3 80 c0')
    sector[0xe0:0xe9]=bytes.fromhex('3e 5a 32 00 d0 d3 fd 37 c9')
    sector[0xf0]=0xc9
    return bytes(sector), [start,end]


def summarize(path,a,marks):
    if 'req' in a: return summarize3391(path,a,marks)
    ev=base.events(path/'io')
    if ev is None: return {'判定':'欠測（ログ取りこぼし）'}
    starts=[i for i,e in enumerate(ev) if e[:2]==('OUT',0x7e) and e[3]==0xc015]
    if not starts: return {'判定':'欠測（開始印なし）'}
    limit=starts[1] if len(starts)>1 else len(ev)
    relevant=[(i,e) for i,e in enumerate(ev[starts[0]+1:limit],starts[0]+1) if e[:2]==('OUT',0x7f) and e[3] in marks]
    if not relevant: return {'判定':'欠測（区間開始印なし）'}
    if relevant[0][1][3]!=marks[0] or len(relevant)>2 or (len(relevant)==2 and relevant[1][1][3]!=marks[1]): return {'判定':'欠測（印の順序異常）'}
    returned=len(relevant)==2; lo=relevant[0][0]; hi=relevant[1][0] if returned else limit
    counts=collections.Counter((e[0],e[1]) for e in ev[lo+1:hi])
    result={'判定':'取得','戻り':'確認' if returned else '戻らない（再起動）' if limit<len(ev) else '時間上限内未確認', '再起動':limit<len(ev), 'スタック先頭到達':returned if a['mode']!='call' else '対象外', '割り込み受理':'欠測（観測器未実装）', 'I/O':[{'方向':d,'ポート':f'{p:02X}','件数':n} for (d,p),n in sorted(counts.items())]}
    before=[e[2] for e in ev[starts[0]+1:lo] if e[:2]==('OUT',0x7d) and e[3]==0xc0b9]
    after=[e[2] for e in ev[hi+1:limit] if e[:2]==('OUT',0x7d) and e[3]==0xc0b9] if returned else []
    ok=len(before)==len(after)==0x2f00
    from b86_add1 import ranges
    result['RAM']={'比較範囲':'C100-EFF7','器具の書き込み':'C000-C0FF、EFF8-FFFF','判定':'取得' if ok else '欠測','変化番地範囲':ranges([0xc100+i for i,(x,y) in enumerate(zip(before[:0x2ef8],after[:0x2ef8])) if x!=y]) if ok else None}
    snap=[e[2] for e in ev[hi+1:limit] if e[:2]==('OUT',0x7c)] if returned else []
    if len(snap)==10:
        vals=dict(a=0x10,bc=0x1234,de=0x5678,hl=0xd100)
        if a['reg']!='base': vals[a['reg']]^=1
        pairs=[snap[i]+256*snap[i+1] for i in range(0,10,2)]
        result['レジスタ']={'SP差':(pairs[0]+8-0xf000)&0xffff,'HL一致':pairs[1]==vals['hl'],'DE一致':pairs[2]==vals['de'],'BC一致':pairs[3]==vals['bc'],'A一致':pairs[4]>>8==vals['a'],'フラグ一致':pairs[4]&255==0}
    else: result['レジスタ']='欠測'
    return result

def main():
    cmd=sys.argv[1]
    if cmd=='list': print('\n'.join(name for name,_ in arms())); return
    path=pathlib.Path(sys.argv[2]); a=dict(arms())[sys.argv[3]]; sector,marks=generate(a)
    if cmd=='generate':
        (path/'probe.bin').write_bytes(sector); (path/'probe.d88').write_bytes(base.disk(sector))
    elif cmd=='summarize':
        pathlib.Path(sys.argv[4]).write_text(json.dumps(summarize(path,a,marks),ensure_ascii=False,indent=2)+'\n')
    else: raise ValueError('不明な操作')

if __name__=='__main__': main()
