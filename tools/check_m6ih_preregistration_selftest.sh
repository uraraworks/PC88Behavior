#!/usr/bin/env bash
# m6i-h G3/G9照合器の陽性対照、凍結値の陰性対照、frontend前停止。
set -uo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK="$(mktemp -d)"; trap 'rm -rf "$WORK"' EXIT
CHECK="$REPO/tools/check_m6ih_preregistration.py"; CONFIG="$REPO/tools/m6ih_frozen.tsv"
python3 "$CHECK" >"$WORK/positive.out" 2>"$WORK/positive.err" || exit 1
expect_fail() {
  local name="$1"; shift
  if "$@" >"$WORK/$name.out" 2>"$WORK/$name.err"; then echo "NG: $name" >&2; exit 1; fi
  grep -q gate_failed "$WORK/$name.err" || exit 1
}
mutate() {
  local old="$1" new="$2" out="$3"
  sed "s|$old|$new|" "$CONFIG" >"$out"
}
mutate $'arm_frames\t600' $'arm_frames\t599' "$WORK/value.tsv"
expect_fail frozen_value python3 "$CHECK" --config "$WORK/value.tsv"
grep -v $'arm\tH-A' "$CONFIG" >"$WORK/arm.tsv"
expect_fail arm_name python3 "$CHECK" --config "$WORK/arm.tsv"
mutate $'issue_frame\tH-N:6' $'issue_frame\tH-N:7' "$WORK/frame.tsv"
expect_fail issue_frame python3 "$CHECK" --config "$WORK/frame.tsv"
awk -F '\t' 'BEGIN{OFS="\t"} $1=="expected_state" && $2=="H-A:*,1,0"{$2="H-A:1,1,0"}{print}' \
  "$CONFIG" >"$WORK/state.tsv"
expect_fail nonfrozen_a python3 "$CHECK" --config "$WORK/state.tsv"
mutate $'retry_marker_address\t0xE00D' $'retry_marker_address\t0xE00E' "$WORK/retry.tsv"
expect_fail retry_marker python3 "$CHECK" --config "$WORK/retry.tsv"
mutate $'result_condition\tH-B:retry' $'result_condition\tH-B:standard' "$WORK/result.tsv"
expect_fail result_condition python3 "$CHECK" --config "$WORK/result.tsv"
mutate $'judgment\th_a_success' $'judgment\th_a_changed' "$WORK/judgment.tsv"
expect_fail judgment python3 "$CHECK" --config "$WORK/judgment.tsv"

cat >"$WORK/fake_frontend" <<'SH'
#!/usr/bin/env bash
: >"$M6IH_FRONTEND_SENTINEL"
exit 99
SH
chmod +x "$WORK/fake_frontend"
set +e
M6IH_FROZEN_CONFIG="$WORK/value.tsv" M6IH_FRONTEND="$WORK/fake_frontend" \
M6IH_FRONTEND_SENTINEL="$WORK/started" "$REPO/tools/measure_m6ih.sh" \
  --arm H-N --result "$WORK/result.json" >"$WORK/measure.out" 2>"$WORK/measure.err"
rc=$?
set -e
if [ "$rc" -eq 0 ] || [ -e "$WORK/started" ] || ! grep -q preregistration_mismatch "$WORK/measure.out"; then
  echo "NG: frontend前停止" >&2; exit 1
fi
echo "check_m6ih_preregistration_selftest: 項目数=9、陰性対照8件（凍結値7・起動前停止1）OK"
