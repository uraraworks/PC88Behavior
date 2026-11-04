#!/usr/bin/env bash
# 生記録は作業場に留め、結果には事前登録の行だけを書く。
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
: "${PC88_REF_ROM_DIR:?}" "${PC88_G1_DISK:?}" "${PC88_B77_WORK:?}"
[[ ! -e "$PC88_B77_WORK" && -f "$PC88_G1_DISK" ]] || exit 2
mkdir -p "$PC88_B77_WORK"
work="$(cd "$PC88_B77_WORK" && pwd)"
vendor="${PC88_VENDOR_DIR:-$REPO/../vendor}"
core="${PC88_B77_CORE:-$(ls "$vendor"/quasi88-libretro/quasi88_libretro.* 2>/dev/null | head -1)}"
[[ -f "$core" ]] || exit 1
trap 'rm -rf "$work"/run-*; rm -f "$work"/*.png' EXIT
TMPDIR="$work" python3 "$REPO/src/build_main_rom.py" "$work/self" --unscii-hex "$vendor/unscii/unscii-8.hex" --misaki-bdf "$vendor/misaki/misaki_gothic.bdf" >"$work/build.log" 2>&1
cc -O2 -std=c99 -D_POSIX_C_SOURCE=200809L -I"${PC88_B77_CORE_SRC:-$vendor/quasi88-libretro/src}/LIBRETRO/libretro-common/include" -I"$REPO/tools/harness/core" "$REPO/tools/harness/frontend/main.c" -ldl -o "$work/front" >"$work/frontend-build.log" 2>&1
run_one() {
  local arm="$1" rom="$2" first="$3" frames="$4" name="$1-$3" rc=0
  local run_dir="$work/run-$1-$3" prefix="$work/$1-$3" frame n=0 key
  local -a keys=(--key-hold 60 --type-at 3600 --type ' ' --key-at 7200 --key RETROK_F1) sequence=(RETROK_RETURN RETROK_SPACE)
  for ((frame=12000; frame<43200; frame+=2400)); do
    key="${sequence[n % ${#sequence[@]}]}"
    keys+=(--key-at "$frame" --key "$key")
    ((n+=1))
  done
  mkdir -p "$run_dir/rom"
  cp -RL "$rom/." "$run_dir/rom/"
  find "$run_dir" -name '*.srm' -type f -delete
  cp "$PC88_G1_DISK" "$run_dir/G1-1.d88"
  "$work/front" --core "$core" --rom-dir "$run_dir/rom" --disk "$run_dir/G1-1.d88" --insert-disk2 "$run_dir/G1-1.d88" --insert-disk2-at 1 --insert-disk2-image 1 --frames "$frames" "${keys[@]}" --int-log "$prefix.int" --int-log-from-frame "$first" --out "$prefix.out" --screenshot "$prefix.png" >"$prefix.stdout" 2>"$prefix.stderr" || rc=$?
  rm -rf "$run_dir"
  printf '%s rc=%s\n' "$name" "$rc" >>"$work/progress"
  if rg -q '打てない文字を無視' "$prefix.stderr"; then return 1; fi
  return "$rc"
}
for arm in O S; do
  rom="$PC88_REF_ROM_DIR"
  [[ "$arm" != S ]] || rom="$work/self"
  for pair in '11400 12000' '12000 12600' '12600 13200'; do
    read -r first last <<<"$pair"
    run_one "$arm" "$rom" "$first" "$last"
  done
done
: >"$work/result"
for arm in O S; do
  for pair in '11400 12000' '12000 12600' '12600 13200'; do
    read -r first last <<<"$pair"
    python3 "$REPO/tools/b77_interrupts.py" "$work/$arm-$first.int" --arm "$arm" --window "$first-$((last-1))" >>"$work/result"
  done
done
mkdir -p "$REPO/measurements"
cp "$work/result" "$REPO/measurements/b77-g1-f1-interrupts.txt"
