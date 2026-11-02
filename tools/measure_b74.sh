#!/usr/bin/env bash
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
work="${PC88_B74_WORK:?作業先を指定してください}"
core="${PC88_SUB_READ_CORE:?コアを指定してください}"
core_src="${PC88_SUB_READ_CORE_SRC:-$(cd "$REPO/.." && pwd)/vendor/quasi88-libretro/src}"
dry=""; output="$REPO/measurements"
while (($#)); do
  case "$1" in
    --dry-run-sub-rom) dry="$2"; shift 2;;
    --output-dir) output="$2"; shift 2;;
    *) exit 2;;
  esac
done
[[ ! -e "$work" && -f "$core" ]] || exit 1
if [[ -n "$dry" ]]; then
  [[ -f "$dry" ]] || exit 1
  arms=(S)
else
  ref="${PC88_REF_ROM_DIR:?}/DISK.ROM"
  [[ -f "$ref" ]] || exit 1
  arms=(O S)
fi
mkdir -p "$work"; work="$(cd "$work" && pwd)"
cc -O2 -std=c99 -D_POSIX_C_SOURCE=200809L -I"$core_src/LIBRETRO/libretro-common/include" -I"$REPO/tools/harness/core" "$REPO/tools/harness/frontend/main.c" -ldl -o "$work/front"
python3 "$REPO/tools/make_l3_testdisk.py" "$work/a.d88" --cylinders 40 --double-sided --sectors-per-track 16 --content-rule coord-header --disk-id 0xA1 >"$work/disk.log"
if [[ -z "$dry" ]]; then
  python3 "$REPO/src/l3_service/make_subrom.py" "$work/sub" >"$work/sub.log" 2>&1
  dry="$work/sub/DISK.ROM"
fi
for row in {1..4}; do
  TMPDIR="$work" python3 "$REPO/src/build_main_rom.py" "$work/rom-$row" --inject-b74-row "$row" --labels-out "$work/labels-$row.json" >"$work/build-$row.log" 2>&1
done
for arm in "${arms[@]}"; do
  sub="$dry"; [[ "$arm" != O ]] || sub="$ref"
  for row in {1..4}; do
    cp "$sub" "$work/rom-$row/DISK.ROM"
    for run in 1 2; do
      prefix="$work/$arm-$row-$run"; pipe="$prefix.pipe"
      mkfifo "$pipe"
      python3 "$REPO/tools/analyze_b74.py" --row "$row" --arm "$arm" --memlog "$pipe" --labels "$work/labels-$row.json" >"$prefix.result" &
      analyzer=$!
      if ! /usr/bin/perl -e 'alarm shift; exec @ARGV' 120 "$work/front" --core "$core" --rom-dir "$work/rom-$row" --frames 2010 --disk "$work/a.d88" --mem-write-log "$pipe" --mem-write-range DE00-E07F >"$prefix.out" 2>"$prefix.err"; then
        kill "$analyzer" 2>/dev/null || :; wait "$analyzer" 2>/dev/null || :; rm -f "$pipe"; exit 1
      fi
      wait "$analyzer"; rm "$pipe"
    done
  done
done
mkdir -p "$output"
result="$output/b74-sub-0e-after-00c1.txt"
: > "$result"; rc=0
for arm in "${arms[@]}"; do
  for row in {1..4}; do
    cat "$work/$arm-$row-1.result" >> "$result"
    cmp -s "$work/$arm-$row-1.result" "$work/$arm-$row-2.result" || { echo "B74: $arm 行$row の2走が不一致です" >&2; rc=1; }
  done
done
exit "$rc"
