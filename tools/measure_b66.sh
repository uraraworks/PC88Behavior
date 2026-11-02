#!/usr/bin/env bash
# 生記録は作業場に留め、事前登録の行だけを結果に書く。
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
: "${PC88_REF_ROM_DIR:?}" "${PC88_G1_DISK:?}" "${PC88_B66_WORK:?}"
[[ ! -e "$PC88_B66_WORK" && -f "$PC88_G1_DISK" ]] || exit 2
mkdir -p "$PC88_B66_WORK"
work="$(cd "$PC88_B66_WORK" && pwd)"
vendor="${PC88_VENDOR_DIR:-$REPO/../vendor}"
core="${PC88_B66_CORE:-$(ls "$vendor"/quasi88-libretro/quasi88_libretro.* 2>/dev/null | head -1)}"
[[ -f "$core" ]] || exit 1
trap 'rm -rf "$work"/run-*' EXIT
TMPDIR="$work" python3 "$REPO/src/build_main_rom.py" "$work/self" --unscii-hex "$vendor/unscii/unscii-8.hex" --misaki-bdf "$vendor/misaki/misaki_gothic.bdf" >"$work/build.log" 2>&1
cc -O2 -std=c99 -D_POSIX_C_SOURCE=200809L -I"${PC88_B66_CORE_SRC:-$vendor/quasi88-libretro/src}/LIBRETRO/libretro-common/include" -I"$REPO/tools/harness/core" "$REPO/tools/harness/frontend/main.c" -ldl -o "$work/front" >"$work/frontend-build.log" 2>&1
run_one() {
  local name="$1" rom="$2" shift_frames="$3" prefix="$work/$1" run_dir="$work/run-$1" rc=0
  local frame n=0 key
  local -a keys=(--key-hold 60 --type-at 3600 --type ' ' --key-at 7200 --key RETROK_F1)
  local -a sequence=(RETROK_RETURN RETROK_SPACE)
  for ((frame=12000; frame<43200; frame+=2400)); do
    key="${sequence[n % ${#sequence[@]}]}"
    keys+=(--key-at "$((frame + shift_frames))" --key "$key")
    ((n+=1))
  done
  printf '%s\n' "$name" >"$work/progress"
  mkdir -p "$run_dir/rom"
  cp -RL "$rom/." "$run_dir/rom/"
  find "$run_dir" -name '*.srm' -type f -delete
  cp "$PC88_G1_DISK" "$run_dir/G1-1.d88"
  "$work/front" --core "$core" --rom-dir "$run_dir/rom" --disk "$run_dir/G1-1.d88" --insert-disk2 "$run_dir/G1-1.d88" --insert-disk2-at 1 --insert-disk2-image 1 --frames 43200 "${keys[@]}" --sub-reg-log "$prefix.reg" --out "$prefix.out" >"$prefix.stdout" 2>"$prefix.stderr" || rc=$?
  rm -rf "$run_dir"
  if rg -q '打てない文字を無視' "$prefix.stderr"; then return 1; fi
  return "$rc"
}
run_one OO-1 "$PC88_REF_ROM_DIR" 0
run_one OO-2 "$PC88_REF_ROM_DIR" 0
cmp -s "$work/OO-1.reg" "$work/OO-2.reg" || exit 1
run_one SS-1 "$work/self" 0
for k in {0..5}; do
  run_one "shift-$k-OO" "$PC88_REF_ROM_DIR" "$k"
  run_one "shift-$k-SS" "$work/self" "$k"
done
python3 "$REPO/tools/b40_cross_table.py" "$work/OO-1.reg" "$work/SS-1.reg" >"$work/table"
PYTHONPATH="$REPO/tools" python3 - "$work" <<'PY'
import pathlib
import sys
from b40_cross_table import read

w = pathlib.Path(sys.argv[1])
lines = [line for line in (w / 'table').read_text(encoding='utf-8').splitlines()
         if line.split(maxsplit=1)[0] in ('count', 'C', 'LEFT', 'RIGHT')]
for k in range(6):
    left = len(read(w / f'shift-{k}-OO.reg'))
    right = len(read(w / f'shift-{k}-SS.reg'))
    lines.append(f'shift {k} cross={left} {right}')
(w / 'result').write_text('\n'.join(lines) + '\n', encoding='utf-8')
PY
mkdir -p "$REPO/measurements"
cp "$work/result" "$REPO/measurements/b66-g1-f1-cross-table.txt"
printf 'done\n' >"$work/progress"
