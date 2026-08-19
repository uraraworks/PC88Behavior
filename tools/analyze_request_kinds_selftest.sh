#!/usr/bin/env bash
# tools/analyze_request_kinds_selftest.sh — tools/analyze_request_kinds.py
# の検出力を合成フィクスチャで検算する（m7bj）。公式ROM・公式ディスク不要。
#
# 「陽性対照は成果物が実際に変わるところまで確認する」規律
# （過去に空振り2回。tools/analyze_record_boundaries_selftest.sh の作法を踏襲）。
#
# 検査内容:
#   i.   陽性対照その1: 或る先頭バイトのrun長を1件だけ変えると、
#        「run長が一意でない」（不一致・例外1件）と報告されること
#   ii.  陽性対照その2: データポートが伏せ字(--)されたログを入力すると、
#        解析不能としてrc≠0で拒否すること
#   iii. 陽性対照その3: 座標(lt/R)を持つ末尾2バイトの位置を1バイトずらすと、
#        報告される一致位置がずれた分だけ変わること
#
# フィクスチャの値はすべてダミー(公式データ不使用)。C/H/Rも架空の値。

set -uo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO" || exit 1
ANALYZE="$REPO/tools/analyze_request_kinds.py"

say() { printf '\n\033[36m==>\033[0m %s\n' "$1"; }
ok()  { printf '  \033[32mOK\033[0m   %s\n' "$1"; }
ng()  { printf '  \033[31mNG\033[0m   %s\n' "$1"; }
overall_rc=0

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

# --- フィクスチャ生成 --------------------------------------------------
# gen 出力 run長 shift 伏せ字
#   run長: 3回分のrun長をカンマ区切り(例 "5,5,5" / "5,5,4")
#   shift: lt/Rの後ろに挟む余計なfillerバイトの個数(位置をずらす陽性対照用)
#   伏せ字: 1でIN $FCの値を"--"にする(拒否テスト用)
gen() {
  python3 - "$1" "$2" "$3" "${4:-0}" <<'PYEOF'
import sys
path, runlens_s, shift, corrupt = sys.argv[1], sys.argv[2], int(sys.argv[3]), sys.argv[4] == "1"
runlens = [int(x) for x in runlens_s.split(",")]

rows = []
seq = [0]
clock = [0]

def ev(cpu, kind, port, value):
    seq[0] += 1
    clock[0] += 1
    v = value if value is not None else "--"
    rows.append(f"{seq[0]:>6} {clock[0]:>7} {clock[0]:>6}  {cpu:<4}  {kind:<4}  {port}   {v}   0100")

# 座標: C=2, H=1, R=7 -> lt = (C<<1)|H = 5
C, H, R = 2, 1, 7
LT = (C << 1) | H

def emit_run(length, shift):
    # 先頭バイトは固定0x11。中間は適当な埋め、末尾2バイトが[LT, R]。
    # shift>0のときは[LT, R]のさらに後ろにshift個のfillerを足し、
    # run全体の長さはlength+shiftへ伸ばす(=座標フィールドの位置が
    # 末尾から遠ざかる)。
    body = [0x11] + [0x22] * max(0, length - 3) + [LT, R] + [0x33] * shift
    for v in body:
        ev("sub", "IN", "00FC", None if corrupt else f"{v:02X}")
    ev("sub", "OUT", "00FD", "00")  # runの終端

def emit_read():
    ev("sub", "OUT", "00FB", "06")  # READ DATA
    params = [0, C, H, R, 2, 0, 0, 0]
    for p in params:
        ev("sub", "OUT", "00FB", f"{p:02X}")
    for _ in range(7):
        ev("sub", "IN", "00FB", "00")

for length in runlens:
    emit_run(length, shift)
    emit_read()

with open(path, "w") as f:
    f.write("# analyze_request_kinds_selftest の合成フィクスチャ(公式データ不使用)\n")
    f.write("core      : (テスト用ダミー)\nframes    : 1\n\n")
    f.write("# main\n# seq    clock   frame  cpu   kind  port  value  pc\n\n")
    f.write("# sub\n# seq    clock   frame  cpu   kind  port  value  pc\n")
    f.write("\n".join(rows) + "\n")
PYEOF
}

run_analyze() {  # $1=iolog $2=out
  python3 "$ANALYZE" --iolog "$1" --label selftest --out "$2"
}

# --- i. 陽性対照: run長を1件だけ変えると「不一致」になること ---------------
gen "$WORK/uniform.iolog.txt" "5,5,5" 0
UNIFORM_OUT="$WORK/uniform_report.txt"
run_analyze "$WORK/uniform.iolog.txt" "$UNIFORM_OUT" >/dev/null
cat "$UNIFORM_OUT" | sed 's/^/  /'
if grep -q "長さ=5 " "$UNIFORM_OUT" && grep -q "例外: 0件" "$UNIFORM_OUT"; then
  ok "i-a. 3回とも長さ5で揃うと「長さ=5」・例外0件と報告される"
else
  ng "i-a. 揃った長さのケースで期待どおりの報告が出なかった"
  overall_rc=1
fi

gen "$WORK/varied.iolog.txt" "5,5,4" 0
VARIED_OUT="$WORK/varied_report.txt"
run_analyze "$WORK/varied.iolog.txt" "$VARIED_OUT" >/dev/null
cat "$VARIED_OUT" | sed 's/^/  /'
if grep -q "不一致" "$VARIED_OUT" && grep -q "例外: 1件" "$VARIED_OUT"; then
  ok "i-b. 陽性対照: run長を1件だけ5→4に変えると「不一致」・例外1件に変わる(検出力の確認)"
else
  ng "i-b. run長を変えても報告が追随しなかった(決め打ちの疑い)"
  overall_rc=1
fi

# --- ii. 陽性対照: 伏せ字ログを解析不可として拒否すること ------------------
gen "$WORK/corrupt.iolog.txt" "5,5,5" 0 1
CORRUPT_OUT="$WORK/corrupt_report.txt"
if python3 "$ANALYZE" --iolog "$WORK/corrupt.iolog.txt" --label corrupt --out "$CORRUPT_OUT" >/tmp/rk_stdout.$$ 2>&1; then
  rc=0
else
  rc=$?
fi
if [[ "$rc" -ne 0 ]] && grep -q "解析不可" "$CORRUPT_OUT"; then
  ok "ii. 陽性対照: 伏せ字済み(--)データポートを検出し解析を拒否する(rc=$rc)"
else
  ng "ii. 伏せ字ログを拒否しなかった(黙って解析してしまった)"
  cat "$CORRUPT_OUT" | sed 's/^/  /'
  overall_rc=1
fi
rm -f /tmp/rk_stdout.$$

# --- iii. 陽性対照: 座標フィールドの位置を1バイトずらすと報告位置が変わる --
gen "$WORK/base.iolog.txt" "5,5,5" 0
BASE_OUT="$WORK/base_report.txt"
run_analyze "$WORK/base.iolog.txt" "$BASE_OUT" >/dev/null

gen "$WORK/shifted.iolog.txt" "6,6,6" 1
SHIFTED_OUT="$WORK/shifted_report.txt"
run_analyze "$WORK/shifted.iolog.txt" "$SHIFTED_OUT" >/dev/null

cat "$BASE_OUT" | sed 's/^/  base:    /'
cat "$SHIFTED_OUT" | sed 's/^/  shifted: /'

if grep -q "論理トラック規則.*位置-1で3/3" "$BASE_OUT" && grep -q "R一致位置: 位置0(末尾)で3/3" "$BASE_OUT"; then
  base_ok=1
else
  base_ok=0
fi
if grep -q "論理トラック規則.*位置-2で3/3" "$SHIFTED_OUT" && grep -q "R一致位置: 位置-1で3/3" "$SHIFTED_OUT"; then
  shifted_ok=1
else
  shifted_ok=0
fi
if [[ "$base_ok" -eq 1 && "$shifted_ok" -eq 1 ]]; then
  ok "iii. 陽性対照: 座標フィールドを1バイト後ろへずらすと、一致位置の報告も"\
"(-1,0)から(-2,-1)へ追随して変わる(決め打ちでないことの確認)"
else
  ng "iii. 位置をずらしても報告が追随しなかった(決め打ちの疑い)"
  overall_rc=1
fi

echo
if [[ "$overall_rc" -eq 0 ]]; then
  echo "analyze_request_kinds_selftest: OK(全項目)"
else
  echo "analyze_request_kinds_selftest: 失敗あり"
fi
exit "$overall_rc"
