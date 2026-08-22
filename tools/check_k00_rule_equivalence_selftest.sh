#!/usr/bin/env bash
# m7bxの5規則等価性検査を、無傷と故障注入の両方で検算する。
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CHECK="$REPO/tools/check_k00_rule_equivalence.py"
TABLE="$REPO/measurements/m7bx-k00-equivalence.tsv"
WORK_K00_EQ="$(mktemp -d)"
trap 'rm -rf "$WORK_K00_EQ"' EXIT
overall_rc=0

healthy_out="$WORK_K00_EQ/healthy.txt"
if python3 "$CHECK" "$TABLE" >"$healthy_out" \
   && grep -q 'K00記号標本: 20件' "$healthy_out" \
   && grep -q '5規則間の不一致標本: 0件' "$healthy_out" \
   && grep -q '判定: 等価' "$healthy_out"; then
  echo '  OK   無傷: 20標本で5規則が観測列と一致し、規則間不一致0件'
else
  echo '  NG   無傷の20標本を等価と判定できない'
  overall_rc=1
fi

# 陽性対照: B標本1件の直前runだけK05からK04へ変える。直前run規則だけが
# Aを返し、他4規則のBと食い違うため「非等価」にならなければならない。
broken="$WORK_K00_EQ/broken.tsv"
awk 'BEGIN{FS=OFS="\t"} NR==3{$4="K04"} {print}' "$TABLE" >"$broken"
broken_out="$WORK_K00_EQ/broken.txt"
python3 "$CHECK" "$broken" >"$broken_out" 2>&1
broken_rc=$?
if [[ "$broken_rc" -eq 1 ]] \
   && grep -q '直前run: 観測列との不一致1件' "$broken_out" \
   && grep -q '5規則間の不一致標本: 1件' "$broken_out" \
   && grep -q '判定: 非等価' "$broken_out"; then
  echo '  OK   故障注入: 1標本の候補分離を非等価として検出（陽性対照）'
else
  echo '  NG   故障注入が非等価の症状で落ちない'
  overall_rc=1
fi

if [[ "$overall_rc" -eq 0 ]]; then
  echo 'check_k00_rule_equivalence selftest: OK（無傷合格・注入不合格）'
else
  echo 'check_k00_rule_equivalence selftest: 失敗あり'
fi
exit "$overall_rc"
