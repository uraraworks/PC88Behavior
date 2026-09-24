#!/usr/bin/env bash
# tools/check_m6fc_preregistration.py の自己検査。
#
# 検査項目:
#   1. 現行の tools/m6fc_frozen.tsv でrc=0。
#   2. 陰性対照: 打鍵1文字を書き換えるとrc!=0で拒否される。
#   3. 陰性対照: framesを1つ書き換えるとrc!=0。
#   4. 陰性対照: 判定名を1つ削るとrc!=0。
#   5. 陰性対照: 腕を1つ削るとrc!=0。
#
# 使い方: tools/check_m6fc_preregistration_selftest.sh
set -uo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CHECK="$REPO/tools/check_m6fc_preregistration.py"
CONFIG="$REPO/tools/m6fc_frozen.tsv"
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

# --- 打鍵1文字の改ざん ------------------------------------------------------
sed '/^segment\tA1:700:/s/"ok"/"OK"/' "$CONFIG" > "$WORK/mutant_key.tsv"
python3 "$CHECK" --config "$WORK/mutant_key.tsv" >/dev/null 2>"$WORK/mk.err"
rc_mk=$?
if [ "$rc_mk" -ne 0 ]; then
  ok "陰性対照: A1の打鍵1文字改ざんを拒否した"
else
  ng "陰性対照: A1の打鍵1文字改ざんが素通りした"
fi

# --- framesの改ざん ---------------------------------------------------------
sed 's/^frames\tA3:30000$/frames\tA3:30001/' "$CONFIG" > "$WORK/mutant_frames.tsv"
python3 "$CHECK" --config "$WORK/mutant_frames.tsv" >/dev/null 2>"$WORK/mf.err"
rc_mf=$?
if [ "$rc_mf" -ne 0 ]; then
  ok "陰性対照: A3のframes改ざんを拒否した"
else
  ng "陰性対照: A3のframes改ざんが素通りした"
fi

# --- 判定名の欠落 ------------------------------------------------------------
grep -v '^judgment\tlink_other$' "$CONFIG" > "$WORK/mutant_judgment.tsv"
python3 "$CHECK" --config "$WORK/mutant_judgment.tsv" >/dev/null 2>"$WORK/mj.err"
rc_mj=$?
if [ "$rc_mj" -ne 0 ]; then
  ok "陰性対照: 判定名link_otherの欠落を拒否した"
else
  ng "陰性対照: 判定名の欠落が素通りした"
fi

# --- 腕の欠落 ----------------------------------------------------------------
grep -v '^arm\tSW-7F$' "$CONFIG" > "$WORK/mutant_arm.tsv"
python3 "$CHECK" --config "$WORK/mutant_arm.tsv" >/dev/null 2>"$WORK/ma.err"
rc_ma=$?
if [ "$rc_ma" -ne 0 ]; then
  ok "陰性対照: 腕SW-7Fの欠落を拒否した"
else
  ng "陰性対照: 腕の欠落が素通りした"
fi

# --- 512打鍵超過 -------------------------------------------------------------
python3 - "$CONFIG" "$WORK/mutant_long.tsv" <<'PY'
import sys
src, dst = sys.argv[1], sys.argv[2]
lines = open(src, encoding="utf-8").read().splitlines()
out = []
for line in lines:
    if line.startswith("segment\tA1:700:"):
        key, rest = line.split("\t", 1)
        arm_frame, text = rest.split(":", 2)[0] + ":" + rest.split(":", 2)[1], rest.split(":", 2)[2]
        text = text + ("x" * 600)
        out.append(f"{key}\t{arm_frame}:{text}")
    else:
        out.append(line)
open(dst, "w", encoding="utf-8").write("\n".join(out) + "\n")
PY
python3 "$CHECK" --config "$WORK/mutant_long.tsv" >/dev/null 2>"$WORK/ml.err"
rc_ml=$?
if [ "$rc_ml" -ne 0 ]; then
  ok "陰性対照: 512打鍵超過を拒否した"
else
  ng "陰性対照: 512打鍵超過が素通りした"
fi

echo
if [ "$rc" -eq 0 ]; then
  echo "全項目 OK"
else
  echo "NG あり"
fi
exit "$rc"
