#!/usr/bin/env bash
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
VENDOR="$(cd "$REPO/.." && pwd)/vendor/quasi88-libretro"
CORE="${PC88_SUB_READ_CORE:-$(ls "$VENDOR"/quasi88_libretro.* 2>/dev/null | head -1)}"
CORE_SRC="${PC88_SUB_READ_CORE_SRC:-$VENDOR/src}"
if [[ ! -f "$CORE" ]]; then echo 'B41: コアがありません' >&2; exit 1; fi
if [[ ! -f "$CORE_SRC/LIBRETRO/libretro-common/include/libretro.h" ]]; then echo 'B41: コアのソースがありません' >&2; exit 1; fi
mkdir -p "$REPO/tmp/b41-work"
WORK="$(mktemp -d "$REPO/tmp/b41-work/selftest.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT
cc -O2 -std=c99 -D_POSIX_C_SOURCE=200809L -I"$CORE_SRC/LIBRETRO/libretro-common/include" -I"$REPO/tools/harness/core" "$REPO/tools/harness/frontend/main.c" -ldl -o "$WORK/front"
python3 - "$WORK/rom" <<'PY'
import pathlib, sys
p = pathlib.Path(sys.argv[1]); p.mkdir()
main = bytearray(0x8000); main[:4] = bytes.fromhex('db fc 18 fc')
sub = bytearray(0x800)
ram = bytes.fromhex('c3 60 00 c3 50 00')
boot = bytes.fromhex('31 00 60 01 34 12 11 00 00 21 00 02 11 00 40 01') + bytes([len(ram), 0]) + bytes.fromhex('ed b0 01 34 12 c3 50 00')
sub[:len(boot)] = boot
sub[0x50:0x57] = bytes.fromhex('11 00 40 21 00 40 e9')
sub[0x60:0x68] = bytes.fromhex('11 34 12 21 03 40 e5 c9')
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
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$REPO/tools" python3 - "$WORK" <<'PY'
import pathlib, subprocess, sys
from b41_cross_origin import read, render
w = pathlib.Path(sys.argv[1]); rows = read(w/'reg'); lines = render('OO', rows)
assert len(lines) > 4
assert lines[:4] == ['O OO 0 4000 1 0 no yes no', 'O OO 1 4003 2 2 no no yes', 'O OO 2 4000 1 0 no yes no', 'O OO 3 4003 2 2 no no yes']
r = [0]*18; r[6] = 0x4000; r[7] = 0x6000
assert render('SS', [(tuple(r), 0x55, 0x6000)])[0] == 'O SS 0 4000 1 0 yes yes yes'
r[2] = 0xA51B; r[7] = 0x6005
assert render('SS', [(tuple(r), 0x55, 0x6000)])[0].endswith('other no no no')
p = subprocess.run([sys.executable, str(pathlib.Path(__import__('b41_cross_origin').__file__)), str(w/'reg'), str(w/'reg')], capture_output=True, text=True)
assert p.returncode == 0
sample = '\n'.join(p.stdout.splitlines()[:5])
assert all(x not in sample for x in ('0056', '0067', '1234', '6000'))
(w/'bad').write_text('secret-marker\n')
p = subprocess.run([sys.executable, str(pathlib.Path(__import__('b41_cross_origin').__file__)), str(w/'bad'), str(w/'reg')], capture_output=True, text=True)
assert p.returncode == 1 and 'secret-marker' not in p.stdout + p.stderr
PY
printf 'B41 自己検査 PASS\n'
