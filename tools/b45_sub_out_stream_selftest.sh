#!/usr/bin/env bash
set -euo pipefail
repo="$(cd "$(dirname "$0")/.." && pwd)"
PYTHONPATH="$repo/tools" python3 - <<'PY'
import contextlib
import io
from pathlib import Path
import subprocess
import sys
import tempfile
from b45_sub_out_stream import compare, read

with tempfile.TemporaryDirectory() as d:
    d = Path(d)
    # ブロックは先行位置と他方の別位置にだけ現れる。
    block = bytes(range(132))
    left = bytearray([238]) * (76570 + 132)
    right = bytearray([239]) * (76570 + 132)
    left[100:232] = block
    left[76570:] = block
    right[300:432] = block
    right[76570:] = bytes(reversed(block))
    def log(path, main, sub):
        with path.open('w') as f:
            f.write('# main\n')
            for i, value in enumerate(main, 1):
                f.write(f'{i} 0 0 main IN 00FC {value:02X} C000\n')
            f.write(f'# 取りこぼし: 0件 / 総イベント数: {len(main)}件\n# sub\n')
            for i, (port, value, pc) in enumerate(sub, 1):
                f.write(f'{i} 0 0 sub OUT {port:04X} {value:02X} {pc:04X}\n')
            f.write(f'# 取りこぼし: 0件 / 総イベント数: {len(sub)}件\n')
    a, b = d/'a', d/'b'
    log(a, left, [(0xFD, 0xA5, 0x1234), (0xFD, 0xA5, 0x2345)])
    log(b, right, [(0xFD, 0xA5, 0x1234), (0xFD, 0x5A, 0x3456)])
    rows = compare(read(a), read(b))
    assert rows[0] == 'port OUT 00FD compared=2 differ=1 first=1 left=0 right=0'
    assert rows[1] == 'first-out-difference: 00FD 1 hi hi 2345 3456'
    assert 'block 左 self-match 100' in rows and 'block 左 other-match 300' in rows
    same = compare(read(a), read(a))
    assert same[1] == 'first-out-difference: none'
    assert 'block 右 other-match none' in rows
    log(b, right, [(0xFD, 0xA5, 0x1234), (0xFD, 0x5A, 0x1FFF)])
    assert compare(read(a), read(b))[1] == 'first-out-difference: 00FD 1 hi lo 2345 lo'
    tool = Path(__import__('b45_sub_out_stream').__file__)
    result = subprocess.run([sys.executable, str(tool), str(a), str(b)], capture_output=True, text=True)
    assert result.returncode == 0 and 'A5' not in result.stdout + result.stderr and '5A' not in result.stdout + result.stderr and '1FFF' not in result.stdout + result.stderr
    b.write_text('A5 5A 1FFF')
    result = subprocess.run([sys.executable, str(tool), str(a), str(b)], capture_output=True, text=True)
    assert result.returncode != 0 and 'A5' not in result.stdout + result.stderr and '5A' not in result.stdout + result.stderr and '1FFF' not in result.stdout + result.stderr
print('B45 自己検査成功')
PY
