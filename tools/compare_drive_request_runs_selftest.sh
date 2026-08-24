#!/usr/bin/env bash
# 合成要求runで全位置比較器の検出力を確認する。公式データ不使用。
set -u
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ANALYZER="$REPO/tools/compare_drive_request_runs.py"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
fail=0
ok() { echo "OK  - $1"; }
ng() { echo "NG  - $1"; fail=1; }

gen() {
  python3 - "$1" "$2" <<'PYEOF'
import sys
path, mode = sys.argv[1:]
runs = [[0x10, 0x20], [0x02, 0x01, 0x00, 0x33, 0x44, 0x06, 0x12, 0x60], [0x55]]
if mode == "value":
    runs[1][2] = 0x01
elif mode == "structure":
    runs[0].append(0x21)
rows=[]; seq=0; clock=0
for run in runs:
    for pos, value in enumerate(run):
        seq += 1; clock += 1
        pc = "3811" if pos % 2 else "37F4"
        rows.append(f"{seq:6d} {clock:7d} {701:6d} main  OUT   00FD   {value:02X}   {pc}")
        if pos + 1 < len(run):
            seq += 1; clock += 1
            rows.append(f"{seq:6d} {clock:7d} {701:6d} main  IN    00FE   00   37DC")
    seq += 1; clock += 1
    rows.append(f"{seq:6d} {clock:7d} {701:6d} main  IN    00FC   00   3863")
open(path, "w", encoding="utf-8").write("# main\n" + "\n".join(rows) + "\n")
PYEOF
}

gen "$WORK/base.iolog.txt" base
gen "$WORK/same.iolog.txt" base
gen "$WORK/value.iolog.txt" value
gen "$WORK/structure.iolog.txt" structure

if python3 "$ANALYZER" --drive-a "$WORK/base.iolog.txt" --drive-b "$WORK/same.iolog.txt" \
     --out "$WORK/same.txt" && grep -q '値差: 0件' "$WORK/same.txt"; then
  ok "同一入力はrc=0・値差0件"
else
  ng "同一入力を一致判定できない"
fi

if python3 "$ANALYZER" --drive-a "$WORK/base.iolog.txt" --drive-b "$WORK/value.iolog.txt" \
     --out "$WORK/value.txt"; then rc=0; else rc=$?; fi
if [ "$rc" -eq 1 ] && grep -q 'run\[1\] byte\[2\]: A=00 B=01' "$WORK/value.txt" \
   && grep -q 'fixed8\[0\].*差位置=2' "$WORK/value.txt"; then
  ok "陽性対照: 1位置の故障を位置・値つきで検出"
else
  ng "1位置の故障を検出できない"
fi

if python3 "$ANALYZER" --drive-a "$WORK/base.iolog.txt" --drive-b "$WORK/structure.iolog.txt" \
     --out "$WORK/structure.txt"; then rc=0; else rc=$?; fi
if [ "$rc" -eq 1 ] && grep -q 'run長差: 1件' "$WORK/structure.txt"; then
  ok "陽性対照: run長の故障を構造差として検出"
else
  ng "run構造の故障を検出できない"
fi

exit "$fail"
