#!/usr/bin/env python3
"""B85 生記録から許可項目だけを生成する。例外の内容は公開しない。"""
import argparse
from collections import Counter
import json
from pathlib import Path
import sys
from analyze_main_to_sub import parse_iolog
from analyze_m6ia_main_sub import read_memlog
from analyze_b16 import io_drops
from b13_sub_fdc import read_events
from b38_sub_snapshot_compare import read as snapshot
from analyze_b12 import CMDS
from b85_build_rom import ROWS

NAMES = {v[0] for v in CMDS.values()} | {'unknown'}

def load(io, mem):
    if io_drops(io) != 0: raise ValueError()
    read_events(io)  # sub の連番と両ログの欠落を検査
    ev, masked = parse_iolog(io)
    if masked or not ev: raise ValueError()
    m = {e.addr: e.value for e in read_memlog(mem)}
    if m.get(0xdf53) != 1 or m.get(0xdf52) not in (0, 1, 2) or 0xdf50 not in m or 0xdf51 not in m: raise ValueError()
    main = [e for e in ev if e.cpu == 'main']
    marks = [(a,b) for a,b in zip(main,main[1:]) if a.kind == b.kind == 'IN' and a.port == b.port == '0040' and b.pc != a.pc]
    frequencies = Counter((a.pc, b.pc) for a,b in marks)
    marks = [(a,b) for a,b in marks if frequencies[a.pc,b.pc] == 1]
    if len(marks) != 1: raise ValueError()
    fc = [e for e in main if e.kind == 'IN' and e.port == '00FC']
    if not fc or fc[-1].clock <= marks[0][1].clock: raise ValueError()
    return ev, m, marks[0][1].clock, fc[-1].clock, len(fc)-1

def analyze(root, row, run):
    p = root / 'raw' / f'{row}-{run}'
    ev, m, start, end, target = load(p.with_suffix('.final.io'), p.with_suffix('.final.mem'))
    first = load(p.with_suffix('.first.io'), p.with_suffix('.first.mem'))
    if first[4] != target or first[1] != m: raise ValueError()
    def transcript(events, lo, hi):
        return [(e.cpu, e.kind, e.port, e.value) for e in events if lo < e.clock < hi]
    if transcript(*first[:1], first[2], first[3]) != transcript(ev, start, end): raise ValueError()
    if p.with_suffix('.first.d88').read_bytes() != p.with_suffix('.d88').read_bytes(): raise ValueError()
    window = [e for e in ev if start < e.clock < end]
    sends = [e.value for e in window if e.cpu == 'main' and e.kind == 'OUT' and e.port == '00FD']
    if m[0xdf50] > len(ROWS[row-1]) or sends[:m[0xdf50]] != list(ROWS[row-1][:m[0xdf50]]) or len(sends) > m[0xdf50] + 1: raise ValueError()
    writes = [e.value for e in window if e.cpu == 'sub' and e.kind == 'OUT' and e.port == '00FB']
    counts = Counter(); i = 0
    while i < len(writes):
        name, length = CMDS.get(writes[i] & 31, ('unknown', 1))
        if i + length > len(writes): raise ValueError()
        counts[name] += 1; i += length
    snap = snapshot(p.with_suffix('.snap'))[0]
    base = root / 'raw' / f'1-{run if row != 1 else 3-run}.snap'
    reference = snapshot(base)[0]
    addresses = [i + 0x4000 for i,(a,b) in enumerate(zip(reference,snap)) if a != b]
    (root/'raw'/f'{row}-{run}.changed-addresses.json').write_text(json.dumps(addresses)+'\n')
    return {'_changed_addresses': addresses, 'sub_received_count': sum(e.cpu == 'sub' and e.kind == 'IN' and e.port == '00FC' for e in window),
            'sub_sent_count': sum(e.cpu == 'sub' and e.kind == 'OUT' and e.port == '00FD' for e in window),
            'main_received_count': sum(e.cpu == 'main' and e.kind == 'IN' and e.port == '00FC' for e in window),
            'reply_length': m[0xdf51], 'send_count': m[0xdf50], 'send_timeout': m[0xdf52] == 1, 'reply_truncated': m[0xdf52] == 2,
            'fdc_commands': dict(sorted(counts.items())),
            'medium_unchanged': p.with_suffix('.before.d88').read_bytes() == p.with_suffix('.d88').read_bytes(),
            'changed_address_count': len(addresses)}

def summarize(root):
    valid = {}; failed = False
    for row in range(1,9):
        for run in (1,2):
            try: valid[row,run] = analyze(root,row,run)
            except Exception: valid[row,run] = None; failed = True
    failed = failed or any(x is not None and x['reply_truncated'] for x in valid.values())
    try: controls = (root/'raw'/'controls.status').read_text().strip() == 'pass'
    except OSError: controls = False
    reproducible = not failed and all(valid[r,1] == valid[r,2] for r in range(1,9))
    result = []
    for row in range(1,9):
        if failed: judgment = 'instrument_invalid'
        elif not controls: judgment = 'controls_failed'
        elif not reproducible: judgment = 'not_reproducible'
        elif row in range(3,7): judgment = 'observed_difference' if valid[row,1] != valid[2,1] else 'no_difference_observed'
        else: judgment = 'control'
        public_runs = [None if valid[row,run] is None else {k:v for k,v in valid[row,run].items() if k != '_changed_addresses'} for run in (1,2)]
        result.append({'arm':row, 'runs':public_runs, 'judgment':judgment})
    data = {'controls_passed':controls,'arms':result}
    validate(data)
    (root/'summary'/'b85.json').write_text(json.dumps(data,indent=2,ensure_ascii=True)+'\n')
    return failed or not controls

def validate(data):
    assert set(data) == {'controls_passed','arms'} and type(data['controls_passed']) is bool and len(data['arms']) == 8
    fields = {'sub_received_count','sub_sent_count','main_received_count','reply_length','send_count','send_timeout','reply_truncated','fdc_commands','medium_unchanged','changed_address_count'}
    for i, arm in enumerate(data['arms'],1):
        assert set(arm) == {'arm','runs','judgment'} and arm['arm'] == i and len(arm['runs']) == 2
        assert arm['judgment'] in {'instrument_invalid','controls_failed','not_reproducible','observed_difference','no_difference_observed','control'}
        for run in arm['runs']:
            if run is None: continue
            assert set(run) == fields
            for k in fields - {'send_timeout','reply_truncated','fdc_commands','medium_unchanged'}: assert type(run[k]) is int and run[k] >= 0
            assert type(run['reply_truncated']) is bool and type(run['send_timeout']) is bool and type(run['medium_unchanged']) is bool
            assert set(run['fdc_commands']) <= NAMES and all(type(v) is int and v > 0 for v in run['fdc_commands'].values())

def main():
    p=argparse.ArgumentParser(); p.add_argument('--target',nargs=2,type=Path); p.add_argument('root',nargs='?',type=Path); a=p.parse_args()
    try:
        if a.target: print(load(*a.target)[4]); return 0
        if not a.root: return 2
        summarize(a.root); return 0
    except Exception:
        print('B85: 記録を検証できません',file=sys.stderr); return 1
if __name__ == '__main__': sys.exit(main())
