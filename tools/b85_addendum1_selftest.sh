#!/usr/bin/env bash
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
for name in ${!PC88_REF_@}; do unset "$name"; done
work="$(mktemp -d "${TMPDIR:-/tmp}/b85a-test.XXXXXX")"; trap 'rm -rf "$work"' EXIT
if [[ $# == 1 ]]; then ln -s "$1" "$work/run"; else bash "$REPO/tools/b85_addendum1_run.sh" "$work/run" || true; fi
PYTHONPATH="$REPO/tools" python3 - "$work" <<'PY'
import json, sys
from pathlib import Path
from b85_addendum1_summary import analyze
from b85_addendum1_rom import PATTERN
root=Path(sys.argv[1]); data=json.loads((root/'run/summary/b85-addendum1.json').read_text())
assert len(data['arms'])==15
controls_ok = data['controls_passed'] and all(all(r is not None for r in x['runs']) for x in data['arms'])
# 合成ログで65536+1バイト、一致・不一致、取りこぼしを検査する。
t=root/'synthetic'; (t/'raw').mkdir(parents=True)
setup=[12,0x78,0,0,16,*PATTERN]; request=[9,0x78,0,0,1]
def make(bad=False, drop=False):
    main=[]; sub=[]
    def add(out, clock, cpu, kind, port, value, pc):
        out.append(f'{len(out)+1} {clock} 0 {cpu} {kind} {port:04X} {value:02X} {pc:04X}\n')
    for i,v in enumerate(setup): add(main,i+1,'main','OUT',0xfd,v,1)
    add(main,100,'main','IN',0x40,0,2); add(main,101,'main','IN',0x40,0,3)
    for i,v in enumerate(request):
        add(main,102+2*i,'main','OUT',0xfd,v,1); add(sub,103+2*i,'sub','IN',0xfc,v,1)
    for i in range(65537):
        v=PATTERN[i%16] ^ (1 if bad and i==0 else 0)
        add(sub,200+2*i,'sub','OUT',0xfd,v,1); add(main,201+2*i,'main','IN',0xfc,v,1)
    (t/'raw/1-1.io').write_text('# main\n'+''.join(main)+f'# 取りこぼし: {int(drop)}件 / 総イベント数: {len(main)}件\n# sub\n'+''.join(sub)+f'# 取りこぼし: 0件 / 総イベント数: {len(sub)}件\n')
    (t/'raw/1-1.mem').write_text('1 0 0000 DF52 03\n2 0 0000 DF53 01\n# 取りこぼし: 0件 / 総イベント数: 2件\n')
make(); r=analyze(t,1,1); assert r['reply_length']==65537 and r['pattern_prefix_match'] is True
make(bad=True); assert analyze(t,1,1)['pattern_prefix_match'] is False
make(drop=True)
try: analyze(t,1,1)
except ValueError: pass
else: raise AssertionError('欠落を検出できない')
print('B85 追補1: 65537バイト・一致不一致・欠落検出 PASS')
if not controls_ok:
    print('B85 追補1: 自作器具対照 FAIL', file=sys.stderr)
    sys.exit(1)
print('B85 追補1: 自作09腕は記録のみ・器具対照 PASS')
PY
