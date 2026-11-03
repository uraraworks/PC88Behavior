#!/usr/bin/env bash
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
CORE="${PC88_SUB_READ_CORE:-$(ls "$REPO"/../vendor/quasi88-libretro/quasi88_libretro.* 2>/dev/null | head -1)}"
CORE_SRC="${PC88_SUB_READ_CORE_SRC:-$(cd "$REPO/.." && pwd)/vendor/quasi88-libretro/src}"
[[ -f "$CORE" && -f "$CORE_SRC/LIBRETRO/libretro-common/include/libretro.h" ]] || exit 1
mkdir -p "$REPO/tmp/b62-work"
WORK="$(mktemp -d "$REPO/tmp/b62-work/selftest.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT
cc -O2 -std=c99 -D_POSIX_C_SOURCE=200809L -I"$CORE_SRC/LIBRETRO/libretro-common/include" -I"$REPO/tools/harness/core" "$REPO/tools/harness/frontend/main.c" -ldl -o "$WORK/front"
python3 - "$WORK/rom" <<'PY'
import pathlib, sys
p = pathlib.Path(sys.argv[1]); p.mkdir()
main = bytearray(0x8000)
ram = bytes.fromhex('3e a5 32 00 90 3a 00 90 db f0 d3 f1 c3 00 80')
boot = bytes.fromhex('31 00 a0 21 00 02 11 00 80 01') + bytes([len(ram), 0]) + bytes.fromhex('ed b0 c3 00 80')
main[:len(boot)] = boot; main[0x200:0x200+len(ram)] = ram
(p/'N88.ROM').write_bytes(main); (p/'DISK.ROM').write_bytes(bytes(0x800))
PY
for mode in off on; do
  args=()
  if [[ "$mode" == on ]]; then args=(--main-event-log "$WORK/event" --main-event-from-frame 10); fi
  "$WORK/front" --core "$CORE" --rom-dir "$WORK/rom" --frames 20 --out "$WORK/$mode" --boundary-log "$WORK/b-$mode" --io-log "$WORK/io-$mode" ${args[@]+"${args[@]}"} >"$WORK/stdout-$mode" 2>"$WORK/stderr-$mode"
done
cmp "$WORK/off" "$WORK/on"
cmp "$WORK/b-off" "$WORK/b-on"
cmp "$WORK/io-off" "$WORK/io-on"
PYTHONPATH="$REPO/tools" python3 - "$WORK" <<'PY'
from pathlib import Path
import sys
from b62_main_event_compare import MAGIC, RECORD, records, compare
w = Path(sys.argv[1]); event = w/'event'
a = list(records(event))
assert a and {r[0] for r in a} == {'R', 'W', 'I', 'O'}
assert all(r[1] >= 0x8000 and r[4] >= 10 for r in a)
assert all((r[0], r[2]) in {('R', 0x9000), ('W', 0x9000), ('I', 0xf0), ('O', 0xf1)} for r in a)
assert compare(event, event)[1] == 'first-diff none'
def write(name, rows):
    path = w/name
    with path.open('wb') as f:
        f.write(MAGIC)
        for kind, pc, addr, value, frame in rows:
            f.write(RECORD.pack(kind.encode(), pc, addr, value, frame))
    return path
base = [(k, 0x8000+i, 0x9000+i, 0xa5, i+10) for i,k in enumerate('RWIO')]
l = write('left', base)
for i in range(4):
    changed = list(base); row = list(changed[i]); row[3] = 0x7b; changed[i] = tuple(row)
    result = '\n'.join(compare(l, write('right', changed)))
    assert f'first-diff {i} value ' in result
    assert 'A5' not in result and '7B' not in result
changed = list(base); row = list(changed[0]); row[2] += 1; changed[0] = tuple(row)
assert 'first-diff 0 addr ' in '\n'.join(compare(l, write('right', changed)))
changed = [(k,p,a,v,f+100) for k,p,a,v,f in base]
assert compare(l, write('right', changed))[1] == 'first-diff none'
PY
printf 'secret-marker' > "$WORK/invalid"
if python3 "$REPO/tools/b62_main_event_compare.py" "$WORK/invalid" "$WORK/event" >"$WORK/badout" 2>"$WORK/baderr"; then exit 1; fi
! grep -q 'secret-marker' "$WORK/badout" "$WORK/baderr"
printf 'B62 自己検査 PASS\n'
