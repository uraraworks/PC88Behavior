#!/usr/bin/env bash
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
VENDOR="$(cd "$REPO/.." && pwd)/vendor/quasi88-libretro"
CORE="${PC88_SUB_READ_CORE:-$(ls "$VENDOR"/quasi88_libretro.* 2>/dev/null | head -1)}"
CORE_SRC="${PC88_SUB_READ_CORE_SRC:-$VENDOR/src}"
if [[ ! -f "$CORE" ]]; then echo 'B38: コアがありません' >&2; exit 1; fi
mkdir -p "$REPO/tmp/b38-work"
WORK="$(mktemp -d "$REPO/tmp/b38-work/selftest.XXXXXX")"
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
for mode in off on; do
  args=()
  if [[ "$mode" == on ]]; then args=(--sub-snapshot "$WORK/snap" --sub-snapshot-at-fc 100); fi
  "$WORK/front" --core "$CORE" --rom-dir "$WORK/rom" --frames 20 --sub-cpu-mode 2 --out "$WORK/$mode" --boundary-log "$WORK/b-$mode" --io-log "$WORK/io-$mode" ${args[@]+"${args[@]}"} >"$WORK/stdout-$mode" 2>"$WORK/stderr-$mode"
done
cmp "$WORK/off" "$WORK/on"
cmp "$WORK/b-off" "$WORK/b-on"
cmp "$WORK/io-off" "$WORK/io-on"
python3 - "$WORK" "$REPO/tools" <<'PYTEST'
import pathlib, sys
sys.path.insert(0, sys.argv[2])
from b38_sub_snapshot_compare import read, compare
w = pathlib.Path(sys.argv[1]); raw = bytearray((w / 'snap').read_bytes())
a = read(w / 'snap')
assert not any(x.startswith('D ') for x in compare(a, a))
raw[8 + 0x123] ^= 0x5a
raw[-36] ^= 0xa5
(w / 'changed').write_bytes(raw)
lines = compare(a, read(w / 'changed'))
assert [x for x in lines if x.startswith('D ')] == ['D 4123-4123 unwritten unwritten 1']
assert [x for x in lines if x.endswith(' differ')] == ['REG AF differ']
assert lines[-1] == 'total differ=1'
PYTEST
python3 "$REPO/tools/b38_sub_snapshot_compare.py" "$WORK/snap" "$WORK/changed" >"$WORK/compare" 2>"$WORK/err"
python3 - "$WORK/compare" <<'PYTEST'
import pathlib, re, sys
lines = pathlib.Path(sys.argv[1]).read_text().splitlines()
assert lines[0] == '# 識別子: G1'
assert all(re.fullmatch(r'D [0-9A-F]{4}-[0-9A-F]{4} (?:unwritten|rom-written|ram-written) (?:unwritten|rom-written|ram-written) [0-9]+|REG (?:AF|BC|DE|HL|IX|IY|PC|SP|AF1|BC1|DE1|HL1|I|R|IFF|IFF2|IM|HALT) (?:same|differ)|total differ=[0-9]+', line) for line in lines[1:])
assert 'D 4123-4123 unwritten unwritten 1' in lines
PYTEST
printf 'secret-marker' > "$WORK/invalid"
if python3 "$REPO/tools/b38_sub_snapshot_compare.py" "$WORK/invalid" "$WORK/snap" >"$WORK/badout" 2>"$WORK/baderr"; then exit 1; fi
! grep -q 'secret-marker' "$WORK/badout" "$WORK/baderr"
[[ ! -s "$WORK/err" ]]
printf 'B38 自己検査 PASS\n'
