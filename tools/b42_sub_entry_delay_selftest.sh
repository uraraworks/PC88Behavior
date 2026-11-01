#!/usr/bin/env bash
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
git -C "$REPO" show ff113bf:src/l3_service/make_subrom.py > "$work/reference.py"
python3 "$work/reference.py" "$work/reference" > /dev/null
python3 "$REPO/src/l3_service/make_subrom.py" "$work/current" > /dev/null
cmp -s "$work/reference/DISK.ROM" "$work/current/DISK.ROM"
PYTHONPATH="$REPO/src/l3_service" python3 - <<'PY'
import make_subrom as m
for n in (1,8,16,24,32,48,64,128,255):
    rom, used = m.build(dry_run_sub_entry_delay=n)
    a = m._LAST_ASM
    assert used <= m.SUB_ROM_FETCH_WINDOW
    p = a.labels['_sub_entry_delay']
    assert rom[p-2:p+5] == bytes((6,n,16,254,0x4f,0xaf,0x47))
    # 実際の入口命令を JP (HL) まで逐次実行し、受け渡しを検査する。
    pc = p - 2
    A, B, C, D, E, SP = 0x0d, 0, 0, 1, 1, 0
    while True:
        op = rom[pc]; pc += 1
        if op == 0x06:
            B = rom[pc]; pc += 1
        elif op == 0x10:
            displacement = int.from_bytes(rom[pc:pc+1], 'little', signed=True); pc += 1
            B = (B - 1) & 255
            if B: pc += displacement
        elif op == 0x4f: C = A
        elif op == 0xaf: A = 0
        elif op == 0x47: B = A
        elif op == 0x57: D = A
        elif op == 0x5f: E = A
        elif op == 0x31:
            SP = int.from_bytes(rom[pc:pc+2], 'little'); pc += 2
        elif op == 0xe9: break
        else: raise AssertionError('予期しない入口命令')
    assert (A, B, C, D, E, SP) == (0, 0, 0x0d, 0, 0, 0x8000)
print('B42 自己検査 OK')
PY
