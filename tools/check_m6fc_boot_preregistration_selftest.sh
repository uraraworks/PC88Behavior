#!/usr/bin/env bash
# tools/check_m6fc_boot_preregistration.py の自己検査。
#
# 検査項目:
#   1. 現行の tools/m6fc_boot_frozen.tsv でrc=0。
#   2. 陰性対照: 打鍵を書き換えるとrc!=0。
#   3. 陰性対照: framesを書き換えるとrc!=0。
#   4. 陰性対照: 判定名を1つ削るとrc!=0。
#   5. 陰性対照: 未登録キーを混ぜるとrc!=0。
#
# 使い方: tools/check_m6fc_boot_preregistration_selftest.sh
set -uo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CHECK="$REPO/tools/check_m6fc_boot_preregistration.py"
CONFIG="$REPO/tools/m6fc_boot_frozen.tsv"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
rc=0
ok() { printf 'OK: %s\n' "$1"; }
ng() { printf 'NG: %s\n' "$1"; rc=1; }

if python3 "$CHECK" --config "$CONFIG" >/dev/null 2>"$WORK/base.err"; then
  ok "現行の凍結表でrc=0"
else
  ng "現行の凍結表がrc=0でない: $(cat "$WORK/base.err")"
fi

# --- 打鍵の改ざん ------------------------------------------------------------
sed 's/"bt"/"BT"/' "$CONFIG" > "$WORK/mutant_key.tsv"
python3 "$CHECK" --config "$WORK/mutant_key.tsv" >/dev/null 2>"$WORK/mk.err"
if [ $? -ne 0 ]; then
  ok "陰性対照: 打鍵の改ざんを拒否した"
else
  ng "陰性対照: 打鍵の改ざんが素通りした"
fi

# --- framesの改ざん ---------------------------------------------------------
sed 's/^frames\t3000$/frames\t3001/' "$CONFIG" > "$WORK/mutant_frames.tsv"
python3 "$CHECK" --config "$WORK/mutant_frames.tsv" >/dev/null 2>"$WORK/mf.err"
if [ $? -ne 0 ]; then
  ok "陰性対照: framesの改ざんを拒否した"
else
  ng "陰性対照: framesの改ざんが素通りした"
fi

# --- 判定名の欠落 ------------------------------------------------------------
grep -v '^judgment\tnot_found$' "$CONFIG" > "$WORK/mutant_judgment.tsv"
python3 "$CHECK" --config "$WORK/mutant_judgment.tsv" >/dev/null 2>"$WORK/mj.err"
if [ $? -ne 0 ]; then
  ok "陰性対照: 判定名not_foundの欠落を拒否した"
else
  ng "陰性対照: 判定名の欠落が素通りした"
fi

# --- 未登録キーの混入 ---------------------------------------------------------
printf 'unknown_key\tsomething\n' > "$WORK/mutant_extra.tsv"
cat "$CONFIG" >> "$WORK/mutant_extra.tsv"
python3 "$CHECK" --config "$WORK/mutant_extra.tsv" >/dev/null 2>"$WORK/me.err"
if [ $? -ne 0 ]; then
  ok "陰性対照: 未登録キーの混入を拒否した"
else
  ng "陰性対照: 未登録キーの混入が素通りした"
fi

# --- repetitionsの改ざん ------------------------------------------------------
sed 's/^repetitions\t2$/repetitions\t1/' "$CONFIG" > "$WORK/mutant_rep.tsv"
python3 "$CHECK" --config "$WORK/mutant_rep.tsv" >/dev/null 2>"$WORK/mr.err"
if [ $? -ne 0 ]; then
  ok "陰性対照: repetitionsの改ざんを拒否した"
else
  ng "陰性対照: repetitionsの改ざんが素通りした"
fi

echo
if [ "$rc" -eq 0 ]; then
  echo "全項目 OK"
else
  echo "NG あり"
fi
exit "$rc"
