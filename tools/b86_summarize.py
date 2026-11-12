#!/usr/bin/env python3
"""B86 の非公開記録から値を含まない集計を作る。"""
import collections
import json
import pathlib
import re
import sys


def summarize(d):
    sector = (d / 'probe.bin').read_bytes()
    call = sector.index(b'\xd3\x7f\xcd')
    start_pc, end_pc = 0xc000 + call, 0xc000 + call + 5
    io = (d / 'io').read_text()
    mem = (d / 'mem').read_text()
    drops = re.findall(r'取りこぼし: (\d+)件', io)
    mdrops = re.findall(r'取りこぼし: (\d+)件', mem)
    if len(drops) != 2 or len(mdrops) != 1:
        raise ValueError('記録が不完全')
    events = []
    for line in io.splitlines():
        m = re.fullmatch(r'\s*\d+\s+\d+\s+\d+\s+(main|sub)\s+(IN|OUT)\s+([0-9A-F]{4})\s+([0-9A-F]{2})\s+([0-9A-F]{4})', line)
        if m and m[1] == 'main':
            events.append((m[2], int(m[3], 16), int(m[4], 16), int(m[5], 16)))
    starts = [i for i,e in enumerate(events) if e[0]=='OUT' and e[1]==0x7f and e[3]==start_pc]
    ends = [i for i,e in enumerate(events) if e[0]=='OUT' and e[1]==0x7f and e[3]==end_pc]
    clean = all(int(x)==0 for x in drops) and int(mdrops[0])==0
    valid_start = clean and len(starts)==1
    returned = valid_start and len(ends)==1 and ends[0]>starts[0]
    before = [e[2] for e in events[:starts[0]] if e[0]=='OUT' and e[1]==0x7d and e[3]==0xc081] if valid_start else []
    after = [e[2] for e in events[ends[0]+1:] if e[0]=='OUT' and e[1]==0x7d and e[3]==0xc081] if returned else []
    count = 0x2f00
    ram_ok = returned and len(before)==count and len(after)==count
    changed = [0xc100+i for i,(a,b) in enumerate(zip(before,after)) if a!=b] if ram_ok else []
    ports = collections.Counter((e[0],e[1]) for e in events[starts[0]+1:ends[0]]) if returned else {}
    result_writes = {}
    for line in mem.splitlines():
        m = re.fullmatch(r'\s*\d+\s+\d+\s+[0-9A-F]{4}\s+([0-9A-F]{4})\s+([0-9A-F]{2})', line)
        if m and 0xc0c0 <= int(m[1],16) <= 0xc0ca:
            result_writes[int(m[1],16)] = int(m[2],16)
    regs_ok = returned and all(a in result_writes for a in range(0xc0c0,0xc0cb)) and result_writes.get(0xc0ca)==0xa5
    (d/'result.json').write_text(json.dumps({'register_bytes': {f'{a:04X}':v for a,v in result_writes.items()}, 'ram_changes': [[f'{a:04X}',before[a-0xc100],after[a-0xc100]] for a in changed]}, ensure_ascii=False, indent=2)+'\n')
    return {'J_start': '確認' if valid_start else '欠測', 'J_return': '確認' if returned else ('時間上限内に戻らず' if valid_start and not ends else '欠測'), 'J_regs': '取得' if regs_ok else '欠測', 'J_ram': {'判定': '取得' if ram_ok else '欠測', '範囲': 'C100-EFFF', '変化番地数': len(changed) if ram_ok else None, '変化範囲': [f'{min(changed):04X}', f'{max(changed):04X}'] if changed else None}, 'J_io': {'判定': '取得' if returned else '欠測', 'ポート別回数': [{'方向':k[0], 'ポート':f'{k[1]:02X}', '回数':v} for k,v in sorted(ports.items())]}, 'J_cycles':'欠測'}

if __name__=='__main__':
    result=summarize(pathlib.Path(sys.argv[1]))
    pathlib.Path(sys.argv[2]).write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n')
