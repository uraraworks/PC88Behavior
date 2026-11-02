#!/usr/bin/env bash
# 生記録は作業場に留める。
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
: "${PC88_REF_ROM_DIR:?}" "${PC88_G1_DISK:?}" "${PC88_B71_WORK:?}"
[[ ! -e "$PC88_B71_WORK" && -f "$PC88_G1_DISK" ]] || exit 1
mkdir -p "$PC88_B71_WORK"
work="$(cd "$PC88_B71_WORK" && pwd)"
vendor="${PC88_VENDOR_DIR:-$REPO/../vendor}"
core="${PC88_B71_CORE:-$(ls "$vendor"/quasi88-libretro/quasi88_libretro.* 2>/dev/null | head -1)}"
[[ -f "$core" ]] || exit 1
trap 'rm -rf "$work"/run-*' EXIT
cc -O2 -std=c99 -D_POSIX_C_SOURCE=200809L -I"${PC88_B71_CORE_SRC:-$vendor/quasi88-libretro/src}/LIBRETRO/libretro-common/include" -I"$REPO/tools/harness/core" "$REPO/tools/harness/frontend/main.c" -ldl -o "$work/front" >"$work/frontend-build.log" 2>&1
run_one() {
  local name="$1" prefix="$work/$1" run_dir="$work/run-$1"
  local frame n=0 key
  local -a keys=(--key-hold 60 --type-at 3600 --type ' ' --key-at 7200 --key RETROK_F1)
  local -a sequence=(RETROK_RETURN RETROK_SPACE)
  for ((frame=12000; frame<43200; frame+=2400)); do
    key="${sequence[n % ${#sequence[@]}]}"
    keys+=(--key-at "$frame" --key "$key")
    ((n+=1))
  done
  mkdir -p "$run_dir/rom"
  cp -RL "$PC88_REF_ROM_DIR/." "$run_dir/rom/"
  find "$run_dir" -name '*.srm' -type f -delete
  cp "$PC88_G1_DISK" "$run_dir/G1-1.d88"
  "$work/front" --core "$core" --rom-dir "$run_dir/rom" --disk "$run_dir/G1-1.d88" --insert-disk2 "$run_dir/G1-1.d88" --insert-disk2-at 1 --insert-disk2-image 1 --frames 43200 "${keys[@]}" --sub-rom-access-log "$prefix.access" --sub-rom-access-window 112680,112700 --out "$prefix.out" >"$prefix.stdout" 2>"$prefix.stderr"
  rm -rf "$run_dir"
  python3 "$REPO/tools/b51_whitelist.py" "$prefix.access" --out "$prefix.filtered" 2>"$prefix.filter-log"
}
run_one OO-1
run_one OO-2
cmp -s "$work/OO-1.filtered" "$work/OO-2.filtered" || exit 1
mkdir -p "$REPO/measurements"
cp "$work/OO-1.filtered" "$REPO/measurements/b71-g1-0e-target-range.txt"
