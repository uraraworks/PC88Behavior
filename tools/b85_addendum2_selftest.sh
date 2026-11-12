#!/usr/bin/env bash
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
for name in ${!PC88_REF_@}; do unset "$name"; done
work="$(mktemp -d "${TMPDIR:-/tmp}/b85a2-test.XXXXXX")"; trap 'rm -rf "$work"' EXIT
if [[ $# == 1 ]]; then ln -s "$1" "$work/run"; else bash "$REPO/tools/b85_addendum2_run.sh" "$work/run"; fi
PYTHONPATH="$REPO/tools" python3 - "$work" <<'PY'
import json, sys
from pathlib import Path
from b85_addendum2_rom import ARMS, pattern
from b85_addendum2_summary import analyze
root=Path(sys.argv[1]); data=json.loads((root/'run/summary/b85-addendum2.json').read_text())
assert data['controls_passed'] and len(data['arms'])==6
assert all(a['judgment']=='record_only' and all(r is not None for r in a['runs']) for a in data['arms'])
t=root/'synthetic'; (t/'raw').mkdir(parents=True)
def make(row, length, bad=False, drop=False, status=3):
    addr,end,size=ARMS[row-1]; setup=[12,addr>>8,addr&255,size>>8,size&255,*pattern(size)]; request=[9,addr>>8,addr&255,end>>8,end&255]
    main=[]; sub=[]
    def add(out, clock, cpu, kind, port, value, pc): out.append(f'{len(out)+1} {clock} 0 {cpu} {kind} {port:04X} {value:02X} {pc:04X}\n')
    for i,v in enumerate(setup): add(main,i+1,'main','OUT',0xfd,v,1)
    marker=len(setup)+10
    add(main,marker,'main','IN',0x40,0,2); add(main,marker+1,'main','IN',0x40,0,3)
    for i,v in enumerate(request):
        add(main,marker+2+2*i,'main','OUT',0xfd,v,1); add(sub,marker+3+2*i,'sub','IN',0xfc,v,1)
    for i in range(length):
        v=pattern(size)[i%size] ^ (1 if bad and i==size-1 else 0)
        add(sub,marker+20+2*i,'sub','OUT',0xfd,v,1); add(main,marker+21+2*i,'main','IN',0xfc,v,1)
    (t/f'raw/{row}-1.io').write_text('# main\n'+''.join(main)+f'# 取りこぼし: {int(drop)}件 / 総イベント数: {len(main)}件\n# sub\n'+''.join(sub)+f'# 取りこぼし: 0件 / 総イベント数: {len(sub)}件\n')
    (t/f'raw/{row}-1.mem').write_text(f'1 0 0000 DF52 {status:02X}\n2 0 0000 DF53 01\n# 取りこぼし: 0件 / 総イベント数: 2件\n')
    return analyze(t,row,1)
for row in (1,2,3,4,6):
    length=(ARMS[row-1][1]-ARMS[row-1][0])&65535
    assert make(row,length)['length_matches_hypothesis'] is True
    assert make(row,length,bad=True)['pattern_match'] is False
assert make(5,0)['length_matches_hypothesis'] is True
r=make(5,65536); assert r['length_matches_hypothesis'] is False and r['pattern_match'] is True
r=make(5,65537,status=4); assert r['receive_cap'] and r['length_matches_hypothesis'] is None
try: make(1,1,drop=True)
except ValueError: pass
else: raise AssertionError('欠落を検出できない')
print('B85 追補2: 自作対照・長さ・全域と先頭・枠・欠落 PASS')
PY
