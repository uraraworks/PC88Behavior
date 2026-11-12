#!/usr/bin/env python3
"""B86 追補4: 自作セクタ、呼び出し区間、値なし集計。"""
import json
import pathlib
import sys
import b86_add3 as old
from b86_add1 import word, TARGETS
from make_l3_testdisk import coord_header_pattern

VARIANTS = ((0, 0, 0xd000, 0xd400), (1, 1, 0xd000, 0xd400),
            (2, 0, 0xd400, 0xd000), (255, 255, 0, 0))
def arms():
    for n in (1, 2, 8, 165):
        for m in (1, 2, 256, 257):
            for v in range(len(VARIANTS)):
                yield f'n{n}-m{m}-v{v}', n, m, v, '3847'
    for t in ('control', 'positive'):
        yield t, 2, 2, 0, t

def generate(arm):
    _, n, m, v, target = arm
    a, da, hl, de = VARIANTS[v]
    code = bytearray.fromhex('f3 31 00 f0 21 00 d0 01 00 08 af 77 23 3c 0b 57 78 b1 7a 20 f6')
    code += bytes.fromhex('dd 21 00 00 fd 21 00 00')
    code += b'\x01\x01\x00\x11' + word(de) + b'\x21' + word(hl) + b'\x3e' + bytes([a])
    pcs = []
    def call(t):
        pcs.append(0xc000+len(code)); code.extend(b'\xd3\x7f\xcd'+word(TARGETS[t]))
        pcs.append(0xc000+len(code)); code.extend(b'\xd3\x7f')
    call('37c9' if target == '3847' else target)
    def loop(count, t, reset):
        # 器具専用カウンタ。AF・HL を保存し、呼び先の戻り状態を維持する。
        code.extend(b'\xf5\xe5\x21'+word(count)+b'\x22\x00\xc1\xe1\xf1')
        start=len(code)
        if reset:
            code.extend(b'\x3e'+bytes([da])+b'\x21'+word(hl)+b'\x11'+word(de))
        call(t)
        code.extend(bytes.fromhex('f5 e5 2a 00 c1 2b 22 00 c1 7c b5 e1 f1'))
        # POP AF が Z を復元するので条件分岐は POP AF の前に置く。
        del code[-2:]
        code.extend(b'\xe1\x28\x04\xf1\xc3'+word(0xc000+start)+b'\xf1')
    loop(n, '37d2' if target == '3847' else target, True)
    loop(m, target, False)
    code.extend(bytes.fromhex('f3 76 18 fd'))
    if len(code)>0xe0: raise ValueError('器具領域重複')
    sector=code+bytes(256-len(code))
    sector[0xe0:0xe9]=bytes.fromhex('3e 5a 32 00 d0 d3 fd 37 c9')
    sector[0xf0]=0xc9
    return bytes(sector), pcs

def summarize(path, arm, pcs):
    ev=old.events(path/'io')
    if ev is None: return {'判定':'欠測（ログ取りこぼし）'}
    marks=[(i,pcs.index(e[3]),e[2]) for i,e in enumerate(ev)
           if e[0]=='OUT' and e[1]==0x7f and e[3] in pcs]
    expected=[0,1]+[x for _ in range(arm[1]) for x in (2,3)]+[x for _ in range(arm[2]) for x in (4,5)]
    # 再起動や順序不正は全体を欠測にする。
    observed=[x[1] for x in marks]
    if observed != expected[:len(observed)]: return {'判定':'欠測（印の順序異常）'}
    patterns={(c,h,s): (path/'probe.bin').read_bytes() if (c,h,s)==(0,0,1) else coord_header_pattern(0xa1,c,h,s)
              for c in range(40) for h in range(2) for s in range(1,17)}
    rows=[]
    offset=2+2*arm[1]
    for j in range(arm[2]):
        k=offset+2*j
        if k>=len(marks):
            rows.append({'回':j+1,'開始':'欠測','戻り':'欠測'}); continue
        start=marks[k][0]; end=marks[k+1][0] if k+1<len(marks) else len(ev)
        seg=ev[start+1:end]
        recv=bytes(e[2] for e in seg if e[:2]==('IN',0xfc))
        row={'回':j+1,'開始':'確認','戻り':'確認' if k+1<len(marks) else '時間上限内未確認',
             '送信件数':sum(e[:2]==('OUT',0xfd) for e in seg), '受信件数':len(recv)}
        if k+1<len(marks):
            value=marks[k+1][2]
            row['戻りAと一致する受信済み自作媒体の位置']=[{'座標':list(coord),'位置':[i for i,b in enumerate(data) if b==value]}
                for coord,data in patterns.items() if data in recv and value in data]
        rows.append(row)
    return {'判定':'取得','前置き完了':'確認' if len(marks)>=offset else '未確認', '区間':rows}

def main():
    cmd=sys.argv[1]
    if cmd=='list': print('\n'.join(a[0] for a in arms())); return
    path=pathlib.Path(sys.argv[2]); arm=next(a for a in arms() if a[0]==sys.argv[3]); sector,pcs=generate(arm)
    if cmd=='generate':
        (path/'probe.bin').write_bytes(sector); (path/'probe.d88').write_bytes(old.disk(sector))
    elif cmd=='summarize': pathlib.Path(sys.argv[4]).write_text(json.dumps(summarize(path,arm,pcs),ensure_ascii=False,indent=2)+'\n')
    else: raise ValueError('不明な操作')
if __name__=='__main__': main()
