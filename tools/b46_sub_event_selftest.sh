#!/usr/bin/env bash
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
VENDOR="$(cd "$REPO/.." && pwd)/vendor/quasi88-libretro"
CORE="${PC88_SUB_READ_CORE:-$(ls "$VENDOR"/quasi88_libretro.* 2>/dev/null | head -1)}"
CORE_SRC="${PC88_SUB_READ_CORE_SRC:-$VENDOR/src}"
if [[ ! -f "$CORE" ]]; then echo 'B46: コアがありません' >&2; exit 1; fi
mkdir -p "$REPO/tmp/b46-work"
WORK="$(mktemp -d "$REPO/tmp/b46-work/selftest.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT
cc -O2 -std=c99 -D_POSIX_C_SOURCE=200809L -I"$CORE_SRC/LIBRETRO/libretro-common/include" -I"$REPO/tools/harness/core" "$REPO/tools/harness/frontend/main.c" -ldl -o "$WORK/front"
python3 - "$WORK/rom" <<'PY'
import pathlib, sys
p = pathlib.Path(sys.argv[1]); p.mkdir()
main = bytearray(0x8000); main[:4] = bytes.fromhex('db fc 18 fc')
sub = bytearray(0x800)
# RAM 内で即値、データ読み書き、IN、OUT を繰り返す。
ram = bytes.fromhex('3e a5 32 00 50 3a 00 50 db f0 d3 f1 c3 00 40')
boot = bytes.fromhex('31 00 60 21 00 02 11 00 40 01') + bytes([len(ram), 0]) + bytes.fromhex('ed b0 c3 00 40')
sub[:len(boot)] = boot; sub[0x200:0x200+len(ram)] = ram
(p/'N88.ROM').write_bytes(main); (p/'DISK.ROM').write_bytes(sub)
PY
for mode in off on; do
  args=()
  if [[ "$mode" == on ]]; then args=(--sub-event-log "$WORK/event"); fi
  "$WORK/front" --core "$CORE" --rom-dir "$WORK/rom" --frames 20 --sub-cpu-mode 2 --out "$WORK/$mode" --boundary-log "$WORK/b-$mode" --io-log "$WORK/io-$mode" ${args[@]+"${args[@]}"} >"$WORK/stdout-$mode" 2>"$WORK/stderr-$mode"
done
cmp "$WORK/off" "$WORK/on"
cmp "$WORK/b-off" "$WORK/b-on"
cmp "$WORK/io-off" "$WORK/io-on"
PYTHONPATH="$REPO/tools" python3 - "$WORK" <<'PY'
from pathlib import Path
import sys
from b46_sub_event_compare import MAGIC, RECORD, records, compare
w = Path(sys.argv[1]); event = w/'event'
a = list(records(event))
assert a and {r[0] for r in a} == {'R', 'W', 'O'}
assert all(r[1] >= 0x4000 for r in a)
assert all((r[0], r[2]) in {('R', 0x5000), ('W', 0x5000), ('O', 0xf1)} for r in a)
assert compare(event, event)[2] == 'first-diff none'
def write(name, rows):
    path = w/name
    with path.open('wb') as f:
        f.write(MAGIC)
        for kind, pc, addr, value, fc in rows:
            f.write(RECORD.pack(kind.encode(), pc, addr, value, fc))
    return path
base = [('R', 0x4000, 0x5000, 0xa5, 1), ('W', 0x4001, 0x5001, 0xa5, 2), ('O', 0x4002, 0xf1, 0xa5, 3)]
l = write('left', base)
for i in range(3):
    changed = list(base); row = list(changed[i]); row[3] = 0x7b; changed[i] = tuple(row)
    result = '\n'.join(compare(l, write('right', changed)))
    assert f'first-diff {i} value ' in result
    assert 'A5' not in result and '7B' not in result
changed = list(base); row = list(changed[0]); row[2] += 1; changed[0] = tuple(row)
assert 'first-diff 0 addr ' in '\n'.join(compare(l, write('right', changed)))
changed = [(k,p,a,v,f+100) for k,p,a,v,f in base]
assert compare(l, write('right', changed))[2] == 'first-diff none'
PY
printf 'secret-marker' > "$WORK/invalid"
if python3 "$REPO/tools/b46_sub_event_compare.py" "$WORK/invalid" "$WORK/event" >"$WORK/badout" 2>"$WORK/baderr"; then exit 1; fi
! grep -q 'secret-marker' "$WORK/badout" "$WORK/baderr"
printf 'B46 自己検査 PASS\n'
