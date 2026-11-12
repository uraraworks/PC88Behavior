#!/usr/bin/env bash
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
source "$REPO/tools/lib_l3_measure.sh"
[[ $# == 1 && ! -e "$1" ]] || { echo '新規の出力ディレクトリを指定してください' >&2; exit 2; }
parent="$(cd "$(dirname "$1")" && pwd -P)"
case "$parent/$(basename "$1")/" in "$REPO/"*) echo '出力はリポジトリ外に指定してください' >&2; exit 2;; esac
mkdir "$1"; out="$(cd "$1" && pwd -P)"; mkdir "$out/raw" "$out/summary"
core="${PC88_SUB_READ_CORE:-$(find_l3_core)}"
ensure_l3_frontend >"$out/raw/frontend.log" 2>&1
[[ -z "${PC88_REF_ROM_DIR:-}" || -f "$PC88_REF_ROM_DIR/DISK.ROM" ]] || exit 2
work="$(mktemp -d "${TMPDIR:-/tmp}/b85a.XXXXXX")"; trap 'rm -rf "$work"' EXIT
if bash "$REPO/tools/b85_controls.sh" >"$out/raw/controls.log" 2>&1; then echo pass >"$out/raw/controls.status"; else echo fail >"$out/raw/controls.status"; fi
# 自作どうしの対照: 09なしと、0Cで書いたバッファの既知要求による読み戻し。
for control in negative positive; do
  TMPDIR="$work" python3 "$REPO/tools/b85_addendum1_rom.py" "$work/control-$control" --row 1 --control "$control" >"$out/raw/control-$control.build" 2>&1
  python3 "$REPO/tools/make_l3_testdisk.py" "$out/raw/control-$control.d88" --cylinders 40 --double-sided --sectors-per-track 16 --content-rule coord-header --disk-id 0xA1 >"$out/raw/control-$control.disk.log" 2>&1
  if ! /usr/bin/perl -e 'alarm shift; exec @ARGV' 300 "$REPO/tools/harness/frontend/q88measure" --core "$core" --rom-dir "$work/control-$control" --frames 2010 --disk "$out/raw/control-$control.d88" --io-log "$out/raw/control-$control.io" --mem-write-log "$out/raw/control-$control.mem" --mem-write-range DF50-DF53 >"$out/raw/control-$control.out" 2>"$out/raw/control-$control.err"; then echo fail >"$out/raw/controls.status"; fi
done
if ! PYTHONPATH="$REPO/tools" python3 "$REPO/tools/b85_addendum1_control.py" "$out" >"$out/raw/addendum-controls.log" 2>&1; then echo fail >"$out/raw/controls.status"; fi
for row in $(seq 1 15); do
  TMPDIR="$work" python3 "$REPO/tools/b85_addendum1_rom.py" "$work/rom-$row" --row "$row" >"$out/raw/build-$row.log" 2>&1
  if [[ -n "${PC88_REF_ROM_DIR:-}" ]]; then cp "$PC88_REF_ROM_DIR/DISK.ROM" "$work/rom-$row/DISK.ROM"; fi
  for run in 1 2; do
    p="$out/raw/$row-$run"
    python3 "$REPO/tools/make_l3_testdisk.py" "$p.d88" --cylinders 40 --double-sided --sectors-per-track 16 --content-rule coord-header --disk-id 0xA1 >"$p.disk.log" 2>&1
    /usr/bin/perl -e 'alarm shift; exec @ARGV' 300 "$REPO/tools/harness/frontend/q88measure" --core "$core" --rom-dir "$work/rom-$row" --frames 2010 --disk "$p.d88" --io-log "$p.io" --mem-write-log "$p.mem" --mem-write-range DF50-DF53 >"$p.out" 2>"$p.err" || { echo '実行失敗' >&2; exit 1; }
  done
done
python3 "$REPO/tools/b85_addendum1_summary.py" "$out"
