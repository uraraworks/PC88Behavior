#!/usr/bin/env bash
set -euo pipefail
repo="$(cd "$(dirname "$0")/.." && pwd)"
PYTHONPATH="$repo/tools" python3 - "$repo" <<'PY'
from pathlib import Path
import subprocess
import sys
import tempfile

repo = Path(sys.argv[1])
tool = repo / 'tools/b47_pio_handoff.py'

def make(path, negative=False):
    main = []
    for i in range(76574):
        value = 'A7' if negative or i < 76570 else ['D9', 'B8', 'C6', 'D9'][i - 76570]
        main.append(f'{i+1} {10+i*10} 0 main IN 00FC {value} C000')
    t = 10 + 76570*10
    sub = [f'1 1 0 sub OUT 00FD A7 1234',
           f'2 {t-2} 0 sub OUT 00FD {"A7" if negative else "B8"} 1234',
           f'3 {t+2} 0 sub OUT 00FD {"A7" if negative else "D9"} 1234']
    path.write_text('# main\n' + '\n'.join(main) + f'\n# 取りこぼし: 0件 / 総イベント数: {len(main)}件\n# sub\n' + '\n'.join(sub) + '\n# 取りこぼし: 0件 / 総イベント数: 3件\n')

with tempfile.TemporaryDirectory() as d:
    path = Path(d) / 'io'
    def run():
        return subprocess.run([sys.executable, str(tool), str(path), '--arm', 'OO'], capture_output=True, text=True)
    make(path)
    result = run()
    assert result.returncode == 0 and not result.stderr
    assert 'first-differ=76570' in result.stdout
    assert 'prev=1 next=1 neither=1' in result.stdout
    assert all(v not in result.stdout for v in ('A7', 'B8', 'D9', 'C6'))
    make(path, True)
    result = run()
    assert result.returncode == 0 and 'first-differ=none' in result.stdout and not result.stderr
    assert all(v not in result.stdout for v in ('A7', 'B8', 'D9', 'C6'))
    text = path.read_text()
    path.write_text(text.replace('1 1 0 sub', '1 10 0 sub'))
    result = run()
    assert result.returncode == 1 and not result.stdout and not result.stderr
    path.write_text(text.replace('1 1 0 sub', '1 0 sub'))
    result = run()
    assert result.returncode == 1 and not result.stdout and not result.stderr
print('B47 自己検査成功')
PY
