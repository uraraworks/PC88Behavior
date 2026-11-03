#!/usr/bin/env bash
# 生記録は作業場に留め、事前登録の行だけを結果に書く。
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
: "${PC88_REF_ROM_DIR:?}" "${PC88_G1_DISK:?}" "${PC88_B76_WORK:?}"
[[ ! -e "$PC88_B76_WORK" && -f "$PC88_G1_DISK" ]] || exit 2
mkdir -p "$PC88_B76_WORK"
work="$(cd "$PC88_B76_WORK" && pwd)"
vendor="${PC88_VENDOR_DIR:-$REPO/../vendor}"
core="${PC88_B76_CORE:-$(ls "$vendor"/quasi88-libretro/quasi88_libretro.* 2>/dev/null | head -1)}"
[[ -f "$core" ]] || exit 1
trap 'rm -rf "$work"/run-*; rm -f "$work"/*.png' EXIT
printf 'build\n' >"$work/progress"
TMPDIR="$work" python3 "$REPO/src/build_main_rom.py" "$work/self" --unscii-hex "$vendor/unscii/unscii-8.hex" --misaki-bdf "$vendor/misaki/misaki_gothic.bdf" >"$work/build.log" 2>&1
cc -O2 -std=c99 -D_POSIX_C_SOURCE=200809L -I"${PC88_B76_CORE_SRC:-$vendor/quasi88-libretro/src}/LIBRETRO/libretro-common/include" -I"$REPO/tools/harness/core" "$REPO/tools/harness/frontend/main.c" -ldl -o "$work/front" >"$work/frontend-build.log" 2>&1
run_one() {
  local name="$1" rom="$2" shift_frames="$3" hold="$4" later="$5" prefix="$work/$1" run_dir="$work/run-$1" rc=0
  local frame n=0 key
  local -a keys=(--key-hold 60 --type-at 3600 --type ' ' --key-at 7200 --key RETROK_F1 --key-hold "$hold")
  local -a sequence=(RETROK_RETURN RETROK_SPACE)
  if [[ "$later" == yes ]]; then
    for ((frame=12000; frame<43200; frame+=2400)); do
      key="${sequence[n % ${#sequence[@]}]}"
      keys+=(--key-at "$((frame + shift_frames))" --key "$key")
      ((n+=1))
    done
  fi
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
for arm in D{0..9} H120 H300 L1; do
  shift_frames=0 hold=60 later=yes
  case "$arm" in
    D*) shift_frames=$((6 * ${arm#D})) ;;
    H120) hold=120 ;;
    H300) hold=300 ;;
    L1) later=no ;;
  esac
  run_one "$arm-OO" "$PC88_REF_ROM_DIR" "$shift_frames" "$hold" "$later"
  run_one "$arm-SS" "$work/self" "$shift_frames" "$hold" "$later"
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
def label(value):
    return 'same' if value else 'differ'
rows = []
for arm in [*(f'D{k}' for k in range(10)), 'H120', 'H300', 'L1']:
    oo, ss = (f'{arm}-{x}' for x in ('OO', 'SS'))
    a, b = read(w / (oo + '.reg')), read(w / (ss + '.reg'))
    image = (w / (oo + '.png')).read_bytes() == (w / (ss + '.png')).read_bytes()
    with contextlib.redirect_stdout(io.StringIO()):
        screen = compare_rows(read_screen(w / (oo + '.out')), read_screen(w / (ss + '.out')))
    rows.append(f"arm {arm} cross={len(a['C'])} {len(b['C'])} fc={len(a['F'])} {len(b['F'])} image={label(image)} text={label(screen)}")
(w / 'result').write_text('\n'.join(rows) + '\n', encoding='utf-8')
PY
mkdir -p "$REPO/measurements"
cp "$work/result" "$REPO/measurements/b76-g1-f1-key-sweep.txt"
printf 'done\n' >"$work/progress"
