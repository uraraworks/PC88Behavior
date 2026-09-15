#!/usr/bin/env bash
# tools/l4_rep10_selftest.sh — tools/l4_rep10.py(REP10候補、l4-s4iの実測に
# 事後で当てた3つ目の候補)自体を検査する。公式ROM不要。
#
# 使い方: tools/l4_rep10_selftest.sh
# 全項目 OK なら終了コード 0、1つでも落ちたら 1。

set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

FAIL=0
pass() { echo "OK  - $1"; }
fail() { echo "NG  - $1"; FAIL=1; }

PY() { python3 "$@"; }

# --- 1. 親の指示どおりの単体の検算: 5.1e+10 -----------------------------
CHECK1="$(PY - "$REPO_ROOT" <<'EOF'
import sys
sys.path.insert(0, sys.argv[1])
from tools import l4_rep10 as rep10
from tools import l4_mbf_oracle_v2 as oracle

sign, exp_byte, mant = rep10.rep10_single_value("5.1e+10")
num = oracle.GwNum("single", sign=sign, exp=exp_byte, mant=mant)
rep10_val = num.exact()

ex = oracle.parse_literal("5.1e+10", "exact")
gx = oracle.parse_literal("5.1e+10", "gw")

ok = (rep10_val == 51000004608) and (ex.exact() == 51000000512) and (gx.exact() == 51000000512)
print("OK" if ok else f"NG rep10={rep10_val} exact={ex.exact()} gw={gx.exact()}")
EOF
)"
if [ "$CHECK1" = "OK" ]; then pass "5.1e+10: REP10=51000004608, EXACT/GW=51000000512"; else fail "5.1e+10 checksum: $CHECK1"; fi

# --- 2. 食い違わない既知の定数でEXACT/GW/REP10が一致する ------------------
CHECK2="$(PY - "$REPO_ROOT" <<'EOF'
import sys
sys.path.insert(0, sys.argv[1])
from tools import l4_rep10 as rep10
from tools import l4_mbf_oracle_v2 as oracle

lits = ["1.5", ".5", "-.5", "123.456", "1/3", "200*200", "1e10", "-1.5e+20", "1e-10"]
ok = True
for t in lits:
    ke, pe = rep10.predict_any(t, "exact")
    kg, pg = rep10.predict_any(t, "gw")
    kr, pr = rep10.predict_rep10(t)
    if not (pe == pg == pr):
        print(f"MISMATCH {t}: exact={pe!r} gw={pg!r} rep10={pr!r}")
        ok = False
print("OK" if ok else "NG")
EOF
)"
if [ "$CHECK2" = "OK" ]; then pass "既知の非分岐リテラルでEXACT/GW/REP10が一致"; else fail "非分岐リテラル一致: $CHECK2"; fi

# --- 3. 故障注入: 丸め方を偶数丸めに変えると1.のチェックが壊れて検出できる -
CHECK3="$(PY - "$REPO_ROOT" <<'EOF'
import sys
sys.path.insert(0, sys.argv[1])
from tools import l4_rep10 as rep10
from fractions import Fraction

# _round_half_up_mag を偶数丸めに差し替えて壊す(検査器の自己検査)
def broken_round_half_even(x: Fraction) -> int:
    n, d = x.numerator, x.denominator
    q, r = divmod(n, d)
    twice = 2 * r
    if twice < d:
        return q
    if twice > d:
        return q + 1
    return q if (q % 2 == 0) else q + 1

orig = rep10._round_half_up_mag
rep10._round_half_up_mag = broken_round_half_even
try:
    sign, exp_byte, mant = rep10.rep10_single_value("5.1e+10")
finally:
    rep10._round_half_up_mag = orig

import tools.l4_mbf_oracle_v2 as oracle
val = oracle.GwNum("single", sign=sign, exp=exp_byte, mant=mant).exact()
# 偶数丸めに壊すと51000004608と一致しなくなる(はず)ことを確認
print("OK" if val != 51000004608 else "NG (fault injection did not change result)")
EOF
)"
if [ "$CHECK3" = "OK" ]; then pass "故障注入(偶数丸めに壊す)で5.1e+10のチェックが崩れることを確認"; else fail "故障注入: $CHECK3"; fi

# --- 4. 決定性: gen_l4_rep10_vs_committed.py / gen_l4_s4j_candidates.py --
if [ -f "$REPO_ROOT/tools/gen_l4_s4j_candidates.py" ]; then
    OUT1="$(PY "$REPO_ROOT/tools/gen_l4_s4j_candidates.py" 2>/dev/null | sha256sum | awk '{print $1}')"
    OUT2="$(PY "$REPO_ROOT/tools/gen_l4_s4j_candidates.py" 2>/dev/null | sha256sum | awk '{print $1}')"
    if [ "$OUT1" = "$OUT2" ] && [ -n "$OUT1" ]; then
        pass "gen_l4_s4j_candidates.py の再生成がバイト一致(決定的)"
    else
        fail "gen_l4_s4j_candidates.py の再生成が決定的でない"
    fi
else
    echo "SKIP - gen_l4_s4j_candidates.py が無い(先にtask3/4のスクリプトを追加すること)"
fi

echo
if [ "$FAIL" -eq 0 ]; then
    echo "全項目 OK"
else
    echo "失敗あり"
fi
exit "$FAIL"
