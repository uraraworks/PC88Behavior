#!/usr/bin/env bash
# tools/l4_mbf_oracle_selftest.sh — tools/l4_mbf_oracle.py 自体を検査する。
#
# CLAUDE.md / docs/notes の方針どおり、検査器を信用してよいのは
# わざと壊して検出できることを確かめた後だけ（tools/cmp_io_selftest.sh の
# 作法を踏襲）。公式ROM不要・GW-BASICソースへの参照も実行時には無い
# （予測器はビルド済みのPythonロジックだけで完結する）。
#
# 使い方: tools/l4_mbf_oracle_selftest.sh
# 全項目 OK なら終了コード 0、1つでも落ちたら 1。

set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

FAIL=0
pass() { echo "OK  - $1"; }
fail() { echo "NG  - $1"; FAIL=1; }

PY() { python3 "$@"; }

# --- 1. 既知のMBFバイト表現との一致 -----------------------------------
CHECK1="$(PY - "$REPO_ROOT" <<'EOF'
import sys
sys.path.insert(0, sys.argv[1])
import tools.l4_mbf_oracle as m
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
  pass "既知のMBF単精度バイト列4件（1.0/0.5/-1.0/10.0）と往復変換"
else
  fail "既知のMBF単精度バイト列: $CHECK1"
fi

# --- 2. 予測表の再生成がバイト一致すること -----------------------------
ARMS="$REPO_ROOT/docs/notes/l4-s4a-gwbasic-predictions.tsv"
if [ -f "$ARMS" ]; then
  TMP="$(mktemp)"
  (cd "$REPO_ROOT" && PY tools/gen_l4_s4a_predictions.py) > "$TMP" 2>/tmp/l4_oracle_gen.err
  if diff -q "$TMP" "$ARMS" >/dev/null 2>&1; then
    pass "docs/notes/l4-s4a-gwbasic-predictions.tsv の再生成がバイト一致"
  else
    fail "予測表の再生成が既存ファイルと不一致(diff未一致)"
  fi
  rm -f "$TMP"
else
  echo "SKIP - 予測表(l4-s4a-gwbasic-predictions.tsv)がまだ無い(1本目のコミット時点では正常)"
fi

# --- 3. 故障注入: 丸めを「常に切り上げ」に壊すと偶数丸め検査が落ちること --
# .5 を最も近い偶数へ丸める例(2.5->2, 3.5->4)で偶数丸めを確認し、
# L4_ORACLE_FAULT=round_up で意図的に壊すと不一致になることを確かめる。
ROUND_CHECK="$(PY - "$REPO_ROOT" <<'EOF'
import sys
sys.path.insert(0, sys.argv[1])
import tools.l4_mbf_oracle as m
from fractions import Fraction as F
# 2.5 -> 2 (偶数), 3.5 -> 4 (偶数)。ROUNS の TSTEVN 分岐と同じ規則。
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

FAULT_CHECK="$(L4_ORACLE_FAULT=round_up PY - "$REPO_ROOT" <<'EOF'
import sys
sys.path.insert(0, sys.argv[1])
import tools.l4_mbf_oracle as m
from fractions import Fraction as F
a = m._round_half_even(F(5, 2))
b = m._round_half_even(F(7, 2))
# 故障注入(常に切り上げ)なら 2.5->3 になり、a==2 は満たさなくなる
print("FAULT_DETECTED" if a != 2 else "FAULT_NOT_DETECTED")
EOF
)"
if [ "$FAULT_CHECK" = "FAULT_DETECTED" ]; then
  pass "故障注入(L4_ORACLE_FAULT=round_up)で偶数丸め検査が意図どおり不一致になる"
else
  fail "故障注入が検出されなかった(検査器が壊れを見逃している): $FAULT_CHECK"
fi

# --- 4. 故障注入: 整数溢れ時の単精度昇格を壊すと 30000+30000 が壊れること --
PROMO_CHECK="$(PY - "$REPO_ROOT" <<'EOF'
import sys
sys.path.insert(0, sys.argv[1])
import tools.l4_mbf_oracle as m
kind, pred = m.predict("30000+30000")
print("PASS" if (kind == "numeric" and pred.strip() == "60000") else f"FAIL {kind} {pred!r}")
EOF
)"
if [ "$PROMO_CHECK" = "PASS" ]; then
  pass "整数溢れ時の単精度昇格(30000+30000=60000)"
else
  fail "整数溢れ昇格: $PROMO_CHECK"
fi

# 上と同じ昇格ロジックを一時的に無効化(常にintのまま16bit折り返しで計算)して
# 壊れることを確認する。ソースは直接いじらず、読み込んだ関数をモンキー
# パッチして「わざと壊した版」を作る。
PROMO_FAULT_CHECK="$(PY - "$REPO_ROOT" <<'EOF'
import sys
sys.path.insert(0, sys.argv[1])
import tools.l4_mbf_oracle as m

def broken(a, b, op):
    if op in "+-*" and a.kind == "int" and b.kind == "int":
        if op == "+":
            r = a.ivalue + b.ivalue
        elif op == "-":
            r = a.ivalue - b.ivalue
        else:
            r = a.ivalue * b.ivalue
        r16 = ((r + 32768) % 65536) - 32768  # 昇格せず16bit折り返し(わざと壊す)
        return m.GwNum.from_int(r16)
    raise AssertionError("fault stub only covers the int/int path")

m.gw_binop = broken
val = m.eval_expr("30000+30000")
print("FAULT_DETECTED" if val.ivalue != 60000 else "FAULT_NOT_DETECTED")
EOF
)"
if [ "$PROMO_FAULT_CHECK" = "FAULT_DETECTED" ]; then
  pass "故障注入(昇格無効化)で 30000+30000 の検査が意図どおり不一致になる"
else
  fail "故障注入(昇格無効化)が検出されなかった: $PROMO_FAULT_CHECK"
fi

# --- 5. 型昇格・エラー系の代表値 ---------------------------------------
REP_CHECK="$(PY - "$REPO_ROOT" <<'EOF'
import sys
sys.path.insert(0, sys.argv[1])
import tools.l4_mbf_oracle as m

cases = [
    ("1e10", "numeric", " 1E+10 "),
    (".1", "numeric", " .1 "),
    ("1e-10", "numeric", " 1E-10 "),
    ("-32768-1", "numeric", "-32769 "),
    ("1/0", "error", None),   # 数値行はDIV0Sの丸め詳細に依存するので種別のみ確認
    ("1e38*10", "error", None),
]
ok = True
for expr, want_kind, want_pred in cases:
    kind, pred = m.predict(expr)
    if kind != want_kind:
        print(f"MISMATCH {expr}: kind={kind} want={want_kind}")
        ok = False
        continue
    if want_pred is not None and pred != want_pred:
        print(f"MISMATCH {expr}: pred={pred!r} want={want_pred!r}")
        ok = False
    if want_kind == "error" and ";" not in pred:
        print(f"MISMATCH {expr}: error predicted without ';' separator: {pred!r}")
        ok = False
print("PASS" if ok else "FAIL")
EOF
)"
if [ "$REP_CHECK" = "PASS" ]; then
  pass "代表値(指数表記/固定小数点/整数溢れ/エラー系)の形"
else
  fail "代表値: $REP_CHECK"
fi

echo
if [ "$FAIL" = "0" ]; then
  echo "l4_mbf_oracle_selftest: 全項目OK"
else
  echo "l4_mbf_oracle_selftest: NGあり"
fi
exit "$FAIL"
