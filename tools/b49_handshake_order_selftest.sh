#!/usr/bin/env bash
set -euo pipefail
repo="$(cd "$(dirname "$0")/.." && pwd)"
PYTHONPATH="$repo/tools" python3 - "$repo" <<'PY'
from pathlib import Path
import subprocess
import sys
import tempfile

repo = Path(sys.argv[1])
tool = repo / 'tools/b49_handshake_order.py'
with tempfile.TemporaryDirectory() as directory:
    path = Path(directory) / 'io'
    main, sub = [], []
    def add(rows, cpu, clock, kind, port, value, pc):
        rows.append(f'{len(rows)+1} {clock} 0 {cpu} {kind} {port:04X} {value:02X} {pc:04X}')
    for i in range(76574):
        add(main, 'main', i * 10 + 5, 'IN', 0xFC, 0xA7, 0xC000 if i == 0 else 0x1234)
        if i >= 76545:
            add(sub, 'sub', i * 10 + 1, 'OUT', 0xFD, 0xB8, 0x1234)
            if i == 76570:
                add(main, 'main', i * 10 + 6, 'IN', 0xFE, 0xDA, 0x5678)
                add(sub, 'sub', i * 10 + 7, 'OUT', 0xFF, 0xEB, 0x5678)
                add(main, 'main', i * 10 + 8, 'IN', 0xFF, 0xCC, 0x5678)
                add(sub, 'sub', i * 10 + 9, 'OUT', 0xFE, 0xDD, 0x5678)
    for i in range(25):
        add(sub, 'sub', 765740 + i * 2, 'IN', 0xFB, 0xB8, 0x1234)
    def write():
        path.write_text('# main\n' + '\n'.join(main) + f'\n# 取りこぼし: 0件 / 総イベント数: {len(main)}件\n# sub\n' + '\n'.join(sub) + f'\n# 取りこぼし: 0件 / 総イベント数: {len(sub)}件\n')
    def run(*args):
        return subprocess.run([sys.executable, str(tool), str(path), *args], capture_output=True, text=True)
    write()
    result = run('--arm', 'OO')
    assert result.returncode == 0 and not result.stderr
    lines = result.stdout.splitlines()
    controls = [line for line in lines if '$FE' in line or '$FF' in line]
    assert controls == ['E OO 1 main IN $FE 3 A', 'E OO 1 sub OUT $FF 4 B', 'E OO 1 main IN $FF 3 C', 'E OO 1 sub OUT $FE 4 D']
    assert any('sub IN $FB 1 - x' in line or 'sub IN $FB 2 - x' in line for line in lines)
    assert all(secret not in result.stdout + result.stderr for secret in ('A7', 'B8', '1234', '5678', 'C000'))
    assert all(line.startswith('E OO ') for line in lines)
    window = run('--arm', 'SS', '--event-window', '0', '300')
    assert window.returncode == 0 and all(line.startswith('E SS ') for line in window.stdout.splitlines())
    assert run('--arm', 'OO', '--before-first-main-fd-0e', '200').returncode == 1
    add(main, 'main', 765900, 'OUT', 0xFD, 0x0E, 0x1234)
    write()
    before = run('--arm', 'OO', '--before-first-main-fd-0e', '200')
    assert before.returncode == 0 and '$FD' in before.stdout and '0E' not in before.stdout
    assert run('--arm', 'OO', '--event-window', '0', '999999').returncode == 1
    path.write_text(path.read_text().replace('取りこぼし: 0件', '取りこぼし: 1件', 1))
    bad = run('--arm', 'OO')
    assert bad.returncode == 1 and not bad.stdout and not bad.stderr
    assert run('--arm', 'SS', '--event-window', '0', '300').returncode == 1
    assert run('--arm', 'OO', '--before-first-main-fd-0e', '200').returncode == 1
    bad = run('--arm', 'invalid')
    assert bad.returncode == 1 and not bad.stdout and not bad.stderr
print('B49 自己検査成功')
PY
