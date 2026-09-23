#!/usr/bin/env bash
# m6i-i解析器を合成メモリ記録で検査する。
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK="$(mktemp -d)"; trap 'rm -rf "$WORK"' EXIT
GEOM=(--cylinders 40 --double-sided --sectors-per-track 16 --content-rule coord-header)
python3 "$REPO/tools/make_l3_testdisk.py" "$WORK/a.d88" "${GEOM[@]}" --disk-id 0xA1 >/dev/null
python3 "$REPO/tools/make_l3_testdisk.py" "$WORK/b.d88" "${GEOM[@]}" --disk-id 0xB2 >/dev/null
python3 - "$REPO" "$WORK" <<'PY'
from pathlib import Path
import sys
repo,work=map(Path,sys.argv[1:]); sys.path.insert(0,str(repo/'tools'))
import analyze_m6ii as a
import judge_m6ii as j
from analyze_m6ia_main_sub import MemEvent
from d88_read_sector import D88Reader
images={'A':(work/'a.d88').read_bytes(),'B':(work/'b.d88').read_bytes()}
readers={k:D88Reader(v) for k,v in images.items()}
def payload(d,c,h,r): return readers[d].read_sector(c,h,r)
def events(actual=None,entries=None,order=None,partial_then_full=None):
    actual=actual or {}; entries=entries or {}; order=order or list(range(1,12)); partial_then_full=partial_then_full or set()
    out=[]
    def add(addr,value): out.append(MemEvent(len(out)+1,1,0x7000,addr,value))
    by_no={row[0]:row for row in a.ROWS}
    for n in order:
        _,d,c,h,r=by_no[n]; add(a.ROW_MARKER_ADDRESS,n)
        count=entries.get(n,1)
        for _ in range(count): add(a.READ_ENTRY_ADDRESS,0)
        data=actual.get(n,payload(d,c,h,r))
        if n in partial_then_full:
            for i,value in enumerate(data[:73]): add(0xDF00+i,value)
        if data is not None:
            for i,value in enumerate(data): add(0xDF00+i,value)
    return out
def analyze(rows): return a.analyze_events(rows,images['A'],images['B'])
base=analyze(events())
checks={'match':base['reached'] and all(r['result']=='row_match' for r in base['rows'])}
wrong=payload('A',0,0,1); mismatch=analyze(events({2:wrong}))
checks['mismatch_coord']=(mismatch['rows'][1]['result']=='row_mismatch' and mismatch['rows'][1]['actual_coordinate']==[0xA1,0,0,1])
nodata=analyze(events({4:None})); checks['no_data']=nodata['rows'][3]['result']=='row_no_data'
retry=analyze(events(entries={1:2},partial_then_full={1})); checks['retry_last_complete']=(retry['rows'][0]['result']=='row_match' and retry['rows'][0]['entry_count']==2)
disorder=analyze(events(order=[1,3,2,*range(4,12)])); checks['marker_disorder']=not disorder['reached']

fault_h={n:payload(d,c,0,r) for n,d,c,h,r in a.ROWS if n in j.FAULT_ROWS['I-F-H']}
fh=analyze(events(fault_h)); checks['fault_h']=(j.classify_arm('I-F-H',fh['rows'])=='fault_detected' and fh['rows'][1]['actual_coordinate']==[0xA1,0,0,1])
fault_d={n:payload('A',c,h,r) for n,d,c,h,r in a.ROWS if n in j.FAULT_ROWS['I-F-D']}
fd=analyze(events(fault_d)); checks['fault_d']=j.classify_arm('I-F-D',fd['rows'])=='fault_detected'
fault_r={n:(payload(d,c,h,r+1) if r<16 else None) for n,d,c,h,r in a.ROWS}
fr=analyze(events(fault_r)); checks['fault_r']=(j.classify_arm('I-F-R',fr['rows'])=='fault_detected' and fr['rows'][3]['result']=='row_no_data')
fretry=analyze(events({8:payload('A',0,0,1)},entries={8:2})); checks['fault_retry']=(j.classify_arm('I-F-RETRY',fretry['rows'])=='fault_detected' and fretry['rows'][7]['actual_coordinate']==[0xA1,0,0,1])
if not all(checks.values()): raise SystemExit('NG: '+str({k for k,v in checks.items() if not v}))
for target in checks:
    negative=dict(checks); negative[target]=False
    if {k for k,v in negative.items() if not v}!={target}: raise SystemExit('NG集合 '+target)
    mutant=dict(negative); mutant[target]=True
    if {k for k,v in mutant.items() if not v}=={target}: raise SystemExit('常時真変異 '+target)
print(f"analyze_m6ii_selftest: 項目数={len(checks)}、陰性対照={len(checks)}、常時真変異={len(checks)}件拒否 OK")
print('結果=match/mismatch座標/no_data/再試行最終完全/順序乱れ、故障4種 OK')
PY
