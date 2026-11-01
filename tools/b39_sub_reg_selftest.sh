#!/usr/bin/env bash
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
VENDOR="$(cd "$REPO/.." && pwd)/vendor/quasi88-libretro"
CORE="${PC88_SUB_READ_CORE:-$(ls "$VENDOR"/quasi88_libretro.* 2>/dev/null | head -1)}"
CORE_SRC="${PC88_SUB_READ_CORE_SRC:-$VENDOR/src}"
if [[ ! -f "$CORE" ]]; then echo 'B39: コアがありません' >&2; exit 1; fi
mkdir -p "$REPO/tmp/b39-work"
WORK="$(mktemp -d "$REPO/tmp/b39-work/selftest.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT
cc -O2 -std=c99 -D_POSIX_C_SOURCE=200809L -I"$CORE_SRC/LIBRETRO/libretro-common/include" -I"$REPO/tools/harness/core" "$REPO/tools/harness/frontend/main.c" -ldl -o "$WORK/front"
python3 - "$WORK/rom" <<'PY'
import pathlib, sys
p = pathlib.Path(sys.argv[1]); p.mkdir()
main = bytearray(0x8000); main[:4] = bytes.fromhex('db fc 18 fc')
sub = bytearray(0x800)
ram = bytes.fromhex('5f cb 5f ed 5f ed 57 c3 30 00')
boot = bytes.fromhex('31 00 60 ed 5f 21 00 02 11 00 40 01') + bytes([len(ram), 0]) + bytes.fromhex('ed b0 c3 00 40')
sub[:len(boot)] = boot
sub[0x30:0x33] = bytes.fromhex('c3 00 40')
sub[0x200:0x200+len(ram)] = ram
(p/'N88.ROM').write_bytes(main); (p/'DISK.ROM').write_bytes(sub)
PY
for mode in off on; do
  args=()
  if [[ "$mode" == on ]]; then args=(--sub-reg-log "$WORK/reg"); fi
  "$WORK/front" --core "$CORE" --rom-dir "$WORK/rom" --frames 20 --sub-cpu-mode 2 --out "$WORK/$mode" --boundary-log "$WORK/b-$mode" --io-log "$WORK/io-$mode" ${args[@]+"${args[@]}"} >"$WORK/stdout-$mode" 2>"$WORK/stderr-$mode"
done
cmp "$WORK/off" "$WORK/on"
cmp "$WORK/b-off" "$WORK/b-on"
cmp "$WORK/io-off" "$WORK/io-on"
python3 - "$WORK" "$REPO/tools" <<'PY'
import pathlib, sys
sys.path.insert(0, sys.argv[2])
from b39_sub_reg_compare import read, compare
w = pathlib.Path(sys.argv[1]); a = read(w/'reg')
assert a['C'] and a['F'] and a['R'] and a['I']
assert set(a['R']) == {0x4003} and set(a['I']) == {0x4005}
lines = compare(a, a)
assert all(' none' in x for x in lines if 'first-' in x)
text = (w/'reg').read_text().splitlines()
for i, line in enumerate(text):
    if line.startswith('C '):
        p = line.split(); p[2] = 'A51B'; text[i] = ' '.join(p); break
for i, line in enumerate(text):
    if line.startswith('F '):
        p = line.split(); p[4] = 'A51B'; text[i] = ' '.join(p); break
(w/'changed').write_text('\n'.join(text)+'\n')
lines = compare(a, read(w/'changed'))
assert any(x.startswith('cross first-reg-differ BC 0 ') for x in lines)
assert any(x.startswith('fc first-reg-differ HL 0 ') for x in lines)
assert not any('A51B' in x for x in lines)
# 短い合成記録で PC 条件と元の F 行番号を確かめる。
def row(pc, bc, hl):
    values = [0] * 18
    values[6], values[1], values[3] = pc, bc, hl
    return 'F ' + ' '.join(f'{v:04X}' for v in values)
left = [row(0x1000, 1, 1), row(0x2000, 1, 1), row(0x2001, 1, 1), row(0x2002, 1, 1)]
right = [row(0x1000, 2, 2), row(0x2001, 2, 2), row(0x2001, 2, 1), row(0x2002, 1, 2)]
for name, rows in (('synthetic-left', left), ('synthetic-right', right)):
    (w/name).write_text('Q88REG1\n' + '\n'.join(rows) + '\nEND\n')
synthetic = compare(read(w/'synthetic-left'), read(w/'synthetic-right'))
assert 'fc first-reg-differ-same-pc BC 2' in synthetic
assert 'fc first-reg-differ-same-pc HL 3' in synthetic
assert 'fc last-reg-same-before BC 3' in synthetic
assert 'fc last-reg-same-before HL 2' in synthetic
# measure_b39.sh の同じ腕どうしの関門と同じ判定。
same = compare(read(w/'synthetic-left'), read(w/'synthetic-left'))
assert all(' none' in line for line in same if 'first-' in line)
assert 'fc first-reg-differ-same-pc BC none' in same
assert 'fc last-reg-same-before BC 3' in same
PY
python3 "$REPO/tools/b39_sub_reg_compare.py" "$WORK/reg" "$WORK/changed" >"$WORK/compare" 2>"$WORK/err"
! grep -q 'A51B' "$WORK/compare" "$WORK/err"
printf 'secret-marker' > "$WORK/invalid"
if python3 "$REPO/tools/b39_sub_reg_compare.py" "$WORK/invalid" "$WORK/reg" >"$WORK/badout" 2>"$WORK/baderr"; then exit 1; fi
! grep -q 'secret-marker' "$WORK/badout" "$WORK/baderr"
[[ ! -s "$WORK/err" ]]
printf 'B39 自己検査 PASS\n'
