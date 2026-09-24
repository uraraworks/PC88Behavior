#!/usr/bin/env bash
# tools/check_m6fc_protect_preregistration.py の自己検査。
#
# 検査項目:
#   1. 本物の凍結表 tools/m6fc_protect_frozen.tsv に対してrc=0。
#   2. 陰性対照: 凍結表の1行(keystrokes)を改ざんするとrc=1で検出する
#      (m6f-c本編のSW区間との不一致)。
#   3. 陰性対照: targetの座標を割り当て表セクタへ変えるとrc=1で検出する。
#   4. 陰性対照: judgment行を1つ落とすとrc=1で検出する。
#   5. 陰性対照: 事前登録ノートの必須文言を欠いた版を渡すとrc=1で検出する。
#
# 使い方: tools/check_m6fc_protect_preregistration_selftest.sh
set -uo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CHECK="$REPO/tools/check_m6fc_protect_preregistration.py"
CONFIG="$REPO/tools/m6fc_protect_frozen.tsv"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
rc=0
ok() { printf 'OK: %s\n' "$1"; }
ng() { printf 'NG: %s\n' "$1"; rc=1; }

if python3 "$CHECK" --config "$CONFIG" >"$WORK/pos.out" 2>&1; then
  ok "本物の凍結表でrc=0"
else
  ng "本物の凍結表でrc=0にならなかった: $(cat "$WORK/pos.out")"
fi

# --- 陰性対照: keystrokesを改ざん -------------------------------------------
sed 's/^keystrokes\t.*/keystrokes\tbogus/' "$CONFIG" > "$WORK/bad_keystrokes.tsv"
if python3 "$CHECK" --config "$WORK/bad_keystrokes.tsv" >"$WORK/bk.out" 2>&1; then
  ng "keystrokes改ざんを検出できなかった"
else
  ok "陰性対照: keystrokes改ざんをrc!=0で検出した"
fi

# --- 陰性対照: targetを割り当て表セクタへ ------------------------------------
sed 's/^target\tP13:.*/target\tP13:18,1,14/' "$CONFIG" > "$WORK/bad_target.tsv"
if python3 "$CHECK" --config "$WORK/bad_target.tsv" >"$WORK/bt.out" 2>&1; then
  ng "target改ざん(割り当て表セクタ)を検出できなかった"
else
  ok "陰性対照: target改ざん(割り当て表セクタ)をrc!=0で検出した"
fi

# --- 陰性対照: judgment行を1行落とす -----------------------------------------
grep -v '^judgment\tprotect_sector_not_found$' "$CONFIG" > "$WORK/bad_judgment.tsv"
if python3 "$CHECK" --config "$WORK/bad_judgment.tsv" >"$WORK/bj.out" 2>&1; then
  ng "judgment欠落を検出できなかった"
else
  ok "陰性対照: judgment欠落をrc!=0で検出した"
fi

# --- 陰性対照: 事前登録ノートの必須文言欠落 -----------------------------------
printf '# 空のノート\n' > "$WORK/empty_prereg.md"
if python3 "$CHECK" --config "$CONFIG" --prereg "$WORK/empty_prereg.md" >"$WORK/ep.out" 2>&1; then
  ng "事前登録本文欠落を検出できなかった"
else
  ok "陰性対照: 事前登録本文欠落をrc!=0で検出した"
fi

echo
if [ "$rc" -eq 0 ]; then
  echo "全項目 OK"
else
  echo "NG あり"
fi
exit "$rc"
