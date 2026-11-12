#!/usr/bin/env python3
"""B86 追補5: 自作プローブと値なし集計。"""
import json
import pathlib
import sys
import b86_add3 as old
from b86_add1 import word, TARGETS
from make_l3_testdisk import coord_header_pattern

PATTERN = bytes((i * 73 + 41) & 255 for i in range(256))

def arms():
    for reg in ('a','c','e','l'):
        for n in (1,16,256):
            yield (f'ram-{reg}-{n}', 'ram', reg, n)
    for kind in ('disk','disk-no15'):
        yield (kind,kind,'a',256)
    for kind in ('control','positive'):
        yield (kind,kind,'a',16)

def generate(arm):
    name,kind,reg,n=arm
    code=bytearray(); labels={}; fix=[]; markers={}
    def emit(b): code.extend(b)
    def label(s): labels[s]=0xc000+len(code)
    def call(s): emit(b'\xcd\0\0'); fix.append((len(code)-2,s))
    def jump(s): emit(b'\xc3\0\0'); fix.append((len(code)-2,s))
    def mark(s): markers[s]=0xc000+len(code); emit(b'\xd3\x7f')
    emit(bytes.fromhex('f3 31 00 f0 01 01 00 11 00 00 21 00 00 dd 21 00 00 fd 21 00 00 d3 7e'))
    # テーブルは要求番号・引数を交互に解釈せず、明示的な短い列として送る。
    def request(v): emit(b'\x3e'+bytes([v])); call('request')
    def args(values, sender="send"):
        for v in values: emit(b'\x3e'+bytes([v])); call(sender)
    if kind in ('ram','control','positive'):
        request(0x0c); args([0x60,0,1,0], "setup")
        emit(bytes.fromhex('af 32 04 c1'))
        label('body'); emit(bytes.fromhex('3a 04 c1 6f 87 87 87 85 87 87 87 85 c6 29')); call('setup')
        emit(bytes.fromhex('3a 04 c1 3c 32 04 c1')); emit(b'\xc2\0\0'); fix.append((len(code)-2,'body'))
        request(9); args([0x60,0,0x61,0])
    else:
        request(2); args([1,0,0,2])
        if kind=='disk': request(0x15); args([0x50,0,1,0])
    emit(b'\x21'+word(n)+bytes.fromhex('22 00 c1'))
    label('receive_loop'); call('receive')
    emit(bytes.fromhex('2a 00 c1 2b 22 00 c1 7c b5')); emit(b'\xc2\0\0'); fix.append((len(code)-2,'receive_loop'))
    emit(bytes.fromhex('f3 76 18 fd'))
    target=lambda t: TARGETS[kind] if kind in ('control','positive') else TARGETS[t]
    label('request'); mark('request_start'); emit(b'\xcd'+word(target('37c9'))); mark('request_end'); emit(b'\xc9')
    label('setup'); mark('setup_start'); emit(b'\xcd'+word(target('37d2'))); mark('setup_end'); emit(b'\xc9')
    label('send')
    if reg!='a': emit({'c':b'\x4f','e':b'\x5f','l':b'\x6f'}[reg]+b'\x3e\xa5')
    mark('send_start'); emit(b'\xcd'+word(target('37d2'))); mark('send_end'); emit(b'\xc9')
    label('receive'); mark('receive_start'); emit(b'\xcd'+word(target('3847'))); mark('receive_end'); emit(b'\xc9')
    for pos,s in fix: code[pos:pos+2]=word(labels[s])
    if len(code)>0xe0: raise ValueError(f'器具領域超過: {len(code)}')
    sector=code+bytes(256-len(code)); sector[0xe0:0xe9]=bytes.fromhex('3e 5a 32 00 d0 d3 fd 37 c9'); sector[0xf0]=0xc9
    return bytes(sector),markers

def plan(arm):
    _,kind,_,n=arm
    if kind in ('ram','control','positive'): return ['request']+['setup']*260+['request']+['send']*4+['receive']*n
    return ['request']+['send']*4+(['request']+['send']*4 if kind=='disk' else [])+['receive']*n

def summarize(path,arm,marks):
    ev=old.events(path/'io')
    if ev is None: return {'判定':'欠測（ログ取りこぼし）'}
    starts=[i for i,e in enumerate(ev) if e[0:2]==('OUT',0x7e) and e[3]==0xc015]
    if not starts: return {'判定':'欠測（開始印なし）'}
    end=starts[1] if len(starts)>1 else len(ev)
    relevant=[(i,e) for i,e in enumerate(ev[starts[0]+1:end],starts[0]+1) if e[0:2]==('OUT',0x7f) and e[3] in marks.values()]
    rows=[]; idx=0; received=[]
    for typ in plan(arm):
        if idx>=len(relevant): break
        i,e=relevant[idx]
        if e[3]!=marks[typ+'_start']: return {'判定':'欠測（印の順序異常）'}
        idx+=1
        returned=idx<len(relevant) and relevant[idx][1][3]==marks[typ+'_end']
        if idx<len(relevant) and not returned: return {'判定':'欠測（印の順序異常）'}
        stop=relevant[idx][0] if returned else end
        seg=ev[i+1:stop]
        row={'呼出':typ,'戻り': '確認' if returned else '戻らない（再起動）' if end<len(ev) else '時間上限内未確認', '送信件数':sum(x[:2]==('OUT',0xfd) for x in seg),'受信件数':sum(x[:2]==('IN',0xfc) for x in seg)}
        if typ=='receive' and returned:
            value=relevant[idx][1][2]; received.append(value)
            if arm[1] in ('ram','control','positive'): row['模様と一致']=value==PATTERN[len(received)-1]
            elif arm[1]=='disk': row['媒体と一致']=value==coord_header_pattern(0xa1,0,0,2)[len(received)-1]
        rows.append(row)
        if not returned: break
        idx+=1
    if idx<len(relevant): return {'判定':'欠測（印の順序異常）'}
    result={'判定':'取得','再起動':end<len(ev),'区間':rows,'予定呼出数':len(plan(arm)),'受信戻り数':len(received)}
    if arm[1]=='disk': result['媒体座標']=[0,0,2]; result['全256一致']=len(received)==256 and bytes(received)==coord_header_pattern(0xa1,0,0,2)
    return result

def main():
    cmd=sys.argv[1]
    if cmd=='list': print('\n'.join(a[0] for a in arms())); return
    path=pathlib.Path(sys.argv[2]); arm=next(a for a in arms() if a[0]==sys.argv[3]); sector,marks=generate(arm)
    if cmd=='generate': (path/'probe.bin').write_bytes(sector); (path/'probe.d88').write_bytes(old.disk(sector))
    elif cmd=='summarize': pathlib.Path(sys.argv[4]).write_text(json.dumps(summarize(path,arm,marks),ensure_ascii=False,indent=2)+'\n')
    else: raise ValueError('不明な操作')
if __name__=='__main__': main()
