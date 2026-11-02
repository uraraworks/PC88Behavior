#!/usr/bin/env bash
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
work="${PC88_B68_WORK:?作業先を指定してください}"
core="${PC88_SUB_READ_CORE:?コアを指定してください}"
sub="${PC88_REF_ROM_DIR:?ROM ディレクトリを指定してください}/DISK.ROM"
[[ ! -e "$work" && -f "$core" && -f "$sub" ]] || { echo 'B68: 作業先または入力が不正です' >&2; exit 1; }
mkdir -p "$work"; work="$(cd "$work" && pwd)"
core_src="${PC88_SUB_READ_CORE_SRC:-$(cd "$REPO/.." && pwd)/vendor/quasi88-libretro/src}"
cc -O2 -std=c99 -D_POSIX_C_SOURCE=200809L -I"$core_src/LIBRETRO/libretro-common/include" -I"$REPO/tools/harness/core" "$REPO/tools/harness/frontend/main.c" -ldl -o "$work/front"
python3 "$REPO/tools/make_l3_testdisk.py" "$work/a.d88" --cylinders 40 --double-sided --sectors-per-track 16 --content-rule coord-header --disk-id 0xA1 >"$work/disk.log" 2>&1
for row in {1..8}; do
  TMPDIR="$work" python3 "$REPO/src/build_main_rom.py" "$work/rom-$row" --inject-b68-row "$row" --labels-out "$work/labels-$row.json" >"$work/build-$row.log" 2>&1
  cp "$sub" "$work/rom-$row/DISK.ROM"
  for run in 1 2; do
    prefix="$work/$row-$run"
    /usr/bin/perl -e 'alarm shift; exec @ARGV' 120 "$work/front" --core "$core" --rom-dir "$work/rom-$row" --frames 2010 --disk "$work/a.d88" --io-log "$prefix.first.io" >"$prefix.first.out" 2>"$prefix.first.err"
    read -r target count < <(python3 "$REPO/tools/analyze_b68.py" "$row" "$prefix.first.io" /dev/null /dev/null "$work/labels-$row.json" --fc-info)
    if [[ "$target" == -1 ]]; then
      cp "$prefix.first.io" "$prefix.io"
      continue
    fi
    /usr/bin/perl -e 'alarm shift; exec @ARGV' 120 "$work/front" --core "$core" --rom-dir "$work/rom-$row" --frames 2010 --disk "$work/a.d88" --io-log "$prefix.io" --sub-snapshot "$prefix.snap" --sub-snapshot-at-fc "$target" >"$prefix.out" 2>"$prefix.err"
    read -r target2 count2 < <(python3 "$REPO/tools/analyze_b68.py" "$row" "$prefix.io" /dev/null /dev/null "$work/labels-$row.json" --fc-info)
    [[ "$count" == "$count2" && "$target" == "$target2" && -s "$prefix.snap" ]] || { echo 'B68: IN $FC の回数またはスナップショットが不一致です' >&2; exit 1; }
  done
done
for run in 1 2; do
  result="$work/result-$run.txt"; : > "$result"
  for row in {1..8}; do
    control="$work/8-$run.snap"
    [[ "$row" != 8 ]] || control="$work/8-$((3-run)).snap"
    python3 "$REPO/tools/analyze_b68.py" "$row" "$work/$row-$run.io" "$control" "$work/$row-$run.snap" "$work/labels-$row.json" >>"$result"
  done
done
output="${PC88_B68_OUTPUT_DIR:-$REPO/measurements}"
mkdir -p "$output"
cp "$work/result-1.txt" "$output/b68-official-1.txt"
cp "$work/result-2.txt" "$output/b68-official-2.txt"
