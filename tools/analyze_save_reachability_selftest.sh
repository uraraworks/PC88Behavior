#!/usr/bin/env bash
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/pc88-save-reach-selftest.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT

gen() {
  python3 - "$1" "$2" <<'PY'
import sys

path, fault = sys.argv[1], sys.argv[2]
rows = []
seq = 0
def ev(kind, port, value, pc="0100"):
    global seq
    seq += 1
    rows.append(f"{seq:6} {seq:6} {seq // 100:6}  sub   {kind:<4}  {port}   {value & 0xFF:02X}   {pc}")

# SAVE候補の直前にある2バイトrun。OUT $FDで窓(a)を切る。
for _ in range(2): ev("IN", "00FC", 0x14)
ev("OUT", "00FD", 0x00)

is_official = "official" in path
n = 261 if is_official else 12
for pos in range(1, n + 1):
    ev("IN", "00FC", 0x00 if pos == 1 else pos)
    if pos <= 5:
        ev("OUT", "00FF", 0x0C); ev("OUT", "00FF", 0x0B)
    elif pos < 261 and pos % 2 == 1:
        ev("OUT", "00FF", 0x0C); ev("OUT", "00FF", 0x0B)
    elif pos == 261:
        ev("OUT", "00FF", 0x0C)
    if fault == "phase" and pos == 6:
        ev("OUT", "00FF", 0x0C)  # 対内継続を単発完了へ壊す故障注入

if is_official:
    ev("OUT", "00F8", 0x07)
    ev("OUT", "00F7", 0x08)
    if fault == "early-tc": ev("IN", "00F8", 0xFF)
    # WRITE DATA 1件（公開コマンド語、合成値のみ）。
    ev("OUT", "00FB", 0x45)
    params = [0, 0, 0, 1, 1, 16, 14, 255]
    if fault == "parameter": params[5] = 15
    for k in params: ev("OUT", "00FB", k)
    for k in range(256): ev("OUT", "00FB", k)
    if fault != "missing-data-tc": ev("IN", "00F8", 0xFF)
    for k in range(7): ev("IN", "00FB", k)
    if fault == "post-tc": ev("OUT", "00F8", 0x07)
    ev("IN", "00FC", 0)
    ev("OUT", "00FD", 0)
else:
    # WRITEなしでもパーサが空でない陽性対照にする。
    ev("OUT", "00FB", 0x03); ev("OUT", "00FB", 0); ev("OUT", "00FB", 0)

with open(path, "w", encoding="utf-8") as f:
    f.write("\n".join(rows) + "\n")
PY
}

gen "$WORK/official-ok.iolog" ok
gen "$WORK/mixed-ok.iolog" ok
out="$(python3 "$REPO/tools/analyze_save_reachability.py" \
    --official "$WORK/official-ok.iolog" --mixed "$WORK/mixed-ok.iolog" \
    --expected-official-writes 1 --expected-mixed-writes 0 \
    --expected-mixed-run-length 12 --expected-opcode-prefix 0)"
if [ "$?" -ne 0 ]; then
  echo "NG: 無傷の合成ログが不合格"
  printf '%s\n' "$out"
  exit 1
fi

gen "$WORK/official-broken.iolog" phase
if python3 "$REPO/tools/analyze_save_reachability.py" \
    --official "$WORK/official-broken.iolog" --mixed "$WORK/mixed-ok.iolog" \
    --expected-official-writes 1 --expected-mixed-writes 0 \
    --expected-mixed-run-length 12 --expected-opcode-prefix 0 >/dev/null 2>&1; then
  echo "NG: 位置6の単発化故障を検出できない"
  exit 1
fi

for fault in post-tc early-tc missing-data-tc parameter; do
  gen "$WORK/official-$fault.iolog" "$fault"
  if python3 "$REPO/tools/analyze_save_reachability.py" \
      --official "$WORK/official-$fault.iolog" --mixed "$WORK/mixed-ok.iolog" \
      --expected-official-writes 1 --expected-mixed-writes 0 \
      --expected-mixed-run-length 12 --expected-opcode-prefix 0 >/dev/null 2>&1; then
    echo "NG: WRITE境界故障($fault)を検出できない"
    exit 1
  fi
done

echo "analyze_save_reachability_selftest: OK（無傷合格、WRITE位相・前後境界故障を検出）"
