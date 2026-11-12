#!/usr/bin/env python3
"""B86 追補1: 自作入力の生成と値なし集計。"""
import collections
import json
import pathlib
import re
import sys
from b2_make_boot_probe import build_disk
from make_l3_testdisk import coord_header_pattern

TARGETS = {'3391': 0x3391, '369a': 0x369a, '37c9': 0x37c9, '37d2': 0x37d2, '3847': 0x3847, 'control': 0xc0f0, 'positive': 0xc0e0}

def arms():
    for variant in ('zero', 'a', 'bc', 'de', 'hl', 'flags', 'mem-hl-zero', 'mem-hl-one', 'mem-de-zero', 'mem-de-one'):
        yield (f'3391-{variant}', ['3391'], int(variant == 'a'), int(variant == 'bc'),
               0xd100 if variant.startswith('mem-de-') else int(variant == 'de'),
               0xd000 if variant.startswith('mem-hl-') else int(variant == 'hl'), int(variant == 'flags'))
    for bc in (1, 2, 0x100, 0x200):
        for carry in (0, 1):
            for hl, de in ((0xd000, 0xd400), (0xd400, 0xd000), (0, 0xd000)):
                yield f'369a-b{bc:04x}-c{carry}-h{hl:04x}-d{de:04x}', ['369a'], 0, bc, de, hl, carry
    for a in (0, 1, 2, 255):
        for hl, de in ((0xd000, 0xd400), (0xd400, 0xd000), (0, 0)):
            yield f'37c9-a{a:02x}-h{hl:04x}-d{de:04x}', ['37c9'], a, 1, de, hl, 0
    for first in ('37c9', '369a'):
        for second in ('37d2', '3847', '3391'):
            yield f'{first}-then-{second}', [first, second], 1, 1, 0xd400, 0xd000, 0
    for target in ('control', 'positive'):
        yield target, [target], 0, 1, 0xd400, 0xd000, 0

def word(n): return bytes((n & 255, n >> 8))
def generate(arm):
    name, targets, a, bc, de, hl, carry = arm
    code = bytearray(bytes.fromhex('f3 31 00 f0'))
    # D000-D7FF を 00..FF の繰り返しで初期化。
    code += bytes.fromhex('21 00 d0 01 00 08 af 77 23 3c 0b 57 78 b1 7a 20 f6')
    if name in ('3391-mem-hl-one', '3391-mem-de-one'):
        addr = 0xd000 if name == '3391-mem-hl-one' else 0xd100
        code += b'\x3e\x01\x32' + word(addr)
    code += bytes.fromhex('21 00 c1 01 00 2f cd 80 c0')
    code += b'\x21' + word((a << 8) | carry) + b'\xe5\xf1'
    code += b'\x01' + word(bc) + b'\x11' + word(de) + b'\x21' + word(hl)
    markers = []
    mem_markers = []
    for target in targets:
        mem_markers.append(0xc000 + len(code)); code += b'\x32\xc0\xc0'
        markers.append(0xc000 + len(code)); code += b'\xd3\x7f\xcd' + word(TARGETS[target])
        markers.append(0xc000 + len(code)); code += b'\xd3\x7f'
        mem_markers.append(0xc000 + len(code)); code += b'\x32\xc0\xc0'
    code += bytes.fromhex('21 00 c1 01 00 2f cd 80 c0 f3 76 18 fd')
    if len(code) > 0x80: raise ValueError('器具の領域重複')
    sector = code + bytes(256-len(code))
    sector[0x80:0x8a] = bytes.fromhex('7e d3 7d 23 0b 78 b1 20 f7 c9')
    sector[0xe0:0xe9] = bytes.fromhex('3e 5a 32 00 d0 d3 fd 37 c9')
    sector[0xf0] = 0xc9
    return bytes(sector), markers, mem_markers

def ranges(addrs):
    result = []
    for x in addrs:
        if result and x == result[-1][1]+1: result[-1][1] = x
        else: result.append([x, x])
    return [[f'{a:04X}', f'{b:04X}'] for a,b in result]

def summarize(d, arm, markers, mem_markers):
    io = (d/'io').read_text(); mem = (d/'mem').read_text()
    drops = re.findall(r'取りこぼし: (\d+)件', io)
    mdrops = re.findall(r'取りこぼし: (\d+)件', mem)
    clean = len(drops)==2 and len(mdrops)==1 and not any(int(x) for x in drops+mdrops)
    events = []
    for line in io.splitlines():
        m = re.fullmatch(r'\s*\d+\s+\d+\s+\d+\s+(main|sub)\s+(IN|OUT)\s+([0-9A-F]{4})\s+([0-9A-F]{2})\s+([0-9A-F]{4})', line)
        if m and m[1]=='main': events.append((m[2], int(m[3],16), int(m[4],16), int(m[5],16)))
    if any(sum(1 for e in events if e[0]=='OUT' and e[1]==0x7f and e[3]==pc)>1 for pc in markers): clean = False
    indices = []
    for pc in markers:
        found = [i for i,e in enumerate(events) if e[0]=='OUT' and e[1]==0x7f and e[3]==pc]
        indices.append(found[0] if clean and len(found)==1 else None)
    writes = []
    for line in mem.splitlines():
        m = re.fullmatch(r'\s*\d+\s+\d+\s+([0-9A-F]{4})\s+([0-9A-F]{4})\s+([0-9A-F]{2})', line)
        if m: writes.append((int(m[1],16),int(m[2],16)))
    if any(writes.count((pc, 0xc0c0))>1 for pc in mem_markers):
        clean = False
        indices = [None] * len(indices)
    mi = []
    for pc in mem_markers:
        found = [i for i, e in enumerate(writes) if e == (pc, 0xc0c0)]
        mi.append(found[0] if clean and len(found)==1 else None)
    _, targets, a, bc, de, hl, carry = arm
    rows = []
    for n, target in enumerate(targets):
        start, end = indices[n*2:n*2+2]
        if start is None or (n and (indices[n*2-1] is None or start <= indices[n*2-1])):
            rows.append({'入口':target,'開始':'欠測','戻り':'欠測','I/O':'欠測'}); continue
        valid_end = end is not None and end > start
        missing_end = end is None and any(x is not None and x > start for x in indices[n*2+2:])
        if missing_end or (end is not None and not valid_end):
            rows.append({'入口':target,'開始':'確認','戻り':'欠測','I/O':'欠測'}); continue
        segment = events[start+1:end if valid_end else len(events)]
        counts = collections.Counter((e[0],e[1]) for e in segment)
        sent = bytes(e[2] for e in segment if e[:2]==('OUT',0xfd))
        recv = bytes(e[2] for e in segment if e[:2]==('IN',0xfc))
        input_bytes = bytearray(i & 255 for i in range(0x800))
        if arm[0] == '3391-mem-hl-one': input_bytes[0] = 1
        if arm[0] == '3391-mem-de-one': input_bytes[0x100] = 1
        def region(addr, length):
            return bytes(input_bytes[addr-0xd000:addr-0xd000+length]) if 0xd000 <= addr and addr+length <= 0xd800 else None
        candidates = {'A':bytes([a]), 'HL下位':bytes([hl & 255]), 'HL上位':bytes([hl >> 8]), 'DE下位':bytes([de & 255]), 'DE上位':bytes([de >> 8]), 'HL領域256':region(hl, 256), 'HL領域512':region(hl, 512), 'DE領域256':region(de, 256)}
        matches = {k: (sent == v if v is not None else None) for k,v in candidates.items()}
        matches.update({k+'末尾':(sent.endswith(v) if v is not None and len(sent)>=len(v) else False if v is not None else None) for k,v in candidates.items() if '領域' in k})
        coords = [[c,h,s] for c in range(40) for h in range(2) for s in range(1,17) if coord_header_pattern(0xa1,c,h,s) in recv]
        ms, me = mi[n*2:n*2+2]
        write_ok = ms is not None and (me is None or me > ms)
        addresses = sorted({addr for _,addr in writes[ms+1:me] if 0xc100 <= addr <= 0xefff}) if write_ok else []
        rows.append({'書き込み番地範囲':ranges(addresses) if write_ok else None,'入口':target,'開始':'確認','戻り':'確認' if valid_end else ('時間上限内に戻らず' if end is None else '欠測'),'I/O':[{'方向':k[0],'ポート':f'{k[1]:02X}','回数':v} for k,v in sorted(counts.items())], '送信長':len(sent),'送信と入力の一致':matches,'受信長':len(recv),'受信内の自作媒体座標':coords})
    before = [e[2] for e in events[:indices[0]] if e[:2]==('OUT',0x7d) and e[3]==0xc081] if indices[0] is not None else []
    last = indices[-1]
    after = [e[2] for e in events[last+1:] if e[:2]==('OUT',0x7d) and e[3]==0xc081] if last is not None else []
    ok = len(before)==len(after)==0x2f00 and all(x is not None for x in indices)
    changed = [0xc100+i for i,(x,y) in enumerate(zip(before,after)) if x!=y] if ok else []
    data = bytes(after)
    coords = [[c,h,s] for c in range(40) for h in range(2) for s in range(1,17) if coord_header_pattern(0xa1,c,h,s) in data] if ok else []
    return {'区間':rows,'RAM':{'判定':'取得' if ok else '欠測','範囲':'C100-EFFF','変化番地範囲':ranges(changed) if ok else None,'自作媒体座標':coords if ok else None}}

def main():
    command, path, *rest = sys.argv[1:]; path = pathlib.Path(path)
    if command == 'list':
        print('\n'.join(x[0] for x in arms())); return
    arm = next(x for x in arms() if x[0]==rest[0]); sector, markers, mem_markers = generate(arm)
    if command == 'generate':
        (path/'probe.bin').write_bytes(sector); (path/'probe.d88').write_bytes(build_disk(sector,'none'))
    elif command == 'summarize':
        pathlib.Path(rest[1]).write_text(json.dumps(summarize(path,arm,markers,mem_markers),ensure_ascii=False,indent=2)+'\n')
    else: raise ValueError('不明な操作')
if __name__=='__main__': main()
