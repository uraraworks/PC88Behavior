#!/usr/bin/env bash
# tools/l4_mbf_oracle_v9_s7a.py の自己検査(公式ROM不要)。
# 候補規則自体の性質(even/away/trunc/coarse8/fmulsの相互関係)を、
# 手で検算できる小さな例で確認する。
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="python3"

ok() { printf 'OK: %s\n' "$1"; }
ng() { printf 'NG: %s\n' "$1" >&2; exit 1; }

run() {
  "$PY" "$REPO/tools/l4_mbf_oracle_v9_s7a.py" "$1" "$2" "$3"
}

# --- 1. 誤差ゼロの単純な例は全候補が一致する ---------------------------
out="$(run '1.5!' '2!' '*')"
n_lines="$(printf '%s\n' "$out" | grep -c '0:82:c00000')"
[ "$n_lines" -ge 4 ] || ng "1.5*2=3.0は候補間で一致するはずが一致しなかった"
ok "誤差の無い乗算は候補間で一致する"

# --- 2. tie(even/awayが割れる)の既知例: 1.25!*0.3!=0.375+ε/2 --------
out="$(run '1.25!' '0.3!' '*')"
printf '%s\n' "$out" | grep -q 'even *0:7f:c00000' || ng "even候補のビットが想定と違う"
printf '%s\n' "$out" | grep -q 'away *0:7f:c00001' || ng "away候補のビットが想定と違う(tieでevenと割れるはず)"
printf '%s\n' "$out" | grep -q 'trunc *0:7f:c00000' || ng "trunc候補のビットが想定と違う"
ok "tie腕(1.25!*0.3!)でeven/awayが想定どおり割れる"

# --- 3. false_tie(coarse8がeven/awayと割れる)既知例: 78.9!+3.3! -------
out="$(run '78.9!' '3.3!' '+')"
even_bits="$(printf '%s\n' "$out" | awk '/^  even/{print $2}')"
away_bits="$(printf '%s\n' "$out" | awk '/^  away/{print $2}')"
coarse_bits="$(printf '%s\n' "$out" | awk '/^  coarse8/{print $2}')"
[ "$even_bits" = "$away_bits" ] || ng "78.9!+3.3! はtieでないはずなのにeven!=away"
[ "$even_bits" != "$coarse_bits" ] || ng "78.9!+3.3! はfalse_tie腕のはずなのにcoarse8==even"
ok "false_tie腕(78.9!+3.3!)でcoarse8だけevenと割れる"

# --- 4. 加減乗除の全4演算子が例外無く動く ------------------------------
for op in '+' '-' '*' '/'; do
  run '7!' '3!' "$op" >/dev/null || ng "演算子 $op が失敗した"
done
ok "四則演算すべてが例外無く動く"

# --- 5. 乗算のfmuls候補が既存v2のgw_mul_singleと一致する(二重実装でない確認) --
"$PY" - "$REPO/tools" << 'PYEOF'
import sys
sys.path.insert(0, sys.argv[1])
import l4_mbf_oracle_v9_s7a as v9
import l4_mbf_oracle_v2 as v2

exact, out = v9.predict_all('8191!', '12.3!', '*')
an = v2.parse_literal('8191!', fin_algo='rep01')
bn = v2.parse_literal('12.3!', fin_algo='rep01')
r0 = v2.gw_mul_single(an, bn)
expect = (r0.sign, r0.exp, r0.mant)
assert out['fmuls'] == expect, (out['fmuls'], expect)
print("ok: fmuls候補はv2.gw_mul_singleの直接呼び出しと一致")
PYEOF

echo "ALL OK: l4_mbf_oracle_v9_s7a"
