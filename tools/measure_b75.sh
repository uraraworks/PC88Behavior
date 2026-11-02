#!/usr/bin/env bash
# 生記録は作業場に留め、事前登録の E 行だけを結果に書く。
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
: "${PC88_REF_ROM_DIR:?}" "${PC88_G1_DISK:?}" "${PC88_B75_WORK:?}"
[[ ! -e "$PC88_B75_WORK" && -f "$PC88_G1_DISK" ]] || exit 2
mkdir -p "$PC88_B75_WORK"
work="$(cd "$PC88_B75_WORK" && pwd)"
vendor="${PC88_VENDOR_DIR:-$REPO/../vendor}"
core="${PC88_B75_CORE:-$(ls "$vendor"/quasi88-libretro/quasi88_libretro.* 2>/dev/null | head -1)}"
[[ -f "$core" ]] || exit 1
trap 'rm -rf "$work"/run-*; rm -f "$work"/*.png' EXIT
TMPDIR="$work" python3 "$REPO/src/build_main_rom.py" "$work/self" --unscii-hex "$vendor/unscii/unscii-8.hex" --misaki-bdf "$vendor/misaki/misaki_gothic.bdf" >"$work/build.log" 2>&1
cc -O2 -std=c99 -D_POSIX_C_SOURCE=200809L -I"${PC88_B75_CORE_SRC:-$vendor/quasi88-libretro/src}/LIBRETRO/libretro-common/include" -I"$REPO/tools/harness/core" "$REPO/tools/harness/frontend/main.c" -ldl -o "$work/front" >"$work/frontend-build.log" 2>&1
run_one() {
  local rom="$2" end="$3" prefix="$work/$1" run_dir="$work/run-$1" rc=0
  local frame n=0 key
  local -a keys=(--key-hold 60 --type-at 3600 --type ' ' --key-at 7200 --key RETROK_F1) sequence=(RETROK_RETURN RETROK_SPACE)
  for ((frame=12000; frame<43200; frame+=2400)); do
    key="${sequence[n % 2]}"
    keys+=(--key-at "$frame" --key "$key")
    ((n+=1))
  done
  mkdir -p "$run_dir/rom"
  cp -RL "$rom/." "$run_dir/rom/"
  find "$run_dir" -name '*.srm' -type f -delete
  cp "$PC88_G1_DISK" "$run_dir/G1-1.d88"
  "$work/front" --core "$core" --rom-dir "$run_dir/rom" --disk "$run_dir/G1-1.d88" --insert-disk2 "$run_dir/G1-1.d88" --insert-disk2-at 1 --insert-disk2-image 1 --frames "$end" "${keys[@]}" --io-log "$prefix.io" --io-log-from-frame 12000 --sub-reg-log "$prefix.reg" --out "$prefix.out" --screenshot "$prefix.png" >"$prefix.stdout" 2>"$prefix.stderr" || rc=$?
  rm -rf "$run_dir"
  if rg -q '打てない文字を無視' "$prefix.stderr"; then return 1; fi
  return "$rc"
}
run_one OO-io "$PC88_REF_ROM_DIR" 19800
python3 "$REPO/tools/b49_handshake_order.py" "$work/OO-io.io" --arm OO --before-first-main-fd-0e 200 >"$work/OO.result"
run_one SS-io "$work/self" 12600
python3 "$REPO/tools/b49_handshake_order.py" "$work/SS-io.io" --arm SS --event-window 0 300 >"$work/SS.result"
mkdir -p "$REPO/measurements"
cat "$work/OO.result" "$work/SS.result" >"$work/result"
cp "$work/result" "$REPO/measurements/b75-g1-f1-handshake-before-0e.txt"
