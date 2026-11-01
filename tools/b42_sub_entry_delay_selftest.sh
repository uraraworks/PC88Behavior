#!/usr/bin/env bash
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
python3 "$REPO/src/l3_service/make_subrom.py" "$work/current" > /dev/null
python3 "$REPO/src/build_main_rom.py" "$work/distribution" > /dev/null
cmp -s "$work/distribution/DISK.ROM" "$work/current/DISK.ROM"
PYTHONPATH="$REPO/src/l3_service" python3 - <<'PY'
import make_subrom as m
for n in (1,8,16,24,32,48,64,128,255):
    rom, used = m.build(dry_run_sub_entry_delay=n)
    a = m._LAST_ASM
    assert used <= m.SUB_ROM_FETCH_WINDOW
    p = a.labels['_sub_entry_delay']
    assert rom[p-2:p+5] == bytes((6,n,16,254,0x31,0x00,0x80))
    # 実際の入口命令を JP (HL) まで逐次実行し、受け渡しを検査する。
    pc = p - 2
    A, F, B, C, D, E, SP = 0x0d, 0, 0, 0, 1, 1, 0
    while True:
        op = rom[pc]; pc += 1
        if op == 0x06:
            B = rom[pc]; pc += 1
        elif op == 0x10:
            displacement = int.from_bytes(rom[pc:pc+1], 'little', signed=True); pc += 1
            B = (B - 1) & 255
            if B: pc += displacement
        elif op == 0x31:
            SP = int.from_bytes(rom[pc:pc+2], 'little'); pc += 2
        elif op == 0x01:
            C, B = rom[pc:pc+2]; pc += 2
        elif op == 0xc5:
            SP -= 2; stack = (B, C)
        elif op == 0xf1:
            A, F = stack; SP += 2
        elif op == 0x0e: C = rom[pc]; pc += 1
        elif op == 0x50: D = B
        elif op == 0x58: E = B
        elif op == 0xe9: break
        else: raise AssertionError('予期しない入口命令')
    assert (A, F, B, C, D, E, SP) == (0, 0xc1, 0, 0x0d, 0, 0, 0x8000)
print('B42 自己検査 OK')
PY
