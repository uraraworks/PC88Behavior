#!/usr/bin/env bash
# 生記録と画像は作業場に留め、事前登録の行だけを結果に書く。
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
: "${PC88_REF_ROM_DIR:?}" "${PC88_G1_DISK:?}" "${PC88_B64_WORK:?}"
[[ ! -e "$PC88_B64_WORK" && -f "$PC88_G1_DISK" ]] || exit 2
mkdir -p "$PC88_B64_WORK"
work="$(cd "$PC88_B64_WORK" && pwd)"
vendor="${PC88_VENDOR_DIR:-$REPO/../vendor}"
core="${PC88_B64_CORE:-$(ls "$vendor"/quasi88-libretro/quasi88_libretro.* 2>/dev/null | head -1)}"
[[ -f "$core" ]] || exit 1
trap 'rm -rf "$work"/run-*; rm -f "$work"/*.png' EXIT
TMPDIR="$work" python3 "$REPO/src/build_main_rom.py" "$work/self" --unscii-hex "$vendor/unscii/unscii-8.hex" --misaki-bdf "$vendor/misaki/misaki_gothic.bdf" >"$work/build.log" 2>&1
cc -O2 -std=c99 -D_POSIX_C_SOURCE=200809L -I"${PC88_B64_CORE_SRC:-$vendor/quasi88-libretro/src}/LIBRETRO/libretro-common/include" -I"$REPO/tools/harness/core" "$REPO/tools/harness/frontend/main.c" -ldl -o "$work/front" >"$work/frontend-build.log" 2>&1
run_one() {
  local name="$1" rom="$2" key="$3" k="$4" prefix="$work/$1" run_dir="$work/run-$1" rc=0
  mkdir -p "$run_dir/rom"
  cp -RL "$rom/." "$run_dir/rom/"
  find "$run_dir" -name '*.srm' -type f -delete
  cp "$PC88_G1_DISK" "$run_dir/G1-1.d88"
  "$work/front" --core "$core" --rom-dir "$run_dir/rom" --disk "$run_dir/G1-1.d88" --frames 14400 --type-at 3600 --type ' ' --key-at "$((7200 + k))" --key "RETROK_$key" --sub-reg-log "$prefix.reg" --out "$prefix.out" --screenshot "$prefix.png" >"$prefix.stdout" 2>"$prefix.stderr" || rc=$?
  rm -rf "$run_dir"
  printf '%s rc=%s\n' "$name" "$rc" >>"$work/progress"
  if rg -q '打てない文字を無視' "$prefix.stderr"; then return 1; fi
  return "$rc"
}
: >"$work/progress"
for key in 2 i; do
  for k in {0..15}; do
    run_one "$key-o$k" "$PC88_REF_ROM_DIR" "$key" "$k"
    if [[ "$k" == 0 ]]; then run_one "$key-o0-repeat" "$PC88_REF_ROM_DIR" "$key" 0; fi
    run_one "$key-s$k" "$work/self" "$key" "$k"
  done
done
status=0
PYTHONPATH="$REPO/tools" python3 - "$work" <<'PY' || status=1
import contextlib
import io
import pathlib
import sys
from b39_sub_reg_compare import read
from check_l3_screen_output import compare_rows, read_screen

w = pathlib.Path(sys.argv[1])
def path(name, ext): return w / f'{name}.{ext}'
def image(a, b): return path(a, 'png').read_bytes() == path(b, 'png').read_bytes()
def screen(a, b):
    with contextlib.redirect_stdout(io.StringIO()):
        return compare_rows(read_screen(path(a, 'out')), read_screen(path(b, 'out')))
def label(value): return 'same' if value else 'differ'
status = 0
with (w / 'result').open('w', encoding='utf-8') as out:
    for key in ('2', 'i'):
        first, repeat = f'{key}-o0', f'{key}-o0-repeat'
        if not (image(first, repeat) and screen(first, repeat) and read(path(first, 'reg')) == read(path(repeat, 'reg'))):
            status = 1
        for k in range(16):
            for other in range(16):
                a, b = f'{key}-o{k}', f'{key}-s{other}'
                out.write(f'pair {key} o{k} s{other} image={label(image(a, b))} text={label(screen(a, b))}\n')
        for side in ('o', 's'):
            for k in range(16):
                reg = read(path(f'{key}-{side}{k}', 'reg'))
                out.write(f"run {key} {side}{k} cross={len(reg['C'])} fc={len(reg['F'])}\n")
sys.exit(status)
PY
printf 'comparison rc=%s\n' "$status" >>"$work/progress"
mkdir -p "$REPO/measurements"
cp "$work/result" "$REPO/measurements/b64-g1-key-phase.txt"
exit "$status"
