#!/usr/bin/env bash
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
python3 - "$REPO" "$work" <<'PY'
import pathlib
import sys
sys.path.insert(0, str(pathlib.Path(sys.argv[1]) / 'tools'))
from b77_interrupts import summarize
w = pathlib.Path(sys.argv[2])
header = '# seq    clock   frame  cpu   im  level  ret_pc  handler_pc\n'
def write(name, events, dropped=0):
    rows = ''.join(f'{i} {i} {i} main {im} {level} ABCD {pc}\n' for i, (im, level, pc) in enumerate(events, 1))
    empty = '' if events else '# (記録されたイベントなし)\n'
    (w / name).write_text('# main\n' + header + empty + rows + f'# 取りこぼし: {dropped}件 / 総イベント数: {len(events)}件\n\n# sub\n' + header + '# (記録されたイベントなし)\n# 取りこぼし: 0件 / 総イベント数: 0件\n', encoding='utf-8')
write('a', [(2, 1, '1234'), (1, 0, '8000')])
write('b', [(2, 1, '1234'), (1, 0, '8000'), (2, 1, '7FFF'), (2, 1, '9000')])
assert summarize(w/'a', w/'b', 'O', '11400-11999') == ['int O 11400-11999 IM2-L1 9000 1', 'int O 11400-11999 IM2-L1 rom 1', 'total O 11400-11999 2']
assert summarize(w/'a', w/'a', 'S', '12000-12599') == ['total S 12000-12599 0']
write('bad', [], 1)
for a, b in (('a', 'bad'), ('b', 'a')):
    try:
        summarize(w/a, w/b, 'O', '11400-11999')
    except ValueError:
        pass
    else:
        raise AssertionError('不正な記録を受理')
print('OK: B77 合成記録')
PY
