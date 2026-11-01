#!/usr/bin/env bash
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
VENDOR="$(cd "$REPO/.." && pwd)/vendor/quasi88-libretro"
CORE="${PC88_SUB_READ_CORE:-$(ls "$VENDOR"/quasi88_libretro.* 2>/dev/null | head -1)}"
CORE_SRC="${PC88_SUB_READ_CORE_SRC:-$VENDOR/src}"
mkdir -p "$REPO/tmp/b37-work"
WORK="$(mktemp -d "$REPO/tmp/b37-work/selftest.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT
cc -O2 -std=c99 -D_POSIX_C_SOURCE=200809L -I"$CORE_SRC/LIBRETRO/libretro-common/include" -I"$REPO/tools/harness/core" "$REPO/tools/harness/frontend/main.c" -ldl -o "$WORK/front"
python3 - "$WORK/rom" <<'PY'
import pathlib, sys
p = pathlib.Path(sys.argv[1]); p.mkdir()
main = bytearray(0x8000); main[:4] = bytes.fromhex('db fc 18 fc')
sub = bytearray(0x800)
# RAM code writes 5400, then jumps back to ROM; ROM repeatedly reads all three classes.
ram = bytes.fromhex('3e a5 32 00 54 3a 00 52 c3 30 00')
boot = bytes.fromhex('31 00 60 3e a5 32 00 51 21 00 02 11 00 40 01') + bytes([len(ram), 0]) + bytes.fromhex('ed b0 c3 00 40')
sub[:len(boot)] = boot
sub[0x30:0x30+17] = bytes.fromhex('3a 00 53 3a 00 51 3a 00 54 3a 00 01 3e a5 c3 30 00')
sub[0x200:0x200+len(ram)] = ram
(p/'N88.ROM').write_bytes(main); (p/'DISK.ROM').write_bytes(sub)
PY
for mode in off on outside; do
  args=()
  case "$mode" in on) args=(--sub-rom-read-log "$WORK/log" --sub-rom-read-window 0,10000000);; outside) args=(--sub-rom-read-log "$WORK/outside" --sub-rom-read-window 100000000,100000001);; esac
  "$WORK/front" --core "$CORE" --rom-dir "$WORK/rom" --frames 20 --sub-cpu-mode 2 --out "$WORK/$mode" --boundary-log "$WORK/b-$mode" ${args[@]+"${args[@]}"} >"$WORK/stdout-$mode" 2>"$WORK/stderr-$mode"
done
cmp "$WORK/off" "$WORK/on"
cmp "$WORK/b-off" "$WORK/b-on"
python3 - "$WORK/log" "$WORK/outside" "$REPO/tools" <<'PY'
import sys
sys.path.insert(0, sys.argv[3])
from b37_whitelist_sub_rom_reads import valid
lines = open(sys.argv[1]).read().splitlines()
assert all(map(valid, lines)) and lines[-1] == 'dropped=0 complete=1'
for addr, cls in [('5300','unwritten'),('5100','rom-written'),('5400','ram-written')]:
    assert any(f'{addr}-{addr} {cls}' in x for x in lines), (addr, cls)
assert all(not x.startswith('W ') or all(z not in x for z in ('4000-', '0100-', '0030-', '5200-')) for x in lines)
assert open(sys.argv[2]).read() == 'dropped=0 complete=1\n'
PY
cat > "$WORK/overflow.c" <<'C'
#include <assert.h>
#include "q88h_sub_rom_read.h"
int main(void) {
 retro_q88h_sub_rom_read_reset(); retro_q88h_sub_rom_read_config(0,1);
 q88h_srr_fc(); q88h_srr_instr(0);
 q88h_srr_suppress(1); q88h_srr_data(0x5000); q88h_srr_suppress(0);
 assert(retro_q88h_sub_rom_read()->count == 0);
 q88h_srr_data(0x5000); q88h_srr_data(0x5001);
 assert(retro_q88h_sub_rom_read()->count == 1 && retro_q88h_sub_rom_read()->dropped == 1);
 retro_q88h_sub_rom_read_reset(); retro_q88h_sub_rom_read_config(1,1);
 q88h_srr_instr(0x2000); q88h_srr_write(0x5000); q88h_srr_fc();
 q88h_srr_instr(0); q88h_srr_data(0x5000);
 assert(retro_q88h_sub_rom_read()->count == 0);
 q88h_srr_fc(); q88h_srr_data(0x5000);
 assert(retro_q88h_sub_rom_read()->count == 1 && retro_q88h_sub_rom_read()->events[0].writer == 2);
 return 0;
}
C
cc -DQ88H_SRR_CAPACITY=1 -I"$REPO/tools/harness/core" "$WORK/overflow.c" "$REPO/tools/harness/core/q88h_sub_rom_read.c" -o "$WORK/overflow"
"$WORK/overflow"
python3 "$REPO/tools/b37_whitelist_sub_rom_reads.py" "$WORK/log" --out "$WORK/filtered"
python3 "$REPO/tools/b37_sub_rom_reads_compare.py" "$WORK/filtered" "$WORK/filtered" | grep -qx none
printf 'secret\nW 0 1000-1000 unwritten 同じ 1\n' > "$WORK/bad"
python3 "$REPO/tools/b37_whitelist_sub_rom_reads.py" "$WORK/bad" --out "$WORK/clean" 2>"$WORK/dropped"
grep -qx '除外: 2 行' "$WORK/dropped"
echo 'B37 自己検査 PASS'
