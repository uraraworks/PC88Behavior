#!/usr/bin/env bash
# tools/l4_mbf_z80_selftest.sh — M7段階4a-1。src/l4_basic/mbf_single.asm
# （単精度MBF四則演算・符号反転・比較・整数変換）を実際にZ80として実行し、
# tools/l4_mbf_oracle_v2.py（GW-BASIC由来の予測器）とバイト単位で突き合わせる
# tools/l4_mbf_conform.py のラッパ。詳細・実行手段の説明は
# tools/l4_mbf_conform.py のモジュールdocstring参照。
#
# run_all_selftests.sh から毎回回す想定のため、件数は数千件規模の探索的な
# 照合（開発時にターミナルで直接 l4_mbf_conform.py を叩いて行った）より
# 少なめに抑えている（境界値・機械構成した丸め境界は件数によらず常に
# 含まれるので、検出力そのものは大きく落ちない）。
#
# 公式ROM・私物は一切不要（自作の空ROMをq88measureで走らせるだけ）。
# tools/harness/frontend/q88measure と vendor/quasi88-libretro のコアが
# 要る（tools/setup_harness.sh 済みであること。無ければ即NGで知らせる）。

set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONFORM="$REPO/tools/l4_mbf_conform.py"
VENDOR="$(cd "$REPO/.." && pwd)/vendor/quasi88-libretro"
FRONTEND="$REPO/tools/harness/frontend/q88measure"

ok() { printf '  \033[32mOK\033[0m   %s\n' "$1"; }
ng() { printf '  \033[31mNG\033[0m   %s\n' "$1" >&2; }

CORE="$(ls "$VENDOR"/quasi88_libretro.* 2>/dev/null | head -1 || true)"
if [ -z "$CORE" ]; then
  echo "NG: コア成果物が無い。先に tools/setup_harness.sh を実行すること" >&2
  exit 1
fi

make -s -C "$REPO/tools/harness/frontend" || { echo "NG: q88measureのビルドに失敗" >&2; exit 1; }
[ -x "$FRONTEND" ] || { echo "NG: $FRONTEND が無い" >&2; exit 1; }

overall=0

run_case() {
  local desc="$1"; shift
  if python3 "$CONFORM" "$@" >/tmp/l4mbf_z80_selftest.$$ 2>&1; then
    ok "$desc"
  else
    ng "$desc"
    cat /tmp/l4mbf_z80_selftest.$$ >&2
    overall=1
  fi
  rm -f /tmp/l4mbf_z80_selftest.$$
}

echo "==> 正常系（境界値＋乱数、演算ごと）"
run_case "add  N=400"  add  -n 400 --frames 90
run_case "sub  N=400"  sub  -n 400 --frames 90
run_case "neg  N=300"  neg  -n 300 --frames 60
run_case "cmp  N=300"  cmp  -n 300 --frames 60
run_case "itos N=400"  itos -n 400 --frames 60
run_case "mul  N=400"  mul  -n 400 --frames 200
run_case "div  N=400"  div  -n 400 --frames 900
# fin: docs/spec/l4-basic.md 第3.6版5.1.1節の推定REP01(1手ごとに
# 単精度へ丸め直す、$FINE/MDPTENの倍精度56bit経由・$CSD1回丸めではない)
# に作り直し済み(2026-09-15、M7)。予測器もfin_algo="rep01"に合わせて
# あり(tools/l4_mbf_conform.py expected_fin)、乱数複数シード計5000件超・
# 境界値(指数上下限近く・7桁定数・`!`・e+/e-の大小・小数点以下の桁数・
# 先頭0の小数)の照合で不一致0件を確認済みなので--max-mismatchは0のまま
# 使う(REP01自体がl4-s4i・l4-s4j実測57件中55件しか再現しない推定である
# ことは仕様書5.1.1節に記録済みで、この0件はZ80実装と予測器の一致を
# 指すもの)。
run_case "fin  N=1300 seed1" fin -n 1300 --seed 1 --frames 3000 --max-mismatch 0
run_case "fin  N=1300 seed2" fin -n 1300 --seed 2 --frames 3000 --max-mismatch 0
run_case "fin  N=1300 seed3" fin -n 1300 --seed 3 --frames 3000 --max-mismatch 0
run_case "fin  N=1300 seed4" fin -n 1300 --seed 4 --frames 3000 --max-mismatch 0
# fout: 本件(M7段階4-2)でGW手順($FOTNV相当の倍精度DBL_TABLEスケール＋
# 「0.5を足して切り捨て」)へ作り直した。乱数照合は複数シード合計
# 5000件超・境界値(MAX_POS/MAX_NEG/MIN_POS/MIN_NEG含む)・仕様書第5節の
# 観測例つきで不一致0件を確認済みなので--max-mismatchは0にする
# (frames=20000: 倍精度演算が単精度より1ステップあたり重く、旧来の
# frames=2000では大きいバッチの途中でフレーム予算が尽き出力が書かれない
# 〔missing〕まま不一致扱いになったため引き上げた)。
run_case "fout N=1700 seed1" fout -n 1700 --seed 1 --frames 20000 --max-mismatch 0
run_case "fout N=1700 seed2" fout -n 1700 --seed 2 --frames 20000 --max-mismatch 0
run_case "fout N=1700 seed3" fout -n 1700 --seed 3 --frames 20000 --max-mismatch 0

echo "==> 故障注入（陰性対照。不一致が出ることを正常系として扱う）"
run_case "add  --fault sticky"         add -n 800 --frames 90  --fault sticky         --expect-ng
run_case "sub  --fault sticky"         sub -n 800 --frames 90  --fault sticky         --expect-ng
run_case "add  --fault round_truncate" add -n 400 --frames 90  --fault round_truncate --expect-ng
run_case "sub  --fault round_truncate" sub -n 400 --frames 90  --fault round_truncate --expect-ng
run_case "mul  --fault mul_coarse"     mul -n 400 --frames 200 --fault mul_coarse     --expect-ng
run_case "div  --fault div_sticky"     div -n 400 --frames 900 --fault div_sticky     --expect-ng
run_case "fin  --fault fin_bang"       fin -n 30  --frames 400 --fault fin_bang       --expect-ng
run_case "fin  --fault fin_exact"      fin -n 100 --frames 1500 --fault fin_exact      --expect-ng
run_case "fin  --fault fin_rep10"      fin -n 100 --frames 1500 --fault fin_rep10      --expect-ng
run_case "fout --fault fout_trunc"       fout -n 200 --frames 20000 --fault fout_trunc       --expect-ng
run_case "fout --fault fout_round_even"  fout -n 200 --frames 20000 --fault fout_round_even  --expect-ng
run_case "fout --fault fout_len7"        fout -n 200 --frames 20000 --fault fout_len7        --expect-ng
run_case "fout --fault fout_6dig"        fout -n 200 --frames 20000 --fault fout_6dig        --expect-ng

if [ "$overall" -eq 0 ]; then
  echo "l4_mbf_z80_selftest: OK"
else
  echo "l4_mbf_z80_selftest: NG" >&2
fi
exit "$overall"
