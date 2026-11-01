#!/usr/bin/env bash
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
source "$REPO/tools/lib_l3_measure.sh"
work="${PC88_B52C_WORK:-}"; dry=""; output="$REPO/measurements"
core="${PC88_SUB_READ_CORE:-}"
while (($#)); do
  case "$1" in
    --work) work="$2"; shift 2;;
    --dry-run-sub-rom) dry="$2"; shift 2;;
    --output-dir) output="$2"; shift 2;;
    *) exit 2;;
  esac
done
[[ -n "$work" && ! -e "$work" ]] || { echo '作業先は未作成のパスを指定してください' >&2; exit 2; }
[[ -n "$core" ]] || core="$(find_l3_core)"
[[ -f "$core" ]] || { echo 'B52c: コアがありません' >&2; exit 1; }
if [[ -n "$dry" ]]; then sub="$dry"; else sub="${PC88_REF_ROM_DIR:?}/DISK.ROM"; fi
[[ -f "$sub" ]] || { echo 'B52c: サブ ROM がありません' >&2; exit 1; }
mkdir -p "$work"; work="$(cd "$work" && pwd)"
python3 "$REPO/tools/make_l3_testdisk.py" "$work/a.d88" --cylinders 40 --double-sided --sectors-per-track 16 --content-rule coord-header --disk-id 0xA1 >"$work/disk.log" 2>&1
core_src="${PC88_SUB_READ_CORE_SRC:-$(cd "$REPO/.." && pwd)/vendor/quasi88-libretro/src}"
cc -O2 -std=c99 -D_POSIX_C_SOURCE=200809L -I"$core_src/LIBRETRO/libretro-common/include" -I"$REPO/tools/harness/core" "$REPO/tools/harness/frontend/main.c" -ldl -o "$work/front"
for row in 1 2 3 4 5; do
  TMPDIR="$work" python3 "$REPO/src/build_main_rom.py" "$work/rom-$row" --inject-b52c-row "$row" --labels-out "$work/labels-$row.json" >"$work/build-$row.log" 2>&1
  cp "$sub" "$work/rom-$row/DISK.ROM"
  for run in 1 2; do
    prefix="$work/$row-$run"
    /usr/bin/perl -e 'alarm shift; exec @ARGV' 120 "$work/front" --core "$core" --rom-dir "$work/rom-$row" --frames 2010 --disk "$work/a.d88" --sub-snapshot "$prefix.snap" --sub-snapshot-at-fc 0 --mem-write-log "$prefix.mem" --mem-write-range DE00-DE04 >"$prefix.out" 2>"$prefix.err"
    [[ -s "$prefix.snap" ]] || { echo 'B52c: スナップショットを取得できません' >&2; exit 1; }
    python3 - "$prefix.mem" <<'PY'
import sys
lines = [line.split() for line in open(sys.argv[1])]
assert any(len(x) >= 5 and x[3:5] == ['DE01', '01'] for x in lines)
assert not any(len(x) >= 5 and x[3:5] == ['DE00', '01'] for x in lines)
PY
  done
done
mkdir -p "$output"
kind=official; [[ -z "$dry" ]] || kind=self
for run in 1 2; do
  result="$work/result-$run"
  : > "$result"
  for row in 1 2 3 4 5; do
    printf '# row %s\n' "$row" >> "$result"
    target="$work/$row-$run.snap"
    [[ "$row" != 5 ]] || target="$work/5-$((3-run)).snap"
    python3 "$REPO/tools/b52c_diff.py" "$work/5-$run.snap" "$target" "$row" >> "$result"
    printf '\n' >> "$result"
  done
  cp "$result" "$output/b52c-$kind-$run.txt"
done
