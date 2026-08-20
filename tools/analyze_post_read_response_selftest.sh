#!/usr/bin/env bash
# m7bl解析器の陽性対照。合成値のみを使い、成果物の変化まで検査する。
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ANALYZE="$REPO/tools/analyze_post_read_response.py"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
overall_rc=0

gen() { # 出力 recv ack trigger 先行ダミー数 伏せ字
  python3 - "$@" <<'PYEOF'
import sys
path, recv, ack, trigger = sys.argv[1], *(int(x, 0) for x in sys.argv[2:5])
shift, masked = int(sys.argv[5]), int(sys.argv[6])
rows=[]; seq=0; clock=0
def ev(cpu, kind, port, value, pc="0100"):
    global seq, clock
    seq += 1; clock += 1
    v = "--" if value is None else f"{value:02X}"
    rows.append(f"{seq:6} {clock:7} {clock:6}  {cpu:<4}  {kind:<4}  {port}   {v}   {pc}")

# classify_transactions が認識する起動時高速バルクの末尾。
ev("main", "IN", "00FC", 0x55, "C269")
# READ DATA: command+8 params+データ/結果263件。
ev("sub", "OUT", "00FB", 0x06)
for v in (0, 1, 0, 1, 2, 1, 0x1b, 0xff): ev("sub", "OUT", "00FB", v)
for _ in range(263): ev("sub", "IN", "00FB", 0)
# 位置追随用の無関係なpayloadイベント。
for _ in range(shift): ev("sub", "OUT", "00FD", 0x99)
ev("sub", "IN", "00FC", None if masked else recv)
ev("sub", "OUT", "00FD", ack)
ev("sub", "IN", "00FC", trigger)
for n in range(256): ev("sub", "OUT", "00FD", n)

with open(path, "w") as f:
    f.write("# 合成フィクスチャ（公式データ不使用）\n")
    f.write("\n".join(rows) + "\n")
PYEOF
}

run() { python3 "$ANALYZE" --iolog "$1" --label selftest --out "$2" >/dev/null; }

gen "$WORK/base.iolog" 0x11 0x22 0x33 0 0
run "$WORK/base.iolog" "$WORK/base.txt"
gen "$WORK/value.iolog" 0x11 0x2A 0x33 0 0
run "$WORK/value.iolog" "$WORK/value.txt"
if grep -q 'ack.*0x22' "$WORK/base.txt" && grep -q 'ack.*0x2A' "$WORK/value.txt" \
   && ! cmp -s "$WORK/base.txt" "$WORK/value.txt"; then
  echo "OK i: 注入したack値の変更が成果物へ反映された"
else
  echo "NG i: 値変更が成果物を変えなかった"; overall_rc=1
fi

gen "$WORK/masked.iolog" 0x11 0x22 0x33 0 1
if python3 "$ANALYZE" --iolog "$WORK/masked.iolog" --label masked \
    --out "$WORK/masked.txt" >/dev/null 2>&1; then rc=0; else rc=$?; fi
if [[ "$rc" -ne 0 ]] && grep -q '解析不可' "$WORK/masked.txt"; then
  echo "OK ii: 伏せ字ログを解析不可として拒否した(rc=$rc)"
else
  echo "NG ii: 伏せ字ログを拒否しなかった"; overall_rc=1
fi

gen "$WORK/shifted.iolog" 0x11 0x22 0x33 1 0
run "$WORK/shifted.iolog" "$WORK/shifted.txt"
if grep -q '検出開始位置: 1' "$WORK/base.txt" \
   && grep -q '検出開始位置: 2' "$WORK/shifted.txt" \
   && ! cmp -s "$WORK/base.txt" "$WORK/shifted.txt"; then
  echo "OK iii: イベント列を1つずらすと報告位置も1つずれた"
else
  echo "NG iii: 位置変更が成果物へ追随しなかった"; overall_rc=1
fi

if [[ "$overall_rc" -eq 0 ]]; then
  echo "analyze_post_read_response_selftest: OK(全項目)"
else
  echo "analyze_post_read_response_selftest: 失敗あり"
fi
exit "$overall_rc"
