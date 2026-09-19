#!/usr/bin/env bash
# tools/l4_sqr_bank_selftest.sh — src/ext_bank/bank0.asm EXT_BANK0_SQR_ENTRY
# （単精度SQR、docs/spec/l4-program.md 第4.16b節実装メモ）を実際にZ80として
# 実行し、tools/l4_mbf_oracle_v10_m9.py の sqr_impl とバイト単位で突き合わせる
# tools/l4_sqr_bank_conform.py のラッパ。tools/l4_mbf_z80_selftest.sh と同じ
# 流儀（run_all_selftests.sh から毎回回す想定なので件数は開発時の探索的な
# 照合〔1900件〕より少なめに抑える）。
#
# 公式ROM・私物は一切不要。tools/harness/frontend/q88measure と
# vendor/quasi88-libretro のコアが要る（tools/setup_harness.sh 済みであること）。

set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONFORM="$REPO/tools/l4_sqr_bank_conform.py"
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
  if python3 "$CONFORM" "$@" >/tmp/l4sqr_bank_selftest.$$ 2>&1; then
    ok "$desc"
  else
    ng "$desc"
    cat /tmp/l4sqr_bank_selftest.$$ >&2
    overall=1
  fi
  rm -f /tmp/l4sqr_bank_selftest.$$
}

echo "==> 正常系（境界値＋乱数）"
run_case "sqr N=250 seed1" -n 250 --seed 1
run_case "sqr N=250 seed2" -n 250 --seed 2

echo "==> 故障注入（陰性対照。不一致が出ることを正常系として扱う）"
run_case "sqr --fault iter1"    -n 150 --fault iter1
run_case "sqr --fault no_halve" -n 150 --fault no_halve

if [ "$overall" -eq 0 ]; then
  echo "l4_sqr_bank_selftest: OK"
else
  echo "l4_sqr_bank_selftest: NG" >&2
fi
exit "$overall"
