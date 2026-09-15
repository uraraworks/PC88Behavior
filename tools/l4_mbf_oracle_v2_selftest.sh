#!/usr/bin/env bash
# tools/l4_mbf_oracle_v2_selftest.sh — tools/l4_mbf_oracle_v2.py 自体を検査する。
#
# v1(tools/l4_mbf_oracle_selftest.sh)と同じ作法: 検査器を信用してよいのは
# わざと壊して検出できることを確かめた後だけ。公式ROM不要。
#
# 使い方: tools/l4_mbf_oracle_v2_selftest.sh
# 全項目 OK なら終了コード 0、1つでも落ちたら 1。

set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

FAIL=0
pass() { echo "OK  - $1"; }
fail() { echo "NG  - $1"; FAIL=1; }

PY() { python3 "$@"; }

# --- 1. 既知のMBFバイト列4件との一致・往復変換(v1と同じ検査) -----------
CHECK1="$(PY - "$REPO_ROOT" <<'EOF'
import sys
sys.path.insert(0, sys.argv[1])
import tools.l4_mbf_oracle_v2 as m
from fractions import Fraction as F

vectors = [
    (F(1), 24, bytes.fromhex("00000081")),
    (F(1, 2), 24, bytes.fromhex("00000080")),
    (F(-1), 24, bytes.fromhex("00008081")),
    (F(10), 24, bytes.fromhex("00002084")),
]
ok = True
for val, nbits, want in vectors:
    s, e, mant = m.encode_mbf(val, nbits)
    got = m.mbf4_bytes(s, e, mant)
    if got != want:
        print(f"MISMATCH {val}: got {got.hex()} want {want.hex()}")
        ok = False
    s2, e2, mant2 = m.mbf4_from_bytes(got)
    back = m.decode_mbf(s2, e2, mant2, nbits)
    if back != val:
        print(f"ROUNDTRIP MISMATCH {val}: back={back}")
        ok = False
print("PASS" if ok else "FAIL")
EOF
)"
if [ "$CHECK1" = "PASS" ]; then
  pass "既知のMBF単精度バイト列4件(1.0/0.5/-1.0/10.0)と往復変換"
else
  fail "既知のMBF単精度バイト列: $CHECK1"
fi

# --- 2. INFPD/INFMD(MATH1.ASM 776-792)の実バイト列と一致 ----------------
CHECK_INF="$(PY - "$REPO_ROOT" <<'EOF'
import sys
sys.path.insert(0, sys.argv[1])
import tools.l4_mbf_oracle_v2 as m
# 単精度: FF FF 7F FF (符号+仮数部, 指数255) = 仮数全ビット1
s, e, mant = m.encode_mbf(__import__("fractions").Fraction(0), 24)  # ダミー呼び出し確認用ではない
n = m._max_value_num("single", 0)
b = m.mbf4_bytes(n.sign, n.exp, n.mant)
want = bytes.fromhex("FFFF7FFF")
print("PASS" if b == want else f"FAIL {b.hex()} != {want.hex()}")
EOF
)"
if [ "$CHECK_INF" = "PASS" ]; then
  pass "INFPD/INFMD相当(最大値)のバイト列がFF FF 7F FF(単精度)と一致"
else
  fail "INFPD/INFMD: $CHECK_INF"
fi

# --- 3. 予測表v2の再生成がバイト一致すること -----------------------------
ARMS="$REPO_ROOT/docs/notes/l4-s4a-gwbasic-predictions-v2.tsv"
if [ -f "$ARMS" ]; then
  TMP="$(mktemp)"
  (cd "$REPO_ROOT" && PY tools/gen_l4_s4a_predictions_v2.py) > "$TMP" 2>/tmp/l4_oracle_v2_gen.err
  if diff -q "$TMP" "$ARMS" >/dev/null 2>&1; then
    pass "docs/notes/l4-s4a-gwbasic-predictions-v2.tsv の再生成がバイト一致"
  else
    fail "予測表v2の再生成が既存ファイルと不一致(diff未一致)"
  fi
  rm -f "$TMP"
else
  echo "SKIP - 予測表v2(l4-s4a-gwbasic-predictions-v2.tsv)がまだ無い(1本目のコミット時点では正常)"
fi

# --- 3.5 --single-digits を足しても既定(7=GW-BASICどおり)は変わらないこと --
# 仮説H6検証用に単精度の有効桁数を差し替え可能にしたが、既定7のときは
# 従来のv2予測(l4-s4a-gwbasic-predictions-v2.tsv)とバイト一致する必要が
# ある。predict()の引数省略とpredict(...,7)の一致、およびCLIの
# --single-digits省略時の出力一致の両方を確認する。
DEFAULT_MATCH_CHECK="$(PY - "$REPO_ROOT" <<'EOF'
import sys
sys.path.insert(0, sys.argv[1])
import tools.l4_mbf_oracle_v2 as m

arms = [
    "1.5", ".5", "-.5", "0.25", "123.456",
    "1/3", "2/3", "10/3", "1234567.8", "12345678",
    "999999", "9999999", "10000000", "1e10", "-1.5e+20",
    ".1", ".01", ".001", "1e-10",
    "40000", "30000+30000", "-32768-1", "200*200", "7/2",
    "1#/3", "1d10", "12345678901234#", "1/3#",
    ".1+.2", "1/3*3",
    "1e38*10", "1/0",
]
ok = True
for expr in arms:
    a = m.predict(expr)
    b = m.predict(expr, 7)
    c = m.predict(expr, m.MBF_SINGLE_DIGITS)
    if not (a == b == c):
        print(f"MISMATCH {expr}: default={a} explicit7={b} const={c}")
        ok = False
print("PASS" if ok else "FAIL")
EOF
)"
if [ "$DEFAULT_MATCH_CHECK" = "PASS" ]; then
  pass "--single-digits 省略時(既定7)は明示的に7を渡した場合と一致(32腕全件)"
else
  fail "既定値の一致: $DEFAULT_MATCH_CHECK"
fi

CLI_DEFAULT_CHECK="$( (cd "$REPO_ROOT" && PY tools/l4_mbf_oracle_v2.py "1/3") )"
CLI_EXPLICIT7_CHECK="$( (cd "$REPO_ROOT" && PY tools/l4_mbf_oracle_v2.py --single-digits 7 "1/3") )"
if [ "$CLI_DEFAULT_CHECK" = "$CLI_EXPLICIT7_CHECK" ] && [ -n "$CLI_DEFAULT_CHECK" ]; then
  pass "CLIの--single-digits省略時と--single-digits 7の出力が一致"
else
  fail "CLI既定値: default=[$CLI_DEFAULT_CHECK] explicit7=[$CLI_EXPLICIT7_CHECK]"
fi

# 倍精度は --single-digits の影響を受けないこと(W1: 1#/3 は常に16桁)
DOUBLE_UNAFFECTED_CHECK="$(PY - "$REPO_ROOT" <<'EOF'
import sys
sys.path.insert(0, sys.argv[1])
import tools.l4_mbf_oracle_v2 as m
k6, p6, a6 = m.predict("1#/3", 6)
k7, p7, a7 = m.predict("1#/3", 7)
print("PASS" if (k6, p6) == (k7, p7) else f"FAIL 6={p6!r} 7={p7!r}")
EOF
)"
if [ "$DOUBLE_UNAFFECTED_CHECK" = "PASS" ]; then
  pass "倍精度は --single-digits の影響を受けない(1#/3 がN=6でもN=7でも同じ)"
else
  fail "倍精度が影響を受けてしまっている: $DOUBLE_UNAFFECTED_CHECK"
fi

# --- 3.6 仮説H6予測表(単精度6桁)の再生成がバイト一致すること --------------
for pair in \
  "docs/notes/l4-s4b-h6-predictions.tsv:tools/gen_l4_s4b_h6_predictions.py" \
  "docs/notes/l4-s4a-h6-posthoc.tsv:tools/gen_l4_s4a_h6_posthoc.py"
do
  OUT="${pair%%:*}"
  GEN="${pair##*:}"
  TARGET="$REPO_ROOT/$OUT"
  if [ -f "$TARGET" ]; then
    TMP="$(mktemp)"
    (cd "$REPO_ROOT" && PY "$GEN") > "$TMP" 2>/tmp/l4_oracle_h6_gen.err
    if diff -q "$TMP" "$TARGET" >/dev/null 2>&1; then
      pass "$OUT の再生成がバイト一致"
    else
      fail "$OUT の再生成が既存ファイルと不一致(diff未一致)"
    fi
    rm -f "$TMP"
  else
    echo "SKIP - $OUT がまだ無い(1本目のコミット時点では正常)"
  fi
done

# --- 4. v1とv2の乖離例(9924.8*984025.0)を固定する -----------------------
# 単精度乗算$FMULSは厳密48bit積の下位16bitをスティッキーなしで捨てる
# (MATH2.ASM 449-450)。この腕は「厳密値を求めて1回偶数丸め」(v1)と
# 「8086の部分積どおりに丸め」(v2)が実際に食い違う具体例として見つけた。
DIVERGE_CHECK="$(PY - "$REPO_ROOT" <<'EOF'
import sys
sys.path.insert(0, sys.argv[1])
import tools.l4_mbf_oracle as v1
import tools.l4_mbf_oracle_v2 as v2

expr = "9924.8*984025.0"
k1, p1 = v1.predict(expr)
k2, p2, approx = v2.predict(expr)
want1 = ("numeric", " 9.766252E+09 ")
want2 = ("numeric", " 9.76625E+09 ")
ok = (k1, p1) == want1 and (k2, p2) == want2 and (k1, p1) != (k2, p2)
print("PASS" if ok else f"FAIL v1=({k1},{p1!r}) v2=({k2},{p2!r})")
EOF
)"
if [ "$DIVERGE_CHECK" = "PASS" ]; then
  pass "v1/v2の乖離例 9924.8*984025.0 (v1= 9.766252E+09 / v2= 9.76625E+09) を固定"
else
  fail "v1/v2乖離例: $DIVERGE_CHECK"
fi

# --- 5. 32腕そのものはv1/v2で差が無いことの確認(記録) --------------------
NODIFF_CHECK="$(PY - "$REPO_ROOT" <<'EOF'
import sys
sys.path.insert(0, sys.argv[1])
import tools.l4_mbf_oracle as v1
import tools.l4_mbf_oracle_v2 as v2

arms = [
    "1.5", ".5", "-.5", "0.25", "123.456",
    "1/3", "2/3", "10/3", "1234567.8", "12345678",
    "999999", "9999999", "10000000", "1e10", "-1.5e+20",
    ".1", ".01", ".001", "1e-10",
    "40000", "30000+30000", "-32768-1", "200*200", "7/2",
    "1#/3", "1d10", "12345678901234#", "1/3#",
    ".1+.2", "1/3*3",
    "1e38*10", "1/0",
]
diffs = []
for expr in arms:
    k1, p1 = v1.predict(expr)
    k2, p2, _ = v2.predict(expr)
    if (k1, p1) != (k2, p2):
        diffs.append(expr)
print("PASS(0件)" if not diffs else f"DIFFS:{diffs}")
EOF
)"
if [ "$NODIFF_CHECK" = "PASS(0件)" ]; then
  pass "32腕自体はv1/v2で出力差0件(乖離は上記9924.8*984025.0の別入力でのみ確認)"
else
  fail "32腕の想定外差分: $NODIFF_CHECK"
fi

# --- 6. 故障注入: 単精度乗算のスティッキー破棄をv1相当に「壊す」と、
#        乖離例での判定が反転すること -------------------------------------
FAULT_MUL_CHECK="$(L4_ORACLE_FAULT=mul_sticky PY - "$REPO_ROOT" <<'EOF'
import sys
sys.path.insert(0, sys.argv[1])
import tools.l4_mbf_oracle_v2 as m
expr = "9924.8*984025.0"
kind, pred, approx = m.predict(expr)
# 故障注入(mul_sticky)は v1 と同じ「厳密丸め」に戻すので、
# v1の既知の答え(9.766252E+09)に一致するはず == 通常のv2結果とは異なる
print("FAULT_DETECTED" if pred == " 9.766252E+09 " else f"FAULT_NOT_DETECTED pred={pred!r}")
EOF
)"
if [ "$FAULT_MUL_CHECK" = "FAULT_DETECTED" ]; then
  pass "故障注入(L4_ORACLE_FAULT=mul_sticky)で単精度乗算の判定がv1相当に戻ることを確認"
else
  fail "故障注入(mul_sticky)が検出されなかった: $FAULT_MUL_CHECK"
fi

# --- 7. 偶数丸めの故障注入(v1と同じ検査を流用) --------------------------
ROUND_CHECK="$(PY - "$REPO_ROOT" <<'EOF'
import sys
sys.path.insert(0, sys.argv[1])
import tools.l4_mbf_oracle_v2 as m
from fractions import Fraction as F
a = m._round_half_even(F(5, 2))
b = m._round_half_even(F(7, 2))
print("PASS" if (a == 2 and b == 4) else f"FAIL a={a} b={b}")
EOF
)"
if [ "$ROUND_CHECK" = "PASS" ]; then
  pass "偶数丸め(round-half-to-even)が2.5->2, 3.5->4を満たす"
else
  fail "偶数丸め: $ROUND_CHECK"
fi

FAULT_ROUND_CHECK="$(L4_ORACLE_FAULT=round_up PY - "$REPO_ROOT" <<'EOF'
import sys
sys.path.insert(0, sys.argv[1])
import tools.l4_mbf_oracle_v2 as m
from fractions import Fraction as F
a = m._round_half_even(F(5, 2))
print("FAULT_DETECTED" if a != 2 else "FAULT_NOT_DETECTED")
EOF
)"
if [ "$FAULT_ROUND_CHECK" = "FAULT_DETECTED" ]; then
  pass "故障注入(L4_ORACLE_FAULT=round_up)で偶数丸め検査が意図どおり不一致になる"
else
  fail "故障注入(round_up)が検出されなかった: $FAULT_ROUND_CHECK"
fi

# --- 8. 整数溢れ時の単精度昇格(v1と同じ検査を流用) ----------------------
PROMO_CHECK="$(PY - "$REPO_ROOT" <<'EOF'
import sys
sys.path.insert(0, sys.argv[1])
import tools.l4_mbf_oracle_v2 as m
kind, pred, approx = m.predict("30000+30000")
print("PASS" if (kind == "numeric" and pred.strip() == "60000") else f"FAIL {kind} {pred!r}")
EOF
)"
if [ "$PROMO_CHECK" = "PASS" ]; then
  pass "整数溢れ時の単精度昇格(30000+30000=60000)"
else
  fail "整数溢れ昇格: $PROMO_CHECK"
fi

echo
if [ "$FAIL" = "0" ]; then
  echo "l4_mbf_oracle_v2_selftest: 全項目OK"
else
  echo "l4_mbf_oracle_v2_selftest: NGあり"
fi
exit "$FAIL"
