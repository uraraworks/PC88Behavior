#!/usr/bin/env bash
# tools/l4_sincos_bank_selftest.sh — src/ext_bank/bank0.asm
# EXT_BANK0_SIN_ENTRY/COS_ENTRY/TAN_ENTRY（単精度SIN/COS/TAN、
# docs/spec/l4-program.md 第4.16a節）を実際にZ80として実行し、
# tools/l4_mbf_oracle_v10_m9.py の sin_impl/cos_impl/tan_impl とバイト
# 単位で突き合わせる tools/l4_sincos_bank_conform.py のラッパ。
# tools/l4_sqr_bank_selftest.shと同じ流儀（run_all_selftests.shから
# 毎回回す想定なので件数は開発時の探索的な照合〔800件×3関数〕より
# 少なめに抑える）。
#
# 公式ROM・私物は一切不要。tools/harness/frontend/q88measure と
# vendor/quasi88-libretro のコアが要る（tools/setup_harness.sh 済みであること）。

set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONFORM="$REPO/tools/l4_sincos_bank_conform.py"
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
  if python3 "$CONFORM" "$@" >/tmp/l4sincos_bank_selftest.$$ 2>&1; then
    ok "$desc"
  else
    ng "$desc"
    cat /tmp/l4sincos_bank_selftest.$$ >&2
    overall=1
  fi
  rm -f /tmp/l4sincos_bank_selftest.$$
}

echo "==> 正常系（境界値＋乱数）"
run_case "sin N=150 seed1" --func sin -n 150 --seed 1
run_case "sin N=150 seed2" --func sin -n 150 --seed 2
run_case "cos N=150 seed1" --func cos -n 150 --seed 1
run_case "cos N=150 seed2" --func cos -n 150 --seed 2
run_case "tan N=150 seed1" --func tan -n 150 --seed 1
run_case "tan N=150 seed2" --func tan -n 150 --seed 2

echo "==> 故障注入（陰性対照。不一致が出ることを正常系として扱う）"
run_case "sin --fault wrong_reduce_op"       --func sin -n 100 --fault wrong_reduce_op
run_case "sin --fault bad_coeff"             --func sin -n 100 --fault bad_coeff
run_case "sin --fault wrong_sin10_threshold" --func sin -n 100 --fault wrong_sin10_threshold

if [ "$overall" -eq 0 ]; then
  echo "l4_sincos_bank_selftest: OK"
else
  echo "l4_sincos_bank_selftest: NG" >&2
fi
exit "$overall"
