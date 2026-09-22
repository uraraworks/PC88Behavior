#!/usr/bin/env bash
# m6i-b G3/G9照合器の陽性対照・陰性対照と、測定前停止のend-to-end検査。
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CHECK="$REPO/tools/check_m6ib_preregistration.py"
CONFIG="$REPO/tools/m6ib_frozen.tsv"
PREREG="$REPO/docs/notes/m6i-b-first-request-timing-preregistration.md"
ADDENDUM="$REPO/docs/notes/m6i-a-addendum1-frozen-values.md"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

python3 "$CHECK" >"$WORK/positive.out" 2>"$WORK/positive.err" || {
  echo "NG: 正常な凍結値を拒否した" >&2
  exit 1
}

expect_fail() {
  local label="$1"
  shift
  if "$@" >"$WORK/${label}.out" 2>"$WORK/${label}.err"; then
    echo "NG: ${label}を通した" >&2
    exit 1
  fi
  grep -q 'gate_failed' "$WORK/${label}.err" || {
    echo "NG: ${label}がgate_failedを出さなかった" >&2
    exit 1
  }
}

awk -F '\t' 'BEGIN {OFS="\t"} $1=="timeout_limit" {$2="65534"} {print}' \
  "$CONFIG" >"$WORK/value.tsv"
expect_fail frozen_value python3 "$CHECK" --config "$WORK/value.tsv"

awk -F '\t' '$1!="arm" || $2!="B5"' "$CONFIG" >"$WORK/arm_removed.tsv"
expect_fail arm_removed python3 "$CHECK" --config "$WORK/arm_removed.tsv"

cp "$CONFIG" "$WORK/arm_added.tsv"
printf 'arm\tB7\n' >>"$WORK/arm_added.tsv"
expect_fail arm_added python3 "$CHECK" --config "$WORK/arm_added.tsv"

awk -F '\t' 'BEGIN {OFS="\t"} $1=="judgment" && $2=="abc_sufficient" \
  {$2="abc_changed"} {print}' "$CONFIG" >"$WORK/judgment.tsv"
expect_fail judgment_changed python3 "$CHECK" --config "$WORK/judgment.tsv"

sed 's/| `timeout_limit` | 65535 |/| `timeout_limit` | 65534 |/' \
  "$ADDENDUM" >"$WORK/addendum.md"
expect_fail m6ia_addendum python3 "$CHECK" --m6ia-addendum "$WORK/addendum.md"

# 壊れた設定を本物の測定入口へ渡す。偽frontendが触る印が無いことで、
# エミュレータexecより前に照合器が止めたことを確認する。
cat >"$WORK/fake_frontend" <<'SH'
#!/usr/bin/env bash
: >"$M6IB_FRONTEND_SENTINEL"
exit 99
SH
chmod +x "$WORK/fake_frontend"
set +e
M6IB_FROZEN_CONFIG="$WORK/value.tsv" \
M6IB_FRONTEND="$WORK/fake_frontend" \
M6IB_FRONTEND_SENTINEL="$WORK/frontend_started" \
  "$REPO/tools/measure_m6ib_first_request.sh" --arm B0 \
  --result "$WORK/result.json" >"$WORK/measure.out" 2>"$WORK/measure.err"
measure_rc=$?
set -e
if [ "$measure_rc" -eq 0 ] || [ -e "$WORK/frontend_started" ] \
   || ! grep -q 'gate_failed' "$WORK/measure.out" \
   || ! grep -q 'gate_failed' "$WORK/measure.err"; then
  echo "NG: 測定経路をエミュレータ起動前にgate_failedで止められない" >&2
  exit 1
fi

echo "check_m6ib_preregistration_selftest: G3/G9陰性対照・起動前停止 OK"
