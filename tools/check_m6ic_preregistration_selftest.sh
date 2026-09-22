#!/usr/bin/env bash
# m6i-c G3/G9照合器の陽性対照、陰性対照、測定入口の起動前停止。
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
CHECK="$REPO/tools/check_m6ic_preregistration.py"
CONFIG="$REPO/tools/m6ic_frozen.tsv"

python3 "$CHECK" >"$WORK/positive.out" 2>"$WORK/positive.err" || exit 1

expect_fail() {
  local label="$1"
  shift
  if "$@" >"$WORK/$label.out" 2>"$WORK/$label.err"; then
    echo "NG: $label を通した" >&2
    exit 1
  fi
  grep -q gate_failed "$WORK/$label.err" || exit 1
}

awk -F '\t' 'BEGIN {OFS="\t"} $1=="timeout_limit" {$2="65534"} {print}' \
  "$CONFIG" >"$WORK/value.tsv"
expect_fail frozen_value python3 "$CHECK" --config "$WORK/value.tsv"

awk -F '\t' '$1!="arm" || $2!="C2"' "$CONFIG" >"$WORK/arm.tsv"
expect_fail arm_name python3 "$CHECK" --config "$WORK/arm.tsv"

awk -F '\t' 'BEGIN {OFS="\t"} $1=="judgment" && $2=="c2_success" \
  {$2="c2_changed"} {print}' "$CONFIG" >"$WORK/judgment.tsv"
expect_fail judgment_name python3 "$CHECK" --config "$WORK/judgment.tsv"

sed 's/| `gate_run_min_length` | 32 |/| `gate_run_min_length` | 33 |/' \
  "$REPO/docs/notes/m6i-c-addendum1-gate-observation.md" >"$WORK/addendum.md"
expect_fail gate_min python3 "$CHECK" --addendum "$WORK/addendum.md"

sed 's/d3becfe5051f7002d268824a2da2824f543442e71ae3226e4d22139e0adce05c/03becfe5051f7002d268824a2da2824f543442e71ae3226e4d22139e0adce05c0/' \
  "$REPO/docs/notes/m6i-a-main-sub-link-preregistration.md" >"$WORK/m6ia.md"
expect_fail media_sha python3 "$CHECK" --m6ia-prereg "$WORK/m6ia.md"

cat >"$WORK/fake_frontend" <<'SH'
#!/usr/bin/env bash
: >"$M6IC_FRONTEND_SENTINEL"
exit 99
SH
chmod +x "$WORK/fake_frontend"
set +e
M6IC_FROZEN_CONFIG="$WORK/value.tsv" \
M6IC_FRONTEND="$WORK/fake_frontend" M6IC_FRONTEND_SENTINEL="$WORK/started" \
  "$REPO/tools/measure_m6ic.sh" --arm C0 --result "$WORK/result.json" \
  >"$WORK/measure.out" 2>"$WORK/measure.err"
measure_rc=$?
set -e
if [ "$measure_rc" -eq 0 ] || [ -e "$WORK/started" ] \
   || ! grep -q preregistration_mismatch "$WORK/measure.out"; then
  echo "NG: 測定入口をfrontend前に停止できない" >&2
  exit 1
fi

echo "check_m6ic_preregistration_selftest: 項目数=7、陰性対照6件・起動前停止 OK"
