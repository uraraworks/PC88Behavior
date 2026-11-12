#!/usr/bin/env bash
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
source "$REPO/tools/lib_l3_measure.sh"
[[ $# == 1 && ! -e "$1" ]] || { echo '新規の出力ディレクトリを指定してください' >&2; exit 2; }
parent="$(cd "$(dirname "$1")" && pwd -P)"
case "$parent/$(basename "$1")/" in "$REPO/"*) echo '出力はリポジトリ外に指定してください' >&2; exit 2;; esac
mkdir "$1"; out="$(cd "$1" && pwd -P)"; mkdir "$out/raw" "$out/summary"
core="${PC88_SUB_READ_CORE:-$(find_l3_core)}"
if [[ -z "${PC88_SUB_READ_CORE:-}" ]]; then
  symbols="$(nm "$core" 2>/dev/null || true)"
  if [[ "$symbols" != *retro_q88h_sub_snapshot* ]]; then
    for candidate in "$REPO"/tmp/b62-core/core/quasi88_libretro.* "$REPO"/tmp/b38-final/core/quasi88_libretro.*; do
      [[ -f "$candidate" ]] || continue
      symbols="$(nm "$candidate" 2>/dev/null || true)"
      if [[ "$symbols" == *retro_q88h_sub_snapshot* && "$symbols" == *retro_q88h_sub_rom_read* ]]; then core="$candidate"; break; fi
    done
  fi
fi
[[ -f "$core" ]] || { echo 'コアがありません' >&2; exit 1; }
ensure_l3_frontend >"$out/raw/frontend.log" 2>&1
if [[ -n "${PC88_REF_ROM_DIR:-}" ]]; then [[ -f "$PC88_REF_ROM_DIR/DISK.ROM" ]] || exit 2; fi
work="$(mktemp -d "${TMPDIR:-/tmp}/b85-rom.XXXXXX")"; trap 'rm -rf "$work"' EXIT
if bash "$REPO/tools/b85_controls.sh" >"$out/raw/controls.log" 2>&1; then echo pass >"$out/raw/controls.status"; else echo fail >"$out/raw/controls.status"; fi
for row in {1..8}; do
  TMPDIR="$work" python3 "$REPO/tools/b85_probe_rom.py" "$work/rom-$row" --row "$row" >"$out/raw/build-$row.log" 2>&1
  if [[ -n "${PC88_REF_ROM_DIR:-}" ]]; then cp "$PC88_REF_ROM_DIR/DISK.ROM" "$work/rom-$row/DISK.ROM"; fi
  for run in 1 2; do
    p="$out/raw/$row-$run"
    python3 "$REPO/tools/make_l3_testdisk.py" "$p.d88" --cylinders 40 --double-sided --sectors-per-track 16 --content-rule coord-header --disk-id 0xA1 >"$p.disk.log" 2>&1
    cp "$p.d88" "$p.before.d88"
    # 最初の走行で終端 IN FC の通し番号を求め、同一初期条件で採取する。
    for pass in first final; do
      cp "$p.before.d88" "$p.d88"
      args=(); if [[ "$pass" == final ]]; then args=(--sub-snapshot "$p.snap" --sub-snapshot-at-fc "$target"); fi
      /usr/bin/perl -e 'alarm shift; exec @ARGV' 120 "$REPO/tools/harness/frontend/q88measure" --core "$core" --rom-dir "$work/rom-$row" --frames 2010 --disk "$p.d88" --io-log "$p.$pass.io" --mem-write-log "$p.$pass.mem" --mem-write-range DF50-DF53 ${args[@]+"${args[@]}"} >"$p.$pass.out" 2>"$p.$pass.err" || true
      if [[ "$pass" == first ]]; then cp "$p.d88" "$p.first.d88"; target="$(python3 "$REPO/tools/b85_summarize.py" --target "$p.first.io" "$p.first.mem" || echo 0)"; fi
    done
  done
done
python3 "$REPO/tools/b85_summarize.py" "$out" 
