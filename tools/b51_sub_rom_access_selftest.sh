#!/usr/bin/env bash
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
VENDOR="$(cd "$REPO/.." && pwd)/vendor/quasi88-libretro"
CORE="${PC88_SUB_READ_CORE:-$(ls "$VENDOR"/quasi88_libretro.* 2>/dev/null | head -1)}"
CORE_SRC="${PC88_SUB_READ_CORE_SRC:-$VENDOR/src}"
if [[ ! -f "$CORE" ]]; then echo "B51: コアがありません" >&2; exit 1; fi
mkdir -p "$REPO/tmp/b51-work"
WORK="$(mktemp -d "$REPO/tmp/b51-work/selftest.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT
cc -O2 -std=c99 -D_POSIX_C_SOURCE=200809L -I"$CORE_SRC/LIBRETRO/libretro-common/include" -I"$REPO/tools/harness/core" "$REPO/tools/harness/frontend/main.c" -ldl -o "$WORK/front"
python3 - "$WORK/rom" <<'PY'
import pathlib, sys
p = pathlib.Path(sys.argv[1]); p.mkdir()
main = bytearray(0x8000); main[:4] = bytes.fromhex('db fc 18 fe')
sub = bytearray(0x800)
# RAM code writes 5400, then jumps back to ROM; ROM repeatedly reads all three classes.
ram = bytes.fromhex('3e a5 32 00 54 3a 00 52 c3 30 00')
boot = bytes.fromhex('31 00 60 3e a5 32 00 51 21 00 02 11 00 40 01') + bytes([len(ram), 0]) + bytes.fromhex('ed b0 c3 00 40')
sub[:len(boot)] = boot
loop = bytes.fromhex('3a 00 53 3a 00 53 3a 01 53 3a 02 53 3a 00 51 3a 00 54 3a 00 01 3e a5 c3 30 00')
sub[0x30:0x30+len(loop)] = loop
sub[0x200:0x200+len(ram)] = ram
(p/'N88.ROM').write_bytes(main); (p/'DISK.ROM').write_bytes(sub)
PY
for mode in off on outside; do
  args=()
  case "$mode" in on) args=(--sub-rom-access-log "$WORK/log" --sub-rom-access-window 0,10000000);; outside) args=(--sub-rom-access-log "$WORK/outside" --sub-rom-access-window 100000000,100000001);; esac
  "$WORK/front" --core "$CORE" --rom-dir "$WORK/rom" --frames 20 --sub-cpu-mode 2 --out "$WORK/$mode" --boundary-log "$WORK/b-$mode" --io-log "$WORK/io-$mode" ${args[@]+"${args[@]}"} >"$WORK/stdout-$mode" 2>"$WORK/stderr-$mode"
done
cmp "$WORK/off" "$WORK/on"
cmp "$WORK/b-off" "$WORK/b-on"
cmp "$WORK/io-off" "$WORK/io-on"
PYTHONPATH="$REPO/tools" python3 - "$WORK" <<'PYCODE'
from pathlib import Path
import sys
from b51_whitelist import filter_line
w = Path(sys.argv[1]); lines = (w/'log').read_text().splitlines()
assert lines[-1] == 'dropped=0 complete=1'
assert any(x.startswith('A R 0100-0100 ') for x in lines)
assert any(x.startswith('A W 5100-5100 ') for x in lines)
assert any(x.startswith('A R 5300-5300 同じ 2 ') for x in lines)
assert any(x.startswith('A R 5301-5302 増える 2 ') for x in lines)
assert all(filter_line(x) is not None for x in lines)
assert not any(x.startswith('A R 5200-') for x in lines)
assert (w/'outside').read_text() == 'dropped=0 complete=1\n'
assert filter_line('A R 0100-0100 同じ 1 3') == 'A R rom-short 1 3'
assert filter_line('A R 0100-010F 増える 16 3') == 'A R 0100-010F 増える 16 3'
assert filter_line('A R 0100-0100 同じ 1 3 A5') is None
PYCODE
cat > "$WORK/unit.c" <<'C'
#include <assert.h>
#include "q88h_sub_rom_access.h"
int main(void) {
 retro_q88h_sub_rom_access_reset(); retro_q88h_sub_rom_access_config(1,1);
 q88h_sra_instr(0); q88h_sra_fc(); q88h_sra_record('R', 1);
 q88h_sra_fc(); q88h_sra_suppress(1); q88h_sra_record('R', 2); q88h_sra_suppress(0);
 q88h_sra_instr(0x2000); q88h_sra_record('W', 3); q88h_sra_instr(0);
 assert(retro_q88h_sub_rom_access()->count == 0);
 q88h_sra_record('R', 4); q88h_sra_record('W', 5);
 assert(retro_q88h_sub_rom_access()->count == 1 && retro_q88h_sub_rom_access()->dropped == 1);
 return 0;
}
C
cc -DQ88H_SRA_CAPACITY=1 -I"$REPO/tools/harness/core" "$WORK/unit.c" "$REPO/tools/harness/core/q88h_sub_rom_access.c" -o "$WORK/unit"
"$WORK/unit"
echo 'B51 自己検査 PASS'
