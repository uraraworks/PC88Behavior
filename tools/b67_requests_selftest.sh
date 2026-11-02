#!/usr/bin/env bash
set -euo pipefail
repo="$(cd "$(dirname "$0")/.." && pwd)"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
python3 - "$work" <<'PY'
from pathlib import Path
import sys
w = Path(sys.argv[1])
events = [('IN',0xFC,0xE7), ('OUT',0xFF,1), ('OUT',0xFD,0xA1), ('OUT',0xFF,0), ('IN',0xFE,0xE7), ('OUT',0xFD,0xE7), ('OUT',0xFF,0), ('IN',0xFC,0xE7), ('OUT',0xFF,1), ('OUT',0xFD,0xB2), ('OUT',0xFF,0)]
with (w/'io').open('w') as f:
    f.write('# main\n')
    for i, (kind, port, value) in enumerate(events, 1):
        f.write(f'{i} {i} 0 main {kind} {port:04X} {value:02X} 8000\n')
    f.write(f'# 取りこぼし: 0件 / 総イベント数: {len(events)}件\n# sub\n# 取りこぼし: 0件 / 総イベント数: 0件\n')
(w/'reg').write_text('Q88REG1\n' + ('F ' + ' '.join(['0000']*18) + '\n')*5 + 'END\n')
(w/'expected').write_text('req O 12000 1 head=A1 size=2 shape=2p fc=4\nreq O 12000 2 head=B2 size=1 shape=1s fc=5\n')
PY
python3 "$repo/tools/b67_requests.py" "$work/io" --sub-reg-log "$work/reg" --arm O --window 12000 >"$work/out" 2>"$work/err"
cmp "$work/expected" "$work/out"
[[ ! -s "$work/err" ]]
! grep -q E7 "$work/out" "$work/err"
if python3 "$repo/tools/b67_requests.py" "$work/E7" --sub-reg-log "$work/reg" --arm O --window 12000 >"$work/out" 2>"$work/err"; then exit 1; fi
[[ ! -s "$work/out" && ! -s "$work/err" ]]
