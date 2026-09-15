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

# --- 3. 予測表v2の再生成がデータ行一致すること -----------------------------
# 見出し行(#で始まる行)は「その予測を生成した時点の予測器」のsha256を
# 指す記録であり、再生成のたびに現在のファイルのsha256で上書きしてよい
# ものではない(事前登録物は測定後に書き換えない。2026-09-15、3482064の
# 誤りをf7e99d5へ戻した際の教訓)。この検査はコメント行を除いた
# データ行どうしだけを比較する。生成スクリプト自体はコミット済みの
# ファイルへ直接書き込まない(標準出力するだけ)ので、比較は常に一時
# ファイル上で行う。
ARMS="$REPO_ROOT/docs/notes/l4-s4a-gwbasic-predictions-v2.tsv"
if [ -f "$ARMS" ]; then
  TMP="$(mktemp)"
  (cd "$REPO_ROOT" && PY tools/gen_l4_s4a_predictions_v2.py) > "$TMP" 2>/tmp/l4_oracle_v2_gen.err
  if diff -q <(grep -v '^#' "$TMP") <(grep -v '^#' "$ARMS") >/dev/null 2>&1; then
    pass "docs/notes/l4-s4a-gwbasic-predictions-v2.tsv の再生成がデータ行一致(見出しのshaは比較対象外)"
  else
    fail "予測表v2の再生成が既存ファイルとデータ行不一致(diff未一致)"
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

# --- 3.6 仮説H6予測表(単精度6桁)の再生成がデータ行一致すること ------------
# ここも見出し行(#で始まる行、生成時点の予測器sha256)は比較対象外にする。
# l4-s4b-h6-predictions.tsv は測定中の事前登録物であり、この検査(比較のみ、
# 一時ファイルへ生成)を含めコミット済みファイルへは一切書き込まない。
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
    if diff -q <(grep -v '^#' "$TMP") <(grep -v '^#' "$TARGET") >/dev/null 2>&1; then
      pass "$OUT の再生成がデータ行一致(見出しのshaは比較対象外)"
    else
      fail "$OUT の再生成が既存ファイルとデータ行不一致(diff未一致)"
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

# --- 9. l4-s4c: --small-rule/--small-len を足しても既定(sym)は変わらない --
SMALL_RULE_DEFAULT_CHECK="$(PY - "$REPO_ROOT" <<'EOF'
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
    b = m.predict(expr, m.MBF_SINGLE_DIGITS, "sym", 0)
    if a != b:
        print(f"MISMATCH {expr}: default={a} explicit={b}")
        ok = False
print("PASS" if ok else "FAIL")
EOF
)"
if [ "$SMALL_RULE_DEFAULT_CHECK" = "PASS" ]; then
  pass "--small-rule/--small-len 省略時(既定sym/0)は明示指定と一致(32腕全件)"
else
  fail "small_rule既定値の一致: $SMALL_RULE_DEFAULT_CHECK"
fi

# --- 10. l4-s4c候補予測表の再生成がデータ行一致すること -------------------
S4C="$REPO_ROOT/docs/notes/l4-s4c-candidate-predictions.tsv"
if [ -f "$S4C" ]; then
  TMP="$(mktemp)"
  (cd "$REPO_ROOT" && PY tools/gen_l4_s4c_candidate_predictions.py) > "$TMP" 2>/tmp/l4_oracle_s4c_gen.err
  if diff -q <(grep -v '^#' "$TMP") <(grep -v '^#' "$S4C") >/dev/null 2>&1; then
    pass "docs/notes/l4-s4c-candidate-predictions.tsv の再生成がデータ行一致"
  else
    fail "l4-s4c候補予測表の再生成が既存ファイルとデータ行不一致(diff未一致)"
  fi
  rm -f "$TMP"
else
  echo "SKIP - l4-s4c候補予測表がまだ無い(1本目のコミット時点では正常)"
fi

# --- 11. 故障注入: LEN(T)のTを1ずらすと判定が変わること(検出力の確認) -----
# K4相当(1.5e-7、単精度6桁)はLEN7では指数表記・LEN8では固定小数点になる
# 境界例。Tを+1/-1ずらすと結果が変わることを確認する。
LEN_FAULT_CHECK="$(PY - "$REPO_ROOT" <<'EOF'
import sys
sys.path.insert(0, sys.argv[1])
import tools.l4_mbf_oracle_v2 as m
expr = "1.5e-7"
_, p7, _ = m.predict(expr, 6, "len", 7)
_, p8, _ = m.predict(expr, 6, "len", 8)
ok = p7 != p8 and p7 == " 1.5E-07 " and p8 == " .00000015 "
print("PASS" if ok else f"FAIL p7={p7!r} p8={p8!r}")
EOF
)"
if [ "$LEN_FAULT_CHECK" = "PASS" ]; then
  pass "LEN(T)のTを1ずらす(7→8)と1.5e-7の判定が指数表記→固定小数点に変わる(検出力の確認)"
else
  fail "LEN故障注入の検出力: $LEN_FAULT_CHECK"
fi

# --- 12. l4-s4c v2: sym-def が事前登録の定義どおり(E>-N)であること --------
# 2026-09-15、l4-s4c v1のS0列が定義と食い違っていた指摘を受けて追加。
# 定義: v=d.ddd×10^E(E<0)、S0は -N<E で固定。K3(1.5e-6, 単精度6桁)は
# E=-6, N=6 なので -6<-6 は偽 -> 指数表記が正しい。
SYMDEF_CHECK="$(PY - "$REPO_ROOT" <<'EOF'
import sys
sys.path.insert(0, sys.argv[1])
import tools.l4_mbf_oracle_v2 as m
cases = [
    ("1.5e-6", 6, " 1.5E-06 "),
    ("1.23e-6", 6, " 1.23E-06 "),
    ("1.2e-6", 6, " 1.2E-06 "),
    ("1/300000", 6, " 3.33333E-06 "),
    ("1d-16", 16, " 1D-16 "),
    ("1.5d-16", 16, " 1.5D-16 "),
]
ok = True
for expr, ndig, want in cases:
    _, pred, _ = m.predict(expr, ndig, "sym-def")
    if pred != want:
        print(f"MISMATCH {expr}: got {pred!r} want {want!r}")
        ok = False
print("PASS" if ok else "FAIL")
EOF
)"
if [ "$SYMDEF_CHECK" = "PASS" ]; then
  pass "sym-def が事前登録の定義(E>-Nで固定)どおり(K3/K5/K9/K13/L2/L4相当の6例)"
else
  fail "sym-defの定義一致: $SYMDEF_CHECK"
fi

# --- 13. l4-s4c v2: 旧sym(既定)はv1のS0列と完全一致(挙動を変えていない) ---
SYM_UNCHANGED_CHECK="$(PY - "$REPO_ROOT" <<'EOF'
import sys
sys.path.insert(0, sys.argv[1])
import tools.l4_mbf_oracle_v2 as m
# l4-s4c v1(0936808)のS0列を再現できるか(旧"sym"のまま)
cases = [
    ("1.5e-6", 6, " .0000015 "),
    ("1d-16", 16, " .0000000000000001 "),
]
ok = True
for expr, ndig, want in cases:
    _, pred, _ = m.predict(expr, ndig, "sym")
    if pred != want:
        print(f"MISMATCH {expr}: got {pred!r} want {want!r}")
        ok = False
print("PASS" if ok else "FAIL")
EOF
)"
if [ "$SYM_UNCHANGED_CHECK" = "PASS" ]; then
  pass "旧sym(既定)はl4-s4c v1のS0列と一致(挙動未変更)"
else
  fail "旧symの後方互換: $SYM_UNCHANGED_CHECK"
fi

# --- 14. l4-s4c v2予測表: LEN列がv1と同一・S0列だけ変わること ------------
S4C_V1="$REPO_ROOT/docs/notes/l4-s4c-candidate-predictions.tsv"
S4C_V2="$REPO_ROOT/docs/notes/l4-s4c-candidate-predictions-v2.tsv"
if [ -f "$S4C_V1" ] && [ -f "$S4C_V2" ]; then
  # LEN7/LEN8/LEN9/LEN16列(5,6,7,8列目)はv1・v2で同一のはず
  V1_LEN="$(grep -v '^#' "$S4C_V1" | cut -f1,2,3,5,6,7,8)"
  V2_LEN="$(grep -v '^#' "$S4C_V2" | cut -f1,2,3,5,6,7,8)"
  if [ "$V1_LEN" = "$V2_LEN" ]; then
    pass "l4-s4c v2のLEN列(id/typed/type込み)はv1と完全一致"
  else
    fail "l4-s4c v2のLEN列がv1と食い違っている"
  fi
  # S0列(4列目)はK3/K5/K9/K13/L2/L4の6腕だけ違うはず
  DIFF_IDS="$(paste <(grep -v '^#' "$S4C_V1" | cut -f1,4) <(grep -v '^#' "$S4C_V2" | cut -f1,4) | awk -F'\t' '$2!=$4{print $1}' | tr '\n' ',' )"
  if [ "$DIFF_IDS" = "K3,K5,K9,K13,L2,L4," ]; then
    pass "l4-s4c v2のS0列がv1と違う腕はK3/K5/K9/K13/L2/L4の6件だけ"
  else
    fail "S0列の差分腕が想定外: [$DIFF_IDS]"
  fi
else
  echo "SKIP - l4-s4c v1/v2予測表のどちらかがまだ無い"
fi

# --- 15. l4-s4c v2予測表の再生成がデータ行一致すること --------------------
if [ -f "$S4C_V2" ]; then
  TMP="$(mktemp)"
  (cd "$REPO_ROOT" && PY tools/gen_l4_s4c_candidate_predictions_v2.py) > "$TMP" 2>/tmp/l4_oracle_s4c_v2_gen.err
  if diff -q <(grep -v '^#' "$TMP") <(grep -v '^#' "$S4C_V2") >/dev/null 2>&1; then
    pass "docs/notes/l4-s4c-candidate-predictions-v2.tsv の再生成がデータ行一致"
  else
    fail "l4-s4c v2予測表の再生成が既存ファイルとデータ行不一致(diff未一致)"
  fi
  rm -f "$TMP"
else
  echo "SKIP - l4-s4c v2予測表がまだ無い(1本目のコミット時点では正常)"
fi

# --- 16. l4-s4d: lene(len上限+E下限)が既定を変えないこと --------------
LENE_DEFAULT_CHECK="$(PY - "$REPO_ROOT" <<'EOF'
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
    b = m.predict(expr, m.MBF_SINGLE_DIGITS, "sym", 0, 0)
    if a != b:
        print(f"MISMATCH {expr}: default={a} explicit={b}")
        ok = False
print("PASS" if ok else "FAIL")
EOF
)"
if [ "$LENE_DEFAULT_CHECK" = "PASS" ]; then
  pass "--small-rule lene 追加後も既定(sym/0/0)は32腕全件で変わらない"
else
  fail "lene追加後の既定値一致: $LENE_DEFAULT_CHECK"
fi

# --- 17. l4-s4d: LE17/LE18が定義どおり(len<=T かつ E>=-15)であること ------
# M1(.001234567890123456#, E=-3, nsig=16, len=18)はLE17=指数・LE18=固定。
# M4(1.234d-15, E=-15, nsig=4, len=18)も同型でLE17=指数・LE18=固定。
LENE_DEF_CHECK="$(PY - "$REPO_ROOT" <<'EOF'
import sys
sys.path.insert(0, sys.argv[1])
import tools.l4_mbf_oracle_v2 as m
cases = [
    (".001234567890123456#", 17, " 1.234567890123456D-03 "),
    (".001234567890123456#", 18, " .001234567890123456 "),
    ("1.234d-15", 17, " 1.234D-15 "),
    ("1.234d-15", 18, " .000000000000001234 "),
]
ok = True
for expr, t, want in cases:
    _, pred, _ = m.predict(expr, 16, "lene", t, -15)
    if pred != want:
        print(f"MISMATCH {expr} T={t}: got {pred!r} want {want!r}")
        ok = False
print("PASS" if ok else "FAIL")
EOF
)"
if [ "$LENE_DEF_CHECK" = "PASS" ]; then
  pass "lene(LE17/LE18)がM1/M4相当の4例で定義どおり"
else
  fail "lene定義一致: $LENE_DEF_CHECK"
fi

# --- 18. 故障注入: Eの下限を1ずらすと判定が変わること(検出力の確認) -------
# "1d-15"はE=-15のちょうど境界例。Emin=-15ならE>=-15を満たし固定、
# Eminを1つ厳しい-14へずらすと-15>=-14が偽になり指数表記へ変わる。
LENE_EMIN_FAULT_CHECK="$(PY - "$REPO_ROOT" <<'EOF'
import sys
sys.path.insert(0, sys.argv[1])
import tools.l4_mbf_oracle_v2 as m
expr = "1d-15"
_, p_ok, _ = m.predict(expr, 16, "lene", 18, -15)
_, p_shift, _ = m.predict(expr, 16, "lene", 18, -14)
ok = p_ok != p_shift and p_ok == " .000000000000001 " and p_shift == " 1D-15 "
print("PASS" if ok else f"FAIL p_ok={p_ok!r} p_shift={p_shift!r}")
EOF
)"
if [ "$LENE_EMIN_FAULT_CHECK" = "PASS" ]; then
  pass "Eの下限を-15から-14へ1つずらすと1d-15の判定が固定→指数に変わる(検出力の確認)"
else
  fail "lene Eの下限の故障注入検出力: $LENE_EMIN_FAULT_CHECK"
fi

# --- 19. l4-s4d予測表の再生成がデータ行一致すること ------------------------
S4D="$REPO_ROOT/docs/notes/l4-s4d-double-candidate-predictions.tsv"
if [ -f "$S4D" ]; then
  TMP="$(mktemp)"
  (cd "$REPO_ROOT" && PY tools/gen_l4_s4d_double_candidate_predictions.py) > "$TMP" 2>/tmp/l4_oracle_s4d_gen.err
  if diff -q <(grep -v '^#' "$TMP") <(grep -v '^#' "$S4D") >/dev/null 2>&1; then
    pass "docs/notes/l4-s4d-double-candidate-predictions.tsv の再生成がデータ行一致"
  else
    fail "l4-s4d予測表の再生成が既存ファイルとデータ行不一致(diff未一致)"
  fi
  rm -f "$TMP"
else
  echo "SKIP - l4-s4d予測表がまだ無い(1本目のコミット時点では正常)"
fi

# --- 20. l4-s4e: --small-rule gw 追加後も既定は変わらない -----------------
GW_DEFAULT_CHECK="$(PY - "$REPO_ROOT" <<'EOF'
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
    b = m.predict(expr, m.MBF_SINGLE_DIGITS, "sym", 0, 0)
    if a != b:
        print(f"MISMATCH {expr}: default={a} explicit={b}")
        ok = False
print("PASS" if ok else "FAIL")
EOF
)"
if [ "$GW_DEFAULT_CHECK" = "PASS" ]; then
  pass "gw/rstar/rstar_b追加後も既定(sym/0/0)は32腕全件で変わらない"
else
  fail "gw追加後の既定値一致: $GW_DEFAULT_CHECK"
fi

# --- 21. l4-s4e: gwがdocs/notes/l4-gwbasic-fofmt-analysis.mdの49件と一致 ---
GW_ANALYSIS_CHECK="$(PY - "$REPO_ROOT" <<'EOF'
import sys
sys.path.insert(0, sys.argv[1])
import tools.l4_mbf_oracle_v2 as m

double_cases = [
    ("1#/3", " .3333333333333333 "), ("1#/7", " .1428571428571429 "),
    (".0001#", " .0001 "), ("1d-17", " 1D-17 "),
    ("1d-15", " .000000000000001 "), ("1d-16", " .0000000000000001 "),
    ("1.5d-15", " .0000000000000015 "), ("1.5d-16", " 1.5D-16 "),
    (".1234567890123456#", " .1234567890123456 "),
    ("1.234567890123456d-2", " 1.234567890123456D-02 "),
    ("1#/3000", " 3.333333333333333D-04 "),
    (".001234567890123456#", " 1.234567890123456D-03 "),
    ("1.23456789012345d-3", " 1.23456789012345D-03 "),
    ("1.23d-15", " 1.23D-15 "), ("1.234d-15", " 1.234D-15 "),
    ("1.2345d-15", " 1.2345D-15 "), ("1#/300", " 3.333333333333333D-03 "),
    ("1#/30", " 3.333333333333333D-02 "), ("1.5d-14", " .000000000000015 "),
    ("1d16", " 1D+16 "), ("12345678901234567#", " 1.234567890123457D+16 "),
]
single7_cases = [
    ("1e-7", " .0000001 "), ("1e-8", " 1E-08 "), ("1.5e-6", " .0000015 "),
    ("1.5e-7", " 1.5E-07 "), ("1.23e-6", " 1.23E-06 "),
    ("1.23456e-2", " .0123456 "), ("1.23456e-3", " 1.23456E-03 "),
    ("1/3000", " 3.333333E-04 "), ("1.23456e-5", " 1.23456E-05 "),
    (".0001", " .0001 "), ("9999999", " 9999999 "),
    ("999999.5", " 999999.5 "), ("1234567", " 1234567 "), ("1/3", " .3333333 "),
]
single6_cases = [
    ("1e-7", " 1E-07 "), ("1e-8", " 1E-08 "), ("1.5e-6", " 1.5E-06 "),
    ("1.5e-7", " 1.5E-07 "), ("1.23e-6", " 1.23E-06 "),
    ("1.23456e-2", " 1.23456E-02 "), ("1.23456e-3", " 1.23456E-03 "),
    ("1/3000", " 3.33333E-04 "), ("1.23456e-5", " 1.23456E-05 "),
    (".0001", " .0001 "), ("9999999", " 1E+07 "),
    ("999999.5", " 1E+06 "), ("1234567", " 1.23457E+06 "), ("1/3", " .333333 "),
]
ok = True
n = 0
for expr, want in double_cases:
    n += 1
    _, pred, _ = m.predict(expr, 16, "gw")
    if pred != want:
        print(f"MISMATCH(double) {expr}: got {pred!r} want {want!r}")
        ok = False
for expr, want in single7_cases:
    n += 1
    _, pred, _ = m.predict(expr, 7, "gw")
    if pred != want:
        print(f"MISMATCH(single7) {expr}: got {pred!r} want {want!r}")
        ok = False
for expr, want in single6_cases:
    n += 1
    _, pred, _ = m.predict(expr, 6, "gw")
    if pred != want:
        print(f"MISMATCH(single6) {expr}: got {pred!r} want {want!r}")
        ok = False
print(f"PASS n={n}" if ok else "FAIL")
EOF
)"
if [ "${GW_ANALYSIS_CHECK%% *}" = "PASS" ]; then
  pass "gwがl4-gwbasic-fofmt-analysis.mdの49件(倍精度21+単精度(a)(b)各14)全て一致"
else
  fail "gwとanalysisの不一致: $GW_ANALYSIS_CHECK"
fi

# --- 22. l4-s4e: rstar/rstar_bがgwと食い違う代表例(k<=14の壁) ------------
RSTAR_CHECK="$(PY - "$REPO_ROOT" <<'EOF'
import sys
sys.path.insert(0, sys.argv[1])
import tools.l4_mbf_oracle_v2 as m
# 2d-16はk=15,s=1,k+s=16<=16なのでgw/rstar_bは固定、rstarはk<=14の壁で指数。
_, gw, _ = m.predict("2d-16", 16, "gw")
_, rstar, _ = m.predict("2d-16", 16, "rstar")
_, rstar_b, _ = m.predict("2d-16", 16, "rstar_b")
ok = gw == " .0000000000000002 " and rstar == " 2D-16 " and rstar_b == " .0000000000000002 "
print("PASS" if ok else f"FAIL gw={gw!r} rstar={rstar!r} rstar_b={rstar_b!r}")
EOF
)"
if [ "$RSTAR_CHECK" = "PASS" ]; then
  pass "2d-16でrstarだけgw/rstar_bと食い違う(k=15>14の壁)ことを確認"
else
  fail "rstarの食い違い確認: $RSTAR_CHECK"
fi

# --- 23. 故障注入: rstarのk上限を1ずらすと2d-16の判定が変わること ---------
RSTAR_FAULT_CHECK="$(PY - "$REPO_ROOT" <<'EOF'
import sys
sys.path.insert(0, sys.argv[1])
import tools.l4_mbf_oracle_v2 as m

def broken_small_side_fixed(e, nsig, ndig, small_rule, small_len, small_emin=0, raw_e=None):
    if small_rule == "rstar":
        k = -e
        # 故障注入: k<=14をk<=15に緩める(1ずらす)
        return (k <= 1) or ((k + nsig <= ndig) and (k <= 15))
    return orig(e, nsig, ndig, small_rule, small_len, small_emin, raw_e)

orig = m._small_side_fixed
m._small_side_fixed = broken_small_side_fixed
kind, pred, approx = m.predict("2d-16", 16, "rstar")
m._small_side_fixed = orig
print("FAULT_DETECTED" if pred != " 2D-16 " else "FAULT_NOT_DETECTED")
EOF
)"
if [ "$RSTAR_FAULT_CHECK" = "FAULT_DETECTED" ]; then
  pass "故障注入(rstarのk上限を14→15に緩める)で2d-16の判定が変わることを確認"
else
  fail "rstar故障注入が検出されなかった: $RSTAR_FAULT_CHECK"
fi

# --- 24. l4-s4e予測表の再生成がデータ行一致すること ------------------------
for pair in \
  "docs/notes/l4-s4e-double-candidate-predictions.tsv:tools/gen_l4_s4e_double_candidate_predictions.py" \
  "docs/notes/l4-s4e-posthoc-inputs.tsv:tools/gen_l4_s4e_posthoc_inputs.py"
do
  OUT="${pair%%:*}"
  GEN="${pair##*:}"
  TARGET="$REPO_ROOT/$OUT"
  if [ -f "$TARGET" ]; then
    TMP="$(mktemp)"
    (cd "$REPO_ROOT" && PY "$GEN") > "$TMP" 2>/tmp/l4_oracle_s4e_gen.err
    if diff -q <(grep -v '^#' "$TMP") <(grep -v '^#' "$TARGET") >/dev/null 2>&1; then
      pass "$OUT の再生成がデータ行一致"
    else
      fail "$OUT の再生成が既存ファイルとデータ行不一致(diff未一致)"
    fi
    rm -f "$TMP"
  else
    echo "SKIP - $OUT がまだ無い(1本目のコミット時点では正常)"
  fi
done

echo
if [ "$FAIL" = "0" ]; then
  echo "l4_mbf_oracle_v2_selftest: 全項目OK"
else
  echo "l4_mbf_oracle_v2_selftest: NGあり"
fi
exit "$FAIL"
