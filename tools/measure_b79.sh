#!/usr/bin/env bash
# 生記録は作業場に留め、事前登録の req 行と E 行だけを結果に書く。
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
: "${PC88_REF_ROM_DIR:?}" "${PC88_G1_DISK:?}" "${PC88_B79_WORK:?}"
[[ ! -e "$PC88_B79_WORK" && -f "$PC88_G1_DISK" ]] || exit 2
mkdir -p "$PC88_B79_WORK"
work="$(cd "$PC88_B79_WORK" && pwd)"
vendor="${PC88_VENDOR_DIR:-$REPO/../vendor}"
core="${PC88_B79_CORE:-$(ls "$vendor"/quasi88-libretro/quasi88_libretro.* 2>/dev/null | head -1)}"
[[ -f "$core" ]] || exit 1
trap 'rm -rf "$work"/run-*; rm -f "$work"/*.png' EXIT
TMPDIR="$work" python3 "$REPO/src/build_main_rom.py" "$work/self" --unscii-hex "$vendor/unscii/unscii-8.hex" --misaki-bdf "$vendor/misaki/misaki_gothic.bdf" >"$work/build.log" 2>&1
cc -O2 -std=c99 -D_POSIX_C_SOURCE=200809L -I"${PC88_B79_CORE_SRC:-$vendor/quasi88-libretro/src}/LIBRETRO/libretro-common/include" -I"$REPO/tools/harness/core" "$REPO/tools/harness/frontend/main.c" -ldl -o "$work/front" >"$work/frontend-build.log" 2>&1
run_one() {
  local rom="$2" prefix="$work/$1" run_dir="$work/run-$1" rc=0
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
  "$work/front" --core "$core" --rom-dir "$run_dir/rom" --disk "$run_dir/G1-1.d88" --insert-disk2 "$run_dir/G1-1.d88" --insert-disk2-at 1 --insert-disk2-image 1 --frames 12060 "${keys[@]}" --io-log "$prefix.io" --io-log-from-frame 12000 --sub-reg-log "$prefix.reg" --out "$prefix.out" --screenshot "$prefix.png" >"$prefix.stdout" 2>"$prefix.stderr" || rc=$?
  rm -rf "$run_dir"
  if rg -q '打てない文字を無視' "$prefix.stderr"; then return 1; fi
  return "$rc"
}
summarize() {
  local name="$1" arm="$2" event_arm="$3" count
  python3 "$REPO/tools/b67_requests.py" "$work/$name.io" --sub-reg-log "$work/$name.reg" --arm "$arm" --window 12000 >"$work/$name.req"
  count="$(PYTHONPATH="$REPO/tools" python3 - "$work/$name.io" <<'PYCOUNT'
import sys
from pathlib import Path
from b67_requests import read
sections, complete = read(Path(sys.argv[1]))
if not complete:
    raise SystemExit(1)
print(sum(map(len, sections.values())))
PYCOUNT
)"
  python3 "$REPO/tools/b49_handshake_order.py" "$work/$name.io" --arm "$event_arm" --event-window "$((count - 60))" "$count" >"$work/$name.events"
  cat "$work/$name.req" "$work/$name.events" >"$work/$name.result"
}
run_one OO-io "$PC88_REF_ROM_DIR"
summarize OO-io O OO
run_one SS-io "$work/self"
summarize SS-io S SS
mkdir -p "$REPO/measurements"
cat "$work/OO-io.result" "$work/SS-io.result" >"$work/result"
cp "$work/result" "$REPO/measurements/b79-g1-f1-requests-before-deadlock.txt"
