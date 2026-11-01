#!/usr/bin/env bash
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/b40-selftest.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$REPO/tools" python3 - "$WORK" <<'PY'
import pathlib, subprocess, sys
from b40_cross_table import read, compare
w = pathlib.Path(sys.argv[1])
def row(kind, **kw):
    r = [0] * 18
    r[6] = 0x4000
    for k, v in kw.items(): r[int(k)] = v
    return kind + ' ' + ' '.join(f'{x:04X}' for x in r)
def save(name, rows):
    (w/name).write_text('Q88REG1\n' + '\n'.join(rows) + '\nEND\n')
save('a', [row('F'), row('C'), row('F'), row('F'), row('C'), row('C')])
save('b', [row('F'), row('F'), row('C', **{'0': 0xAB00}), row('C', **{'0': 0x00CD})])
a, b = read(w/'a'), read(w/'b')
assert compare(a, b) == ['# 識別子: G1', 'count 3 2', 'C 0 4000 4000 1 2 A', 'C 1 4000 4000 3 2 F', 'LEFT 2 4000 3']
assert compare(b, a)[-1] == 'RIGHT 2 4000 3'
assert all(x.endswith(' none') for x in compare(a, a)[2:])
# 全レジスタの分割・除外と出力漏れを検査する。
r = [0xABCD] * 18
r[6] = 0x4000
save('all', ['C ' + ' '.join(f'{x:04X}' for x in r)])
text = '\n'.join(compare(read(w/'all'), read(w/'a')))
assert "A,F,B,C,D,E,H,L,IX,IY,SP,A'F',B'C',D'E',H'L',I,IFF,IFF2,IM,HALT" in text
assert 'ABCD' not in text
save('ignored', [row('C', **{'13': 0xABCD})])
assert compare(read(w/'ignored'), read(w/'a'))[2].endswith(' none')
(w/'bad').write_text('secret-marker\n')
tool = pathlib.Path(__import__('b40_cross_table').__file__)
for x, y in [('all', 'a'), ('bad', 'a')]:
    p = subprocess.run([sys.executable, str(tool), str(w/x), str(w/y)], capture_output=True, text=True)
    assert ('ABCD' not in p.stdout + p.stderr and 'secret-marker' not in p.stdout + p.stderr)
    assert p.returncode == (1 if x == 'bad' else 0)
PY
printf 'B40 自己検査 PASS\n'
