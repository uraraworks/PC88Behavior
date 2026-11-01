#!/usr/bin/env bash
set -euo pipefail
repo="$(cd "$(dirname "$0")/.." && pwd)"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
PYTHONPATH="$repo/tools" python3 - "$work" <<'PY'
from pathlib import Path
import sys
from b50_paired_request import read, bursts, summarize
work = Path(sys.argv[1])
def make(path, shifted=False):
    main, sub = [], []
    clock = 0
    def event(cpu, kind, port, value, pc):
        nonlocal clock
        clock += 1
        (main if cpu == 'main' else sub).append((clock, kind, port, value, pc))
    for i in range(76570):
        event('main', 'IN', 0xFC, (i * 17) % 251, 0xC000)
    for group, size in enumerate((3, 5, 8, 11)):
        for i in range(size):
            event('main', 'OUT', 0xFD, [0xA1, 0xB2, 0xC3, 0xD4][group] if i == 0 else 0xE7, 0x8100 + group * 16 + (i % 2 if group == 2 else 0))
            event('main', 'OUT', 0xFF, 0xE7, 0x8200 + group * 16 + (i % 2 if group == 2 else 0))
            event('sub', 'IN', 0xFC, 0xE7, 0x1000 if group == 2 else 0x3000)
            if group == 2 and i % 2 == 0:
                event('main', 'IN', 0xFE, 0xE7, 0x8300)
    for i in range(40):
        event('main', 'IN', 0xFC, ((i - (1 if shifted else 0)) * 23) % 251, 0xC000)
    with path.open('w') as f:
        for name, rows in [('main', main), ('sub', sub)]:
            f.write('# ' + name + '\n')
            for i, (t, kind, port, val, pc) in enumerate(rows, 1):
                f.write(f'{i} {t} 0 {name} {kind} {port:04X} {val:02X} {pc:04X}\n')
            f.write(f'# 取りこぼし: 0件 / 総イベント数: {len(rows)}件\n')
make(work/'a')
make(work/'b', True)
a, b = read(work/'a'), read(work/'b')
assert [(x[0], x[1]) for x in bursts(a)] == [(3,'single'),(5,'single'),(8,'paired'),(11,'single')]
rows = summarize(a,b)
assert 'sub-reader single hi' in rows and 'sub-reader paired lo' in rows
assert 'shift +1 compared=37 same=37' in rows
assert [r for r in rows if r.startswith('burst ')] == ['burst 1 size=3 mode=single head=A1','burst 2 size=5 mode=single head=B2','burst 3 size=8 mode=paired head=C3','burst 4 size=11 mode=single head=D4']
assert all('E7' not in row for row in rows)
PY
python3 "$repo/tools/b50_paired_request.py" "$work/a" "$work/b" >"$work/out" 2>"$work/err"
! grep -q E7 "$work/out" "$work/err"
if python3 "$repo/tools/b50_paired_request.py" "$work/E7" "$work/b" >"$work/out" 2>"$work/err"; then exit 1; fi
[[ ! -s "$work/out" && ! -s "$work/err" ]]
