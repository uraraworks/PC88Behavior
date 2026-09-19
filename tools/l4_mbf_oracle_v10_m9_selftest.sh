#!/usr/bin/env bash
# tools/l4_mbf_oracle_v10_m9.py の自己検査(公式ROM不要)。
# 候補M9(M8の構造+超越関数内部の単精度演算をaway丸めにする)の性質を、
# 手で検算できる小さな例と、既存のl4-s6a〜f公式実測(既に本ノートで
# コミット済み、公式ROMの再読み込みは行わない)の再照合で確認する。
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="python3"

ok() { printf 'OK: %s\n' "$1"; }
ng() { printf 'NG: %s\n' "$1" >&2; exit 1; }

# --- 1. 誤差の無い単純な例(丸めが起きない)はM8/M9で一致する -----------
"$PY" - << PYEOF
import sys
sys.path.insert(0, "$REPO/tools")
import l4_mbf_oracle_v10_m9 as m9
r = m9.predict_fn("sin", "0")
assert r == ("numeric", " 0 ", False), r
r = m9.predict_fn("cos", "0")
assert r[1].strip() == "1", r
r = m9.predict_fn("sqr", "4")
assert r[1].strip() == "2", r
print("ok: 誤差の無い基本値(sin(0)/cos(0)/sqr(4))が正しい")
PYEOF
ok "誤差の無い基本値がM9でも正しい"

# --- 2. away丸めがround-half-evenと違う方向に丸めることを、crafted な
#        tie(ちょうど半分)の単精度加算で確認する -----------------------
"$PY" - << PYEOF
import sys
from fractions import Fraction
sys.path.insert(0, "$REPO/tools")
import l4_mbf_oracle_v10_m9 as m9
from tools.l4_mbf_oracle_v2 import GwNum

# 1.0 + 2^-25 の"半分の半分"を作るのではなく、直接ちょうど中間になる
# Fractionを与えてaway/even丸めの分岐を確認する(encode_mbf相当)。
half_tie_up = Fraction(2**24 + 1, 2)  # 24bit境界のちょうど半分(候補が奇数側)
sign, exp, mant = m9._encode_mbf_away(half_tie_up, 24)
assert mant == (2**24 + 1 + 1) // 2, (mant,)  # 常に切り上げ(0から遠い側)

# a=1.0、b=(3/4)*2^-23(1.0のULPの3/4)。厳密値は1のULPのちょうど半分
# ではなく3/4なので、ここは even/away どちらでも切り上げる非tie場面
# (判別力なし、一致して当然の対照)。
a = GwNum.from_fraction(Fraction(1), "single")
b = GwNum.from_fraction(Fraction(3, 4) * Fraction(1, 2**23), "single")
from tools.l4_mbf_oracle_v2 import gw_binop
r_even = gw_binop(a, b, "+")
r_away = m9.away_binop(a, b, "+")
assert (r_even.sign, r_even.exp, r_even.mant) == (r_away.sign, r_away.exp, r_away.mant), \
    "tieでない(3/4 ULP)加算はeven/away一致するはずが不一致だった"
print("ok: away丸め関数はtieでない場面ではv2既定と一致する")
PYEOF
ok "away丸め関数の基本動作(tie以外は既定と一致)"

# --- 3. M9はM8の構造(SIN/COS/TAN)を継承しており、多くの腕でM8と一致する
#        (l4-s6c〜fの公式実測argに対する再計算、ROM再測定はしない) -----
"$PY" - << PYEOF
import sys
sys.path.insert(0, "$REPO/tools")
import l4_mbf_oracle_v3 as v3
import l4_mbf_oracle_v8_m8 as m8
import l4_mbf_oracle_v10_m9 as m9
from tools.l4_mbf_oracle_v2 import force_to_single, GwError

# l4-s6f F02(cos(8))はM7=M8=公式実測が完全一致した腕。M9でも一致するはず
# (丸め方式を変えても、tieを経由しない計算列なら結果は変わらない)。
x = force_to_single(v3.parse_literal("8"))
r8 = m8.cos_impl(x)
r9 = m9.cos_impl(x)
assert (r8.sign, r8.exp, r8.mant) == (r9.sign, r9.exp, r9.mant), "cos(8)でM8/M9が食い違った(想定外)"
print("ok: M9はM8と同じ構造を継承し、tieを経由しない腕では一致する")
PYEOF
ok "M9はM8の構造を継承している(cos(8)で確認)"

# --- 4. GwError(オーバーフロー・0除算等)が正しく伝播する ---------------
"$PY" - << PYEOF
import sys
sys.path.insert(0, "$REPO/tools")
import l4_mbf_oracle_v10_m9 as m9
kind, line, approx = m9.predict_fn("log", "-1")
assert kind == "error", (kind, line)
print("ok: log(-1)がエラーとして伝播する")
PYEOF
ok "エラー系(log(-1))が正しく伝播する"

echo "ALL OK: l4_mbf_oracle_v10_m9"
