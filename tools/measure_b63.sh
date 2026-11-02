#!/usr/bin/env bash
# 生記録は作業場に留め、事前登録の行だけを結果に書く。
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
: "${PC88_REF_ROM_DIR:?}" "${PC88_G1_DISK:?}" "${PC88_B63_WORK:?}"
[[ ! -e "$PC88_B63_WORK" && -f "$PC88_G1_DISK" ]] || exit 2
mkdir -p "$PC88_B63_WORK"
work="$(cd "$PC88_B63_WORK" && pwd)"
vendor="${PC88_VENDOR_DIR:-$REPO/../vendor}"
core="${PC88_B63_CORE:-$(ls "$vendor"/quasi88-libretro/quasi88_libretro.* 2>/dev/null | head -1)}"
[[ -f "$core" ]] || exit 1
trap 'rm -rf "$work"/run-*; rm -f "$work"/*.png' EXIT
TMPDIR="$work" python3 "$REPO/src/build_main_rom.py" "$work/self" --unscii-hex "$vendor/unscii/unscii-8.hex" --misaki-bdf "$vendor/misaki/misaki_gothic.bdf" >"$work/build.log" 2>&1
cc -O2 -std=c99 -D_POSIX_C_SOURCE=200809L -I"${PC88_B63_CORE_SRC:-$vendor/quasi88-libretro/src}/LIBRETRO/libretro-common/include" -I"$REPO/tools/harness/core" "$REPO/tools/harness/frontend/main.c" -ldl -o "$work/front" >"$work/frontend-build.log" 2>&1
run_one() {
  local name="$1" rom="$2" mode="$3" key="$4" prefix="$work/$1" run_dir="$work/run-$1" rc=0
  local -a args
  if [[ "$mode" == hold ]]; then
    args=(--frames 14400 --key-hold 60 --type-at 3600 --type ' ')
    if [[ "$key" != none ]]; then args+=(--key-at 7200 --key "RETROK_$key"); fi
    args+=(--sub-reg-log "$prefix.reg" --out "$prefix.out" --screenshot "$prefix.png")
  else
    args=(--frames 3600 --io-log "$prefix.io")
  fi
  mkdir -p "$run_dir/rom"
  cp -RL "$rom/." "$run_dir/rom/"
  find "$run_dir" -name '*.srm' -type f -delete
  cp "$PC88_G1_DISK" "$run_dir/G1-1.d88"
  "$work/front" --core "$core" --rom-dir "$run_dir/rom" --disk "$run_dir/G1-1.d88" "${args[@]}" >"$prefix.stdout" 2>"$prefix.stderr" || rc=$?
  rm -rf "$run_dir"
  if rg -q '打てない文字を無視' "$prefix.stderr"; then return 1; fi
  return "$rc"
}
: >"$work/result"
for key in i F1 2 none; do
  run_one "$key-OO-1" "$PC88_REF_ROM_DIR" hold "$key"
  run_one "$key-OO-2" "$PC88_REF_ROM_DIR" hold "$key"
  run_one "$key-SS-1" "$work/self" hold "$key"
  PYTHONPATH="$REPO/tools" python3 - "$work" "$key" <<'PY'
import contextlib
import io
import pathlib
import sys
from b39_sub_reg_compare import read
from check_l3_screen_output import compare_rows, read_screen
w, key = pathlib.Path(sys.argv[1]), sys.argv[2]
def path(name, ext): return w / f'{name}.{ext}'
def image(a, b): return path(a, 'png').read_bytes() == path(b, 'png').read_bytes()
def screen(a, b):
    with contextlib.redirect_stdout(io.StringIO()):
        return compare_rows(read_screen(path(a, 'out')), read_screen(path(b, 'out')))
def label(value): return 'same' if value else 'differ'
oo1, oo2, ss1 = (f'{key}-{suffix}' for suffix in ('OO-1', 'OO-2', 'SS-1'))
a, b = read(path(oo1, 'reg')), read(path(ss1, 'reg'))
row = f"hold {key} oo={label(image(oo1, oo2))} image={label(image(oo1, ss1))} text={label(screen(oo1, ss1))} cross={len(a['C'])} {len(b['C'])} fc={len(a['F'])} {len(b['F'])}"
with (w / 'result').open('a', encoding='utf-8') as out: out.write(row + '\n')
PY
done
for side in OO SS; do
  if [[ "$side" == OO ]]; then rom="$PC88_REF_ROM_DIR"; else rom="$work/self"; fi
  for n in 1 2; do run_one "port-$side-$n" "$rom" port none; done
done
status=0
PYTHONPATH="$REPO/tools" python3 - "$work" <<'PY' || status=1
import pathlib
import sys
from b63_port_last import read, compare
w = pathlib.Path(sys.argv[1])
o1, o2, s1, s2 = (read(w / f'port-{name}.io') for name in ('OO-1', 'OO-2', 'SS-1', 'SS-2'))
with (w / 'result').open('a', encoding='utf-8') as out:
    for line in compare(o1, s1): out.write(line + '\n')
sys.exit(0 if o1 == o2 and s1 == s2 else 1)
PY
mkdir -p "$REPO/measurements"
cp "$work/result" "$REPO/measurements/b63-g1-key-hold-and-ports.txt"
exit "$status"
