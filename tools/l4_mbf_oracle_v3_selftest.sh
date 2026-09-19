#!/usr/bin/env bash
# tools/l4_mbf_oracle_v3_selftest.sh — tools/l4_mbf_oracle_v3.py の自己検査。
#
# v2 selftestと同じ作法: 検査器を信用してよいのは、わざと壊して検出できる
# ことを確かめた後だけ(陰性対照)。公式ROM不要。
#
# 使い方: tools/l4_mbf_oracle_v3_selftest.sh
# 全項目 OK なら終了コード 0、1つでも落ちたら 1。

set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

FAIL=0
pass() { echo "OK  - $1"; }
fail() { echo "NG  - $1"; FAIL=1; }

# --- 1. 定数復号の妥当性(実世界の定数に近いか。ROM非依存) --------------
CHECK1="$(python3 - "$REPO_ROOT" <<'EOF'
import sys, math
sys.path.insert(0, sys.argv[1])
import tools.l4_mbf_oracle_v3 as m

want = {
    "LOG2E": math.log2(math.e),
    "LN2": math.log(2),
    "ONE_S": 1.0,
    "TAN_PI12": math.tan(math.pi/12),
    "SQRT3": math.sqrt(3),
    "PI2": math.pi/2,
    "PI6": math.pi/6,
    "TWO_PI": 2*math.pi,
}
ok = True
for name, exp in want.items():
    got = float(getattr(m, name).exact())
    if abs(got - exp) > 1e-4:
        print(f"MISMATCH {name}: got {got} want~={exp}")
        ok = False
print("RESULT_OK" if ok else "RESULT_NG")
EOF
)"
if echo "$CHECK1" | grep -q RESULT_OK; then pass "定数復号(LOG2E/LN2/PI2等)が実世界の値と一致"; else fail "定数復号が不一致: $CHECK1"; fi

# --- 2. 既知値(数学的に既知の三角関数・SQR・EXP・LOGの値) ---------------
CHECK2="$(python3 "$REPO_ROOT/tools/l4_mbf_oracle_v3.py" 2>&1)"
if echo "$CHECK2" | grep -q "^NG"; then
  fail "既知値チェックで不一致: $(echo "$CHECK2" | grep '^NG')"
else
  pass "既知値チェック(sqr/sin/cos/tan/atn/exp/log 12件)すべて一致"
fi

# --- 3. 陰性対照: SINCN係数を1つ壊すと SIN(1) が既知値からずれる --------
CHECK3="$(python3 - "$REPO_ROOT" <<'EOF'
import sys
sys.path.insert(0, sys.argv[1])
import tools.l4_mbf_oracle_v3 as m
from tools.l4_mbf_oracle_v2 import GwNum
import math

# 係数の1つを大きく壊す
m.SINCN[2] = GwNum.from_fraction(m.SINCN[2].exact() * 2, "single")
kind, line, approx = m.predict_fn("sin", "1")
got = float(line)
want = math.sin(1)
print("BROKEN_OK" if abs(got - want) > 1e-3 else "BROKEN_NG(壊れているのに一致してしまった)")
EOF
)"
if echo "$CHECK3" | grep -q BROKEN_OK; then
  pass "陰性対照: SINCN係数を壊すとSIN(1)の既知値との差が検出できる"
else
  fail "陰性対照が機能していない: $CHECK3"
fi

# --- 4. 故障注入(L4_ORACLE_V3_FAULT=sqr_break): SQR(2)が既知値からずれる -
CHECK4="$(L4_ORACLE_V3_FAULT=sqr_break python3 - "$REPO_ROOT" <<'EOF'
import sys
sys.path.insert(0, sys.argv[1])
import tools.l4_mbf_oracle_v3 as m
import math
kind, line, approx = m.predict_fn("sqr", "2")
got = float(line)
want = math.sqrt(2)
print("FAULT_OK" if abs(got - want) > 1e-4 else "FAULT_NG")
EOF
)"
if echo "$CHECK4" | grep -q FAULT_OK; then
  pass "故障注入(L4_ORACLE_V3_FAULT=sqr_break)でSQR(2)のずれを検出できる"
else
  fail "故障注入が機能していない: $CHECK4"
fi

# --- 5. エラー系: SQR(-1)・LOG(0)・LOG(-1) は IllegalFunctionCall ------
CHECK5="$(python3 - "$REPO_ROOT" <<'EOF'
import sys
sys.path.insert(0, sys.argv[1])
import tools.l4_mbf_oracle_v3 as m
ok = True
for fname, arg in [("sqr", "-1"), ("log", "0"), ("log", "-1")]:
    kind, line, approx = m.predict_fn(fname, arg)
    if kind != "error" or "IllegalFunctionCall" not in line:
        print(f"MISMATCH {fname}({arg}): kind={kind} line={line}")
        ok = False
print("RESULT_OK" if ok else "RESULT_NG")
EOF
)"
if echo "$CHECK5" | grep -q RESULT_OK; then pass "エラー系(SQR(-1)/LOG(0)/LOG(-1))がIllegalFunctionCall"; else fail "エラー系が不一致: $CHECK5"; fi

echo
if [ "$FAIL" -eq 0 ]; then
  echo "ALL OK"
  exit 0
else
  echo "SOME CHECKS FAILED"
  exit 1
fi
