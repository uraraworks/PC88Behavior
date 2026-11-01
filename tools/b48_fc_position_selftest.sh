#!/usr/bin/env bash
set -euo pipefail
repo="$(cd "$(dirname "$0")/.." && pwd)"
PYTHONPATH="$repo/tools" python3 - "$repo" <<'PY'
from pathlib import Path
import subprocess
import sys
import tempfile

repo = Path(sys.argv[1])
tool = repo / 'tools/b48_fc_position.py'

def make(path, extra):
    main = []
    sub = []
    for i in range(76828):
        pc = 'C000' if i == 0 else ('C012' if i == 76570 else '1234')
        main.append(f'{i+1} {i*10+5} 0 main IN 00FC A7 {pc}')
        if i != 76571:
            sub.append(f'{len(sub)+1} {i*10+1} 0 sub OUT 00FD B8 1234')
        if extra and i == 76570:
            sub.append(f'{len(sub)+1} {i*10+2} 0 sub OUT 00FD B8 1234')
    path.write_text('# main\n' + '\n'.join(main) + f'\n# 取りこぼし: 0件 / 総イベント数: {len(main)}件\n# sub\n' + '\n'.join(sub) + f'\n# 取りこぼし: 0件 / 総イベント数: {len(sub)}件\n')

with tempfile.TemporaryDirectory() as d:
    a, b = Path(d) / 'a', Path(d) / 'b'
    make(a, True)
    make(b, False)
    def run(*args):
        return subprocess.run([sys.executable, str(tool), *map(str, args)], capture_output=True, text=True)
    result = run(a, b)
    assert result.returncode == 0 and not result.stderr
    assert 'at 76570 ok=76572 sk=76571 ok-issuer=C012 sk-issuer=C012' in result.stdout
    assert 'at 76569 ok=76570 sk=76570 ok-issuer=rom sk-issuer=rom' in result.stdout
    assert 'offset-change 0 0\n' in result.stdout and 'offset-change 76570 1\n' in result.stdout
    assert 'step arm=OO range=76315-76827 0=1 1=510 2=1 other=0' in result.stdout
    assert 'issuer arm=OO range=76570-76827 rom=257 ram=1' in result.stdout
    assert all(secret not in result.stdout + result.stderr for secret in ('A7', 'B8', '1234'))
    same = run(b, b)
    assert same.returncode == 0 and 'offset-change 0 0\n' in same.stdout
    assert same.stdout.count('offset-change ') == 1
    text = a.read_text()
    a.write_text(text.replace('1 1 0 sub', '1 5 0 sub'))
    bad = run(a, b)
    assert bad.returncode == 1 and not bad.stdout and not bad.stderr
    bad = run(a)
    assert bad.returncode == 1 and not bad.stdout and not bad.stderr
print('B48 自己検査成功')
PY
