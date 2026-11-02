#!/usr/bin/env bash
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
work="${PC88_B70_WORK:?作業先を指定してください}"
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
[[ ! -e "$work" && -f "$core" ]] || { echo 'B70: 作業先またはコアが不正です' >&2; exit 1; }
if [[ -n "$dry" ]]; then
  [[ -f "$dry" ]] || exit 1
  arms=(S)
else
  ref="${PC88_REF_ROM_DIR:?ROM ディレクトリを指定してください}/DISK.ROM"
  [[ -f "$ref" ]] || exit 1
  arms=(O S)
fi
mkdir -p "$work"; work="$(cd "$work" && pwd)"
cc -O2 -std=c99 -D_POSIX_C_SOURCE=200809L -I"$core_src/LIBRETRO/libretro-common/include" -I"$REPO/tools/harness/core" "$REPO/tools/harness/frontend/main.c" -ldl -o "$work/front"
python3 "$REPO/tools/make_l3_testdisk.py" "$work/a.d88" --cylinders 40 --double-sided --sectors-per-track 16 --content-rule coord-header --disk-id 0xA1 >"$work/disk.log"
python3 "$REPO/tools/make_l3_testdisk.py" "$work/b.d88" --cylinders 40 --double-sided --sectors-per-track 16 --content-rule coord-header --disk-id 0xA2 >>"$work/disk.log"
if [[ -z "$dry" ]]; then
  python3 "$REPO/src/l3_service/make_subrom.py" "$work/sub" >"$work/sub.log" 2>&1
  dry="$work/sub/DISK.ROM"
fi
for row in {1..5}; do
  for kind in row control; do
    TMPDIR="$work" python3 "$REPO/src/build_main_rom.py" "$work/rom-$kind-$row" "--inject-b70-$kind" "$row" --labels-out "$work/labels-$kind-$row.json" >"$work/build-$kind-$row.log" 2>&1
  done
done
for arm in "${arms[@]}"; do
  sub="$dry"; [[ "$arm" != O ]] || sub="$ref"
  for row in {1..5}; do
    diskargs=(--disk "$work/a.d88" --disk2 "$work/b.d88")
    [[ "$row" != 4 ]] || diskargs=(--disk "$work/a.d88" --expect-disk2-empty)
    for kind in row control; do
      cp "$sub" "$work/rom-$kind-$row/DISK.ROM"
      for run in 1 2; do
        prefix="$work/$arm-$row-$kind-$run"
        args=(--core "$core" --rom-dir "$work/rom-$kind-$row" --frames 2010 "${diskargs[@]}")
        /usr/bin/perl -e 'alarm shift; exec @ARGV' 120 "$work/front" "${args[@]}" --io-log "$prefix.first.io" >"$prefix.first.out" 2>"$prefix.first.err"
        read -r target count < <(python3 "$REPO/tools/analyze_b68.py" "$row" "$prefix.first.io" /dev/null /dev/null "$work/labels-$kind-$row.json" --fc-info)
        if [[ "$target" == -1 ]]; then cp "$prefix.first.io" "$prefix.io"; continue; fi
        /usr/bin/perl -e 'alarm shift; exec @ARGV' 120 "$work/front" "${args[@]}" --io-log "$prefix.io" --sub-snapshot "$prefix.snap" --sub-snapshot-at-fc "$target" >"$prefix.out" 2>"$prefix.err"
        read -r target2 count2 < <(python3 "$REPO/tools/analyze_b68.py" "$row" "$prefix.io" /dev/null /dev/null "$work/labels-$kind-$row.json" --fc-info)
        [[ "$count" == "$count2" && "$target" == "$target2" && -s "$prefix.snap" ]] || { echo 'B70: スナップショットが不一致です' >&2; exit 1; }
      done
    done
  done
  for run in 1 2; do
    result="$work/result-$arm-$run"; : > "$result"
    for row in {1..5}; do
      python3 "$REPO/tools/analyze_b68.py" "$row" "$work/$arm-$row-row-$run.io" "$work/$arm-$row-control-$run.snap" "$work/$arm-$row-row-$run.snap" "$work/labels-row-$row.json" --disk2 | sed "s/^row $row /row $row $arm /" >>"$result"
    done
  done
done
mkdir -p "$output"
result="$output/b70-sub-request-0e-drive2.txt"
: > "$result"
rc=0
for arm in "${arms[@]}"; do
  cat "$work/result-$arm-1" >> "$result"
  cmp -s "$work/result-$arm-1" "$work/result-$arm-2" || { echo "B70: $arm の2走が不一致です" >&2; rc=1; }
done
exit "$rc"
