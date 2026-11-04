#!/usr/bin/env bash
# B81: 作業ツリーのsrcから自作ROMを組み、B65と同じ5条件で0x0E後の新規要求を測る。
# 生記録は作業場に留め、比較結果だけをmeasurements/b81-g1-0e-new-request.txtへ書く。
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
: "${PC88_REF_ROM_DIR:?}" "${PC88_G1_DISK:?}" "${PC88_B81_WORK:?}"
[[ ! -e "$PC88_B81_WORK" && -f "$PC88_G1_DISK" ]] || exit 2
mkdir -p "$PC88_B81_WORK"
work="$(cd "$PC88_B81_WORK" && pwd)"
vendor="${PC88_VENDOR_DIR:-$REPO/../vendor}"
core="${PC88_B81_CORE:-$(ls "$vendor"/quasi88-libretro/quasi88_libretro.* 2>/dev/null | head -1)}"
[[ -f "$core" ]] || exit 1
trap 'rm -rf "$work"/run-*; rm -f "$work"/*.png' EXIT
printf 'build\n' >"$work/progress"
TMPDIR="$work" python3 "$REPO/src/build_main_rom.py" "$work/self" --unscii-hex "$vendor/unscii/unscii-8.hex" --misaki-bdf "$vendor/misaki/misaki_gothic.bdf" >"$work/build.log" 2>&1
cc -O2 -std=c99 -D_POSIX_C_SOURCE=200809L -I"${PC88_B81_CORE_SRC:-$vendor/quasi88-libretro/src}/LIBRETRO/libretro-common/include" -I"$REPO/tools/harness/core" "$REPO/tools/harness/frontend/main.c" -ldl -o "$work/front" >"$work/frontend-build.log" 2>&1
run_one() {
  local name="$1" rom="$2" arm="$3" prefix="$work/$1" run_dir="$work/run-$1" rc=0
  local frame n=0 key
  local -a keys=(--key-hold 60 --type-at 3600 --type ' ') sequence=()
  case "$arm" in
    I1|I2|I3) keys+=(--key-at 7200 --key RETROK_i) ;;
    S1) keys+=(--key-at 7200 --key RETROK_s) ;;
    F1) keys+=(--key-at 7200 --key RETROK_F1) ;;
  esac
  case "$arm" in
    I1|S1|F1) sequence=(RETROK_RETURN RETROK_SPACE) ;;
    I2) sequence=(RETROK_{1..9} RETROK_0) ;;
    I3) sequence=(RETROK_ESCAPE RETROK_F{1..5}) ;;
  esac
  for ((frame=12000; frame<43200; frame+=2400)); do
    key="${sequence[n % ${#sequence[@]}]}"
    keys+=(--key-at "$frame" --key "$key")
    ((n+=1))
  done
  printf '%s\n' "$name" >"$work/progress"
  mkdir -p "$run_dir/rom"
  cp -RL "$rom/." "$run_dir/rom/"
  find "$run_dir" -name '*.srm' -type f -delete
  cp "$PC88_G1_DISK" "$run_dir/G1-1.d88"
  "$work/front" --core "$core" --rom-dir "$run_dir/rom" --disk "$run_dir/G1-1.d88" --insert-disk2 "$run_dir/G1-1.d88" --insert-disk2-at 1 --insert-disk2-image 1 --frames 43200 "${keys[@]}" --sub-reg-log "$prefix.reg" --out "$prefix.out" --screenshot "$prefix.png" >"$prefix.stdout" 2>"$prefix.stderr" || rc=$?
  rm -rf "$run_dir"
  if rg -q '打てない文字を無視' "$prefix.stderr"; then return 1; fi
  return "$rc"
}
for arm in I1 I2 I3 S1 F1; do
  run_one "$arm-OO-1" "$PC88_REF_ROM_DIR" "$arm"
  run_one "$arm-OO-2" "$PC88_REF_ROM_DIR" "$arm"
  run_one "$arm-SS-1" "$work/self" "$arm"
done
printf 'compare\n' >"$work/progress"
PYTHONPATH="$REPO/tools" python3 - "$work" <<'PY'
import contextlib
import io
import pathlib
import sys
from b39_sub_reg_compare import read
from check_l3_screen_output import compare_rows, read_screen

w = pathlib.Path(sys.argv[1])
def image(a, b):
    return (w / (a + '.png')).read_bytes() == (w / (b + '.png')).read_bytes()
def screen(a, b):
    with contextlib.redirect_stdout(io.StringIO()):
        return compare_rows(read_screen(w / (a + '.out')), read_screen(w / (b + '.out')))
def label(value):
    return 'same' if value else 'differ'
rows = []
for arm in ('I1', 'I2', 'I3', 'S1', 'F1'):
    oo1, oo2, ss1 = (f'{arm}-{x}' for x in ('OO-1', 'OO-2', 'SS-1'))
    a, b = read(w / (oo1 + '.reg')), read(w / (ss1 + '.reg'))
    first = next((i for i, (x, y) in enumerate(zip(a['C'], b['C'])) if x[6] != y[6]), 'none')
    rows.append(f"arm {arm} oo={label(image(oo1, oo2))} image={label(image(oo1, ss1))} text={label(screen(oo1, ss1))} cross={len(a['C'])} {len(b['C'])} fc={len(a['F'])} {len(b['F'])} first-cross-pc={first}")
(w / 'result').write_text('\n'.join(rows) + '\n', encoding='utf-8')
PY
mkdir -p "$REPO/measurements"
cp "$work/result" "$REPO/measurements/b81-g1-0e-new-request.txt"
printf 'done\n' >"$work/progress"
