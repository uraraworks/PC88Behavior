#!/usr/bin/env bash
# 生記録は作業場に留め、結果には事前登録の行だけを書く。
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
: "${PC88_REF_ROM_DIR:?}" "${PC88_G1_DISK:?}" "${PC88_B60_WORK:?}"
[[ ! -e "$PC88_B60_WORK" && -f "$PC88_G1_DISK" ]] || exit 2
mkdir -p "$PC88_B60_WORK"
work="$(cd "$PC88_B60_WORK" && pwd)"
vendor="${PC88_VENDOR_DIR:-$REPO/../vendor}"
core="${PC88_B60_CORE:-$(ls "$vendor"/quasi88-libretro/quasi88_libretro.* 2>/dev/null | head -1)}"
[[ -f "$core" ]] || exit 1
trap 'rm -rf "$work"/run-*; rm -f "$work"/*.png' EXIT
TMPDIR="$work" python3 "$REPO/src/build_main_rom.py" "$work/self" --unscii-hex "$vendor/unscii/unscii-8.hex" --misaki-bdf "$vendor/misaki/misaki_gothic.bdf" >"$work/build.log" 2>&1
cc -O2 -std=c99 -D_POSIX_C_SOURCE=200809L -I"${PC88_B60_CORE_SRC:-$vendor/quasi88-libretro/src}/LIBRETRO/libretro-common/include" -I"$REPO/tools/harness/core" "$REPO/tools/harness/frontend/main.c" -ldl -o "$work/front" >"$work/frontend-build.log" 2>&1
run_one() {
  local name="$1" rom="$2" key="$3" prefix="$work/$1" run_dir="$work/run-$1" rc=0
  local -a keys=(--type-at 3600 --type ' ')
  if [[ "$key" != none ]]; then keys+=(--key-at 7200 --key "RETROK_$key"); fi
  mkdir -p "$run_dir/rom"
  cp -RL "$rom/." "$run_dir/rom/"
  find "$run_dir" -name '*.srm' -type f -delete
  cp "$PC88_G1_DISK" "$run_dir/G1-1.d88"
  "$work/front" --core "$core" --rom-dir "$run_dir/rom" --disk "$run_dir/G1-1.d88" --frames 14400 "${keys[@]}" --sub-reg-log "$prefix.reg" --boundary-log "$prefix.boundary" --out "$prefix.out" --screenshot "$prefix.png" >"$prefix.stdout" 2>"$prefix.stderr" || rc=$?
  rm -rf "$run_dir"
  printf '%s rc=%s\n' "$name" "$rc" >>"$work/progress"
  if rg -q '打てない文字を無視' "$prefix.stderr"; then
    printf '打鍵の無視: %s\n' "$name" >&2
    return 1
  fi
  return "$rc"
}
: >"$work/result"
status=0
for key in none {0..9} {a..z} F{1..5} ESCAPE TAB BREAK DELETE KP2 KP4 KP5 KP6 KP8; do
  run_one "$key-OO-1" "$PC88_REF_ROM_DIR" "$key"
  run_one "$key-OO-2" "$PC88_REF_ROM_DIR" "$key"
  run_one "$key-SS-1" "$work/self" "$key"
  PYTHONPATH="$REPO/tools" python3 - "$work" "$key" <<'PY' || status=1
import contextlib
import io
import pathlib
import sys
from b1_whitelist_boundary import filter_lines
from b39_sub_reg_compare import read
from check_l3_screen_output import compare_rows, read_screen

w, key = pathlib.Path(sys.argv[1]), sys.argv[2]
def path(name, ext):
    return w / f'{name}.{ext}'
def image(a, b):
    return path(a, 'png').read_bytes() == path(b, 'png').read_bytes()
def screen(a, b):
    with contextlib.redirect_stdout(io.StringIO()):
        return compare_rows(read_screen(path(a, 'out')), read_screen(path(b, 'out')))
def addresses(name):
    lines, _, _ = filter_lines(path(name, 'boundary').read_text(encoding='utf-8', errors='replace').splitlines(), 'G1', 'official')
    return {line.split()[1] for line in lines if line.startswith('A ')}
def label(value):
    return 'same' if value else 'differ'
oo1, oo2, ss1 = (f'{key}-{suffix}' for suffix in ('OO-1', 'OO-2', 'SS-1'))
a, b = read(path(oo1, 'reg')), read(path(ss1, 'reg'))
left = addresses(oo1) - addresses('none-OO-1')
right = addresses(ss1) - addresses('none-SS-1')
first = next ( (i for i, (x, y) in enumerate(zip(a['C'], b['C'])) if x[6] != y[6]), 'none')
row = f"key {key} oo={label(image(oo1, oo2))} image={label(image(oo1, ss1))} text={label(screen(oo1, ss1))} cross={len(a['C'])} {len(b['C'])} fc={len(a['F'])} {len(b['F'])} a-left-new={len(left)} a-right-new={len(right)} first-cross-pc={first}"
with (w / 'result').open('a', encoding='utf-8') as out:
    out.write(row + '\n')
    for addr in sorted(left):
        out.write(f'A-new {key} {addr}\n')
if key == 'none':
    if not (image(oo1, oo2) and screen(oo1, oo2) and read(path(oo1, 'reg')) == read(path(oo2, 'reg')) and addresses(oo1) == addresses(oo2)):
        sys.exit(1)
else:
    for name in (oo1, oo2, ss1):
        for ext in ('png', 'reg', 'boundary', 'out', 'stdout', 'stderr'):
            path(name, ext).unlink(missing_ok=True)
PY
done
mkdir -p "$REPO/measurements"
cp "$work/result" "$REPO/measurements/b60-g1-single-keys.txt"
exit "$status"
