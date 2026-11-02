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
  local name="$1" rom="$2" end="$3" start="${4:-}" prefix="$work/$1" run_dir="$work/run-$1" rc=0
  local frame n=0 key
  local -a keys=(--key-hold 60 --type-at 3600 --type ' ' --key-at 7200 --key RETROK_F1) sequence=(RETROK_RETURN RETROK_SPACE) io=()
  for ((frame=12000; frame<43200; frame+=2400)); do
    key="${sequence[n % 2]}"
    keys+=(--key-at "$frame" --key "$key")
    ((n+=1))
  done
  [[ -z "$start" ]] || io=(--io-log "$prefix.io" --io-log-from-frame "$start")
  mkdir -p "$run_dir/rom"
  cp -RL "$rom/." "$run_dir/rom/"
  find "$run_dir" -name '*.srm' -type f -delete
  cp "$PC88_G1_DISK" "$run_dir/G1-1.d88"
  "$work/front" --core "$core" --rom-dir "$run_dir/rom" --disk "$run_dir/G1-1.d88" --insert-disk2 "$run_dir/G1-1.d88" --insert-disk2-at 1 --insert-disk2-image 1 --frames "$end" "${keys[@]}" "${io[@]}" --sub-reg-log "$prefix.reg" --out "$prefix.out" --screenshot "$prefix.png" >"$prefix.stdout" 2>"$prefix.stderr" || rc=$?
  rm -rf "$run_dir"
  if rg -q '打てない文字を無視' "$prefix.stderr"; then return 1; fi
  return "$rc"
}
count_fc() {
  PYTHONPATH="$REPO/tools" python3 - "$1" <<'PY'
from b39_sub_reg_compare import read
import sys
print(len(read(sys.argv[1])['F']))
PY
}
for arm in OO SS; do
  if [[ "$arm" == OO ]]; then rom="$PC88_REF_ROM_DIR"; lo_fc=112684; hi_fc=112690; tail=0
  else rom="$work/self"; lo_fc=112680; hi_fc=112685; tail=200; fi
  # まず全期間の F 行数を確認し、到達する最初のフレームを二分探索する。
  run_one "$arm-probe" "$rom" 43200
  (( $(count_fc "$work/$arm-probe.reg") >= 112680 )) || exit 1
  low=0; high=43200
  while (( high - low > 1 )); do
    mid=$(((low + high) / 2))
    run_one "$arm-probe" "$rom" "$mid"
    if (( $(count_fc "$work/$arm-probe.reg") >= 112680 )); then high=$mid; else low=$mid; fi
  done
  start=$((high > 30 ? high - 30 : 0)); end=$((high + 30))
  (( end <= 43200 )) || end=43200
  while :; do
    run_one "$arm-io" "$rom" "$end" "$start"
    if PYTHONPATH="$REPO/tools" python3 - "$work/$arm-io.io" <<'PY'
from b67_requests import read
import sys
_, complete = read(__import__('pathlib').Path(sys.argv[1]))
sys.exit(0 if complete else 1)
PY
    then break; fi
    if (( end > high + 1 )); then end=$(((end + high + 1) / 2))
    elif (( start < high - 1 )); then start=$(((start + high) / 2))
    else exit 1; fi
  done
  offset=$(PYTHONPATH="$REPO/tools" python3 - "$work/$arm-io.io" "$work/$arm-io.reg" <<'PY'
from pathlib import Path
from b67_requests import read
from b39_sub_reg_compare import read as read_reg
import sys
sections, complete = read(Path(sys.argv[1]))
offset = len(read_reg(sys.argv[2])['F']) - sum(e[1:3] == ('IN', 0xFC) for e in sections['main'])
if not complete or offset < 0: raise ValueError()
print(offset)
PY
)
  python3 "$REPO/tools/b49_handshake_order.py" "$work/$arm-io.io" --arm "$arm" --offset "$offset" --window "$lo_fc" "$hi_fc" --tail "$tail" >"$work/$arm.result"
done
mkdir -p "$REPO/measurements"
cat "$work/OO.result" "$work/SS.result" >"$work/result"
cp "$work/result" "$REPO/measurements/b75-g1-f1-handshake-before-0e.txt"
