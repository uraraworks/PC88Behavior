#!/usr/bin/env bash
# 通信試験のみ。起動セクタ・集計器の完成検査ではない。
set -euo pipefail
repo="$(cd "$(dirname "$0")/.." && pwd)"
for name in ${!PC88_REF_@}; do unset "$name"; done
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
core="${PC88_CORE:-$(find "$repo/../vendor/quasi88-libretro" -maxdepth 1 -name 'quasi88_libretro.*' -type f | head -1)}"
front="${PC88_FRONTEND:-$repo/tools/harness/frontend/q88measure}"
python3 - "$repo" "$work" "$core" "$front" <<'PY'
import os, pathlib, re, subprocess, sys
repo, work, core, front = map(pathlib.Path, sys.argv[1:])
sys.path.insert(0, str(repo))
sys.path.insert(0, str(repo / 'tools'))
from src.l3_service import make_subrom
from b88_arms import arms
from b88_probe import generate
from b88_lab import main_rom

assert not any(k.startswith('PC88_REF_') for k in os.environ)
rom, _ = make_subrom.build()
assert len(list(arms())) == 130
for arm in arms():
    probe, labels = generate(arm)
    assert probe and labels['start'] < labels['returned'] < labels['negative'] < labels['positive']

def run(name, fault=False):
    arm = next(a for a in arms() if a['name'] == name)
    directory = work / (name + ('-fault' if fault else ''))
    directory.mkdir()
    (directory / 'N88.ROM').write_bytes(main_rom(arm, inject_fault=fault))
    (directory / 'DISK.ROM').write_bytes(rom)
    command = [str(front), '--core', str(core), '--rom-dir', str(directory),
               '--frames', '3000', '--sub-cpu-mode', '2', '--mem-write-log',
               str(directory / 'mem'), '--mem-write-range', '9000-9003']
    subprocess.run(command, check=True, stdout=subprocess.DEVNULL,
                   stderr=subprocess.DEVNULL, timeout=120)
    received = bytearray()
    done = failed = False
    log = (directory / 'mem').read_text()
    drops = re.findall(r'取りこぼし: (\d+)件', log)
    assert drops == ['0'], '記録の欠落'
    for line in log.splitlines():
        m = re.fullmatch(r'\s*\d+\s+\d+\s+[0-9A-Fa-f]+\s+(900[023])\s+([0-9A-Fa-f]{2})\s*', line)
        if m:
            addr, value = int(m[1], 16), int(m[2], 16)
            if addr == 0x9000: received.append(value)
            elif addr == 0x9002: done = value == 1
            else: failed = True
    assert done and not failed and len(received) == 12, '結果の読み出し失敗'
    return received

negative, positive = run('negative'), run('positive')
# 結果領域: 開始印、終了印、SP、HL、DE、BC、AF。
expected = bytes.fromhex('00 a5 00 7e 00 61 00 60 01 00 00 00')
positive_expected = bytes.fromhex('00 a5 00 7e 00 61 00 60 01 00 00 01')
assert negative == expected and positive == positive_expected, '対照結果の不一致'
faulty = run('negative', fault=True)
assert faulty != expected and faulty[4] == (expected[4] ^ 1), '1バイトの故障を検出できない'
print('B88 通信試験 PASS（起動セクタと集計は未検査）')
PY
